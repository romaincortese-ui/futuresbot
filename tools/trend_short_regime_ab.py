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

RESULT, 2026-08-22 -- 74 symbols, 208 days, 29 weekly windows.
DO NOT ENABLE THEM UNCONDITIONALLY. The regime-gated question is UNRESOLVED.

    bucket             weeks  long-only $  both-sides $   delta $   S n
    CRASH   <= -15%        2       +13.25        +87.91    +74.66    35
    DOWN  -15..-5%         2        -1.05         +5.73     +6.78    24
    FLAT   -5..+5%        21      +303.57       +188.69   -114.88   103
    UP     +5..+15%        3       +17.73         +7.18    -10.55    16
    SURGE   >= +15%        1       +92.94        +92.94     +0.00     0
    TOTAL                 29      +426.45       +382.46    -43.99   178
      ex-best week: -91.11   half-split: recent -35.93 / older -8.06 -> BOTH NEGATIVE

    random SHORT baseline on the majors: -0.112/trade (n=600)
    CRASH   35 shorts   +74.66   +2.133/trade   edge +2.245
    DOWN    24 shorts    +6.78   +0.282/trade   edge +0.394
    FLAT   103 shorts  -114.88   -1.115/trade   edge -1.004
    UP      16 shorts   -10.55   -0.659/trade   edge -0.548

UNCONDITIONALLY THIS IS A CLEAR NO: -$43.99, negative in BOTH halves, -$91.11
ex-best. Unlike the wildcard short arm, which passed every one of those.

THE REASON IS WHERE THE SIGNALS LAND. 103 of 178 trend shorts fire in FLAT weeks
and lose -1.115 each. A 24h-extreme breakdown in a chopping market is a
whipsaw generator: the sleeve enters on a new 24h closing LOW, and in a range
that low is the bottom of the range.

AND YET THE CRASH BUCKET IS ENORMOUS: +$74.66 over 2 weeks, +2.133/trade, edge
+2.245 against a random short. The mechanism is sound -- a downtrend-following
short in an actual downtrend. Gating trend shorts on "BTC 7d < -5%" would, on
this data, capture +$81.44 and skip -$125.43.

I DO NOT KNOW WHETHER THAT GATE WORKS, AND THIS DATA CANNOT SETTLE IT. The whole
CRASH result rests on TWO weeks. Choosing the -5% threshold after seeing which
buckets paid is exactly the fit the half-split exists to catch, and with 2 crash
weeks a half-split has no power -- one week per half at best. It is recorded as
an open question, not shipped as a finding.

WHAT THIS DOES SETTLE is that the sleeve is already SAFE in a crash without
shorts: long-only it returns +$13.25 in the CRASH weeks, because its long entry
needs a new 24h closing HIGH and a crash simply does not produce one. It goes
quiet rather than losing. Downside earning is the wildcard short arm's job.

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

    def run_window(allow_trend_short, lo, hi):
        wc_live, tr_live, per = [], [], {}
        tot = 0.0
        tsn = 0
        tsp = 0.0
        for ts, sym, sig, i, bars, kind, side in cands:
            if not (lo <= ts < hi):
                continue
            if kind == "TREND" and side == "SHORT" and not allow_trend_short:
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
        L, _a, _b = run_window(False, lo, hi)
        B, tsn, tsp = run_window(True, lo, hi)
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
    print("=== 3. HALF-SPLIT ===")
    mid = n_win // 2
    dr = sum(r[4] for r in rows if r[0] < mid)
    do = sum(r[4] for r in rows if r[0] >= mid)
    print(f"  recent {dr:+8.2f} | older {do:+8.2f} -> "
          f"{'YES' if dr > 0 and do > 0 else ('no' if dr < 0 and do < 0 else 'one half only')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
