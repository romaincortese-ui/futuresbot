"""Explicit per-side take-profit for the wildcard SHORT arm.

WHY. tools/pit_wildcard_tp.py found that at the live 5R target, 77% of SHORT
signals (288 of 376) have their TP distance cut back to MAX_SHORT_TP_DIST=0.50,
because a short target at or through zero is an unreachable order. Their
EFFECTIVE target is 0.50/sl_frac -- roughly 2.6R on a 19% stop -- not 5R. So the
sleeve already runs an ACCIDENTAL asymmetric target, and it binds hardest on the
side the live record says actually pays (SHORT n=15 +9.70R / +$12.33 vs LONG
n=44 +2.11R, ex-best -2.98R).

THE QUESTION IS NOT "IS THE CLAMP BAD". The clamp is structurally necessary.
The question is whether an EXPLICIT short target chosen on purpose beats the
implicit one the clamp produces by accident. Those differ in an important way:
the clamp gives every short the SAME PRICE DISTANCE (50%), which is a DIFFERENT
R for every trade depending on its stop width -- a wide-stop short gets ~2.6R, a
tight-stop short might get 10R+. An explicit target gives every short the same
R. One of those is principled; the accident might still win.

METHOD. LONG target held FIXED at the live 5R. Short target swept. The clamp is
ALWAYS applied on top (dist = min(tp_r*sl_frac, 0.50)) because it is a
correctness constraint, not a tuning knob. Baseline is the CURRENT behaviour:
nominal 5R for both sides with the clamp doing whatever it does.

WHY TOTAL AND PER-SIDE ARE BOTH REPORTED. Longs and shorts share the same three
wildcard slots, so changing when shorts exit changes slot occupancy and can
displace longs. The total is therefore NOT long_fixed + short_varying, and
reading only the short arm would miss the displacement. Both columns are shown.

Also reported: the MEAN EFFECTIVE short target actually achieved at each setting,
so it is visible what the bot is really asking for versus what was configured.

READ-ONLY. Never places or modifies an order.

RESULTS 2026-08-25 (208d, 150 symbols, 1053 candidates: LONG 676 / SHORT 377).

VERDICT: KEEP THE ACCIDENT. No explicit per-side short target beats the clamp.

  short TP    total $   vs live   SHORT $  shortTP%   recent    older
     1.5R    +205.77    -46.70    +70.02     23.2%   -34.43   -12.27   no
     2.0R    +210.50    -41.97    +72.99     13.3%   -32.56    -9.41   no
     2.5R    +257.71     +5.24   +111.72      9.1%    -2.86    +8.10   one half
     3.0R    +237.37    -15.10    +96.34      6.8%   -17.35    +2.25   one half
     4.0R    +251.68     -0.79   +102.98      4.0%    -0.79    +0.00   one half
     5.0R    +252.47     +0.00   +106.89      3.6%    +0.00    +0.00   LIVE

2.5R is +5.24 -- inside the ~$10 noise floor AND negative in the recent half.
Explicit 1.5R/2.0R targets are badly worse (-42 to -47). Nothing to act on.

WHY THE ACCIDENT IS ACTUALLY GOOD DESIGN. The clamp does NOT give shorts a fixed
low target. It gives them a VARIABLE one:

  nominal 5R -> mean effective 3.68R, min 2.50, max 5.00, 289/377 clamped

A wide-stop (high-ATR) short gets a proportionally LOWER R target; a tight-stop
short gets the full 5R. That is an ATR-CONDITIONED TARGET arrived at by
accident, and conditioning the target on volatility is a defensible thing to do
on purpose. Every FIXED alternative loses to it. The lesson generalises: before
replacing an implicit rule with a principled constant, check whether the
implicit rule is conditioning on something real.

SLOT DISPLACEMENT IS VISIBLE AND MATTERS. The LONG arm drifts +135.75 -> +148.69
across cells even though the long target never changes, because shorts exiting
sooner free slots that longs then take. Judge on the TOTAL column; a short-arm-
only reading would misattribute that $13.

CROSS-RUN LEVELS DIFFER FROM pit_wildcard_tp (baseline +252.47 here vs +220.80
there) because the pool is re-ranked by live turnover every run and the window
rolls. Only within-run comparisons are meaningful. Same discipline as everywhere
else in this family.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from futuresbot import shadow_ledger as shadow
from futuresbot import wildcard as W
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet
from retention_trail_ab import resolve

CHUNK, BAR = 2000, 900
TAIL = 2000
MAX_SHORT_TP_DIST = 0.50
LIVE_TRAIL = ratchet(3.0, 0.75, base=0.30, arm=1.0)
LONG_TP = 5.0
SHORT_TPS = (1.5, 2.0, 2.5, 3.0, 4.0, 5.0)
BASE_SHORT_TP = 5.0          # current behaviour


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars over the window, NOT account P&L.")
    print("    The real account is DOWN lifetime; /report has the true figure. ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 190), int(_env("PJ_POOL", 150))
    min_today = _env("PJ_MIN_TODAY", 3e5)
    eq0 = rt._last_known_equity() or 170.0
    now = int(time.time())
    floor = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wide = [(a, s) for a, s in crypto if s not in majors and a >= min_today]
    cand_syms = [s for _a, s in wide[:pool_n]]
    print("equity $%.2f | wildcard pool %d" % (eq0, len(cand_syms)))

    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}

    frames, _rep = fetch_frames(cl, cand_syms, days=days, workers=6,
                                min_bars=300, now_ts=now)
    print(_rep)
    span = len(next(iter(frames.values()))) * BAR / 86400
    print("frames: %d symbols, %.0fd" % (len(frames), span))

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
        ts = [b[0] for b in bars]
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < floor:
                continue
            if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < 0.08:
                continue
            sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
            if sig is not None:
                C.append({"ts": ts[i], "sym": s, "sig": sig, "i": i, "bars": bars})
    C.sort(key=lambda x: x["ts"])
    nl = sum(1 for x in C if x["sig"].side == "LONG")
    print("candidates: %d  (LONG %d / SHORT %d)" % (len(C), nl, len(C) - nl))

    win_s = 7 * 86400
    n_win = max(1, int(span // 7))
    mid = n_win // 2

    def resolve_set(short_tp):
        res, effs, clamped = {}, [], 0
        for idx, x in enumerate(C):
            sig = x["sig"]
            entry = float(sig.entry_price)
            sl = float(sig.sl_price)
            slf = abs(entry - sl) / entry if entry else 0.0
            nominal = LONG_TP if sig.side == "LONG" else short_tp
            dist = nominal * slf
            if sig.side == "SHORT" and dist >= MAX_SHORT_TP_DIST:
                dist = MAX_SHORT_TP_DIST
                clamped += 1
            tr_eff = (dist / slf) if slf > 0 else nominal
            if sig.side == "SHORT":
                effs.append(tr_eff)
            tp = entry * (1 + dist) if sig.side == "LONG" else entry * (1 - dist)
            row = {"entry": entry, "sl": sl, "tp": tp, "side": sig.side}
            g = resolve(x["bars"], x["i"], entry, sl, tp, tr_eff, sig.side,
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), LIVE_TRAIL,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is not None:
                res[idx] = g
        return res, effs, clamped

    def book(res, k_lo=0, k_hi=None):
        tot = 0.0
        side = {"LONG": [0, 0.0, 0], "SHORT": [0, 0.0, 0]}   # n, $, tp_count
        for k in range(k_lo, n_win if k_hi is None else k_hi):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            slots, per = [], {}
            for idx, x in enumerate(C):
                if not (lo_t <= x["ts"] < hi_t) or idx not in res:
                    continue
                slots[:] = [q for q in slots if q > x["ts"]]
                per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
                if per[x["sym"]] or len(slots) >= 3:
                    continue
                g = res[idx]
                slots.append(g[1])
                per[x["sym"]].append(g[1])
                d = g[0] * eq0 * 0.12 * float(x["sig"].sl_margin_pct) / 100.0
                tot += d
                s_ = x["sig"].side
                side[s_][0] += 1
                side[s_][1] += d
                side[s_][2] += 1 if g[2] == "tp" else 0
        return tot, side

    base = {}
    rows = []
    for stp in SHORT_TPS:
        res, effs, clamped = resolve_set(stp)
        tot, side = book(res)
        r = book(res, 0, mid)[0]
        o = book(res, mid, n_win)[0]
        if stp == BASE_SHORT_TP:
            base = {"tot": tot, "r": r, "o": o, "short": side["SHORT"][1]}
        rows.append({"stp": stp, "tot": tot, "side": side, "r": r, "o": o,
                     "clamped": clamped,
                     "eff": sum(effs) / len(effs) if effs else 0.0,
                     "effmin": min(effs) if effs else 0.0,
                     "effmax": max(effs) if effs else 0.0})

    print("")
    print("LONG target held FIXED at %.1fR. Clamp always applied." % LONG_TP)
    print("%7s %10s %9s %10s %9s %8s %9s %9s  both?"
          % ("short TP", "total $", "vs live", "SHORT $", "vs live", "shortTP%", "recent", "older"))
    for e in rows:
        sn, sd, stp_hit = e["side"]["SHORT"]
        d = e["tot"] - base["tot"]
        dsh = sd - base["short"]
        dr, do = e["r"] - base["r"], e["o"] - base["o"]
        both = "YES" if dr > 0 and do > 0 else ("no" if dr < 0 and do < 0 else "one half")
        tag = "  <-- LIVE" if e["stp"] == BASE_SHORT_TP else ""
        print("%6.1fR %+10.2f %+9.2f %+10.2f %+9.2f %7.1f%% %+9.2f %+9.2f  %s%s"
              % (e["stp"], e["tot"], d, sd, dsh, 100.0 * stp_hit / max(sn, 1),
                 dr, do, both, tag))

    print("")
    print("WHAT THE SHORTS ARE ACTUALLY ASKED FOR (effective R after the clamp)")
    print("%7s %10s %10s %10s %14s" % ("short TP", "mean eff", "min", "max", "clamped"))
    for e in rows:
        print("%6.1fR %10.2f %10.2f %10.2f %11d/%d"
              % (e["stp"], e["eff"], e["effmin"], e["effmax"], e["clamped"], len(C) - nl))

    print("")
    print("LONG ARM (should be near-constant; drift = slot displacement by shorts)")
    print("%7s %10s %8s" % ("short TP", "LONG $", "n"))
    for e in rows:
        ln, ld, _ = e["side"]["LONG"]
        print("%6.1fR %+10.2f %8d" % (e["stp"], ld, ln))
    print("")
    print("If the LONG column moves materially, the short target is changing which")
    print("LONGS get slots -- that is a real effect, not noise, and it means the")
    print("total column is the one to judge on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
