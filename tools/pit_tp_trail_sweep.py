"""TP x trail-arm x retention sweep: what does a BANKABLE book actually cost?

WHY. The operator's withdrawal policy is "see profits, move them to the bank".
That is structurally hostile to this sleeve: the top 5% of trades carry 202% of
the P&L (tools/pit_roc_sweep.py PJ_TAIL), so withdrawing after a win removes the
very trades that fund the bleed between wins. Entry tuning cannot fix it -- the
15-cell ROC sweep found win rates flat at 51-57% in EVERY cell, so triggers move
magnitude, never frequency. Only the EXITS can convert tail into body.

Trials 6-7 already measured that direction as harmful (partial scale-out -0.115R
t -2.06; tight targets "the only provably-bad grid region" t -4.98; tightening
retention monotonically harmful; TP exits ~238% of sumR). But that was in R, in
trial 7, on the BROKEN pool. The recorded principle is "regret-minimisation at
zero EV cost is a legitimate owner preference -- PRICE IT, don't dismiss it", so
this prices it in dollars on the corrected pool at today's config.

WHAT IT REPORTS. Per cell: net $, half-split, and the three numbers that decide
whether a book is bankable -- WIN RATE, TOP-5% CONCENTRATION, and EX-TOP-5%.
A cell that cuts concentration a lot for a small dollar cost is a real option
for the operator even if it loses money in absolute terms; that trade is the
operator's to make, not mine.

METHOD. Entry held FIXED at the live trigger (3h/8%, TREND long-only ETH/XRP/ZEC)
so exits are the only variable. Candidates are generated ONCE and re-resolved per
cell. TP price is rebuilt from the stop distance: sl_frac = |entry-sl|/entry, and
tp_price = entry * (1 +/- tp_r*sl_frac), with the live MAX_SHORT_TP_DIST=0.50
clamp applied to shorts (an unclamped short TP at or through zero is an
unreachable order -- it silently converts the trade into stop-or-nothing).

BASELINE is the true live config: per-sleeve TP (wildcard 5R, trend 3R) with
ratchet(3.0, 0.75, base=0.30, arm=1.0). Grid cells apply their tp_r to BOTH
sleeves, so the (5.0, 1.0, 0.30) cell is near-live but not identical.

MULTIPLICITY: 16 cells. Best-of-16 finds winners by chance. Both-halves is a
guard, not a proof. Same discipline as the ROC sweep.

READ-ONLY. Never places or modifies an order.

*** THE 2026-08-25 RUN BELOW CARRIED A DEFECT IN THE HIGH-TP CELLS. ***
The nominal tp_r was handed to the resolver even when the SHORT clamp had cut
the TP price back to MAX_SHORT_TP_DIST, so clamped shorts were paid at the
nominal R instead of the reachable one. Cells inflate in proportion to how many
clamped shorts they hold, which is worst at TP 5R and negligible at 1.5R (a
short needs sl_frac >= 0.33 to clamp at 1.5R). Consequences:
  - The "(5.0,1.0,0.30) beats live by +82.16" row is VOID. Tested properly in
    tools/pit_trend_tp.py, raising TREND_TP_R 3->5 is worth +0.72 and fails the
    half-split. KEEP 3R.
  - The BANKABLE conclusion stands: the baseline used implied tp_r (correct)
    and the 1.5R cells are unaffected by the clamp, so the 1.5R-vs-live
    comparison is sound. If anything the -174.00 cost is OVERSTATED, because the
    high-TP cells it was measured against were inflated.
Fixed in resolve_all (tr_eff). Re-run before quoting any high-TP row.

RESULTS 2026-08-25 (208d, 152 symbols, 2017 candidates), PRE-FIX.
BASELINE live config: +449.39 / 821 trades / 18-29 wk / win 56.2% /
top5% = 119% of P&L / ex-top5% -87.37.

THE BANKABLE CONFIGURATION EXISTS AND IT IS TP 1.5R, ARM 1.0, RETAIN 0.30.
It is the ONLY cell of sixteen with a POSITIVE ex-top-5% (+2.61 vs the
baseline's -87.37) -- i.e. the only book that still stands up after its five
biggest trades are removed, which is exactly what withdrawing after a win does.
Concentration 99% vs 119%. Cost: -174.00 over 208d, about -39% of the edge.

  TP_R  arm  retain     net $   vs live  win%   top5%   ex-top5%
   1.5  1.0    0.30   +275.39   -174.00  56.5%    99%     +2.61   <-- bankable
   2.0  1.0    0.30   +321.13   -128.26  56.2%   107%    -21.15
   3.0  1.0    0.30   +394.96    -54.43  56.3%   119%    -73.32
   5.0  1.0    0.30   +531.55    +82.16  56.0%   119%   -103.29   <-- see below

TWO PREDICTIONS I MADE BEFORE THE RUN, BOTH PARTLY WRONG, RECORDED AS SUCH:
  1. "TP 1.5R will lose money outright." It does not -- it stays positive at
     +275.39, it just gives up 39% of the edge. The trials 6-7 verdict that
     tight targets are provably bad holds in RELATIVE terms, not absolute.
  2. "The middle of the grid at retain 0.60 will cut concentration cheaply."
     Wrong. At arm 1.0, retain 0.60 is WORSE than 0.30 in nearly every cell and
     does not cut concentration. The cheap concentration reduction comes from
     lowering TP_R, not from tightening retention -- consistent with the trial-7
     finding that tightening retention is monotonically harmful.

WIN RATE IS NOT THE LEVER THE OPERATOR THINKS IT IS. Baseline is ALREADY 56.2%.
Dropping the trail arm to 0.5R lifts it to ~69% -- the highest frequency in the
grid -- but every arm-0.5 cell costs $97-302 AND RAISES concentration to
137-233%. Arming early converts would-be losers into tiny winners, shrinking the
denominator while leaving the tail intact. More wins, less money, MORE tail
dependence. It is the opposite of bankable.

METHODOLOGICAL WARNING ON THE CONCENTRATION COLUMN. top5% is a RATIO, so it
moves when the denominator moves. The arm-0.5 rows look terrible partly because
their totals shrank. EX-TOP-5% IN DOLLARS IS THE HONEST METRIC -- use it.
Also: this baseline reads 119% concentration where pit_roc_sweep PJ_TAIL read
202%. Not a contradiction -- PJ_TAIL booked WILDCARD ONLY, this includes TREND,
which dilutes. Never compare concentration across different sleeve mixes.

SEPARATE FINDING, UNRELATED TO WITHDRAWALS, NEEDS ITS OWN TEST:
(5.0, 1.0, 0.30) beats the baseline by +82.16 with BOTH halves positive
(+52.70 / +29.46) -- the only cell in the grid to beat live. It differs from
baseline in ONE respect: it applies TP 5R to the TREND sleeve, which lives at
3R. That is a candidate for "raise FUTURES_TREND_TP_R 3.0 -> 5.0", arrived at
incidentally, and it should be tested deliberately before anyone believes it.
Do not act on an accidental cell.

DO NOT DEPLOY OFF THIS RUN. 16 cells, replay dollars, trial 16 open.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from futuresbot import shadow_ledger as shadow
from futuresbot import wildcard as W
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime
from futuresbot.trend import detect_trend_signal
from pit_ratchet import ratchet
from retention_trail_ab import resolve

CHUNK, BAR = 2000, 900
TREND_SYMS = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
TAIL = 2000
MAX_SHORT_TP_DIST = 0.50

TP_RS = (1.5, 2.0, 3.0, 5.0)
ARMS = (0.5, 1.0)
RETAINS = (0.30, 0.60)


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars over the window, NOT account P&L.")
    print("    The real account is DOWN lifetime; /report has the true figure. ***")
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
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
    syms = sorted(set(cand_syms) | set(TREND_SYMS))
    print("equity $%.2f | pool %d | floor $%.0fM per bar" % (eq0, len(cand_syms), floor / 1e6))

    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    nch = int(days * 86400 // (CHUNK * BAR)) + 1

    def fetch(s):
        parts, end = [], now
        for _ in range(nch):
            try:
                d = cl.get_klines(s, interval="Min15", start=end - CHUNK * BAR, end=end)
            except Exception:
                break
            if d is None or not len(d):
                break
            parts.append(d)
            end = int(d.index[0].timestamp()) - BAR
        if not parts:
            return s, None
        o = pd.concat(parts[::-1])
        return s, o[~o.index.duplicated(keep="first")].sort_index()

    print("fetching...")
    with ThreadPoolExecutor(max_workers=6) as p:
        frames = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 300}
    span = len(next(iter(frames.values()))) * BAR / 86400
    print("frames: %d symbols, %.0fd" % (len(frames), span))

    print("generating candidates at the LIVE trigger (entry held fixed)...")
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
        if s in TREND_SYMS:
            for i in range(400, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None and sig.side == "LONG":
                    C.append({"ts": ts[i], "sym": s, "sig": sig, "i": i,
                              "bars": bars, "kind": "TREND"})
        if s in cand_syms:
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or roll[i] < floor:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < 0.08:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                if sig is not None:
                    C.append({"ts": ts[i], "sym": s, "sig": sig, "i": i,
                              "bars": bars, "kind": "WILDCARD"})
    C.sort(key=lambda x: x["ts"])
    print("candidates: %d" % len(C))

    win_s = 7 * 86400
    n_win = max(1, int(span // 7))
    mid = n_win // 2

    def resolve_all(tp_r_of, trail):
        res = {}
        for idx, x in enumerate(C):
            sig = x["sig"]
            entry = float(sig.entry_price)
            sl = float(sig.sl_price)
            slf = abs(entry - sl) / entry if entry else 0.0
            tr = tp_r_of(x)
            dist = tr * slf
            if sig.side == "SHORT" and dist >= MAX_SHORT_TP_DIST:
                dist = MAX_SHORT_TP_DIST
            tp = entry * (1 + dist) if sig.side == "LONG" else entry * (1 - dist)
            # DEFECT FIXED 2026-08-25: the nominal tr was passed to resolve even
            # when the SHORT clamp had cut the TP price back to 0.50. That paid
            # a clamped short's TP hit as +5R while its reachable target was
            # worth far less, inflating every high-TP cell and manufacturing the
            # phantom +82.16 "raise TREND_TP_R" finding (refuted by
            # tools/pit_trend_tp.py: the real number is +0.72). Credit the
            # target the price can actually reach.
            tr_eff = (dist / slf) if slf > 0 else tr
            row = {"entry": entry, "sl": sl, "tp": tp, "side": sig.side}
            g = resolve(x["bars"], x["i"], entry, sl, tp, tr_eff, sig.side,
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), trail,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is not None:
                res[idx] = g
        return res

    def book(res, k_lo=0, k_hi=None):
        tot, trades = 0.0, []
        pos = 0
        for k in range(k_lo, n_win if k_hi is None else k_hi):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            wcl, trl, per, wt = [], [], {}, 0.0
            for idx, x in enumerate(C):
                if not (lo_t <= x["ts"] < hi_t) or idx not in res:
                    continue
                wcl[:] = [q for q in wcl if q > x["ts"]]
                trl[:] = [q for q in trl if q > x["ts"]]
                per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
                bk = trl if x["kind"] == "TREND" else wcl
                cap = 2 if x["kind"] == "TREND" else 3
                if per[x["sym"]] or len(bk) >= cap:
                    continue
                g = res[idx]
                bk.append(g[1])
                per[x["sym"]].append(g[1])
                d = g[0] * eq0 * 0.12 * float(x["sig"].sl_margin_pct) / 100.0
                wt += d
                trades.append((float(g[0]), d))
            tot += wt
            pos += 1 if wt > 0 else 0
        return tot, trades, pos

    def profile(trades):
        n = len(trades)
        if not n:
            return 0, 0.0, 0.0, 0.0
        ds = sorted([t[1] for t in trades], reverse=True)
        tot = sum(ds)
        k5 = max(1, n // 20)
        top5 = sum(ds[:k5])
        win = 100.0 * sum(1 for t in trades if t[0] > 0) / n
        conc = 100.0 * top5 / tot if tot else float("nan")
        return n, win, conc, tot - top5

    # BASELINE: true live config, per-sleeve TP.
    live_trail = ratchet(3.0, 0.75, base=0.30, arm=1.0)
    bres = resolve_all(lambda x: shadow.signal_tp_r(x["sig"]), live_trail)
    b, btr, bpos = book(bres)
    br = book(bres, 0, mid)[0]
    bo = book(bres, mid, n_win)[0]
    bn, bwin, bconc, bex = profile(btr)
    print("")
    print("LIVE BASELINE (wildcard 5R / trend 3R, arm 1.0, retain 0.30)")
    print("  %+.2f over %d trades | %d/%d positive weeks | win %.1f%% | "
          "top5%% = %.0f%% of P&L | ex-top5%% %+.2f" % (b, bn, bpos, n_win, bwin, bconc, bex))
    print("")
    print("*** MULTIPLICITY: 16 cells. Best-of-16 finds winners by chance. ***")
    print("")
    print("%5s %5s %7s %10s %9s %7s %7s %8s %10s %9s %9s"
          % ("TP_R", "arm", "retain", "net $", "vs live", "trades", "win%",
             "top5%", "ex-top5%", "recent", "older"))
    rows = []
    for tp_r in TP_RS:
        for arm in ARMS:
            for ret in RETAINS:
                trail = ratchet(3.0, 0.75, base=ret, arm=arm)
                res = resolve_all(lambda x, t=tp_r: t, trail)
                tot, tr, pos = book(res)
                r = book(res, 0, mid)[0] - br
                o = book(res, mid, n_win)[0] - bo
                n, win, conc, ex = profile(tr)
                print("%5.1f %5.1f %7.2f %+10.2f %+9.2f %7d %6.1f%% %7.0f%% %+10.2f %+9.2f %+9.2f"
                      % (tp_r, arm, ret, tot, tot - b, n, win, conc, ex, r, o))
                rows.append({"tp_r": tp_r, "arm": arm, "ret": ret, "tot": tot,
                             "d": tot - b, "win": win, "conc": conc, "ex": ex,
                             "r": r, "o": o, "n": n})

    print("")
    print("THE OPERATOR'S TRADE-OFF -- cells ranked by CONCENTRATION, not dollars.")
    print("A bankable book is a LOW top5%% number. What does each one cost?")
    print("%5s %5s %7s %8s %10s %9s" % ("TP_R", "arm", "retain", "top5%", "cost $", "win%"))
    for e in sorted(rows, key=lambda e: e["conc"])[:6]:
        print("%5.1f %5.1f %7.2f %7.0f%% %+10.2f %8.1f%%"
              % (e["tp_r"], e["arm"], e["ret"], e["conc"], e["d"], e["win"]))
    print("")
    print("baseline concentration %.0f%% at win %.1f%%" % (bconc, bwin))
    print("Cost is in REPLAY dollars over %.0fd; levels are inflated, so read the" % span)
    print("RELATIVE cost against the %+.2f baseline, not the absolute figure." % b)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
