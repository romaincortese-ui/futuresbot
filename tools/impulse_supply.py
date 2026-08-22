"""When the bot goes quiet, is it the MARKET or the GATES? Places nothing.

    railway run --service Futures-bot python tools/impulse_supply.py

"Fewer open trades today, is that expected?" is not answerable from the position
count. A quiet book has two completely different causes with opposite responses:
the market stopped producing the setup (nothing to fix), or the market is
producing it and the gates are eating it (something to fix).

So this separates them. It counts, per UTC day across the whole wildcard band,
how many 15m bars actually carried the sleeve's trigger (|3h ROC| >= the live
FUTURES_WILDCARD_MIN_ROC) — the raw SUPPLY of setups, independent of every gate
downstream. Then it prints what the majors are doing, their Kaufman efficiency,
and exactly which TREND condition each of the three live symbols is failing.

RESULT, 2026-08-22 -- and it inverted the premise it was asked to check.

    day      impulse bars      of     rate
    08-13              83    2691    3.08%
    08-16             135    6624    2.04%
    08-19             230    6720    3.42%
    08-20             274    6720    4.08%
    08-21             499    6720    7.43%
    08-22             480    3150   15.24%   <- half a day in

    symbol        24h      48h      72h       7d   eff24    atr%
    BTC        -0.67%   +7.01%  +19.27%  +22.05%    0.04    0.52%
    ETH        +1.01%   +5.03%  +25.42%  +28.24%    0.03    0.74%
    XRP        +7.10%  +27.34%  +47.91%  +48.32%    0.08    1.94%
    ZEC       +21.89%  +39.02%  +54.71%  +60.53%    0.20    2.08%

The book was nearly empty on the MOST impulsive day of the ten measured -- five
times the 08-13..08-19 baseline. The market did not go quiet; it went
DIRECTIONLESS. Kaufman efficiency across the majors is 0.03-0.20, i.e. violent
churn that arrives nowhere, and all three TREND symbols sat 5-11% below their own
24h highs after the run.

That is the gates working, not failing. Efficiency <= 0.20 is precisely the band
where entries measured +0.103R and +0.019R over 1476 trades -- zero. A sleeve
that stops trading exactly where its edge is zero is behaving as designed.

Keep this distinction: IMPULSE SUPPLY (how often the trigger fires) and TREND
EFFICIENCY (whether the move goes anywhere) move independently, and a chop
regime maximises the first while killing the second.

Read-only. Places nothing.

Env: IR_DAYS (8) IR_POOL (70)
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from futuresbot import wildcard as W
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.risk_controls import trend_efficiency
from futuresbot.runtime import FuturesRuntime

DAYS = int(os.environ.get("IR_DAYS") or 8)
POOL = int(os.environ.get("IR_POOL") or 70)
BAR = 900


def main() -> int:
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    now = int(time.time())
    min_turn = W.wildcard_min_turnover_usdt()
    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    ranked = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wc = [s for a, s in ranked if s not in majors and a >= min_turn][:POOL]
    watch = ["BTC_USDT", "ETH_USDT", "XRP_USDT", "ZEC_USDT"]
    syms = sorted(set(wc) | set(watch))

    def fetch(s):
        try:
            d = cl.get_klines(s, interval="Min15", start=now - (DAYS + 1) * 96 * BAR, end=now)
        except Exception:
            return s, None
        return s, d

    with ThreadPoolExecutor(max_workers=6) as p:
        F = {s: d for s, d in p.map(fetch, syms) if d is not None and len(d) > 200}
    print(f"pool {len(wc)} alt names + big-3 | {len(F)} frames | floor ${min_turn/1e6:.0f}M "
          f"| wildcard needs |3h ROC| >= {min_roc*100:.0f}%")

    # per UTC day: how many 15m bars across the whole pool showed a 3h impulse
    days = {}
    for s in wc:
        df = F.get(s)
        if df is None:
            continue
        c = [float(x) for x in df["close"]]
        ts = [float(x.timestamp()) for x in df.index]
        for i in range(W.ROC_BARS, len(c)):
            d = time.strftime("%m-%d", time.gmtime(ts[i]))
            e = days.setdefault(d, [0, 0])
            e[1] += 1
            if abs(c[i] / c[i - W.ROC_BARS] - 1.0) >= min_roc:
                e[0] += 1

    print(f"\n{'day':<7} {'impulse bars':>13} {'of':>7} {'rate':>8}   per-day trigger supply")
    ks = sorted(days)
    for d in ks:
        hit, tot = days[d]
        rate = 100 * hit / tot if tot else 0
        bar = "#" * int(rate * 6)
        print(f"{d:<7} {hit:13d} {tot:7d} {rate:7.2f}%   {bar}")

    print(f"\n{'symbol':<8} {'24h':>8} {'48h':>8} {'72h':>8} {'7d':>8} {'eff24':>7} "
          f"{'atr%':>7}")
    for s in watch:
        df = F.get(s)
        if df is None:
            continue
        c = [float(x) for x in df["close"]]
        h = [float(x) for x in df["high"]]
        lo = [float(x) for x in df["low"]]

        def chg(n):
            return (c[-1] / c[-min(n, len(c))] - 1.0) * 100

        tr = [max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1]))
              for i in range(max(1, len(c) - 96), len(c))]
        atr = (sum(tr) / len(tr) / c[-1] * 100) if tr else 0.0
        print(f"{s.replace('_USDT',''):<8} {chg(96):+7.2f}% {chg(192):+7.2f}% "
              f"{chg(288):+7.2f}% {chg(672):+7.2f}% {trend_efficiency(c, 96):7.2f} "
              f"{atr:6.2f}%")

    print("\n--- what the TREND sleeve needs: |24h| >= 4% AND a new 24h closing extreme ---")
    for s in ("ETH_USDT", "XRP_USDT", "ZEC_USDT"):
        df = F.get(s)
        if df is None:
            continue
        c = [float(x) for x in df["close"]]
        r24 = (c[-1] / c[-97] - 1.0) * 100
        win = c[-97:]
        at_hi = c[-1] >= max(win) - 1e-12
        at_lo = c[-1] <= min(win) + 1e-12
        gap = (c[-1] / max(win) - 1.0) * 100
        print(f"  {s.replace('_USDT',''):<5} 24h {r24:+6.2f}%  "
              f"{'PASSES roc' if abs(r24) >= 4 else 'roc too small':<14} | "
              f"{'at new high' if at_hi else ('at new low' if at_lo else f'{gap:+.2f}% off the 24h high')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
