"""How much ROOM should a trade get? Stop width and the margin cap, swept.

    railway run --service Futures-bot python tools/pit_stop_width.py

WHY. Owner, 2026-08-28: "test different levels of SL -- would giving more room
decrease the number of losses? focus is high $ P&L to take profits on."

FIRST, THE FRAMING. The request says "move from -1R to -1.5R or -2R". R is
DEFINED as the distance to the stop, so every stop-out is -1R by construction
and "-1.5R stop" is not a setting -- it relabels the same trade. The real dials
are the ones that set stop distance in PRICE:

  FUTURES_WILDCARD_SL_ATR_MULT      3.0 live (code default 1.5, already widened)
  FUTURES_WILDCARD_MAX_SL_MARGIN_PCT 20 live -- caps stop-as-%-of-margin, and
      trims LEVERAGE first so the stop distance survives. Only if even x1
      leverage breaches the cap is the stop itself tightened.

The interaction is the whole question, and it is why the multiplier alone is
not testable: the 2026-08-25 audit found TAC/STX/SPK all stopped at 19-20% of
margin -- AT the cap -- with TAC already at leverage x1. For those trades a
larger multiplier changes nothing; the cap is what governs. So both dials are
swept, and the cell diagnostics report how often each one actually binds.

WHAT WIDENING DOES, mechanically, so the result can be read rather than
guessed. Under the risk dial, margin = risk_pct x equity x 100 / sl_margin_pct,
so 1R IN DOLLARS IS INVARIANT to stop width -- a wider stop buys a smaller
position, not more risk. That makes net R directly comparable in dollars across
every cell here. What DOES change: leverage falls, cost_r = cost/sl_frac falls
(wider stops are cheaper per R), the same price move is worth fewer R, and the
TP price moves out with the stop since tp_price is built from sl_frac.

So the honest prior is that widening trades fewer, larger losses for more,
smaller wins -- and the question is purely which side wins in dollars.

REPORTED, in the owner's terms: net $, the STOP-OUT COUNT (the "number of
losses" actually asked about), win rate, and -- because the stated goal is
withdrawable profit -- top-5% concentration and ex-top-5% net, the two numbers
tools/pit_tp_trail_sweep.py established as deciding whether a book survives
having its best trades taken out of it. Half-split on every cell.

RESULT 2026-08-28: THE +$41 WAS AN ARTIFACT OF THIS TOOL. DO NOT USE THE
NUMBERS BELOW WITHOUT FIXING THE THREE DEFECTS LISTED HERE.

A four-lens adversarial audit refuted the finding. The defect is in run_cell():
the 3-slot book is re-initialised inside `for k in range(n_win)` WEEKLY
windows, so all three slots are freed every 7 days at a boundary anchored to
the wall-clock moment the tool happens to run. The live bot never does this --
its slots run continuously. The reset structurally favours the long-hold arm
(candidate median hold 11.8h vs live 5.0h; timeouts 86 -> 163), and the
reported +$41 is the single luckiest phase of that arbitrary anchor. Sweeping
the boundary 1-6 days on IDENTICAL data: +27.75, -14.63, -28.86, -50.87,
-50.49, -42.29, -45.65 (mean -$29.29). A continuous slot book -- the faithful
model -- gives -$8.85, negative at all 7 phases.

The decisive evidence is the PAIRED test, which removes the slot lottery
entirely: on identical (symbol,bar) entries, widening is worth -$68.50, and an
auditor reproduced -$68.60 on an independent pool. Phase-averaged, live 3.0/20
ranks 2nd of 14 cells; 4.0/30 ranks 9th. There is no "wider pays" gradient.

Two further corrections to the original write-up. (1) The "cap binds on 29.9%
of fills" mechanism is wrong: leverage is stored for reporting and never enters
the P&L, so the cap can only move money via sl_price in the x1-leverage branch;
68% of that dial's apparent benefit was the cap-30 book not taking 27 losing
trades because changed exit times reshuffled slot occupancy. (2) White's
Reality Check on the 10-cell search puts a +$41 gap at p=0.275 -- about half of
it is the arithmetic premium of taking the max of 10 correlated cells.

What DID survive the audit, and is worth keeping: the detector genuinely
re-reads both env dials per call (5 distinct geometries from 5 settings); the
resolver is applied identically across cells (0 divergent outcomes on
identical-geometry pairs); the clamped-short tp_r bug that faked +82 in
pit_trend_tp is structurally absent here (tp_r is derived from the clamped
PRICE, so clamped shorts credit 2.50-4.96R, never a nominal 5R); and the
"1R in dollars is invariant to stop width" claim is exactly true (min = median
= max = $3.889 in every cell), so cross-cell dollar comparisons are legitimate.

BEFORE RERUNNING, FIX: (1) run the slot book continuously rather than per
weekly window; (2) average over week-boundary phases and report the spread;
(3) report the PAIRED same-signal effect as the headline, with the slot book
as a secondary realism check rather than the primary estimator.

METHOD. Point-in-time pool and live exit stack as tools/pit_rerun.py. Frames
are fetched ONCE; each cell re-runs the real detector under its own env so the
leverage trim, the cap and the TP geometry are all rebuilt exactly as live.
WILDCARD only -- TREND has its own stop policy and three fixed symbols.
"""
from __future__ import annotations

import os
import sys
import time
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
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    dollar_r = risk_pct * eq0
    print("equity $%.2f | risk %.4f -> 1R = $%.2f (invariant to stop width)"
          % (eq0, risk_pct, dollar_r))

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    syms = [s for a, s in crypto if s not in majors and a >= _env("PJ_MIN_TODAY", 3e5)][:pool_n]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}

    frames, _rep = fetch_frames(cl, syms, days=days, workers=6,
                                min_bars=300, now_ts=now)
    print(_rep)

    # rolling turnover + trigger bars, computed once and reused by every cell
    prep = {}
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
        hits = [i for i in range(250, len(c))
                if i > W.ROC_BARS and roll[i] >= floor
                and abs(c[i] / c[i - W.ROC_BARS] - 1.0) >= 0.08]
        prep[s] = (df, bars, hits)
    print("trigger bars: %d" % sum(len(h) for _d, _b, h in prep.values()))

    live_floor = ratchet(3.0, 0.75)
    win_s = 7 * 86400
    span = max(b[-1][0] for _d, b, _h in prep.values()) - min(b[0][0] for _d, b, _h in prep.values())
    n_win = max(1, int(span // win_s))
    mid = n_win // 2

    def run_cell(atr_mult, cap_pct):
        os.environ["FUTURES_WILDCARD_SL_ATR_MULT"] = str(atr_mult)
        os.environ["FUTURES_WILDCARD_MAX_SL_MARGIN_PCT"] = str(cap_pct)
        C = []
        for s, (df, bars, hits) in prep.items():
            for i in hits:
                sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                if sig is None:
                    continue
                e, sl, tp = float(sig.entry_price), float(sig.sl_price), float(sig.tp_price)
                one = abs(e - sl)
                if one <= 0 or e <= 0:
                    continue
                slf = one / e
                # the cap bound this signal if the realised stop-as-%-of-margin
                # is at the ceiling, i.e. leverage was trimmed to protect it
                was_capped = slf * float(sig.leverage) * 100.0 >= cap_pct - 0.5
                row = {"entry": e, "sl": sl, "tp": tp, "side": sig.side}
                g = resolve(bars, i, e, sl, tp, abs(tp - e) / one, sig.side,
                            shadow.CONVEX_HORIZON_S, shadow.cost_r(row), live_floor,
                            float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if g is None:
                    continue
                C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                          "kind": g[2], "exit_ts": float(g[1]),
                          "slf": slf, "lev": float(sig.leverage),
                          "capped": was_capped})
        C.sort(key=lambda x: x["ts"])
        # 3 slots, one position per symbol, weekly windows
        taken, older, recent = [], 0.0, 0.0
        for k in range(n_win):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            slots, per, wk = [], {}, 0.0
            for x in C:
                if not (lo_t <= x["ts"] < hi_t):
                    continue
                slots[:] = [q for q in slots if q > x["ts"]]
                per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
                if per[x["sym"]] or len(slots) >= 3:
                    continue
                slots.append(x["exit_ts"])
                per[x["sym"]].append(x["exit_ts"])
                taken.append(x)
                wk += x["net"] * dollar_r
            if k < mid:
                recent += wk
            else:
                older += wk
        return taken, sum(1 for x in taken if x["capped"]), older, recent

    print("\n%-22s %5s %9s %7s %6s %7s %6s %8s | %8s %8s"
          % ("cell (atr x cap%)", "n", "net $", "stops", "win%", "avg lev",
             "cap%", "top5%", "ex-top5", "older/recent"))
    base = None
    for atr_mult, cap_pct in ((3.0, 20), (3.0, 25), (3.0, 30), (3.0, 40),
                              (4.0, 20), (4.0, 30), (5.0, 20), (5.0, 30),
                              (2.0, 20), (1.5, 20)):
        taken, capped, older, recent = run_cell(atr_mult, cap_pct)
        n = len(taken)
        if n == 0:
            continue
        net = sum(x["net"] for x in taken) * dollar_r
        stops = sum(1 for x in taken if x["kind"] == "stop")
        wins = sum(1 for x in taken if x["net"] > 0)
        lev = sum(x["lev"] for x in taken) / n
        vals = sorted((x["net"] * dollar_r for x in taken), reverse=True)
        k5 = max(1, n // 20)
        top5 = sum(vals[:k5])
        ex5 = net - top5
        tag = " <- LIVE" if (atr_mult == 3.0 and cap_pct == 20) else ""
        if base is None:
            base = net
        print("%-22s %5d %+9.2f %6d %5.1f%% %7.2f %5.1f%% %+8.2f | %+8.2f %+7.0f/%+.0f%s"
              % ("%.1f x %d%%" % (atr_mult, cap_pct), n, net, stops,
                 100.0 * wins / n, lev, 100.0 * capped / max(1, n),
                 100.0 * top5 / net if net else 0.0, ex5, older, recent, tag))
    print("\ntop5%% = share of net $ carried by the best 5%% of trades.")
    print("ex-top5 = net $ with those removed: the book you keep if you withdraw the winners.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
