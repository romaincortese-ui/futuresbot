"""Replay acceptance scorer: grade a replay against LIVE over a window, layer by layer, PASS/FAIL against fixed bars.

WHY. The 2026-09-23 impartial assessment graded the replay D and could only do so with eight one-off lanes: exits on
the same trade B- (corr 0.91-0.92, 81% within 0.1R, flaw = last-price wicks), WILDCARD entries F (2.1-2.3x live fills,
recall 0.55, precision 0.26: live scans the FORMING bar, every study uses completed bars), TREND entries C, sizing F
(fixed stake), absolute dollars F (live - replay -$258/mo [-746, +183]). Its standing rule: no configuration change
other than the dial until a scorer has graded the replay. This module is that scorer, runnable every week on data
pulled read-only, so a replay repair is accepted on measurement rather than on another lane's say-so.

THE THREE LAYERS
  ENTRIES  per sleeve: does the replay take the trades live took? fill-count ratio, recall (share of live fills the
           replay also took, same symbol+side within one 15m bar) and precision (share of replay fills live also took).
  EXITS    pooled: on the SAME trades, does the replay's exit give live's R? correlation, share within 0.10R, and bias
           (mean live - replay). Pairs come from the replay's matched fills, or from a separate exits file (the
           replay's exit engine run on live's own entries - the cleaner test, because it isolates exits from entries).
  SIZING / DOLLARS  pooled: (a) the sizing engine (futuresbot.replay.sizing) fed LIVE's own fills must give each fill
           live's 1R and end on live's cash; (b) the replay's fills priced through that same engine - compounding on
           free margin, from live's cash at the window start, with live's flows - must land near live's dollars.
           Every replay is re-priced by the engine, whatever stake it booked itself: compounding by default.

Thresholds live in THRESHOLDS below, each with the measurement that justifies it. The lane that set them (wc/EXP/R1)
found no thresholds in the assessment's remediation design (wc/ASSESS/G defines the measurements, not the bars), so
the bars are set here from the measured values that separate today's replay from the repaired variants.
"""
from __future__ import annotations

import json
import math
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from futuresbot.replay.sizing import (
    MONTH_DAYS,
    CapitalFlow,
    ContractSpec,
    SizingConfig,
    Trade,
    _as_flows,
    live_config,
    simulate,
)

GRADED_SLEEVES = ("WILDCARD", "TREND")

# Live sl_margin_pct median ("0.12 balance_fraction x 15.6% median sl_margin", runtime._entry_margin). Only used to
# lock margin for a replay fill that carries no stop at all; the scorer notes how many fills needed it.
DEFAULT_SL_MARGIN_PCT = 15.6

THRESHOLDS: dict[str, dict[str, float]] = {
    "entries": {
        # Below 20 live fills a 0.75 share has a 95% interval of about +/-0.19 - wider than the distance between a
        # passing and a failing replay - so the layer reports INSUFFICIENT instead of a grade. WILDCARD makes ~12
        # fills a week, which is why the default window is 28 days, not 7.
        "min_live": 20,
        # Same symbol+side, entry within one 15m bar. Live fills land a median 16 s after their scan (p90 22 s); a
        # replay entry an hour away is a different trade in price terms, so lane B's 3600 s is too loose (on the
        # scan-journal replay 900 s and 3600 s matched identically, so nothing honest is lost).
        "match_tol_s": 900,
        # Fill count within 25% either way (symmetric in log: 1/1.25 = 0.80). Replay dollars scale with fill count;
        # today's completed-bar replay books 2.1-2.3x live, and the record's x0.45 discount for that is exactly the
        # calibration this bar retires. The scan-journal replay measured 0.98x.
        "ratio_lo": 0.80,
        "ratio_hi": 1.25,
        # 25-28% of live WILDCARD fills exist only on the FORMING 15m bar, so a completed-bar replay that is right
        # about everything else tops out near 0.72-0.75 recall: 0.75 is the smallest bar that requires reproducing
        # that population. Scan-journal replay + recorded refusals: 0.78 / 0.80. Today's replay: 0.55 / 0.26.
        "recall_min": 0.75,
        "precision_min": 0.75,
    },
    "exits": {
        "min_pairs": 20,
        # Same-trade R correlation. The studies' 15m wick engine measured 0.91-0.92 (graded B-): correlation does not
        # separate wick from fair-price exits; it is the guard against a broken engine.
        "corr_min": 0.90,
        # Share of matched fills within 0.10R of live. Last-price (wick) engines: 0.81-0.87. Fair-price split engines
        # (stops and software exits on FAIR, TP on last, as live): 0.93-0.94 on the same 70 fills. 0.90 fails the
        # wick flaw and passes the fix.
        "within_r": 0.10,
        "within_share_min": 0.90,
        # |mean(live - replay)| R per fill. 0.03R x ~60 live fills/mo x 1R ~$17.7 (1.87% of $949) ~ $32/mo: the size of
        # the record's rule that a replay improvement needs $25-35/mo to mean +$10 live. Measured: fair split -0.026R,
        # 15m wick -0.033R. Tighter is not verifiable in a month (the fair engine's se is ~0.007R at n=70).
        "bias_max_abs": 0.03,
    },
    "sizing": {
        "min_fills": 20,
        # The engine fed LIVE fills must give live's 1R within 5% on 90% of fills. The full chain measured 148/151
        # (98%) on 08-13..09-23; without integer contracts 116/151 (77%), without the recorded streak multiplier
        # 104/151 (69%), sizing off cash instead of available 68/151 (45%). 0.90 fails any chain missing a live part.
        "risk_rel_tol": 0.05,
        "risk_within_share_min": 0.90,
        # Engine cash minus live cash at the window end, per month. Under the owner's +$10/mo ship bar a sizing error
        # cannot flip a ship decision. Full chain: -$1.66 over 41.6 d (-$1.2/mo); without the streak multiplier
        # -$14.00 (-$10.2/mo, fails).
        "cash_gap_max_per_month": 10.0,
    },
    "dollars": {
        # |live - replay| compounded trading dollars per month over the window. This is not sampling noise: a replay
        # that took live's trades with live's exits prices to live's dollars through this engine (the sizing check
        # above), so every dollar here is a mismatch. $35/mo is the top of the record's $25-35/mo replay-to-live
        # discount: a replay inside it no longer needs the discount. Today's replay measured -$258/mo.
        "gap_max_per_month": 35.0,
    },
}


# ---- the common fill schema ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Fill:
    """One fill, live or replay. usd/risk_usdt are what the SOURCE booked (live: realised $ and the $ value of 1R
    taken). The scorer never uses a replay's own usd: it re-prices every replay through the sizing engine."""
    sym: str
    side: str
    sleeve: str
    t_open: float
    t_close: float | None
    r: float | None
    usd: float | None = None
    risk_usdt: float | None = None
    stop_frac: float | None = None
    leverage: float | None = None
    entry_price: float | None = None
    contract_size: float = 0.0
    min_vol: int = 1
    regime_mult: float = 1.0
    streak_mult: float | None = None
    available_at_entry: float | None = None


def _num(x: Any) -> float | None:
    try:
        if x is None or x == "":
            return None
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _ts(x: Any) -> float | None:
    if x is None:
        return None
    v = _num(x)
    if v is not None:
        return v / 1000.0 if v > 1e11 else v          # epoch ms -> s
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return None


def live_fills_from_feature_store(rows: Iterable[Mapping[str, Any]],
                                  trade_history: Iterable[Mapping[str, Any]] = (),
                                  contracts: Mapping[str, Mapping[str, Any]] | None = None,
                                  ) -> list[Fill]:
    """Live fills from /data/futures_feature_store.jsonl rows (one per close), enriched from the runtime state's
    trade_history (entry price, contracts, margin -> contract size; exact on 198/198 rows checked against MEXC contract
    details) and optionally from a contract-details map {symbol: {contractSize, minVol}}. Every kind is returned
    (PMT/SNIPER/... too): graded sleeves are selected later, the rest become cash flows for the dollar layer.

    Live R = pnl_usdt / risk_usdt (the bot's own 1R), falling back to r_multiple when risk_usdt was not recorded."""
    th = []
    for x in trade_history or ():
        xt = _ts(x.get("exit_time"))
        if xt is not None:
            th.append((str(x.get("symbol")), str(x.get("side")), xt, x))
    out: list[Fill] = []
    for r in rows:
        ts = _num(r.get("ts"))
        if ts is None or not r.get("symbol"):
            continue
        hold_min = _num(r.get("hold_min"))
        t_open = ts - hold_min * 60.0 if hold_min is not None else ts
        sym, side = str(r["symbol"]), str(r.get("side") or "")
        kind = str(r.get("kind") or r.get("sleeve") or "UNKNOWN").upper()
        pnl = _num(r.get("pnl_usdt"))
        risk = _num(r.get("risk_usdt"))
        rm = _num(r.get("r_multiple"))
        rr = pnl / risk if (pnl is not None and risk) else rm
        lev = _num(r.get("leverage"))
        slm = _num(r.get("sl_margin_pct"))
        stop = slm / (100.0 * lev) if (slm and lev) else None
        entry = _num(r.get("entry_price"))
        cs = 0.0
        mv = 1
        best = None
        for s_, sd_, xt, x in th:
            if s_ == sym and sd_ == side and abs(xt - ts) <= 180 and (best is None or abs(xt - ts) < best[0]):
                best = (abs(xt - ts), x)
        if best is not None:
            x = best[1]
            entry = entry or _num(x.get("entry_price"))
            et = _ts(x.get("entry_time"))
            if et is not None:
                t_open = et
            n, m, lv = _num(x.get("contracts")), _num(x.get("margin_usdt")), _num(x.get("leverage"))
            if n and m and lv and entry:
                cs = m * lv / (n * entry)
        if contracts and sym in contracts:
            c = contracts[sym]
            cs = _num(c.get("contractSize")) or cs
            mv = int(_num(c.get("minVol")) or 1)
        out.append(Fill(sym=sym, side=side, sleeve=kind, t_open=t_open, t_close=ts, r=rr, usd=pnl, risk_usdt=risk,
                        stop_frac=stop, leverage=lev, entry_price=entry, contract_size=cs, min_vol=mv,
                        regime_mult=_num(r.get("regime_size_mult")) or 1.0,
                        streak_mult=_num(r.get("streak_multiplier")),
                        available_at_entry=_num(r.get("equity_at_entry"))))
    out.sort(key=lambda f: f.t_open)
    return out


def replay_fills_from_rows(rows: Iterable[Mapping[str, Any]], default_sleeve: str = "") -> list[Fill]:
    """Replay fills from a JSON list. Accepts the study conventions already in use: sym|symbol, side, sleeve|kind,
    ts|t_open|entry_ts, exit_ts|t_close, r|net|R, mult|regime_mult, sl_frac|stop_frac, lev|leverage, entry|entry_price,
    and optional risk_usdt / usd (the replay's own stake, reported but never used for dollars)."""
    out = []
    for x in rows:
        t0 = _ts(_first(x, "t_open", "ts", "entry_ts"))
        if t0 is None:
            continue
        stop = _num(_first(x, "stop_frac", "sl_frac"))
        lev = _num(_first(x, "leverage", "lev"))
        slm = _num(x.get("sl_margin_pct"))
        if stop is None and slm and lev:
            stop = slm / (100.0 * lev)
        out.append(Fill(sym=str(_first(x, "sym", "symbol")), side=str(x.get("side") or ""),
                        sleeve=str(_first(x, "sleeve", "kind") or default_sleeve).upper(),
                        t_open=t0, t_close=_ts(_first(x, "t_close", "exit_ts")),
                        r=_num(_first(x, "r", "net", "R")), usd=_num(x.get("usd")), risk_usdt=_num(x.get("risk_usdt")),
                        stop_frac=stop, leverage=lev, entry_price=_num(_first(x, "entry_price", "entry")),
                        contract_size=_num(x.get("contract_size")) or 0.0, min_vol=int(_num(x.get("min_vol")) or 1),
                        regime_mult=_num(_first(x, "regime_mult", "mult")) or 1.0,
                        streak_mult=_num(x.get("streak_mult"))))
    out.sort(key=lambda f: f.t_open)
    return out


def load_jsonl(path: str) -> list[dict[str, Any]]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue            # a torn last line from a live append is not a reason to fail the week
    return rows


# ---- matching and small statistics --------------------------------------------------------------------------------
def match_fills(live: Sequence[Fill], replay: Sequence[Fill], tol_s: float) -> tuple[list[tuple[Fill, Fill]],
                                                                                        list[Fill], list[Fill]]:
    """Greedy, live fills in entry order: each takes the nearest-in-time unused replay fill with the same symbol, side
    and sleeve within tol_s. Returns (pairs, live_only, replay_only). Same rule as lanes B and G."""
    used: set[int] = set()
    pairs: list[tuple[Fill, Fill]] = []
    matched_live: set[int] = set()
    for li, lf in sorted(enumerate(live), key=lambda z: z[1].t_open):
        best = None
        for j, rf in enumerate(replay):
            if j in used or rf.sym != lf.sym or rf.side != lf.side or rf.sleeve != lf.sleeve:
                continue
            d = abs(rf.t_open - lf.t_open)
            if d <= tol_s and (best is None or d < best[0]):
                best = (d, j)
        if best is not None:
            used.add(best[1])
            matched_live.add(li)
            pairs.append((lf, replay[best[1]]))
    return (pairs, [f for i, f in enumerate(live) if i not in matched_live],
            [f for j, f in enumerate(replay) if j not in used])


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def _corr(a: Sequence[float], b: Sequence[float]) -> float | None:
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def _pct(xs: Sequence[float], q: float) -> float:
    s = sorted(xs)
    if not s:
        return float("nan")
    k = (len(s) - 1) * q
    lo = math.floor(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


# ---- results --------------------------------------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    value: float | None
    bar: str
    ok: bool | None           # None = could not be computed


@dataclass
class LayerResult:
    layer: str
    scope: str
    n: int
    verdict: str              # PASS | FAIL | INSUFFICIENT
    checks: list[Check] = field(default_factory=list)
    info: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _verdict(n: int, n_min: float, checks: Sequence[Check]) -> str:
    # A failed bar is a FAIL even when another check could not be computed (an empty replay fails the fill ratio);
    # an uncomputable check with nothing failed is not a PASS.
    if n < n_min:
        return "INSUFFICIENT"
    if any(c.ok is False for c in checks):
        return "FAIL"
    return "INSUFFICIENT" if any(c.ok is None for c in checks) else "PASS"


def score_entries(live: Sequence[Fill], replay: Sequence[Fill], sleeve: str,
                  th: Mapping[str, float] | None = None) -> LayerResult:
    th = th or THRESHOLDS["entries"]
    lv = [f for f in live if f.sleeve == sleeve]
    rp = [f for f in replay if f.sleeve == sleeve]
    pairs, lo, ro = match_fills(lv, rp, th["match_tol_s"])
    k = len(pairs)
    ratio = len(rp) / len(lv) if lv else None
    recall = k / len(lv) if lv else None
    precision = k / len(rp) if rp else None
    checks = [
        Check("fill ratio replay/live", ratio, f"{th['ratio_lo']:.2f}-{th['ratio_hi']:.2f}",
              None if ratio is None else th["ratio_lo"] <= ratio <= th["ratio_hi"]),
        Check("recall", recall, f">= {th['recall_min']:.2f}", None if recall is None else recall >= th["recall_min"]),
        Check("precision", precision, f">= {th['precision_min']:.2f}",
              None if precision is None else precision >= th["precision_min"]),
    ]
    return LayerResult("ENTRIES", sleeve, len(lv), _verdict(len(lv), th["min_live"], checks), checks,
                       info={"live": len(lv), "replay": len(rp), "matched": k,
                             "recall_ci95": _wilson(k, len(lv)), "precision_ci95": _wilson(k, len(rp)),
                             "live_R": sum(f.r for f in lv if f.r is not None),
                             "replay_R": sum(f.r for f in rp if f.r is not None),
                             "live_only_R": sum(f.r for f in lo if f.r is not None),
                             "replay_only_R": sum(f.r for f in ro if f.r is not None)})


def score_exits(live: Sequence[Fill], exits: Sequence[Fill], th: Mapping[str, float] | None = None,
                tol_s: float | None = None, n_boot: int = 2000, seed: int = 11) -> LayerResult:
    th = th or THRESHOLDS["exits"]
    tol = THRESHOLDS["entries"]["match_tol_s"] if tol_s is None else tol_s
    pairs, _, _ = match_fills(live, exits, tol)
    pr = [(a.r, b.r) for a, b in pairs if a.r is not None and b.r is not None]
    n = len(pr)
    d = [a - b for a, b in pr]
    corr = _corr([a for a, _ in pr], [b for _, b in pr])
    within = sum(1 for x in d if abs(x) <= th["within_r"] + 1e-12) / n if n else None
    bias = sum(d) / n if n else None
    ci = (None, None)
    if n >= 2 and n_boot > 0:
        rng = random.Random(seed)
        bs = [sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot)]
        ci = (_pct(bs, 0.025), _pct(bs, 0.975))
    checks = [
        Check("R correlation", corr, f">= {th['corr_min']:.2f}", None if corr is None else corr >= th["corr_min"]),
        Check(f"share within {th['within_r']:.2f}R", within, f">= {th['within_share_min']:.2f}",
              None if within is None else within >= th["within_share_min"]),
    ]
    by = {}
    for a, b in pairs:
        if a.r is not None and b.r is not None:
            by.setdefault(a.sleeve, []).append(a.r - b.r)
    # THE BIAS IS GRADED PER SLEEVE (release gate D1, 2026-09-23). Pooled, TREND's -0.007R/fill diluted WILDCARD's
    # -0.047R/fill - about $56/mo of replay overstatement, [$31, $86] - into a pass. A sleeve with fewer than
    # min_pairs matched fills is reported, not graded; if no sleeve reaches it the layer cannot claim a bias pass.
    graded = {k: v for k, v in by.items() if len(v) >= th["min_pairs"]}
    for k in sorted(graded):
        b_k = sum(graded[k]) / len(graded[k])
        checks.append(Check(f"bias live-replay R/fill [{k}]", b_k, f"|x| <= {th['bias_max_abs']:.3f}",
                            abs(b_k) <= th["bias_max_abs"]))
    if not graded:
        checks.append(Check("bias live-replay R/fill [per sleeve]", bias,
                            f"|x| <= {th['bias_max_abs']:.3f} on a sleeve with >= {th['min_pairs']:.0f} pairs",
                            None))
    return LayerResult("EXITS", "+".join(sorted({a.sleeve for a, _ in pairs})) or "-", n,
                       _verdict(n, th["min_pairs"], checks), checks,
                       info={"bias_pooled": bias, "bias_ci95": ci,
                             "pairs_by_sleeve": {k: len(v) for k, v in by.items()},
                             "bias_by_sleeve": {k: sum(v) / len(v) for k, v in by.items()},
                             "bias_not_graded": sorted(k for k in by if k not in graded)})


def _as_trade(f: Fill, notes: dict[str, int]) -> Trade | None:
    if f.r is None or f.t_close is None:
        notes["no_outcome"] = notes.get("no_outcome", 0) + 1
        return None
    stop, lev = f.stop_frac, f.leverage
    if not stop or not lev:
        notes["default_stop"] = notes.get("default_stop", 0) + 1
        stop, lev = DEFAULT_SL_MARGIN_PCT / 100.0, 1.0
    return Trade(t_open=f.t_open, t_close=max(f.t_close, f.t_open), sleeve=f.sleeve, r=f.r, stop_frac=stop,
                 leverage=lev, entry_price=f.entry_price or 1.0,
                 spec=ContractSpec(f.contract_size if f.entry_price else 0.0, f.min_vol),
                 regime_mult=f.regime_mult, streak_mult=f.streak_mult, symbol=f.sym, side=f.side)


def score_sizing(live: Sequence[Fill], start_cash: float, flows: Sequence[CapitalFlow], days: float,
                 config: SizingConfig | None = None, th: Mapping[str, float] | None = None) -> LayerResult:
    """The engine fed LIVE's own fills (recorded R, regime and streak multipliers, stops, contract specs)."""
    th = th or THRESHOLDS["sizing"]
    cfg = config or live_config()
    notes: dict[str, int] = {}
    pairs = [(f, _as_trade(f, notes)) for f in live]
    pairs = [(f, t) for f, t in pairs if t is not None]
    res = simulate([t for _, t in pairs], start_cash, cfg, flows)
    rel, first_jump = [], None
    for (f, _), fr in zip(pairs, res.fills):
        if fr.taken and f.risk_usdt:
            rel.append(fr.risk_usdt / f.risk_usdt - 1.0)
        if first_jump is None and f.available_at_entry is not None:
            gap = f.available_at_entry - fr.available
            if abs(gap) > max(25.0, 0.10 * abs(f.available_at_entry)):
                first_jump = (f.t_open, gap)
    live_final = start_cash + sum(fl.amount for fl in flows) + sum(f.usd or 0.0 for f, _ in pairs)
    gap = res.final_cash - live_final
    gap_mo = gap * MONTH_DAYS / days if days > 0 else None
    share = sum(1 for x in rel if abs(x) <= th["risk_rel_tol"]) / len(rel) if rel else None
    checks = [
        Check(f"1R within {th['risk_rel_tol'] * 100:.0f}% of live", share, f">= {th['risk_within_share_min']:.2f}",
              None if share is None else share >= th["risk_within_share_min"]),
        Check("cash gap engine-live $/mo", gap_mo, f"|x| <= {th['cash_gap_max_per_month']:.0f}",
              None if gap_mo is None else abs(gap_mo) <= th["cash_gap_max_per_month"]),
    ]
    lr = LayerResult("SIZING", "live fills", len(pairs), _verdict(len(pairs), th["min_fills"], checks), checks,
                     info={"engine_final": res.final_cash, "live_final": live_final, "cash_gap": gap,
                           "skipped_by_engine": [(f.trade.symbol, f.skip_reason) for f in res.skipped],
                           "continuous": sum(1 for f in res.fills if f.continuous), "compared": len(rel)})
    if notes.get("default_stop"):
        lr.notes.append(f"{notes['default_stop']} live fills had no stop recorded; margin locked at "
                        f"{DEFAULT_SL_MARGIN_PCT}% sl_margin")
    if lr.info["continuous"]:
        lr.notes.append(f"{lr.info['continuous']} live fills had no contract spec and were sized continuously "
                        "(pass --runtime-state or --contracts)")
    if first_jump is not None:
        lr.notes.append("live available differs from the engine's by $%+.2f (live - engine) from %s: an unrecorded "
                        "deposit/withdrawal, margin held by a position outside the stream, or a dial change missing "
                        "from sizing.LIVE_DIALS" % (
                            first_jump[1], datetime.fromtimestamp(first_jump[0], timezone.utc).strftime("%m-%d %H:%M")))
    return lr


def score_dollars(live: Sequence[Fill], replay: Sequence[Fill], start_cash: float, flows: Sequence[CapitalFlow],
                  days: float, config: SizingConfig | None = None, th: Mapping[str, float] | None = None,
                  n_boot: int = 4000, seed: int = 11, carried: Sequence[Fill] = ()) -> LayerResult:
    """Replay fills priced through the engine (compounding on free margin from live's cash, live's flows) vs live's
    realised dollars on the graded sleeves. Gap decomposed like lane G: matched pairs, live-only, replay-only.

    `carried` = LIVE fills the replay does not model (a sleeve it does not cover, or entries between the flat start and
    the window) that must still lock margin and move cash in the path; they are priced but not scored. Without them a
    WILDCARD-only replay would size off an account with TREND's margin missing."""
    th = th or THRESHOLDS["dollars"]
    cfg = config or live_config()
    notes: dict[str, int] = {}
    rt = [(f, _as_trade(f, notes)) for f in replay]
    rt = [(f, t) for f, t in rt if t is not None]
    ct = [t for t in (_as_trade(f, {}) for f in carried) if t is not None]
    res = simulate([t for _, t in rt] + ct, start_cash, cfg, flows)
    rep_fills = res.fills[:len(rt)]
    priced = [Fill(**{**f.__dict__, "usd": fr.pnl_usdt, "risk_usdt": fr.risk_usdt}) for (f, _), fr in zip(rt, rep_fills)]
    live_usd = sum(f.usd or 0.0 for f in live)
    rep_usd = sum(fr.pnl_usdt for fr in rep_fills)
    gap = live_usd - rep_usd
    gap_mo = gap * MONTH_DAYS / days if days > 0 else None
    pairs, lo, ro = match_fills(live, priced, THRESHOLDS["entries"]["match_tol_s"])
    dm = [(a.usd or 0.0) - (b.usd or 0.0) for a, b in pairs]
    dl = [a.usd or 0.0 for a in lo]
    dr = [b.usd or 0.0 for b in ro]
    ci = (None, None)
    if n_boot > 0 and days > 0:
        rng = random.Random(seed)
        bs = []
        for _ in range(n_boot):
            s = sum(dm[rng.randrange(len(dm))] for _ in dm) + sum(dl[rng.randrange(len(dl))] for _ in dl) \
                - sum(dr[rng.randrange(len(dr))] for _ in dr)
            bs.append(s * MONTH_DAYS / days)
        ci = (_pct(bs, 0.025), _pct(bs, 0.975))
    declared = [b.risk_usdt / a.risk_usdt for a, b in match_fills(live, replay, THRESHOLDS["entries"]["match_tol_s"])[0]
                if a.risk_usdt and b.risk_usdt]
    # GRADED ON THE INTERVAL (release gate D2, 2026-09-23): PASS only when the whole 95% interval sits inside the bar,
    # FAIL only when it sits entirely outside it, otherwise INSUFFICIENT. The interval runs about +-$180/mo, so a
    # point estimate inside or outside +-$35 is noise, and a grade built on it would break the standing rule to report
    # intervals rather than fragile totals.
    bar = th["gap_max_per_month"]
    lo_ci, hi_ci = ci
    if gap_mo is None or lo_ci is None or hi_ci is None:
        ok = None
    elif -bar <= lo_ci and hi_ci <= bar:
        ok = True
    elif hi_ci < -bar or lo_ci > bar:
        ok = False
    else:
        ok = None
    checks = [Check("gap live-replay $/mo (95% interval)", gap_mo, f"interval within +-{bar:.0f}", ok)]
    scope = "+".join(sorted({f.sleeve for f in live} | {f.sleeve for f in replay})) or "-"
    lr = LayerResult("DOLLARS", scope, len(live),
                     {True: "PASS", False: "FAIL"}.get(checks[0].ok, "INSUFFICIENT"), checks,
                     info={"live_usd": live_usd, "replay_usd_compounded": rep_usd, "gap_usd": gap, "gap_ci95_mo": ci,
                           "matched_part": sum(dm), "live_only_part": sum(dl), "replay_only_part": -sum(dr),
                           "n_pairs": len(dm), "n_live_only": len(dl), "n_replay_only": len(dr),
                           "replay_skipped_by_engine": sum(1 for fr in rep_fills if not fr.taken),
                           "carried_live_fills": len(ct), "path_max_dd": res.max_drawdown,
                           "declared_1R_over_live_median": _pct(declared, 0.5) if declared else None})
    if checks[0].ok is None:
        lr.verdict = "INSUFFICIENT"
    if notes.get("default_stop"):
        lr.notes.append(f"{notes['default_stop']} replay fills carry no stop: margin locked at the live median "
                        f"{DEFAULT_SL_MARGIN_PCT}% sl_margin")
    if notes.get("no_outcome"):
        lr.notes.append(f"{notes['no_outcome']} replay fills have no outcome (r/exit) and were not priced")
    if declared:
        lr.notes.append("the replay declares its own 1R; ignored - re-priced through futuresbot.replay.sizing "
                        f"(declared/live 1R median {lr.info['declared_1R_over_live_median']:.2f} on matched fills)")
    return lr


# ---- window, start cash, report -----------------------------------------------------------------------------------
def flat_start(live_all: Sequence[Fill], since: float) -> tuple[float, float | None]:
    """Where to start the dollar path: the first live entry at or after the latest FLAT instant (no position open) at
    or before `since`, and the available balance live recorded at that entry. When flat, available = cash, so the
    engine starts on live's exact cash with nothing locked - no pre-window position can distort the path."""
    iv = sorted((f.t_open, f.t_close if f.t_close is not None else f.t_open) for f in live_all)
    flat = None
    reach = -math.inf
    for a, b in iv:
        if a > since:
            break
        if a >= reach:
            flat = a                     # nothing open just before this entry
        reach = max(reach, b)
    if reach <= since:
        after = [f for f in live_all if f.t_open >= since]
        flat = min((f.t_open for f in after), default=since)
    if flat is None:
        flat = min((f.t_open for f in live_all), default=since)
    first = next((f for f in sorted(live_all, key=lambda z: z.t_open) if f.t_open >= flat), None)
    return flat, (first.available_at_entry if first is not None else None)


@dataclass
class Report:
    window: tuple[float, float]
    days: float
    start_cash: float
    layers: list[LayerResult]
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"window": list(self.window), "days": self.days, "start_cash": self.start_cash, "notes": self.notes,
                "layers": [{"layer": x.layer, "scope": x.scope, "n": x.n, "verdict": x.verdict,
                            "checks": [c.__dict__ for c in x.checks], "info": x.info, "notes": x.notes}
                           for x in self.layers]}


def grade(live_all: Sequence[Fill], replay: Sequence[Fill], *, since: float, until: float,
          exits: Sequence[Fill] | None = None, flows: Iterable[Any] = (), start_cash: float | None = None,
          sleeves: Sequence[str] = GRADED_SLEEVES, config: SizingConfig | None = None,
          n_boot: int = 2000) -> Report:
    """Grade `replay` against live over [since, until). `live_all` is every live fill (all kinds; the non-graded ones
    become cash flows). With start_cash=None the window start moves back to the latest flat instant (see flat_start)."""
    notes: list[str] = []
    cfg = config or live_config()
    sl = {s.upper() for s in sleeves}
    sized = {k.upper() for k in cfg.dials}          # sleeves the sizing chain prices (a dial exists for them)
    flows_l = _as_flows(flows)
    t_path = since
    if start_cash is None:
        t_path, cash0 = flat_start(live_all, since)
        if cash0 is None:
            raise ValueError("cannot infer the window's start cash: the first live entry has no equity_at_entry; "
                             "pass start_cash")
        start_cash = float(cash0)
        if t_path < since:
            notes.append("dollar path starts %.1f h early, at the latest flat instant %s, so it starts on live's exact "
                         "cash; fills before the window are carried, not scored" % (
                             (since - t_path) / 3600, datetime.fromtimestamp(t_path, timezone.utc).isoformat()))
    days = (until - since) / 86400.0
    path_days = (until - t_path) / 86400.0
    lp = [f for f in live_all if t_path <= f.t_open < until]               # everything the path must carry
    live_sized = [f for f in lp if f.sleeve in sized]
    other = [CapitalFlow(f.t_close or f.t_open, f.usd or 0.0, f"unsized:{f.sleeve}") for f in lp
             if f.sleeve not in sized and f.usd]
    fl = sorted([f for f in flows_l if t_path <= f.ts] + other, key=lambda z: z.ts)
    if other:
        notes.append(f"{len(other)} live fills outside the sized sleeves (${sum(f.amount for f in other):+.2f}) "
                     "applied as cash flows")
    live = [f for f in live_sized if since <= f.t_open and f.sleeve in sl]  # scored
    carried = [f for f in live_sized if not (since <= f.t_open and f.sleeve in sl)]
    rp = [f for f in replay if since <= f.t_open < until and f.sleeve in sl]
    ex = [f for f in (exits if exits is not None else rp) if since <= f.t_open < until and f.sleeve in sl]
    layers = [score_entries(live, rp, s) for s in sleeves]
    layers.append(score_exits(live, ex, n_boot=n_boot))
    layers.append(score_sizing(live_sized, start_cash, fl, path_days, cfg))
    layers.append(score_dollars(live, rp, start_cash, fl, days, cfg, n_boot=n_boot, carried=carried))
    return Report((since, until), days, start_cash, layers, notes)


def _fmt(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:+.3f}" if abs(v) < 10 else f"{v:+.2f}"
    return str(v)


def format_report(rep: Report, title: str = "") -> str:
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")
    out = [f"== REPLAY ACCEPTANCE{(': ' + title) if title else ''}",
           f"   window {iso(rep.window[0])} -> {iso(rep.window[1])} UTC ({rep.days:.1f} d), live cash at start "
           f"${rep.start_cash:,.2f}"]
    out += [f"   note: {n}" for n in rep.notes]
    for x in rep.layers:
        out.append(f"-- {x.layer:<8} {x.scope:<16} n={x.n:<4} {x.verdict}")
        for c in x.checks:
            mark = "ok " if c.ok else ("-- " if c.ok is None else "XX ")
            out.append(f"     {mark}{c.name:<30} {_fmt(c.value):>9}   bar {c.bar}")
        for k, v in x.info.items():
            if isinstance(v, (list, tuple)) and v and isinstance(v[0], (float, int)) and len(v) == 2:
                out.append(f"        {k}: [{_fmt(v[0])}, {_fmt(v[1])}]")
            elif isinstance(v, list):
                if v:
                    out.append(f"        {k}: {v[:8]}{' ...' if len(v) > 8 else ''}")
            elif isinstance(v, dict):
                out.append(f"        {k}: " + ", ".join(f"{a} {_fmt(b)}" for a, b in v.items()))
            else:
                out.append(f"        {k}: {_fmt(v)}")
        out += [f"        note: {n}" for n in x.notes]
    verdicts = {}
    for x in rep.layers:
        key = "SIZING/DOLLARS" if x.layer in ("SIZING", "DOLLARS") else f"{x.layer} {x.scope}" if x.layer == "ENTRIES" \
            else x.layer
        prev = verdicts.get(key)
        verdicts[key] = x.verdict if prev is None else ("FAIL" if "FAIL" in (prev, x.verdict) else
                                                         "INSUFFICIENT" if "INSUFFICIENT" in (prev, x.verdict) else "PASS")
    out.append("== SUMMARY  " + "  |  ".join(f"{k}: {v}" for k, v in verdicts.items()))
    return "\n".join(out)
