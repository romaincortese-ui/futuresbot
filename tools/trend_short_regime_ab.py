"""Should the TREND sleeve be allowed SHORTS? Asked per regime.

    railway run --service Futures-bot python tools/trend_short_regime_ab.py

`FUTURES_TREND_LONG_ONLY=1`, so in a real correction the trend sleeve does
nothing at all — its 24h-extreme entry fires on the way down too, and every one
of those signals is currently discarded (`shorts_blocked` in the scan log).

The wildcard's short arm has now measured as worth keeping
(tools/wildcard_short_regime_ab.py), and it is the ONLY thing in the book that
earns while the market falls. This asks whether the trend sleeve should carry the
same insurance on the three majors it trades.

Same method as the wildcard study: book-level A/B on shared slots by BTC regime,
a same-side random-entry baseline so "shorts made money in the down week" is not
mistaken for a detector edge, a half-split, and an ex-best figure — because a
single week carried 78% of the wildcard result and that had to be said out loud.

RESULT, 2026-08-22 -- 63 symbols, 360 days, 51 weekly windows.
NO UNCONDITIONALLY. NO ON LOOSE GATES. The deep gate is unproven, not shipped.

    bucket             weeks  long-only $  both-sides $   delta $   S n
    CRASH   <= -15%        2        +6.53        +81.20    +74.67    35
    DOWN  -15..-5%         9        -3.73        +48.07    +51.80   106
    FLAT   -5..+5%        34      +317.77       +142.71   -175.07   180
    UP     +5..+15%        5       +24.78        +11.86    -12.91    22
    SURGE   >= +15%        1       +96.83        +96.83     +0.00     0
    TOTAL                 51      +442.18       +380.67    -61.51   343
      ex-best week: -108.64     half-split: recent -80.67 / older +19.16

    random SHORT baseline on the majors: -0.173/trade (n=600)
    CRASH   35 shorts   +74.67   +2.133/trade   edge +2.306
    DOWN   106 shorts   +43.43   +0.410/trade   edge +0.583
    FLAT   180 shorts  -165.77   -0.921/trade   edge -0.748
    UP      22 shorts   -12.91   -0.587/trade   edge -0.414

The window was extended from 208d to 360d specifically to grow the down sample:
the DOWN bucket went from 2 weeks to 9. CRASH stayed at 2 — 360 days simply does
not contain more.

UNCONDITIONALLY IT IS A CLEAR NO: -$61.51, -$108.64 ex-best. 180 of 343 trend
shorts fire in FLAT weeks and lose -0.921 each, with a NEGATIVE edge against a
random short. A new 24h closing low in a range is the bottom of the range, so in
chop the entry is a whipsaw generator.

THE GATE HAD TO BE REBUILT BEFORE IT COULD BE TESTED. Bucketing a week by the
move it went on to make is fine for DESCRIBING a regime and fatal for GATING on
one: live, the bot knows only the past. The sweep below gates each signal on
BTC's return over the 7 days BEFORE it.

    gate    gated $  vs long-only   ex-best    recent     older  both halves?
     -2%    +368.34        -73.83   -120.96    -88.33    +14.49  one half only
     -5%    +394.67        -47.51    -94.63    -61.66    +14.15  one half only
     -8%    +435.92         -6.26    -49.13     +4.52    -10.77  one half only
    -12%    +479.78        +37.60    +11.82    +25.78    +11.82  YES

TWO THINGS FALL OUT, AND THEY POINT OPPOSITE WAYS.

1. LOOSE GATES ACTIVELY LOSE. "Turn shorts on when the market looks a bit weak"
   is -$73.83 at -2% and -$47.51 at -5%. This kills the intuitive version of the
   idea outright. The improvement is monotonic in gate depth, which is at least a
   coherent shape: the tighter the gate, the more it isolates a genuine downtrend
   from chop.

2. ONLY THE DEEPEST GATE PASSES, AND IT PASSES ON ALMOST NOTHING. At -12% the
   recent half is +25.78 and ex-best is +11.82 — so the recent half IS a single
   week, and the older half is the ex-best remainder. That is roughly one
   profitable episode per half. Two episodes is not evidence, and -12% is the
   most extreme threshold tested, chosen after seeing the sweep. Shipping it
   would be threshold-fitting of exactly the kind the half-split exists to catch.

NOT SHIPPED. Recorded as a PRE-REGISTERED CANDIDATE instead: if BTC does fall
>=12% over 7 days, the plan is already written down rather than improvised in the
middle of a drawdown, and the live outcome becomes the out-of-sample test.

WHAT IS SETTLED: the sleeve is already SAFE in a crash without shorts. Long-only
it returns +$6.53 through the CRASH weeks, because its entry needs a new 24h
closing HIGH and a crash does not produce one — it goes quiet rather than losing.
Earning on the downside is the wildcard short arm's job, and that arm is measured
on a far better sample (tools/wildcard_short_regime_ab.py).

Read-only. Places nothing.

Env: TS_DAYS (190) TS_POOL (70) TS_SLOTS (3) TS_TREND_SLOTS (2) TS_RANDOM (600)
"""
from __future__ import annotations

import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace as dc_replace
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
FLOOR = make_floor("flat", 0.30, 1.0)
TREND_SYMS = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")

BUCKETS = [
    ("CRASH   <= -15%", lambda m: m <= -0.15),
    ("DOWN  -15..-5%", lambda m: -0.15 < m <= -0.05),
    ("FLAT   -5..+5%", lambda m: -0.05 < m < 0.05),
    ("UP     +5..+15%", lambda m: 0.05 <= m < 0.15),
    ("SURGE   >= +15%", lambda m: m >= 0.15),
]


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
    days, pool_n = _env("TS_DAYS", 190), int(_env("TS_POOL", 70))
    slots = int(_env("TS_SLOTS", 3))
    tr_slots = int(_env("TS_TREND_SLOTS", 2))
    n_rand = int(_env("TS_RANDOM", 600))
    eq = rt._last_known_equity() or 166.0
    now = int(time.time())
    min_turn = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    ranked = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wc_syms = [s for a, s in ranked if s not in majors and a >= min_turn][:pool_n]
    syms = sorted(set(wc_syms) | set(TREND_SYMS) | {"BTC_USDT"})
    print(f"equity ${eq:.2f} | wildcard {len(wc_syms)} | trend {len(TREND_SYMS)} "
          f"| slots wc {slots} / tr {tr_slots}")

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

    with ThreadPoolExecutor(max_workers=6) as p:
        F = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 400}
    span = len(next(iter(F.values()))) * BAR / 86400
    print(f"frames: {len(F)} symbols, {span:.0f}d")

    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))
    print("generating candidates (trend BOTH sides)...")
    cands, frames = [], {}
    for s, df in F.items():
        cs = sizes.get(s, 0.0)
        c = [float(x) for x in df["close"]]
        v = [float(x) for x in df["volume"]]
        raw = [c[i] * v[i] * cs for i in range(len(c))]
        roll, acc = [0.0] * len(c), 0.0
        for i, x in enumerate(raw):
            acc += x
            if i >= 96:
                acc -= raw[i - 96]
            roll[i] = acc
        bars = list(zip([float(x.timestamp()) for x in df.index],
                        [float(x) for x in df["high"]],
                        [float(x) for x in df["low"]], c))
        ts = [b[0] for b in bars]
        frames[s] = (df, bars, ts, c)

        if s in TREND_SYMS:
            for i in range(400, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    cands.append((ts[i], s, sig, i, bars, "TREND", sig.side))
        if s in wc_syms:
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or roll[i] < min_turn:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    cands.append((ts[i], s, sig, i, bars, "WILDCARD", sig.side))
    cands.sort(key=lambda x: x[0])
    tl = sum(1 for c_ in cands if c_[5] == "TREND" and c_[6] == "LONG")
    tsh = sum(1 for c_ in cands if c_[5] == "TREND" and c_[6] == "SHORT")
    print(f"signals: {len(cands)}  (trend LONG {tl}, trend SHORT {tsh})")

    btc_c, btc_t = frames["BTC_USDT"][3], frames["BTC_USDT"][2]

    def btc_move(lo, hi):
        a = min(range(len(btc_t)), key=lambda i: abs(btc_t[i] - lo))
        b = min(range(len(btc_t)), key=lambda i: abs(btc_t[i] - hi))
        return (btc_c[b] / btc_c[a] - 1.0) if btc_c[a] > 0 else 0.0

    def score(sig, i, bars):
        row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
               "tp": float(sig.tp_price), "side": sig.side}
        g = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                    shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                    shadow.cost_r(row), FLOOR,
                    float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
        if g is None:
            return None
        r_net, ex, _k = g
        return r_net * eq * 0.12 * float(sig.sl_margin_pct) / 100.0, ex

    # TRAILING BTC return, for gating without lookahead. Bucketing a week by the
    # move it went on to make is fine for DESCRIBING regimes and fatal for
    # gating on them: live, the bot only knows the past. This is BTC's return
    # over the 7 days BEFORE each signal.
    TRAIL_BARS = 672          # 7d of 15m bars
    _bt = {int(t): k for k, t in enumerate(btc_t)}

    def btc_trailing(ts):
        k = _bt.get(int(ts))
        if k is None:
            k = min(range(len(btc_t)), key=lambda j: abs(btc_t[j] - ts))
        j = max(0, k - TRAIL_BARS)
        return (btc_c[k] / btc_c[j] - 1.0) if btc_c[j] > 0 else 0.0

    def run_window(mode, lo, hi, gate=-0.05):
        """mode: 'long_only' | 'both' | 'gated' (shorts only after a weak BTC)."""
        wc_live, tr_live, per = [], [], {}
        tot = 0.0
        tsn = 0
        tsp = 0.0
        for ts, sym, sig, i, bars, kind, side in cands:
            if not (lo <= ts < hi):
                continue
            if kind == "TREND" and side == "SHORT":
                if mode == "long_only":
                    continue
                if mode == "gated" and btc_trailing(ts) > gate:
                    continue
            wc_live[:] = [x for x in wc_live if x > ts]
            tr_live[:] = [x for x in tr_live if x > ts]
            per[sym] = [x for x in per.get(sym, []) if x > ts]
            book = tr_live if kind == "TREND" else wc_live
            cap = tr_slots if kind == "TREND" else slots
            if per[sym] or len(book) >= cap:
                continue
            got = score(sig, i, bars)
            if got is None:
                continue
            usd, ex = got
            book.append(ex)
            per[sym].append(ex)
            tot += usd
            if kind == "TREND" and side == "SHORT":
                tsn += 1
                tsp += usd
        return tot, tsn, tsp

    win_s = 7 * 86400
    n_win = max(1, int(span // 7))
    rows = []
    for k in range(n_win):
        hi = now - k * win_s
        lo = hi - win_s
        L, _a, _b = run_window("long_only", lo, hi)
        B, tsn, tsp = run_window("both", lo, hi)
        if L == 0 and B == 0:
            continue
        rows.append((k, btc_move(lo, hi), L, B, B - L, tsn, tsp))

    print()
    print("=== 1. BOOK-LEVEL: trend long-only vs trend both-sides, by regime ===")
    print(f"{'bucket':<17} {'weeks':>6} {'long-only $':>12} {'both-sides $':>13} "
          f"{'delta $':>9} {'S n':>5}")
    for label, fn in BUCKETS:
        sub = [r for r in rows if fn(r[1])]
        if not sub:
            print(f"{label:<17} {0:6d}           --            --        --     --")
            continue
        L, B = sum(r[2] for r in sub), sum(r[3] for r in sub)
        print(f"{label:<17} {len(sub):6d} {L:+12.2f} {B:+13.2f} {B-L:+9.2f} "
              f"{sum(r[5] for r in sub):5d}")
    L, B = sum(r[2] for r in rows), sum(r[3] for r in rows)
    deltas = [r[4] for r in rows]
    best = max(deltas) if deltas else 0.0
    print(f"{'TOTAL':<17} {len(rows):6d} {L:+12.2f} {B:+13.2f} {B-L:+9.2f} "
          f"{sum(r[5] for r in rows):5d}")
    print(f"  ex-best week: {sum(deltas) - best:+.2f}  (best single week {best:+.2f})")

    print()
    print("=== 2. TREND SHORTS vs a same-side random baseline ===")
    random.seed(20260822)
    templates = [c_ for c_ in cands if c_[5] == "TREND"]
    tot = cnt = 0
    tot = 0.0
    for _ in range(n_rand):
        tmpl = random.choice(templates)[2]
        s = random.choice(TREND_SYMS)
        if s not in frames:
            continue
        df, bars, ts, c = frames[s]
        i = random.randrange(400, len(c) - 1)
        e = float(c[i])
        te = float(tmpl.entry_price)
        slf = abs(te - float(tmpl.sl_price)) / te if te else 0.0
        if slf <= 0 or e <= 0:
            continue
        tp_r = shadow.signal_tp_r(tmpl)
        sig = dc_replace(tmpl, symbol=s, side="SHORT", entry_price=e,
                         sl_price=e * (1 + slf),
                         tp_price=max(e * 0.01, e * (1 - slf * tp_r)))
        got = score(sig, i, bars)
        if got is None:
            continue
        tot += got[0]
        cnt += 1
    baseline = tot / cnt if cnt else 0.0
    print(f"random SHORT baseline on the trend majors: {baseline:+.3f}/trade (n={cnt})")
    for label, fn in BUCKETS:
        sub = [r for r in rows if fn(r[1])]
        n = sum(r[5] for r in sub)
        p = sum(r[6] for r in sub)
        if not sub or n == 0:
            print(f"{label:<17}  no trend shorts taken")
            continue
        print(f"{label:<17} {n:4d} shorts  {p:+9.2f}  {p/n:+8.3f}/trade  "
              f"edge {p/n - baseline:+8.3f}")

    print()
    print("=== 3. HALF-SPLIT, unconditional shorts ===")
    mid = n_win // 2
    dr = sum(r[4] for r in rows if r[0] < mid)
    do = sum(r[4] for r in rows if r[0] >= mid)
    print(f"  recent {dr:+8.2f} | older {do:+8.2f} -> "
          f"{'YES' if dr > 0 and do > 0 else ('no' if dr < 0 and do < 0 else 'one half only')}")

    print()
    print("=== 4. GATED on TRAILING BTC (no lookahead), threshold sweep ===")
    print(f"{'gate':>8} {'gated $':>10} {'vs long-only':>13} {'ex-best':>9} "
          f"{'recent':>9} {'older':>9}  both halves?")
    base_tot = sum(r[2] for r in rows)
    for gate in (-0.02, -0.05, -0.08, -0.12):
        per_week = []
        for k in range(n_win):
            hi = now - k * win_s
            lo = hi - win_s
            G, _n, _p = run_window("gated", lo, hi, gate=gate)
            L = next((r[2] for r in rows if r[0] == k), None)
            if L is None:
                continue
            per_week.append((k, G - L))
        tot_d = sum(d for _k, d in per_week)
        best = max((d for _k, d in per_week), default=0.0)
        rec = sum(d for k, d in per_week if k < mid)
        old = sum(d for k, d in per_week if k >= mid)
        ok = "YES" if rec > 0 and old > 0 else ("no" if rec < 0 and old < 0 else "one half only")
        print(f"{gate*100:+7.0f}% {base_tot + tot_d:+10.2f} {tot_d:+13.2f} "
              f"{tot_d - best:+9.2f} {rec:+9.2f} {old:+9.2f}  {ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
