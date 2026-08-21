"""What does a real fill actually cost, as a function of 24h turnover?

    railway run --service Futures-bot python tools/depth_cost_by_turnover.py

The turnover-floor sweep says lower is monotonically better: dropping the $3M
wildcard floor to $0.5M adds ~$53 over 63 days. That is exactly the shape a
COST MODEL THAT IS TOO GENEROUS would produce, because the shipped model is
turnover-BLIND -- shadow_ledger.cost_r applies a flat 0.19% round trip to every
symbol regardless of how thin its book is.

There is already one hard counter-example on record: GPUBSC showed about $21 of
top-10 ask depth against a $16.89 entry and a 2.22% spread. If names in the
$0.5-3M band routinely look like that, the extra signal the lower floor buys is
unfillable and the +$53 is an accounting fiction.

So this measures the thing directly: walk the live order book for every symbol
in the pool, price a round trip at the notional the bot actually trades, and
report cost as a function of 24h turnover. Depth is in CONTRACTS, so every book
is converted to USDT via the symbol's own contractSize -- the same correction
that unblocked the turnover measurement.

Live-book snapshot, so it is a point-in-time read of today's liquidity, not a
history.

RESULT, 2026-08-21 -- 286 of 312 symbols priced at a $150 round trip.
THE MEDIAN IS FINE EVERYWHERE. THE TAIL IS NOT.

    bucket        n  spread bps  top10 ask $  round trip bps  unfillable
    $0.3-1M     152         4.8       20,618             0.0        0/152
    $1-2M        53         4.9       30,714             0.0        0/53
    $2-3M        15         2.7       21,465             0.0        0/15
    $3-5M        22         3.6       23,706             0.0        0/22
    $5-10M       20         2.1       62,883             0.0        0/20
    $10M+        24         2.1      167,500             0.0        0/24

At the notional this bot trades, market impact is ZERO to the first decimal in
every bucket including the thinnest, and the median spread is 2-5bps against a
19bps cost model. The book is 100x the trade. So the liquidity objection to
lowering the turnover floor -- the reason the floor exists -- does NOT hold on
the typical name.

It holds on the tail, and the tail is where GPUBSC lived:

    BASECAT   $0.40M   spread  66.7bps   top10 $ 1,096   142.8bps round trip
    TOAD      $0.79M   spread  85.9bps   top10 $   286   140.2bps
    JIMOTHY   $1.11M   spread  24.7bps   top10 $   105    84.6bps
    ALIGN     $1.04M   spread  15.8bps   top10 $   842    55.5bps
    ANSEM     $0.84M   spread  25.3bps   top10 $   320    44.3bps

Eight sub-$3M names cost 19-143bps against a 19bps model -- up to 7.5x. Two of
them (JIMOTHY, ALIGN) sit ABOVE $1M, so even a $1M floor lets them through.

THE CONCLUSION IS ABOUT THE SHAPE OF THE GATE, NOT ITS LEVEL. Turnover is a
crude proxy for the thing that actually costs money, which is spread and top-of
-book depth. A pre-entry spread veto would gate the eight bad names directly and
let the other ~220 through; a turnover floor can only trade them off against
each other. That veto is worth building IF the signal it unlocks is worth
anything -- and tools/turnover_floor_ab.py says it is not (+$7 to +$19 over 208
days, inside a ~$10 noise band). So: measured, documented, not built.

Read-only. Places nothing.

Env: DC_NOTIONAL (150) DC_POOL (120)
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from futuresbot import shadow_ledger as shadow
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def walk(levels, notional, cs):
    """Cost in bps of filling `notional` USDT against these book levels."""
    if not levels:
        return None
    best = float(levels[0][0])
    left, spend, got = notional, 0.0, 0.0
    for lv in levels:
        px, vol = float(lv[0]), float(lv[1])
        avail = px * vol * cs
        take = min(left, avail)
        spend += take
        got += take / px
        left -= take
        if left <= 0:
            break
    if left > 0 or got <= 0:
        return None          # book cannot absorb it at all
    vwap = spend / got
    return abs(vwap / best - 1.0) * 1e4


def main() -> int:
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    notional, pool_n = _env("DC_NOTIONAL", 150.0), int(_env("DC_POOL", 120))

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    pool = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                   if str(t.get("symbol") or "").endswith("_USDT")
                   and rt._is_tradeable_crypto(str(t.get("symbol") or ""))
                   and str(t.get("symbol") or "") not in majors
                   and float(t.get("amount24") or 0) >= 3e5), reverse=True)[:pool_n]
    print(f"pricing a ${notional:.0f} round trip on {len(pool)} symbols "
          f"(model assumes {shadow.COST_PCT:.2f}% = {shadow.COST_PCT*100:.0f}bps)")

    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}

    def probe(item):
        amt, sym = item
        cs = sizes.get(sym, 0.0)
        try:
            env = cl.public_get(f"/api/v1/contract/depth/{sym}", {"limit": 50}) or {}
        except Exception:
            return None
        d = env.get("data") or {}
        asks, bids = d.get("asks") or [], d.get("bids") or []
        if cs <= 0 or not asks or not bids:
            return None
        ba, bb = float(asks[0][0]), float(bids[0][0])
        spread = (ba / bb - 1.0) * 1e4 if bb > 0 else None
        ca, cb = walk(asks, notional, cs), walk(bids, notional, cs)
        depth = sum(float(l[0]) * float(l[1]) * cs for l in asks[:10])
        rt_bps = (ca + cb) if (ca is not None and cb is not None) else None
        return sym, amt, spread, depth, rt_bps

    with ThreadPoolExecutor(max_workers=6) as p:
        got = [r for r in p.map(probe, pool) if r]
    print(f"priced {len(got)}/{len(pool)}")

    buckets = [("$0.3-1M", 3e5, 1e6), ("$1-2M", 1e6, 2e6), ("$2-3M", 2e6, 3e6),
               ("$3-5M", 3e6, 5e6), ("$5-10M", 5e6, 1e7), ("$10M+", 1e7, 9e99)]
    print(f"\n{'bucket':<10} {'n':>4} {'spread bps':>11} {'top10 ask $':>12} "
          f"{'round trip bps':>15} {'unfillable':>11}")
    for label, lo, hi in buckets:
        sub = [r for r in got if lo <= r[1] < hi]
        if not sub:
            continue
        sp = sorted(r[2] for r in sub if r[2] is not None)
        dp = sorted(r[3] for r in sub)
        ok = [r[4] for r in sub if r[4] is not None]
        bad = sum(1 for r in sub if r[4] is None)
        med = lambda a: a[len(a)//2] if a else float("nan")
        tag = "  <- BELOW LIVE FLOOR" if hi <= 3e6 else ""
        print(f"{label:<10} {len(sub):4d} {med(sp):11.1f} {med(dp):12,.0f} "
              f"{med(sorted(ok)):15.1f} {bad:8d}/{len(sub):<3d}{tag}")

    print(f"\nworst 12 books in the sub-$3M band (the ones a lower floor would buy):")
    sub = sorted((r for r in got if r[1] < 3e6),
                 key=lambda r: -(r[4] if r[4] is not None else 9e9))[:12]
    for sym, amt, spread, depth, rt_bps in sub:
        cost = "UNFILLABLE" if rt_bps is None else f"{rt_bps:8.1f}bps"
        print(f"  {sym.replace('_USDT',''):<12} turn ${amt/1e6:5.2f}M  "
              f"spread {spread or 0:6.1f}bps  top10 ${depth:9,.0f}  {cost}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
