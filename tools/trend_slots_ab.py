"""How many slots should the big-3 TREND sleeve get?

    railway run --service Futures-bot python tools/trend_slots_ab.py

The sleeve trades three symbols and already refuses one it is holding, so slots
cap out at 3 and "3 slots" means literally "one per big-3 name".

Uses the SHIPPED detect_trend_signal, the live convex exits, live sizing and
funding — the only variable is the slot count.

WHY THIS IS NOT JUST A P&L QUESTION. BTC, ETH and SOL move together. Three
concurrent longs is close to three times the same bet, which is a different
proposition from the wildcard's small-cap band where names are idiosyncratic. So
this reports concentration alongside return: how often the book actually held 2
or 3 at once, the realised correlation of those overlaps, and the worst
peak-to-trough of the equity path each setting produced. A slot count that adds
return AND adds drawdown proportionally has added leverage, not edge.

Read-only. Places nothing.

Env: TS_SPAN_D (56) TS_WINDOW_D (7) TS_MAX_SLOTS (3)
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
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime
from futuresbot.trend import detect_trend_signal, lookback_bars, trend_symbols

CHUNK, BAR = 2000, 900


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
    span_d, win_d = _env("TS_SPAN_D", 56), _env("TS_WINDOW_D", 7)
    max_slots = int(_env("TS_MAX_SLOTS", 3))
    eq = rt._last_known_equity() or 140.0
    now = int(time.time())
    syms = list(trend_symbols())
    print(f"equity ${eq:.2f} | universe {', '.join(s.replace('_USDT','') for s in syms)} "
          f"| span {span_d:.0f}d | lookback {lookback_bars()} bars")

    nch = int((span_d * 86400) // (CHUNK * BAR)) + 1

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

    with ThreadPoolExecutor(max_workers=4) as p:
        F = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) > 400}
    n_bars = len(next(iter(F.values())))
    print(f"frames: {len(F)} symbols, {n_bars} bars ({n_bars * BAR / 86400:.0f}d)")
    fund = {s: rt._funding_settlements(s) for s in F}

    C = {}
    for s, df in F.items():
        C[s] = {"c": [float(x) for x in df["close"]], "h": [float(x) for x in df["high"]],
                "l": [float(x) for x in df["low"]],
                "t": [float(x.timestamp()) for x in df.index], "df": df}

    # 24h return correlation across the big 3 — the concentration question in
    # one number, computed before any slot logic.
    rets = {}
    for s, d in C.items():
        c = d["c"]
        rets[s] = [c[i] / c[i - 96] - 1.0 for i in range(96, len(c))]
    keys = list(rets)
    print("\n24h-return correlation (the reason slot count is a risk question):")
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = rets[keys[i]], rets[keys[j]]
            n = min(len(a), len(b))
            a, b = a[-n:], b[-n:]
            ma, mb = sum(a) / n, sum(b) / n
            cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
            va = sum((x - ma) ** 2 for x in a) ** 0.5
            vb = sum((y - mb) ** 2 for y in b) ** 0.5
            r = cov / (va * vb) if va and vb else 0.0
            print(f"  {keys[i].replace('_USDT',''):5s} vs {keys[j].replace('_USDT',''):5s}  "
                  f"r = {r:+.3f}")

    print("\ngenerating candidates with the SHIPPED detector...")
    cands = []
    for s, d in C.items():
        df = d["df"]
        for i in range(400, len(d["c"]) + 1):
            sig = detect_trend_signal(df.iloc[:i], s)
            if sig is not None:
                cands.append((d["t"][i - 1], s, sig))
    cands.sort(key=lambda x: x[0])
    print(f"signals over {span_d:.0f}d: {len(cands)}")

    def run(slots, lo_ts, hi_ts):
        openq, live = {}, []          # symbol -> exit_ts ; list of (exit_ts, sym)
        taken = wins = blocked = 0
        net = 0.0
        events = []                   # (ts, +/-1) for concurrency tracking
        pnl_path = []
        for ts, s, sig in cands:
            if not (lo_ts <= ts < hi_ts):
                continue
            live[:] = [x for x in live if x[0] > ts]
            if openq.get(s, 0) > ts:
                continue
            if len(live) >= slots:
                blocked += 1
                continue
            row = shadow.candidate_row(sig, sleeve="TREND", reject_reason="ab")
            row["ts"] = ts
            done = shadow.resolve_outcome(row, list(zip(C[s]["t"], C[s]["h"], C[s]["l"], C[s]["c"])),
                                          hi_ts, horizon_s=shadow.CONVEX_HORIZON_S, convex=True)
            if done is None:
                continue
            u = shadow.net_usd(done, eq, funding_r=shadow.funding_cost_r(done, fund.get(s) or []))
            if u is None:
                continue
            exit_ts = float(done.get("resolved_ts") or ts)
            taken += 1
            net += u
            wins += 1 if u > 0 else 0
            openq[s] = exit_ts
            live.append((exit_ts, s))
            events.append((ts, 1))
            events.append((exit_ts, -1))
            pnl_path.append((exit_ts, u))
        # peak concurrency, and how much of the window was spent at each level
        events.sort()
        cur = peak = 0
        held = {1: 0.0, 2: 0.0, 3: 0.0}
        prev = None
        for ts, d in events:
            if prev is not None and cur > 0:
                held[min(cur, 3)] = held.get(min(cur, 3), 0.0) + (ts - prev)
            cur += d
            peak = max(peak, cur)
            prev = ts
        # equity path drawdown, ordered by exit
        pnl_path.sort()
        run_eq, peak_eq, dd = 0.0, 0.0, 0.0
        for _ts, u in pnl_path:
            run_eq += u
            peak_eq = max(peak_eq, run_eq)
            dd = min(dd, run_eq - peak_eq)
        return {"taken": taken, "net": net, "wins": wins, "blocked": blocked,
                "peak": peak, "held": held, "dd": dd}

    print(f"\n{'slots':>6} {'net $':>9} {'trades':>7} {'win%':>6} {'blocked':>8} "
          f"{'maxDD $':>8} {'peak concur':>12} {'hrs 2+':>7} {'hrs 3':>6} {'wins/8':>7}")
    results = {}
    for slots in range(1, max_slots + 1):
        tot = trades = wins = blocked = 0.0
        dd_worst = 0.0
        peak = 0
        h2 = h3 = 0.0
        pos_windows = 0
        for k in range(int(span_d // win_d)):
            hi = now - k * win_d * 86400
            lo = hi - win_d * 86400
            r = run(slots, lo, hi)
            tot += r["net"]
            trades += r["taken"]
            wins += r["wins"]
            blocked += r["blocked"]
            dd_worst = min(dd_worst, r["dd"])
            peak = max(peak, r["peak"])
            h2 += (r["held"].get(2, 0.0) + r["held"].get(3, 0.0)) / 3600.0
            h3 += r["held"].get(3, 0.0) / 3600.0
            pos_windows += 1 if r["net"] > 0 else 0
        results[slots] = tot
        print(f"{slots:6d} {tot:+9.2f} {int(trades):7d} "
              f"{(100*wins/trades if trades else 0):5.1f}% {int(blocked):8d} "
              f"{dd_worst:8.2f} {peak:12d} {h2:7.0f} {h3:6.0f} {pos_windows:4d}/8")

    print("\nmarginal value of each extra slot:")
    for slots in range(2, max_slots + 1):
        d = results[slots] - results[slots - 1]
        print(f"  slot {slots}: {d:+.2f}  ({d / max(1e-9, abs(results[1])) * 100:+.0f}% of the 1-slot base)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
