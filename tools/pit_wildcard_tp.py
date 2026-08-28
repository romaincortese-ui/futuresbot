"""WILDCARD take-profit sweep on the corrected point-in-time pool.

WHY. The wildcard does most of the trading and its 5R target completes only
~3% of the time; live exits since 07-13 run TP 17% / stop 48% / other 34%, so
four in five winners are decided by the retention trail, not the target. The
TREND sleeve's target has now been swept twice (trend_tp_ab 08-22, pit_trend_tp
08-25, both KEEP 3R). The wildcard's 5R has never been swept cleanly: the only
run that touched it (pit_tp_trail_sweep) varied BOTH sleeves at once AND carried
the clamped-short defect that paid unreachable short targets at full nominal R.

THE CLAMP MATTERS MORE HERE THAN ANYWHERE. The wildcard trades BOTH sides.
A short's TP distance is capped at MAX_SHORT_TP_DIST=0.50 because a target at or
through zero is an unreachable order. So above some tp_r every additional R goes
to the LONGS ONLY, and the shorts silently stop scaling. This tool credits the
target the price can actually reach (tr_eff = clamped_dist / sl_frac) and reports
how many shorts are clamped at each level, so the asymmetry is visible instead of
being absorbed into the dollar column.

METHOD. Entry fixed at the live trigger (3h/8%). Trail fixed at the live ratchet
(3.0R -> 0.75, base 0.30, arm 1.0). WILDCARD BOOKED IN ISOLATION -- valid because
TREND trades ETH/XRP/ZEC, all majors and therefore excluded from the wildcard
pool, and the sleeves hold separate slot pools. Verified per run and printed.

WHAT TO READ. Dollars AND TP completion rate side by side, because the operator's
question is whether the bot can generate more take-profits. Those two columns are
expected to move in OPPOSITE directions -- on the trend sleeve, 2R gave the most
TPs (28.5%) and the least money. If that holds here, "maximise TP" is refuted as
an objective on the sleeve that matters most.

READ-ONLY. Never places or modifies an order.

RESULTS 2026-08-25 (208d, 150 symbols, 1035 candidates: LONG 659 / SHORT 376).

VERDICT: KEEP 5R. It is the money-optimum and nothing beats it in both halves.

   TP_R      net $    vs 5R      n   TP hit    stop    win%    recent    older
   2.0R    +130.47   -90.33    691    17.4%   42.1%   55.3%   -94.29    +3.96
   3.0R    +160.93   -59.87    667     9.4%   42.1%   54.9%   -62.23    +2.36
   4.0R    +196.63   -24.17    662     5.1%   42.3%   54.8%   -29.34    +5.17
   5.0R    +220.80    +0.00    659     3.6%   42.5%   54.6%    +0.00    +0.00  LIVE
   6.0R    +217.33    -3.47    657     2.1%   42.3%   54.6%    -6.89    +3.41
   8.0R    +209.95   -10.85    657     1.5%   42.5%   54.6%   -10.81    -0.03
  10.0R    +211.89    -8.91    656     1.4%   42.5%   54.6%    -8.88    -0.03

The curve is smooth and peaks exactly at the live value -- a well-behaved
response, not a lucky spike. Every alternative repeats the signature seen on the
trend sleeve: negative in the RECENT half, mildly positive in the OLDER half.

"MAXIMISE TAKE-PROFIT" IS REFUTED HERE, ON THE SLEEVE THAT DOES THE TRADING.

   TP_R   TP count      net $   $ per TP
   2.0R        120    +130.47      +1.09
   5.0R         24    +220.80      +9.20    <- LIVE
  10.0R          9    +211.89     +23.54

Moving 5R -> 2R buys 5x MORE take-profits for 41% LESS money. TP count and
dollars are monotonically opposed across the whole range. TP completions are an
OUTPUT of a good target, never a thing to maximise directly.

Note also: stop rate (42%) and win rate (55%) are FLAT at every level. The target
only ever touches the upper tail; it cannot improve the body. Anyone hoping a
target change will reduce the 42% stop rate is looking at the wrong dial.

NEW STRUCTURAL FINDING -- THE SHORT CLAMP BINDS ON THE PAYING ARM.
  TP_R    shorts clamped (of 376)
  2.0R      0    0%
  3.0R    133   35%
  4.0R    224   60%
  5.0R    288   77%     <- LIVE
  8.0R    365   97%
At the live 5R, 77% of SHORT signals have their target cut back to
MAX_SHORT_TP_DIST=0.50, so their effective target is 0.50/sl_frac (~2.6R on a
19% stop), not 5R. Above ~4R every additional R reaches LONGS ONLY.
This matters because [[futures-bot-trial8-state]] records the wildcard SHORT arm
as the half that PAYS (n=15 +9.70R / +$12.33 vs LONG n=44 +2.11R, ex-best
-2.98R). So the sleeve is already running an accidental asymmetric target, and
the clamp is binding hardest on its better side. Whether an EXPLICIT per-side
target beats the accidental one is UNTESTED and is the natural next question.
Do not assume the accident is wrong -- it may be why the short arm looks good.

NO TARGET SETTING FIXES TAIL DEPENDENCE. Concentration is 193-218% and ex-top-5%
is negative at EVERY level (-134 at 2R to -206 at 5R). The wildcard is
structurally a lottery book regardless of where the target sits; only the
BOTH-SLEEVE 1.5R config in pit_tp_trail_sweep reached positive ex-top-5%, and
that was with TREND diluting.
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
TREND_SYMS = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
TAIL = 2000
MAX_SHORT_TP_DIST = 0.50
LIVE_TRAIL = ratchet(3.0, 0.75, base=0.30, arm=1.0)
TPS = (2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)
LIVE_TP = 5.0


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
    overlap = sorted(set(cand_syms) & set(TREND_SYMS))
    print("equity $%.2f | wildcard pool %d | trend overlap: %s"
          % (eq0, len(cand_syms), overlap or "NONE (isolation valid)"))

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

    def resolve_set(tp_r):
        res, clamped = {}, 0
        for idx, x in enumerate(C):
            sig = x["sig"]
            entry = float(sig.entry_price)
            sl = float(sig.sl_price)
            slf = abs(entry - sl) / entry if entry else 0.0
            dist = tp_r * slf
            if sig.side == "SHORT" and dist >= MAX_SHORT_TP_DIST:
                dist = MAX_SHORT_TP_DIST
                clamped += 1
            tr_eff = (dist / slf) if slf > 0 else tp_r
            tp = entry * (1 + dist) if sig.side == "LONG" else entry * (1 - dist)
            row = {"entry": entry, "sl": sl, "tp": tp, "side": sig.side}
            g = resolve(x["bars"], x["i"], entry, sl, tp, tr_eff, sig.side,
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), LIVE_TRAIL,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is not None:
                res[idx] = g
        return res, clamped

    def book(res, k_lo=0, k_hi=None):
        tot, n, kinds, ds, rs = 0.0, 0, {}, [], []
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
                n += 1
                ds.append(d)
                rs.append(float(g[0]))
                kinds[g[2]] = kinds.get(g[2], 0) + 1
        return tot, n, kinds, ds, rs

    base = {}
    rows = []
    for tp in TPS:
        res, clamped = resolve_set(tp)
        tot, n, kinds, ds, rs = book(res)
        r = book(res, 0, mid)[0]
        o = book(res, mid, n_win)[0]
        if tp == LIVE_TP:
            base = {"tot": tot, "r": r, "o": o}
        rows.append({"tp": tp, "tot": tot, "n": n, "kinds": kinds, "ds": ds,
                     "rs": rs, "r": r, "o": o, "clamped": clamped})

    print("")
    print("WILDCARD SLEEVE IN ISOLATION | trail fixed at live ratchet(3.0->0.75)")
    print("%6s %10s %9s %7s %8s %8s %8s %9s %9s  both?"
          % ("TP_R", "net $", "vs 5R", "n", "TP hit", "stop", "win%", "recent", "older"))
    for e in rows:
        d = e["tot"] - base["tot"]
        dr, do = e["r"] - base["r"], e["o"] - base["o"]
        both = "YES" if dr > 0 and do > 0 else ("no" if dr < 0 and do < 0 else "one half")
        n = max(e["n"], 1)
        tph = 100.0 * e["kinds"].get("tp", 0) / n
        stp = 100.0 * e["kinds"].get("stop", 0) / n
        win = 100.0 * sum(1 for r in e["rs"] if r > 0) / n
        tag = "  <-- LIVE" if e["tp"] == LIVE_TP else ""
        print("%5.1fR %+10.2f %+9.2f %7d %7.1f%% %7.1f%% %7.1f%% %+9.2f %+9.2f  %s%s"
              % (e["tp"], e["tot"], d, e["n"], tph, stp, win, dr, do, both, tag))

    print("")
    print("TP COUNT vs DOLLARS -- the operator's question, stated directly")
    print("%6s %10s %10s %12s" % ("TP_R", "TP count", "net $", "$ per TP"))
    for e in rows:
        tpc = e["kinds"].get("tp", 0)
        print("%5.1fR %10d %+10.2f %12s"
              % (e["tp"], tpc, e["tot"], ("%+.2f" % (e["tot"] / tpc)) if tpc else "n/a"))

    print("")
    print("SHORT CLAMP -- above some level extra R reaches LONGS ONLY")
    print("%6s %14s %10s" % ("TP_R", "shorts clamped", "of %d" % (len(C) - nl)))
    for e in rows:
        print("%5.1fR %14d %9.0f%%"
              % (e["tp"], e["clamped"], 100.0 * e["clamped"] / max(len(C) - nl, 1)))

    print("")
    print("Concentration check on the money-best and TP-best rows:")
    for e in rows:
        ds = sorted(e["ds"], reverse=True)
        if not ds:
            continue
        k5 = max(1, len(ds) // 20)
        tot = sum(ds)
        print("  %4.1fR  top5%% = %5.0f%% of P&L   ex-top5%% %+9.2f"
              % (e["tp"], 100.0 * sum(ds[:k5]) / tot if tot else 0, tot - sum(ds[:k5])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
