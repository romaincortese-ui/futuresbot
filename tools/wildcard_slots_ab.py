"""How many slots should the WILDCARD sleeve get? Currently 2.

    railway run --service Futures-bot python tools/wildcard_slots_ab.py

Same instrument as tools/trend_slots_ab.py, pointed at a very different sleeve.
The contrast is the point:

  - TREND trades three names correlated at r=+0.914 and caps at 3 slots.
  - WILDCARD trades a small-cap band of ~40-100 idiosyncratic names, so its
    slot ceiling is a risk-budget question, not a universe one.

THERE IS A PRIOR TO BEAT. The 2026-08-15 audit read the shadow ledger's
`slot_occupied` rows — +5.36R over 17 resolved — and refused to call it evidence
for a 3rd slot, because +9.96R of that was two lottery tickets (HEI +4.99, SNXX
+4.97) and the other 15 netted -4.60R. That was the right call on 17 rows. This
replays the whole band instead, which is a far better instrument, and it should
be read as a direct test of that refusal.

Shipped detector, live convex exits, funding charged, POINT-IN-TIME turnover
floor (a symbol enters and leaves the band exactly as it did live), and the live
long/short setting. Reports return AND concentration: peak concurrency, hours
held at 2+/3+, max drawdown of the equity path, and return/DD — because a slot
count that adds return and drawdown in equal measure has added leverage, not
edge.

RESULT, 2026-08-20 — 117 band symbols, 63d, 8 windows, live LONG/SHORT config:

    slots   net $   trades  win%   maxDD   ret/DD  wins/8
      1    +49.88     86   57.0%  -28.62   1.74     6/8
      2    +80.03    140   58.6%  -32.05   2.50     6/8   <- live
      3    +95.71    166   57.8%  -35.81   2.67     6/8   (+15.68)
      4    +83.74    175   56.6%  -40.69   2.06     6/8   (-11.98)
      5/6  saturate at 4; peak concurrency never exceeds 4

A genuine PEAK at 3, not a monotone climb — 4 slots costs money AND drawdown.
Long-only peaks at 2 (+81.16, ret/DD 3.16); with shorts, 3 is best, because at
2 slots shorts crowd out longs and at 3 there is room for both.

Band correlation r=+0.211 vs the TREND sleeve's +0.83 — the structural reason a
wider cap can be safe here and not there.

DRIFT-CONTROLLED: band buy&hold was mean +10.9% / median +4.0% over the span,
yet RANDOM entry with the same sizing and exits lost -$0.378/trade long-only and
-$0.479/trade both-sides — about -$79.59 per 166 trades. The detector at 3 slots
is ~$175 per 166 trades ahead of random.

CAVEAT ON THE ABSOLUTE NUMBERS: this replay applies NO vetoes, NO min_vol skip,
NO regime size trim and NO streak throttle, so it takes ~166 trades where the
live sleeve took ~25 and earns far more than the live ledger's +$12.40. The
SLOT COMPARISON is still fair — every arm carries the same omissions — but do
not read +$95.71 as money the live bot would have made.

Read-only. Places nothing.

Env: WS_SPAN_D (56) WS_WINDOW_D (7) WS_MAX_SLOTS (6) WS_POOL_TURNOVER (1e6)
     WS_MAX_SYMS (120) WS_MIN_TURNOVER (3e6)
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from futuresbot import shadow_ledger as shadow
from futuresbot import wildcard as W
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime

CHUNK, BAR = 2000, 900


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    span_d, win_d = _env("WS_SPAN_D", 56), _env("WS_WINDOW_D", 7)
    max_slots = int(_env("WS_MAX_SLOTS", 6))
    min_turn = _env("WS_MIN_TURNOVER", W.wildcard_min_turnover_usdt())
    pool_turn = _env("WS_POOL_TURNOVER", 1e6)
    max_syms = int(_env("WS_MAX_SYMS", 120))
    eq = rt._last_known_equity() or 139.0
    now = int(time.time())
    start_t = now - int(span_d * 86400)

    tickers = cl.get_all_tickers() or []
    majors = rt._major_symbols(
        tickers, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    pool = []
    for t in tickers:
        s = str(t.get("symbol") or "")
        if not s.endswith("_USDT") or not rt._is_tradeable_crypto(s) or s in majors:
            continue
        amt = float(t.get("amount24") or 0.0)
        if amt >= pool_turn:
            pool.append((amt, s))
    pool.sort(reverse=True)
    syms = [s for _a, s in pool[:max_syms]]
    amt_today = {s: a for a, s in pool}
    print(f"equity ${eq:.2f} | wildcard band pool {len(pool)} -> studying {len(syms)} | "
          f"span {span_d:.0f}d | long_only={W.wildcard_long_only()} | "
          f"floor ${min_turn/1e6:.0f}M POINT-IN-TIME")

    nch = int((now - start_t) // (CHUNK * BAR)) + 1

    def fetch(sym):
        parts, end = [], now
        for _ in range(nch):
            try:
                df = cl.get_klines(sym, interval="Min15", start=end - CHUNK * BAR, end=end)
            except Exception:
                break
            if df is None or not len(df):
                break
            parts.append(df)
            end = int(df.index[0].timestamp()) - BAR
            if end <= start_t:
                break
        if not parts:
            return sym, None
        out = pd.concat(parts[::-1])
        return sym, out[~out.index.duplicated(keep="first")].sort_index()

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as pool_ex:
        frames = dict(pool_ex.map(fetch, syms))
    frames = {s: f for s, f in frames.items() if f is not None and len(f) >= 300}
    print(f"frames: {len(frames)} symbols in {time.time()-t0:.0f}s")
    fund = {s: rt._funding_settlements(s) for s in frames}

    C = {}
    for s, df in frames.items():
        c = [float(x) for x in df["close"]]
        v = [float(x) for x in df["volume"]]
        raw = [c[i] * v[i] for i in range(len(c))]
        tail = sum(raw[-96:])
        scale = (amt_today.get(s, 0.0) / tail) if tail > 0 else 0.0
        roll, acc = [0.0] * len(c), 0.0
        for i, x in enumerate(raw):
            acc += x
            if i >= 96:
                acc -= raw[i - 96]
            roll[i] = acc * scale
        C[s] = {"c": c, "h": [float(x) for x in df["high"]], "l": [float(x) for x in df["low"]],
                "t": [float(x.timestamp()) for x in df.index], "turn": roll, "df": df}

    # Band correlation — the contrast with TREND's r=+0.914 is the whole reason
    # a wider slot cap can be safe here and not there.
    keys = [s for s in list(C)[:40]]
    rets = {}
    for s in keys:
        c = C[s]["c"]
        rets[s] = [c[i] / c[i - 96] - 1.0 for i in range(96, len(c))]
    pairs, tot = 0, 0.0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = rets[keys[i]], rets[keys[j]]
            n = min(len(a), len(b))
            if n < 200:
                continue
            a, b = a[-n:], b[-n:]
            ma, mb = sum(a) / n, sum(b) / n
            cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
            va = sum((x - ma) ** 2 for x in a) ** 0.5
            vb = sum((y - mb) ** 2 for y in b) ** 0.5
            if va and vb:
                tot += cov / (va * vb)
                pairs += 1
    print(f"mean pairwise 24h-return correlation across {len(keys)} band names: "
          f"r = {tot/pairs:+.3f}   (TREND's big 3: +0.83 avg)")

    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))
    print("\ngenerating candidates with the SHIPPED detector...")
    cands = []
    for s, d in C.items():
        closes, turn, ts, df = d["c"], d["turn"], d["t"], d["df"]
        for i in range(250, len(closes) + 1):
            j = i - 1
            if j <= W.ROC_BARS or turn[j] < min_turn:
                continue
            if abs(closes[j] / closes[j - W.ROC_BARS] - 1.0) < min_roc:
                continue
            sig = W.detect_wildcard_signal(df.iloc[:i], s)
            if sig is not None:
                cands.append((ts[j], s, sig))
    cands.sort(key=lambda x: x[0])
    longs = sum(1 for _t, _s, g in cands if g.side == "LONG")
    print(f"signals over {span_d:.0f}d: {len(cands)}  (LONG {longs} / SHORT {len(cands)-longs})")

    def run(slots, lo, hi, sides):
        openq, live = {}, []
        taken = wins = blocked = 0
        net = 0.0
        path, ev = [], []
        for ts, s, sig in cands:
            if not (lo <= ts < hi) or sig.side not in sides:
                continue
            live[:] = [x for x in live if x > ts]
            if openq.get(s, 0) > ts:
                continue
            if len(live) >= slots:
                blocked += 1
                continue
            row = shadow.candidate_row(sig, sleeve="WILDCARD", reject_reason="ab")
            row["ts"] = ts
            done = shadow.resolve_outcome(
                row, list(zip(C[s]["t"], C[s]["h"], C[s]["l"], C[s]["c"])), hi,
                horizon_s=shadow.CONVEX_HORIZON_S, convex=True)
            if done is None:
                continue
            u = shadow.net_usd(done, eq, funding_r=shadow.funding_cost_r(done, fund.get(s) or []))
            if u is None:
                continue
            x = float(done.get("resolved_ts") or ts)
            taken += 1
            net += u
            wins += 1 if u > 0 else 0
            openq[s] = x
            live.append(x)
            path.append((x, u))
            ev.append((ts, 1))
            ev.append((x, -1))
        path.sort()
        run_eq = pk = dd = 0.0
        for _t, u in path:
            run_eq += u
            pk = max(pk, run_eq)
            dd = min(dd, run_eq - pk)
        ev.sort()
        cur = peak = 0
        held = 0.0
        prev = None
        for ts, d_ in ev:
            if prev is not None and cur >= 3:
                held += ts - prev
            cur += d_
            peak = max(peak, cur)
            prev = ts
        return {"net": net, "taken": taken, "wins": wins, "blocked": blocked,
                "dd": dd, "peak": peak, "held3": held / 3600.0}

    sides_live = ("LONG",) if W.wildcard_long_only() else ("LONG", "SHORT")
    for label, sides in (("LIVE side config", sides_live), ("LONG only", ("LONG",))):
        if label == "LONG only" and sides == sides_live:
            continue
        print(f"\n=== {label} ({'/'.join(sides)}) ===")
        print(f"{'slots':>6} {'net $':>9} {'trades':>7} {'win%':>6} {'blocked':>8} "
              f"{'maxDD $':>9} {'peak':>5} {'hrs3+':>6} {'ret/DD':>7} {'wins/8':>7}")
        prev_net = None
        for slots in range(1, max_slots + 1):
            tot_net = dd_worst = 0.0
            trades = wins = blocked = 0
            peak = 0
            held3 = 0.0
            pos = 0
            for k in range(int(span_d // win_d)):
                hi = now - k * win_d * 86400
                lo = hi - win_d * 86400
                r = run(slots, lo, hi, sides)
                tot_net += r["net"]
                trades += r["taken"]
                wins += r["wins"]
                blocked += r["blocked"]
                dd_worst = min(dd_worst, r["dd"])
                peak = max(peak, r["peak"])
                held3 += r["held3"]
                pos += 1 if r["net"] > 0 else 0
            marg = "" if prev_net is None else f"  ({tot_net - prev_net:+.2f})"
            print(f"{slots:6d} {tot_net:+9.2f} {trades:7d} "
                  f"{(100*wins/trades if trades else 0):5.1f}% {blocked:8d} "
                  f"{dd_worst:9.2f} {peak:5d} {held3:6.0f} "
                  f"{(tot_net/abs(dd_worst) if dd_worst else 0):7.2f} {pos:4d}/8{marg}")
            prev_net = tot_net
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
