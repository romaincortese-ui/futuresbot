"""Joint slot + entry optimisation across BOTH live sleeves, over 188 days.

    railway run --service Futures-bot python tools/joint_slot_entry_opt.py

WHY THIS EXISTS. Every slot study so far optimised ONE sleeve in isolation:
wildcard slots against wildcard signals, trend slots against trend signals. The
live bot runs them together out of ONE balance, so "3 wildcard + 2 trend" was
never actually measured — it was two separate answers stapled together.

Worse, none of those studies modelled the MARGIN CONSTRAINT. Each entry takes
~12% of balance, so five concurrent positions is ~60% of equity and eight is
~96%. Without that cap, more slots is weakly better forever and the optimum is
an artifact. Here a trade is refused when the margin it needs is not free.

AND IT RUNS 188 DAYS, in weekly windows. The tiered-trail episode (2026-08-21)
showed a 60-day window flipping a sign that a 188-day window then reversed:
+$15 over 60d became -$4 over 188d. Short windows lie. Every number below is
reported with the count of positive weeks beside it, because a mean without a
consistency count is how the last three withdrawn proposals got made.

RESULT, 2026-08-21 — 43 symbols, 208 days, 29 weekly windows, 613 signals.
THE CURRENT SETUP IS ALREADY AT THE OPTIMUM, AND SLOTS ARE NOT THE CONSTRAINT.

1. JOINT SLOT ALLOCATION (wc 8% / trend 4%)
     wc  tr  tot     net $  trades  pos wk  margin-blocked
      2   1    3   +159.43     174   13/29        0
      2   2    4   +173.01     205   15/29        0
      3   1    4   +163.05     176   13/29        0
      3   2    5   +176.64     207   15/29        0   <- LIVE
      3   3    6   +176.64     207   15/29        0
      4   2    6   +176.64     207   15/29        0
      5   2    7   +176.64     207   15/29        0
      6   3    9   +176.64     207   15/29        0

   3/2 is the SATURATION POINT. Every larger allocation returns the identical
   +$176.64 on the identical 207 trades, because the sleeves never produce
   enough concurrent signals to fill more. The margin cap never binds ONCE in
   208 days. At the margin the 2nd TREND slot is worth 3.7x the 3rd WILDCARD
   slot (3/1 -> 3/2 is +$13.59; 2/2 -> 3/2 is +$3.63).

2. ENTRY THRESHOLDS (at 3/2 slots)
     wc roc  tr roc     net $  trades  pos wk
         6%      4%   +177.57     292   17/29
         8%      4%   +176.64     207   15/29   <- LIVE
         6%      5%   +159.29     275   17/29
         8%      5%   +158.35     190   14/29
         6%      3%   +138.01     340   15/29
         8%      3%   +137.07     255   13/29
        10%      4%   +100.49     167   14/29
        10%      5%    +82.20     150   12/29
        10%      3%    +60.92     215   12/29

   Trend 4% clearly beats 3% and 5% at every wildcard setting. Wildcard 10% is
   clearly worse (-$76). Wildcard 6% vs 8% is +$0.93 -- FAR below the ~$16
   run-to-run noise floor measured on 2026-08-21 -- so it is not a real
   difference in dollars, though 6% does buy 2 more positive weeks and 85 more
   trades.

3. THE ACTUAL CONSTRAINT IS SIGNAL SUPPLY, NOT CAPACITY.
     207 trades x 8.8h avg hold = 1,822 slot-hours used
     5 slots x 208 days         = 24,960 slot-hours available
     utilisation 7.3% -- the book sits 93% IDLE, averaging 0.36 concurrent
     positions against 5 slots.

   No slot or threshold change can help a book that empty. The levers that
   remain all ADD SIGNAL: the $3M turnover floor, the two-symbol trend
   universe, and the disabled squeeze sleeve.

Read-only. Places nothing.

Env: JS_DAYS (188) JS_SYMS (40) JS_MARGIN_CAP (0.80)
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
from retention_trail_ab import make_floor, resolve

CHUNK, BAR = 2000, 900
TREND_SYMS = ("ETH_USDT", "SOL_USDT")
LIVE_FLOOR = make_floor("flat", 0.30, 1.0)


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars over the window, NOT account P&L.")
    print("    Arms marked 'live cfg' are the live SETTINGS, not live results.")
    print("    The real account is DOWN lifetime; /report has the true figure. ***")
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, n_syms = _env("JS_DAYS", 188), int(_env("JS_SYMS", 40))
    margin_cap = _env("JS_MARGIN_CAP", 0.80)
    eq = rt._last_known_equity() or 157.0
    bal_frac = 0.12
    now = int(time.time())
    min_turn = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    band = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                   if str(t.get("symbol") or "").endswith("_USDT")
                   and rt._is_tradeable_crypto(str(t.get("symbol") or ""))
                   and str(t.get("symbol") or "") not in majors
                   and float(t.get("amount24") or 0) >= 2e6), reverse=True)
    syms = [s for _a, s in band[:n_syms]] + list(TREND_SYMS) + ["BTC_USDT"]
    amt = {s: a for a, s in band}
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

    with ThreadPoolExecutor(max_workers=8) as pool:
        F = {s: f for s, f in pool.map(fetch, syms) if f is not None and len(f) >= 400}
    span_d = len(next(iter(F.values()))) * BAR / 86400
    print(f"equity ${eq:.2f} | {len(F)} symbols | {span_d:.0f}d | "
          f"margin cap {margin_cap*100:.0f}% of equity")

    C = {}
    for s, df in F.items():
        c = [float(x) for x in df["close"]]
        v = [float(x) for x in df["volume"]]
        raw = [c[i] * v[i] for i in range(len(c))]
        tail = sum(raw[-96:])
        sc = (amt.get(s, 0.0) / tail) if tail > 0 else 0.0
        roll, acc = [0.0] * len(c), 0.0
        for i, x in enumerate(raw):
            acc += x
            if i >= 96:
                acc -= raw[i - 96]
            roll[i] = acc * sc
        C[s] = {"c": c, "h": [float(x) for x in df["high"]], "l": [float(x) for x in df["low"]],
                "t": [float(x.timestamp()) for x in df.index], "turn": roll, "df": df}

    # ---- candidates, generated ONCE per entry threshold ---------------------
    def build(wc_roc, tr_roc):
        out = []
        for s, d in C.items():
            c, turn, ts, df = d["c"], d["turn"], d["t"], d["df"]
            bars = list(zip(d["t"], d["h"], d["l"], d["c"]))
            if s in TREND_SYMS:
                os.environ["FUTURES_TREND_MIN_ROC"] = str(tr_roc)
                for i in range(400, len(c)):
                    if abs(c[i] / c[i - 96] - 1.0) < tr_roc:
                        continue
                    sig = detect_trend_signal(df.iloc[:i + 1], s)
                    if sig is not None and sig.side == "LONG":
                        out.append((ts[i], s, sig, i, bars, "TREND"))
            if s == "BTC_USDT":
                continue
            os.environ["FUTURES_WILDCARD_MIN_ROC"] = str(wc_roc)
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or turn[i] < min_turn:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < wc_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    out.append((ts[i], s, sig, i, bars, "WILDCARD"))
        out.sort(key=lambda x: x[0])
        return out

    win_s = 7 * 86400
    n_win = int(span_d // 7)

    def simulate(cands, wc_slots, tr_slots):
        """One shared book: per-sleeve slot caps AND a shared margin budget."""
        per_win = []
        for k in range(n_win):
            hi = now - k * win_s
            lo = hi - win_s
            live = []            # (exit_ts, sleeve, margin)
            per_sym = {}
            tot = 0.0
            n = 0
            blocked_margin = 0
            for ts, sym, sig, i, bars, sleeve in cands:
                if not (lo <= ts < hi):
                    continue
                live[:] = [x for x in live if x[0] > ts]
                per_sym[sym] = [x for x in per_sym.get(sym, []) if x > ts]
                if per_sym[sym]:
                    continue
                cap = wc_slots if sleeve == "WILDCARD" else tr_slots
                if sum(1 for x in live if x[1] == sleeve) >= cap:
                    continue
                margin = eq * bal_frac
                if sum(x[2] for x in live) + margin > eq * margin_cap:
                    blocked_margin += 1
                    continue
                row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
                       "tp": float(sig.tp_price), "side": sig.side}
                got = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                              shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                              shadow.cost_r(row), LIVE_FLOOR,
                              float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if got is None:
                    continue
                r_net, exit_ts, _k = got
                live.append((exit_ts, sleeve, margin))
                per_sym[sym].append(exit_ts)
                tot += r_net * eq * bal_frac * float(sig.sl_margin_pct) / 100.0
                n += 1
            per_win.append((tot, n, blocked_margin))
        net = sum(w[0] for w in per_win)
        pos = sum(1 for w in per_win if w[0] > 0)
        trades = sum(w[1] for w in per_win)
        bm = sum(w[2] for w in per_win)
        return net, trades, pos, len(per_win), bm

    # ---- 1. joint slot allocation at the live entry thresholds --------------
    base = build(0.08, 0.04)
    print(f"signals at live thresholds: {len(base)}")
    print(f"\n=== 1. JOINT SLOT ALLOCATION (wc 8% / trend 4%) ===")
    print(f"{'wc':>3} {'tr':>3} {'tot':>4} {'net $':>9} {'trades':>7} {'pos wk':>8} "
          f"{'margin-blocked':>15}")
    for wc, tr in ((2, 1), (2, 2), (3, 1), (3, 2), (3, 3), (4, 2), (5, 2), (4, 3), (6, 3)):
        net, trades, pos, nw, bm = simulate(base, wc, tr)
        star = "  <-live cfg" if (wc, tr) == (3, 2) else ""
        print(f"{wc:3d} {tr:3d} {wc+tr:4d} {net:+9.2f} {trades:7d} {pos:4d}/{nw:<3d} "
              f"{bm:15d}{star}")

    # ---- 2. entry thresholds at the best slot setting -----------------------
    print(f"\n=== 2. ENTRY THRESHOLDS (at live 3/2 slots) ===")
    print(f"{'wc roc':>7} {'tr roc':>7} {'net $':>9} {'trades':>7} {'pos wk':>8}")
    for wc_roc in (0.06, 0.08, 0.10):
        for tr_roc in (0.03, 0.04, 0.05):
            cands = build(wc_roc, tr_roc)
            net, trades, pos, nw, _bm = simulate(cands, 3, 2)
            star = "  <-live cfg" if (wc_roc, tr_roc) == (0.08, 0.04) else ""
            print(f"{wc_roc*100:6.0f}% {tr_roc*100:6.0f}% {net:+9.2f} {trades:7d} "
                  f"{pos:4d}/{nw:<3d}{star}")
    os.environ["FUTURES_WILDCARD_MIN_ROC"] = "0.08"
    os.environ["FUTURES_TREND_MIN_ROC"] = "0.04"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
