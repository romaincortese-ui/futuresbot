"""What does the LIVE record say, per market regime — and what loses where?

    railway run --service Futures-bot python tools/live_regime_audit.py <rows.jsonl>

Every regime claim made before this was a REPLAY: today's config applied
retroactively, unconstrained, on a survivorship-biased symbol set, taking roughly
3x the trades the live bot takes. That is the right tool for comparing two rules
against each other and the wrong one for stating what the bot actually does.

The owner pushed back on exactly that, and was right. This reads the live feature
store instead, buckets closes by BTC's TRAILING 7-day move at the time of the
close (no lookahead), and then asks the only question that matters for tuning:
inside the regime that is not working, what specifically is losing?

Regime labels use trailing data, so they LAG. A day that feels like "calm after
the storm" still classifies as SURGE while the previous week's run is inside the
window. That is a property of any implementable regime rule, not a defect of this
one, and it is the single strongest argument against per-regime parameter sets.

RESULT, 2026-08-23 -- 63 live convex closes, 2026-06-27 to 2026-08-23.

    bucket              n     net $     netR   win%   $/trade   best $
    CRASH <=-15%        0       --       --     --        --       --
    DOWN -15..-5%       0       --       --     --        --       --
    FLAT  -5..+5%      40     +7.92    +6.40    38%     +0.20    +9.83
    UP    +5..+15%      6     +0.66    +5.48    33%     +0.11    +3.47
    SURGE  >=+15%      17    +38.68   +15.15    65%     +2.28   +17.94

TWO OF FIVE REGIMES HAVE NEVER HAPPENED. In two months of live convex trading the
bot has closed ZERO trades with BTC's trailing week below -5%. "Weak in a
downturn" was a replay claim and should not have been stated as fact.

FLAT IS NOT LOSING. It is +$7.92 across 40 closes — treading water, not bleeding.
82% of all live convex P&L comes from the 17 SURGE closes, and one trade (TUT
+$17.94) is 46% of that. This is the payoff shape a convex sleeve is supposed to
have: flat in the middle, paid in the tail.

INSIDE FLAT, THE PROBLEM IS ENTRIES, NOT EXITS OR SIZING:

    by peak reached      n=36  never +1R   -$0.10   win 31%   <- 90% of them
                         n= 3  1-3R        +$2.61   win 100%
                         n= 1  >=3R        +$5.42   win 100%
    by side              SHORT n=11  +$8.89  +0.81/trade   win 27%
                         LONG  n=29  -$0.96  -0.03/trade   win 41%
    by exit              STOP  n= 8  -$9.37  -1.17/trade   win  0%
    by entry efficiency  >0.45 clean n=7  +$4.18  win 71%
                         0.20-0.45   n=6  -$1.02  win 33%

NINE OUT OF TEN FLAT-REGIME TRADES NEVER REACH +1R. They never arm the trail, so
the retention floor, the ratchet and the 5R target are all irrelevant to them —
the entire convex exit stack is dead weight on 90% of the flat book. Tuning exits
for flat markets would therefore change almost nothing. If flat is to improve it
has to happen at the ENTRY.

And the shorts carry flat: +$8.89 on 11 closes at a 27% win rate, against longs
at -$0.96 on 29. Low win rate, positive expectancy — the convex shape working as
designed, and a second independent argument for keeping the wildcard short arm.

CAVEAT THAT LIMITS ALL OF THIS: the flat sample is mostly OLD config. It contains
10 SQUEEZE closes from before the sleeve was disabled, 23 rows with no exit_kind
recorded, and 27 with no efficiency stamp. The current sleeve set has 18 live
closes and 17 of them are SURGE. There is no clean live read on the current
config in flat tape, let alone in a downturn.

Read-only. Places nothing.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient

BUCKETS = [
    ("CRASH <=-15%", lambda m: m <= -0.15),
    ("DOWN -15..-5%", lambda m: -0.15 < m <= -0.05),
    ("FLAT  -5..+5%", lambda m: -0.05 < m < 0.05),
    ("UP    +5..+15%", lambda m: 0.05 <= m < 0.15),
    ("SURGE  >=+15%", lambda m: m >= 0.15),
]


def _f(v, d=0.0):
    try:
        return float(v if v is not None else d)
    except (TypeError, ValueError):
        return d


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "rows.jsonl"
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    rows.sort(key=lambda r: _f(r.get("ts")))
    if not rows:
        print("no rows")
        return 0

    cl = MexcFuturesClient(FuturesConfig.from_env())
    now = int(time.time())
    parts, end = [], now
    for _ in range(6):
        d = cl.get_klines("BTC_USDT", interval="Min15", start=end - 2000 * 900, end=end)
        if d is None or not len(d):
            break
        parts.append(d)
        end = int(d.index[0].timestamp()) - 900
    o = pd.concat(parts[::-1])
    o = o[~o.index.duplicated(keep="first")].sort_index()
    bt = [float(x.timestamp()) for x in o.index]
    bc = [float(x) for x in o["close"]]

    def btc7(ts):
        k = min(range(len(bt)), key=lambda i: abs(bt[i] - ts))
        j = max(0, k - 672)
        return (bc[k] / bc[j] - 1.0) if bc[j] > 0 else 0.0

    for r in rows:
        r["_m"] = btc7(_f(r.get("ts")))

    print(f"LIVE convex closes: {len(rows)} | "
          f"{time.strftime('%Y-%m-%d', time.gmtime(_f(rows[0].get('ts'))))} -> "
          f"{time.strftime('%Y-%m-%d', time.gmtime(_f(rows[-1].get('ts'))))}")

    print()
    print(f"{'bucket':<16} {'n':>4} {'net $':>9} {'netR':>8} {'win%':>6} "
          f"{'$/trade':>9} {'best $':>8}")
    for lab, fn in BUCKETS:
        sub = [r for r in rows if fn(r["_m"])]
        if not sub:
            print(f"{lab:<16} {0:4d}       --       --     --        --       --")
            continue
        usd = sum(_f(r.get("pnl_usdt")) for r in sub)
        rr = sum(_f(r.get("r_multiple")) for r in sub)
        w = sum(1 for r in sub if _f(r.get("pnl_usdt")) > 0)
        best = max(_f(r.get("pnl_usdt")) for r in sub)
        print(f"{lab:<16} {len(sub):4d} {usd:+9.2f} {rr:+8.2f} {100*w/len(sub):5.0f}% "
              f"{usd/len(sub):+9.2f} {best:+8.2f}")

    # --- what loses inside the regime that is not working -----------------
    flat = [r for r in rows if -0.05 < r["_m"] < 0.05]
    print()
    print(f"=== INSIDE FLAT ({len(flat)} closes) — where does it go? ===")

    def cut(name, keyfn, order=None):
        groups = {}
        for r in flat:
            groups.setdefault(keyfn(r), []).append(r)
        print(f"\n  by {name}")
        keys = order or sorted(groups, key=lambda k: -sum(_f(x.get('pnl_usdt')) for x in groups[k]))
        for k in keys:
            sub = groups.get(k) or []
            if not sub:
                continue
            usd = sum(_f(r.get("pnl_usdt")) for r in sub)
            w = sum(1 for r in sub if _f(r.get("pnl_usdt")) > 0)
            print(f"    {str(k):<22} n={len(sub):3d}  ${usd:+7.2f}  "
                  f"{usd/len(sub):+6.2f}/trade  win {100*w/len(sub):3.0f}%")

    cut("sleeve", lambda r: str(r.get("kind") or "?"))
    cut("side", lambda r: str(r.get("side") or "?"))
    cut("exit", lambda r: str(r.get("exit_kind") or "none"))

    def eff_band(r):
        e = _f(r.get("size_efficiency"))
        if e <= 0:
            return "unknown"
        return "<=0.20 chop" if e <= 0.20 else ("0.20-0.45 mixed" if e <= 0.45 else ">0.45 clean")
    cut("entry efficiency", eff_band,
        order=["<=0.20 chop", "0.20-0.45 mixed", ">0.45 clean", "unknown"])

    def hold_band(r):
        h = _f(r.get("hold_hours"))
        return "<2h" if h < 2 else ("2-8h" if h < 8 else ("8-20h" if h < 20 else ">=20h clock"))
    cut("hold time", hold_band, order=["<2h", "2-8h", "8-20h", ">=20h clock"])

    def peak_band(r):
        p = _f(r.get("peak_r"))
        return "never +1R" if p < 1.0 else ("1-3R" if p < 3.0 else ">=3R")
    cut("peak reached", peak_band, order=["never +1R", "1-3R", ">=3R"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
