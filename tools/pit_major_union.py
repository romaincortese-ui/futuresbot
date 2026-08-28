"""Multi-horizon UNION gates on the majors: the untested corner of the
market-regime question.

    railway run --service Futures-bot python tools/pit_major_union.py

WHY. Owner, 2026-08-28: "only open trades if BTC is up/down >=2% in 12h AND/OR
5% in 24h AND/OR 10% in 72h; try 10 variants; then ETH, SOL, and pairs."

tools/pit_regime_gate.py (2026-08-25, 208d, 1024 candidates) already refuted
the SINGLE-horizon family decisively: any-major >=5%/24h costs -$246, BTC-only
>=3% costs -$270, all-three >=3% costs -$268, and 6h/12h/48h lookbacks all
lose. Measured against a per-trade proportional benchmark they are WORSE than
randomly dropping the same number of trades -- they actively select bad ones.
Only the inverse (majors CALM) survived, at +$11, a spike not a gradient.

THREE THINGS IN THE REQUEST ARE GENUINELY NEW, which is why this exists:
  1. UNION logic. Every prior cell tested one horizon. "2%/12h OR 5%/24h OR
     10%/72h" fires if ANY condition holds, so it is far more permissive.
     That matters because throttling was a large part of what killed the
     others -- breadth had the best selection in the whole run (+$62 surplus)
     and still lost outright by vetoing 38% of the book.
  2. The 72h horizon. Prior LOOKBACKS were 6h/12h/24h/48h only.
  3. Ticker PAIRS. Prior tested one ticker or all three, never BTC|ETH etc.

PREDICTION, stated before the run so the result cannot be rationalised after:
if the majors carry NEGATIVE selection (the prior study's finding), then a more
permissive union should lose LESS than the single-horizon gates but still lose
-- approaching zero from below as it approaches "no gate at all". A union that
lands clearly POSITIVE would contradict the earlier work and demand a rerun of
both.

METHOD. Point-in-time pool as tools/pit_rerun.py, live exit stack, WILDCARD
only. Two corrections learned the hard way this month:

  - CONTINUOUS SLOT BOOK. tools/pit_stop_width.py reset its 3 slots every
    weekly window, which freed slots on an arbitrary wall-clock boundary and
    manufactured a +$41 finding that vanished when the boundary moved
    (retracted in 9c8e4c7). Slots here run continuously, as the live bot does.
  - PROPORTIONAL BENCHMARK. A gate keeping N trades is compared against the
    no-gate per-trade mean x N, not against zero. Without it, "keeps fewer
    trades" reads as "loses money" and every gate looks bad for the wrong
    reason. Surplus = actual - expected is the only number that isolates
    SELECTION from THROTTLING.

Fail-open on missing major data: a candidate whose major series is unavailable
is KEPT, so the gate is never credited for dropping a trade it could not see.

READ-ONLY. Never places or modifies an order.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

BAR = 900
CHUNK = 1900
TAIL = 260
MAJORS = ("BTC_USDT", "ETH_USDT", "SOL_USDT")
# 12h, 24h, 72h in 15-minute bars. 72h is the horizon the prior study lacked.
H12, H24, H72 = 48, 96, 288


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - linear dollars (R x fixed risk), NOT account P&L. ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 190), int(_env("PJ_POOL", 150))
    now = int(time.time())
    floor = W.wildcard_min_turnover_usdt()
    eq0 = rt._last_known_equity() or 162.0
    dollar_r = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241) * eq0
    print("equity $%.2f -> 1R = $%.2f" % (eq0, dollar_r))

    tk = cl.get_all_tickers() or []
    majors_band = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand_syms = [s for a, s in crypto if s not in majors_band
                 and a >= _env("PJ_MIN_TODAY", 3e5)][:pool_n]
    syms = sorted(set(cand_syms) | set(MAJORS))
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}

    frames, _rep = fetch_frames(cl, syms, days=days, workers=6,
                                min_bars=300, now_ts=now)
    print(_rep)

    # major |return| at each horizon, keyed by bar timestamp
    MRET = {h: {} for h in (H12, H24, H72)}
    for m in MAJORS:
        df = frames.get(m)
        if df is None:
            print("  WARNING: %s unavailable - gates using it will fail open" % m)
            continue
        c = [float(x) for x in df["close"]]
        ts = [float(x.timestamp()) for x in df.index]
        for h in (H12, H24, H72):
            d = MRET[h]
            for i in range(h, len(c)):
                if c[i - h] <= 0:
                    continue
                d.setdefault(ts[i], {})[m] = abs(c[i] / c[i - h] - 1.0)
    print("major series: 12h %d bars | 24h %d | 72h %d"
          % (len(MRET[H12]), len(MRET[H24]), len(MRET[H72])))

    live_floor = ratchet(3.0, 0.75)
    C = []
    for s in cand_syms:
        df = frames.get(s)
        if df is None:
            continue
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
        bars = list(zip([float(x.timestamp()) for x in df.index],
                        [float(x) for x in df["high"]],
                        [float(x) for x in df["low"]], c))
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < floor:
                continue
            if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < 0.08:
                continue
            sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
            if sig is None:
                continue
            e, sl, tp = float(sig.entry_price), float(sig.sl_price), float(sig.tp_price)
            one = abs(e - sl)
            if one <= 0 or e <= 0:
                continue
            row = {"entry": e, "sl": sl, "tp": tp, "side": sig.side}
            g = resolve(bars, i, e, sl, tp, abs(tp - e) / one, sig.side,
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), live_floor,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is None:
                continue
            C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                      "exit_ts": float(g[1])})
    C.sort(key=lambda x: x["ts"])
    span = (C[-1]["ts"] - C[0]["ts"]) if C else 1.0
    mid_ts = C[0]["ts"] + span / 2.0 if C else 0.0
    print("candidates: %d over %.0f days" % (len(C), span / 86400.0))

    def gate(x, tickers, conds):
        """True = allow the trade. conds is a list of (horizon_bars, threshold).
        Union: ANY condition satisfied by ANY listed ticker opens the gate.
        Fails OPEN when the major data is missing for that bar."""
        seen = False
        for h, thr in conds:
            d = MRET[h].get(x["ts"])
            if not d:
                continue
            for t in tickers:
                if t in d:
                    seen = True
                    if d[t] >= thr:
                        return True
        return not seen   # no data anywhere -> keep the trade

    def book(keep):
        """Continuous 3-slot book, one position per symbol. NOT reset weekly -
        that construction manufactured a retracted finding in pit_stop_width."""
        slots, per = [], {}
        tot = older = recent = 0.0
        n = 0
        for x in C:
            if not keep(x):
                continue
            slots[:] = [q for q in slots if q > x["ts"]]
            per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
            if per[x["sym"]] or len(slots) >= 3:
                continue
            slots.append(x["exit_ts"])
            per[x["sym"]].append(x["exit_ts"])
            d = x["net"] * dollar_r
            tot += d
            n += 1
            if x["ts"] < mid_ts:
                older += d
            else:
                recent += d
        return tot, n, older, recent

    base_tot, base_n, base_o, base_r = book(lambda x: True)
    per_trade = base_tot / max(1, base_n)
    print("\nNO GATE (live): $%+.2f over %d trades | $%+.4f/trade | older $%+.2f recent $%+.2f"
          % (base_tot, base_n, per_trade, base_o, base_r))
    print("\nsurplus = actual - (no-gate $/trade x trades kept). It separates SELECTION")
    print("from THROTTLING: a gate with no information scores surplus 0 by construction.\n")

    U = [(H12, 0.02), (H24, 0.05), (H72, 0.10)]          # the owner's rule
    VARIANTS = [
        ("owner 2/12 5/24 10/72", U),
        ("tight 3/12 7/24 15/72", [(H12, 0.03), (H24, 0.07), (H72, 0.15)]),
        ("loose 1/12 3/24 6/72", [(H12, 0.01), (H24, 0.03), (H72, 0.06)]),
        ("v.loose 0.5/12 2/24 4/72", [(H12, 0.005), (H24, 0.02), (H72, 0.04)]),
        ("12h only >=2%", [(H12, 0.02)]),
        ("24h only >=5%", [(H24, 0.05)]),
        ("72h only >=10%", [(H72, 0.10)]),
        ("72h only >=6%", [(H72, 0.06)]),
        ("12h+24h (no 72h)", [(H12, 0.02), (H24, 0.05)]),
        ("24h+72h (no 12h)", [(H24, 0.05), (H72, 0.10)]),
    ]
    SETS = [("BTC", ("BTC_USDT",)), ("ETH", ("ETH_USDT",)), ("SOL", ("SOL_USDT",)),
            ("BTC|ETH", ("BTC_USDT", "ETH_USDT")), ("BTC|SOL", ("BTC_USDT", "SOL_USDT")),
            ("ETH|SOL", ("ETH_USDT", "SOL_USDT")),
            ("BTC|ETH|SOL", MAJORS)]

    def report(title, rows):
        print(title)
        print("  %-26s %6s %6s %9s %9s %9s | %9s %9s"
              % ("rule", "kept", "keep%", "net $", "expected", "SURPLUS", "older", "recent"))
        for lbl, keepfn in rows:
            tot, n, o, r = book(keepfn)
            exp = per_trade * n
            print("  %-26s %6d %5.0f%% %+9.2f %+9.2f %+9.2f | %+9.2f %+9.2f"
                  % (lbl, n, 100.0 * n / max(1, base_n), tot, exp, tot - exp, o, r))

    report("A. THE OWNER'S RULE AND 9 VARIANTS, on BTC:",
           [(lbl, (lambda x, c=conds: gate(x, ("BTC_USDT",), c))) for lbl, conds in VARIANTS])
    report("\nB. THE OWNER'S RULE (2/12 5/24 10/72) ACROSS TICKER SETS:",
           [(name, (lambda x, t=tk2: gate(x, t, U))) for name, tk2 in SETS])
    report("\nC. THE INVERSE - trade only when the majors are QUIET (the one prior survivor):",
           [("NOT " + lbl, (lambda x, c=conds: not gate(x, MAJORS, c)))
            for lbl, conds in VARIANTS[:6]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
