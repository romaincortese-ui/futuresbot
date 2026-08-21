"""What does the retention trail cost in a BIG-MOVE week, up or down?

    railway run --service Futures-bot python tools/trail_bigmove_windows.py

The 60-day sweep put tiered-vs-live at about +$15, i.e. single digits per month.
That window was mostly FLAT, so it cannot answer the question that matters right
now: if BTC/ETH/SOL run another 25% — or crash 25% — over the next one to two
weeks, is the trail still worth single digits, or does it become the largest
line item in the book?

Method: replay the real book across many disjoint 7-day windows, label each
window by BTC's move over it, and report the tiered-minus-live delta PER WINDOW.
Then bucket by the size and sign of the move. If the delta scales with market
movement, the flat-window estimate is a floor, not a forecast — and that is a
different decision.

Both arms share candidates, slots, funding and the point-in-time turnover floor;
only the trail floor differs. The resolver is the one validated against the
shipped resolve_outcome (125/125, max diff 0.0005R).

RESULT, 2026-08-21 — 43 symbols, 188 days, 25 disjoint 7d windows, 522 signals.
THE ANSWER IS NO, AND IT REVERSES THE 60-DAY FINDING.

    bucket            weeks   live $  tiered $   delta $   per wk
    UP   >= +20%          1   +43.05    +45.92     +2.87    +2.87
    UP   +10..20%         0       --        --        --       --
    FLAT -10..+10%       23   +79.75    +71.24     -8.51    -0.37
    DOWN -10..-20%        1   +14.32    +15.85     +1.54    +1.54
    DOWN <= -20%          0       --        --        --       --

    TOTAL over 188 days: tiered is -$4.09 against the live flat rule.

Two things fall out.

1. BIG MOVES DO NOT SCALE THE EFFECT. The +23.5% week is worth +$2.87 and the
   -17.5% week +$1.54. Two such weeks back to back is roughly +$4.4 -- still
   single digits, not a step change. The trail is a SMALL effect in every regime
   measured, including the violent ones.

2. THE 60-DAY +$15 DOES NOT SURVIVE. Over the full 188 days tiered is NEGATIVE,
   and the FLAT bucket -- 23 of 25 weeks, where the bot spends nearly all its
   life -- runs -$0.37/week. The 60-day window was the most recent one, and it
   happened to flatter tiered.

MECHANISM, which also explains why the original 444-entry study found higher
retention monotonically worse: a higher floor exits EARLIER on a trade that dips
and then recovers. Tiered books 0.50 x peak instead of 0.30 x peak, and the floor
is live continuously -- so a position that pulls back to that level and would
have run to 5R gets cut instead. On a convex sleeve where runners pay for
everything, cutting one runner costs more than protecting several faders earns.
The single worst window (-$15.11 on 9 trades) is exactly that.

Noise check, stated so the result is not oversold in the other direction: two
windows (-15.11 and -7.51) carry most of the deficit, and stripping them leaves
tiered around +$18. The effect is noise-dominated whichever way it is read --
which is itself the finding. There is no reliable money here.

Read-only. Places nothing.

Env: BW_DAYS (180) BW_SYMS (40) BW_SLOTS (3)
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


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, n_syms, slots = _env("BW_DAYS", 180), int(_env("BW_SYMS", 40)), int(_env("BW_SLOTS", 3))
    eq = rt._last_known_equity() or 157.0
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
    print(f"equity ${eq:.2f} | {len(F)} symbols | {span_d:.0f}d | {slots} slots")

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

    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))
    print("generating candidates with the SHIPPED detectors...")
    cands = []
    for s, d in C.items():
        c, turn, ts, df = d["c"], d["turn"], d["t"], d["df"]
        bars = list(zip(d["t"], d["h"], d["l"], d["c"]))
        if s in TREND_SYMS:
            for i in range(400, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None and sig.side == "LONG":
                    cands.append((ts[i], s, sig, i, bars))
        if s == "BTC_USDT":
            continue
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or turn[i] < min_turn:
                continue
            if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                continue
            sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
            if sig is not None:
                cands.append((ts[i], s, sig, i, bars))
    cands.sort(key=lambda x: x[0])
    print(f"signals: {len(cands)}")

    btc_c, btc_t = C["BTC_USDT"]["c"], C["BTC_USDT"]["t"]

    def btc_move(lo, hi):
        a = min(range(len(btc_t)), key=lambda i: abs(btc_t[i] - lo))
        b = min(range(len(btc_t)), key=lambda i: abs(btc_t[i] - hi))
        return (btc_c[b] / btc_c[a] - 1.0) if btc_c[a] > 0 else 0.0

    def run_window(floor_fn, lo, hi):
        live_slots, per = [], {}
        tot = 0.0
        n = 0
        for ts, sym, sig, i, bars in cands:
            if not (lo <= ts < hi):
                continue
            live_slots[:] = [x for x in live_slots if x > ts]
            per[sym] = [x for x in per.get(sym, []) if x > ts]
            if per[sym] or len(live_slots) >= slots:
                continue
            row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
                   "tp": float(sig.tp_price), "side": sig.side}
            cr = shadow.cost_r(row)
            got = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                          shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                          cr, floor_fn, float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if got is None:
                continue
            r_net, exit_ts, _k = got
            live_slots.append(exit_ts)
            per[sym].append(exit_ts)
            tot += r_net * eq * 0.12 * float(sig.sl_margin_pct) / 100.0
            n += 1
        return tot, n

    flat = make_floor("flat", 0.30, 1.0)
    tier = make_floor("tiered", 0.0, 1.0)
    win_s = 7 * 86400
    n_win = int(span_d // 7)
    rows = []
    for k in range(n_win):
        hi = now - k * win_s
        lo = hi - win_s
        mv = btc_move(lo, hi)
        L, nl = run_window(flat, lo, hi)
        T, _nt = run_window(tier, lo, hi)
        if nl == 0:
            continue
        rows.append((mv, L, T, T - L, nl))

    print(f"\n{'BTC 7d':>8} {'trades':>7} {'live $':>9} {'tiered $':>9} {'delta $':>9}")
    for mv, L, T, d, n in sorted(rows, key=lambda r: -r[0]):
        print(f"{mv*100:+7.1f}% {n:7d} {L:+9.2f} {T:+9.2f} {d:+9.2f}")

    print("\n=== BUCKETED BY THE SIZE AND SIGN OF THE MOVE ===")
    print(f"{'bucket':<20} {'weeks':>6} {'live $':>9} {'tiered $':>9} {'delta $':>9} {'per wk':>8}")
    buckets = [("UP   >= +20%", lambda m: m >= 0.20),
               ("UP   +10..20%", lambda m: 0.10 <= m < 0.20),
               ("FLAT -10..+10%", lambda m: -0.10 < m < 0.10),
               ("DOWN -10..-20%", lambda m: -0.20 < m <= -0.10),
               ("DOWN <= -20%", lambda m: m <= -0.20)]
    for label, fn in buckets:
        sub = [r for r in rows if fn(r[0])]
        if not sub:
            print(f"{label:<20} {0:6d}        --        --        --       --")
            continue
        L = sum(r[1] for r in sub); T = sum(r[2] for r in sub); d = T - L
        print(f"{label:<20} {len(sub):6d} {L:+9.2f} {T:+9.2f} {d:+9.2f} {d/len(sub):+8.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
