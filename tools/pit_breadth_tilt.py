"""Breadth as a SIZE TILT: the untested half of the market-regime question.

    railway run --service Futures-bot python tools/pit_breadth_tilt.py

WHY. Owner, 2026-08-27, after ten -1R stops in the twelve closes since TUT:
"the bot identified TUT well in an exciting market; when the market calmed it
only triggered losses. Is there an efficient way to identify which market
trend to actually trade in?" tools/pit_regime_gate.py already answered the
GATE half: every majors-movement veto loses ($140-246), and is worse than
randomly dropping the same number of trades. The single positive selection
signal in that run was BREADTH -- fraction of the pool up over 24h -- with
+$62 of surplus over the proportional benchmark, but it still lost outright
as a gate because vetoing throttles 38% of a book whose edge is its tail.
tools/pit_tut_class.py then showed the same asymmetry generically: on 888
candidates, every feature veto fails or kills 10-20% of the TUT-class tail,
while 0.5/1.0/1.5 sizing across the SAME quintiles is positive on every
feature. So the pre-registered question here: does sizing BY BREADTH -- more
size when the pool moves with you, less when it does not -- beat flat sizing?

METHOD. Pool, candidates, breadth series and slot bookkeeping lifted from
tools/pit_regime_gate.py (point-in-time turnover floor, live trigger, 3
wildcard slots, one position per symbol). Exits are the live stack via
retention_trail_ab.resolve with the shipped 3.0/0.75 ratchet. Dollars are
linear: R x (risk_pct x today's equity), no compounding, so the tilt itself
is the only thing measured. Side-aware: a long's breadth is b, a short's is
1-b. Four pre-registered schemes and the old gate re-run as an anchor --
this is deliberately a 5-cell study, not a search.

Judged the way trial 12's mistakes taught: half-split on candidate time,
positive weeks, and for any veto the proportional benchmark (a gate must
beat dropping the same fraction of trades at random, or it is selection
theatre).
"""
from __future__ import annotations

import os
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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
    eq0 = rt._last_known_equity() or 165.0
    dollar_r = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241) * eq0
    print("equity $%.2f -> 1R = $%.2f (linear)" % (eq0, dollar_r))

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand_syms = [s for a, s in crypto if s not in majors and a >= _env("PJ_MIN_TODAY", 3e5)][:pool_n]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}

    frames, _rep = fetch_frames(cl, cand_syms, days=days, workers=6,
                                min_bars=300, now_ts=now)
    print(_rep)

    up, tot = defaultdict(int), defaultdict(int)
    for s, df in frames.items():
        c = [float(x) for x in df["close"]]
        ts = [float(x.timestamp()) for x in df.index]
        for i in range(96, len(c)):
            if c[i - 96] <= 0:
                continue
            tot[ts[i]] += 1
            if c[i] > c[i - 96]:
                up[ts[i]] += 1
    BREADTH = {t: up[t] / tot[t] for t in tot if tot[t] >= 20}
    print("breadth series: %d bars" % len(BREADTH))

    live_floor = ratchet(3.0, 0.75)
    C = []
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
            b = BREADTH.get(bars[i][0])
            C.append({"ts": bars[i][0], "sym": s, "side": sig.side,
                      "net": float(g[0]), "exit_ts": float(g[1]),
                      "b": (b if sig.side == "LONG" else (None if b is None else 1.0 - b))})
    C.sort(key=lambda x: x["ts"])
    print("candidates resolved: %d (breadth known on %d)"
          % (len(C), sum(1 for x in C if x["b"] is not None)))

    win_s = 7 * 86400
    span = max(x["ts"] for x in C) - min(x["ts"] for x in C)
    n_win = max(1, int(span // win_s))
    mid = n_win // 2

    def book(mult_fn):
        """Walk weekly windows with 3 slots; mult_fn(x) sizes each fill.
        Returns (net$, n, wins, pos_weeks, older$, recent$)."""
        total, n, wins, posw = 0.0, 0, 0, 0
        older = recent = 0.0
        for k in range(n_win):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            slots, per, wk = [], {}, 0.0
            for x in C:
                if not (lo_t <= x["ts"] < hi_t):
                    continue
                m = mult_fn(x)
                if m <= 0:
                    continue
                slots[:] = [q for q in slots if q > x["ts"]]
                per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
                if per[x["sym"]] or len(slots) >= 3:
                    continue
                slots.append(x["exit_ts"])
                per[x["sym"]].append(x["exit_ts"])
                d = m * x["net"] * dollar_r
                wk += d
                n += 1
                if x["net"] > 0:
                    wins += 1
            total += wk
            if wk > 0:
                posw += 1
            if k < mid:
                recent += wk
            else:
                older += wk
        return total, n, wins, posw, older, recent

    def m_flat(x):
        return 1.0

    def m_gate50(x):
        return 1.0 if (x["b"] is None or x["b"] >= 0.5) else 0.0

    def m_step(lo, hi):
        def f(x):
            if x["b"] is None:
                return 1.0
            return lo if x["b"] < 0.4 else (hi if x["b"] > 0.6 else 1.0)
        return f

    def m_linear(x):
        if x["b"] is None:
            return 1.0
        return min(1.5, max(0.5, 0.5 + x["b"]))

    base = book(m_flat)
    print("\n%-28s %6s %9s %7s %7s | %9s %9s" %
          ("policy", "n", "net $", "win%", "pos wk", "older $", "recent $"))
    for lbl, fn in (("flat 1.0 (live)", m_flat),
                    ("gate breadth>=50% (anchor)", m_gate50),
                    ("tilt 0.50/1.0/1.50", m_step(0.50, 1.50)),
                    ("tilt 0.75/1.0/1.25", m_step(0.75, 1.25)),
                    ("tilt linear 0.5+b", m_linear)):
        t, n, w, pw, o, r = book(fn)
        print("%-28s %6d %+9.2f %6.1f%% %4d/%-2d | %+9.2f %+9.2f   vs flat %+8.2f"
              % (lbl, n, t, 100.0 * w / max(1, n), pw, n_win, o, r, t - base[0]))

    print("\nBREADTH AT THE LIVE TRIAL-16 LOSERS' ENTRY HOURS (context, not a cell):")
    print("  breadth deciles of all candidates: how much of the book sits in 'calm-market' entries")
    dec = defaultdict(lambda: [0, 0.0])
    for x in C:
        if x["b"] is None:
            continue
        k = min(9, int(x["b"] * 10))
        dec[k][0] += 1
        dec[k][1] += x["net"]
    for k in sorted(dec):
        n2, s2 = dec[k]
        print("  breadth-for-side %2d0-%2d0%%: n=%4d  mean %+0.3fR" % (k, k + 1, n2, s2 / n2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
