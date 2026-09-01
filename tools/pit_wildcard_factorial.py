"""Do the REJECTED WILDCARD changes rescue each other in combination?

    railway ssh --service Futures-bot -> /opt/venv/bin/python tools/pit_wildcard_factorial.py

Companion to pit_trend_factorial.py, which found the owner's intuition sound: on
TREND, `trigger 5%` (-$2.25 alone) and `slots 3` (-$17.80 alone) together make
+$19.51 - a +$39.56 interaction with a MECHANISM behind it, since the third slot
is exactly the capacity that absorbs the trades a higher trigger displaces.

This asks the same of WILDCARD, which books ~2.3x the fills and is therefore
where $10/month is reachable. 2^4 = 16 cells:

    trigger   8% (live)  |  7%          the OPEN hypothesis - the 7-8% band runs
                                        +$0.617/fill and is excluded today
    exit      5R cap     |  SECURE 6R   best exit cell found (+$32.97), refused
                                        alone because $24.66 of it is one trade
    slots     3 (live)   |  4           the analogue of the pair that rescued on
                                        TREND, never swept on the corrected book
    cooldown  off (live) |  6h          refused alone at every scope; freezes a
                                        SYMBOL for 6h after that symbol exits

SAME DISCIPLINE AS THE TREND RUN. The search uses the 220-day corrected book,
because trials 17-18 span ~5 days and cannot support a 16-cell search. The trial
window is reported descriptively and must not break a tie. A cell with no true
edge still clears the boundary-swept screen ~25% of the time, so ~4 spurious
passes are expected among 16 - section C states that null before any cell is
read, and section B separates real interaction from the sum of the parts.

READ-ONLY.
"""
from __future__ import annotations

import collections
import datetime as dt
import itertools
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# detection must reach the lowest trigger under test; the detector has its own
# gate (wildcard.py:234) so this has to precede the import
os.environ["FUTURES_WILDCARD_MIN_ROC"] = "0.07"

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_book import take  # noqa: E402
from pit_corrected import secured  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_pool import day_key, daily_turnover, pit_majors  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

TAIL = 260
TRIGGERS = (0.08, 0.07)          # live first
SECURES = (None, 6.0)            # None = the live 5R cap
SLOTS = (3, 4)
COOLDOWNS = (0.0, 6 * 3600.0)
LIVE = (0.08, None, 3, 0.0)
TRIAL_START = dt.datetime(2026, 8, 27, tzinfo=dt.UTC).timestamp()



def decompose(by, LIVE, alt):
    """FULL 2^k factorial decomposition by Yates' method - every main effect AND
    every interaction up to k-way, not just pairs.

    effect(S) = sum over subsets T of S of (-1)^(|S|-|T|) * y(T), where y(T) is
    the cell with exactly the factors in T switched away from live. A 3-way term
    is what the trio is worth BEYOND its three main effects and three pairwise
    interactions - so a large one means the combination does something none of
    its parts or pairs predicts.
    """
    k = len(LIVE)
    out = []
    for r in range(1, k + 1):
        for S in itertools.combinations(range(k), r):
            eff, ok = 0.0, True
            for r2 in range(0, r + 1):
                for T in itertools.combinations(S, r2):
                    cell = list(LIVE)
                    for t in T:
                        cell[t] = alt[t]
                    v = by.get(tuple(cell))
                    if v is None:
                        ok = False
                        break
                    eff += ((-1) ** (r - r2)) * v
                if not ok:
                    break
            if ok:
                out.append((r, S, eff))
    return out


def print_decomposition(by, LIVE, alt, names):
    terms = decompose(by, LIVE, alt)
    label = {1: "MAIN EFFECT", 2: "2-WAY", 3: "3-WAY", 4: "4-WAY"}
    for order in sorted({t[0] for t in terms}):
        rows = sorted([t for t in terms if t[0] == order], key=lambda t: -abs(t[2]))
        print("  --- %s ---" % label.get(order, "%d-WAY" % order))
        for _, S, eff in rows:
            print("  %-46s %+10.2f" % (" + ".join(names[i] for i in S), eff))
    print()
    print("  Higher orders are SURPRISE: what a combination is worth beyond")
    print("  everything its parts and pairs already explain. Large higher-order")
    print("  terms on 16 cells are ALSO the classic signature of overfitting,")
    print("  so magnitude alone is not evidence - the screen still rules.")


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def _lbl(cell):
    tg, sec, sl_, cd = cell
    return ("%.0f%% / %s / %d slots / %s"
            % (tg * 100, "5R cap" if sec is None else "SECURE %.0fR" % sec, sl_,
               "no cd" if cd <= 0 else "%.0fh cd" % (cd / 3600.0)))


def main() -> int:
    print("*** SIMULATED REPLAY on the CORRECTED book - model dollars, not P&L ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    now = int(time.time())
    days, pool_n = _env("PJ_DAYS", 220), int(_env("PJ_POOL", 170))
    eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    tp_r = _env("FUTURES_WILDCARD_TP_R", 5.0)
    scan_s = _env("FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS", 450.0)
    slmp = _env("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", 20.0)
    lo_, hi_ = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    floor_to = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band_n = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    calm_max = _env("FUTURES_WILDCARD_MAX_CALM_RATIO", 0.75)
    # DEFECT FIXED 2026-09-01. Live resolves this gate through the RANGE branch,
    # not the MOVE branch: FUTURES_WILDCARD_RANGE_PREFILTER defaults TRUE, so
    # min_move = FUTURES_WILDCARD_MIN_24H_RANGE, which is unset and therefore
    # DEFAULTS TO min_roc = 0.08 (runtime.py:5765-5769). Reading
    # FUTURES_WILDCARD_MIN_24H_MOVE=0.03 instead applied a 3% gate where the bot
    # applies 8%, admitting a far wider universe - the live scan reports
    # movers=39-42 while this replay was scanning ~170.
    _pref = (os.environ.get("FUTURES_WILDCARD_RANGE_PREFILTER") or "1") not in ("0", "false", "False")
    _roc_live = _env("FUTURES_WILDCARD_MIN_ROC_LIVE", 0.08)
    min_move = (_env("FUTURES_WILDCARD_MIN_24H_RANGE", _roc_live) if _pref
                else _env("FUTURES_WILDCARD_MIN_24H_MOVE", 0.08))
    base_ret = _env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50)
    rat_r = _env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0)
    rat_hi = _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75)
    plain = ratchet(rat_r, rat_hi, base=base_ret, arm=1.0)
    latch = secured(6.0, base_ret, rat_r, rat_hi)
    print("%d/%d slots | TP %.1fR | scan %.0fs | 16 cells\n"
          % (SLOTS[0], SLOTS[1], tp_r, scan_s))

    tk = cl.get_all_tickers() or []
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 2e5)][:pool_n]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    frames, rep = fetch_frames(cl, cand, days=days, workers=6, min_bars=300, now_ts=now)
    print(rep)

    ROLLS, PREP = {}, {}
    for s, df in frames.items():
        cs = sizes.get(s, 0.0)
        c = [float(x) for x in df["close"]]
        v = [float(x) for x in df["volume"]]
        raw = [c[k] * v[k] * cs for k in range(len(c))]
        roll, acc = [0.0] * len(c), 0.0
        for k, x in enumerate(raw):
            acc += x
            if k >= 96:
                acc -= raw[k - 96]
            roll[k] = acc
        ts_all = [float(x.timestamp()) for x in df.index]
        ROLLS[s] = [(ts_all[k], roll[k]) for k in range(96, len(c))]
        PREP[s] = (df, list(zip(ts_all, [float(x) for x in df["high"]],
                                [float(x) for x in df["low"]], c)), roll, c)
    PIT = pit_majors(daily_turnover(ROLLS), n=band_n)

    # ONE detection pass at the lowest trigger; the trigger is a pure filter on
    # the detector's own roc, and the exit variants change only how a signal
    # RESOLVES, so the geometry is identical across all 16 cells.
    SIG = []
    for s, (df, bars, roll, c) in PREP.items():
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < floor_to:
                continue
            roc = abs(c[i] / c[i - W.ROC_BARS] - 1.0)
            if roc < min(TRIGGERS):
                continue
            if i >= 96:
                w_hi, w_lo = max(c[i - 96:i + 1]), min(c[i - 96:i + 1])
                if w_lo > 0 and (w_hi / w_lo - 1.0) < min_move:
                    continue
            if band_n and s in PIT.get(day_key(bars[i][0]), ()):
                continue
            sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
            if sig is None:
                continue
            e, sl = float(sig.entry_price), float(sig.sl_price)
            if abs(e - sl) <= 0 or e <= 0:
                continue
            cr = getattr(sig, "calm_ratio", None)
            eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
            SIG.append((s, bars, i, e, sl, float(sig.tp_price), sig.side, roc,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0),
                        (float(cr) if cr is not None else None),
                        regime_size_multiplier(eff, lo=lo_, hi=hi_, floor_mult=flm)))
    print("signals detected at the %.0f%% floor: %d\n" % (min(TRIGGERS) * 100, len(SIG)))

    RESOLVED = {}
    for sec in SECURES:
        out = []
        for s, bars, i, e, sl, tp, side, roc, atr, cr, mlt in SIG:
            row = {"entry": e, "sl": sl, "tp": tp, "side": side}
            # DEFECT FIXED 2026-09-01. resolve() takes the TP as a PRICE and the
            # R it credits SEPARATELY (retention_trail_ab.py:155-156). Passing
            # tp_r=99 while leaving `tp` at the 5R price credited +99R to every
            # trade that merely touched its ordinary take-profit, which inflated
            # the SECURE arm from ~+$33 to ~+$3,584. To remove the cap the PRICE
            # must move too, so it is rebuilt at 99R from the same 1R distance.
            if sec is None:
                use_tp, use_tp_r = tp, tp_r
            else:
                one_r = abs(e - sl)
                use_tp_r = 99.0
                use_tp = (e + use_tp_r * one_r if side == "LONG"
                          else e - use_tp_r * one_r)
            g = resolve(bars, i, e, sl, use_tp, use_tp_r, side,
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row),
                        (plain if sec is None else latch), atr, now)
            if g is None:
                continue
            out.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                        "exit_ts": float(g[1]), "kind": str(g[2]), "roc": roc,
                        "calm_ratio": cr, "mult": mlt})
        out.sort(key=lambda z: z["ts"])
        RESOLVED[sec] = out
        print("  resolved %-12s: %d candidates"
              % ("5R cap" if sec is None else "SECURE 6R", len(out)))
    print()

    def book(cell):
        tg, sec, sl_, cd = cell
        return take([z for z in RESOLVED[sec] if z["roc"] >= tg], slots=sl_,
                    equity=eq0, risk_pct=risk_pct, sl_margin_pct=slmp,
                    scan_s=scan_s, one_per_scan=True, calm_max=calm_max,
                    cooldown_s=cd)

    BASE = book(LIVE)
    if not BASE:
        print("no fills at live")
        return 1
    t0, t1 = BASE[0]["ts"], BASE[-1]["ts"]
    base_usd = sum(z["usd"] for z in BASE)

    def halves(f, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(z["usd"] for z in f if z["ts"] < cut),
                sum(z["usd"] for z in f if z["ts"] >= cut))

    rows = []
    for cell in itertools.product(TRIGGERS, SECURES, SLOTS, COOLDOWNS):
        f = book(cell)
        if not f:
            continue
        u = sum(z["usd"] for z in f)
        vals = sorted((z["usd"] for z in f), reverse=True)
        ex5 = sum(vals[max(1, len(vals) // 20):])
        ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                    *halves(f, fr), *halves(BASE, fr))
                 for fr in (0.35, 0.425, 0.5, 0.575, 0.65))
        tw = [z for z in f if z["ts"] >= TRIAL_START]
        rows.append({"cell": cell, "n": len(f), "usd": u, "d": u - base_usd,
                     "ex5": ex5, "pf": u / len(f), "ok": ok, "live": cell == LIVE,
                     "tw_n": len(tw), "tw_usd": sum(z["usd"] for z in tw)})

    for r in rows:
        if abs(r["pf"]) > 3.0:
            print("!! IMPLAUSIBLE $/fill %.3f on %s - mean risk is ~$4, so this "
                  "is a wiring error, not a result." % (r["pf"], _lbl(r["cell"])))
    rows.sort(key=lambda r: -r["usd"])
    print("=" * 112)
    print("A. ALL %d CELLS, best net $ first.  LIVE = %s" % (len(rows), _lbl(LIVE)))
    print("=" * 112)
    print("%-40s %6s %10s %10s %10s %8s %6s"
          % ("cell", "fills", "net $", "vs live", "ex-top5", "$/fill", "both?"))
    for r in rows:
        print("%-40s %6d %+10.2f %+10.2f %+10.2f %8.3f %6s%s"
              % (_lbl(r["cell"]), r["n"], r["usd"], r["d"], r["ex5"], r["pf"],
                 "base" if r["live"] else ("YES" if r["ok"] else "no"),
                 "   <- LIVE" if r["live"] else ""))

    by = {r["cell"]: r["d"] for r in rows}
    names = {0: "trigger 7%", 1: "SECURE 6R", 2: "slots 4", 3: "cooldown 6h"}
    alt = {0: 0.07, 1: 6.0, 2: 4, 3: 6 * 3600.0}
    print()
    print("=" * 112)
    print("B. SINGLE-DIAL vs INTERACTION - does any pair beat the sum of its parts?")
    print("=" * 112)
    solo = {}
    print("  %-30s %10s" % ("change, applied ALONE", "vs live"))
    for k in range(4):
        cell = list(LIVE)
        cell[k] = alt[k]
        solo[k] = by.get(tuple(cell))
        print("  %-30s %+10.2f"
              % (names[k], solo[k] if solo[k] is not None else float("nan")))
    print()
    print("  %-30s %10s %10s %11s   %s"
          % ("PAIR", "actual", "sum alone", "interaction", "verdict"))
    for a, b in itertools.combinations(range(4), 2):
        cell = list(LIVE)
        cell[a], cell[b] = alt[a], alt[b]
        act = by.get(tuple(cell))
        if act is None or solo[a] is None or solo[b] is None:
            continue
        exp = solo[a] + solo[b]
        print("  %-30s %+10.2f %+10.2f %+11.2f   %s"
              % ("%s + %s" % (names[a], names[b]), act, exp, act - exp,
                 "RESCUES" if (act > 0 and exp <= 0) else
                 ("synergy" if act - exp > 0 else "no")))

    print()
    print("=" * 112)
    print("B2. FULL DECOMPOSITION TO %d-WAY - pairs were not the whole story" % len(LIVE))
    print("=" * 112)
    print_decomposition(by, LIVE, alt, names)

    passes = [r for r in rows if r["ok"] and not r["live"] and r["d"] > 0]
    n_cells = len(rows) - 1
    print()
    print("=" * 112)
    print("C. IS THIS SIGNAL OR SEARCH? the multiplicity null")
    print("=" * 112)
    print("  non-live cells tested            : %d" % n_cells)
    print("  cells beating live AND screening : %d" % len(passes))
    print("  expected by CHANCE at ~25%%        : %.1f" % (0.25 * n_cells))
    print("  -> %s" % ("AT OR BELOW the null - indistinguishable from search"
                       if len(passes) <= 0.25 * n_cells
                       else "above the null; read the MARGIN, not the rank"))
    for r in passes:
        d30 = (t1 - t0) / 86400.0 / 30.0
        print("     %-40s %+8.2f = $%+.2f/month at $%.0f"
              % (_lbl(r["cell"]), r["d"], r["d"] / d30, eq0))
    print()
    print("=" * 112)
    print("D. THE TRIAL 17-18 WINDOW - DESCRIPTIVE ONLY, ~5 days, no power")
    print("=" * 112)
    for r in rows[:6]:
        print("  %-40s %4d fills %+9.2f%s"
              % (_lbl(r["cell"]), r["tw_n"], r["tw_usd"],
                 "   <- LIVE" if r["live"] else ""))
    print()
    print("  exit mix of the top cell: %s"
          % dict(collections.Counter(z["kind"] for z in book(rows[0]["cell"]))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
