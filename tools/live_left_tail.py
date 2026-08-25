"""The LIVE left tail, measured from real exchange fills. No replay.

WHY. Every replay in this repo fills stops AT the stop price -- no slippage, no
gap, no liquidation cascade. tools/pit_roc_sweep.py reports min -1.05R and 0.0%
of trades beyond -1.1R, while the live feature store records 13% beyond -1.1R
and a worst of -3.79R. So the instrument that produced every backtest number is
structurally blind to the failure mode that has actually cost money.

METHOD. `profitRatio` from history_positions is the realised P&L as a fraction
of margin. The convex sleeves cap designed loss at FUTURES_WILDCARD_MAX_SL_
MARGIN_PCT = 20% of margin: sizing trims LEVERAGE until sl_frac*lev*100 <= 20,
so -20% is the designed worst case for ANY convex trade regardless of its ATR.
Anything worse than -20% is therefore slippage past the intended stop, and needs
no per-trade stop price to identify -- which matters, because the feature store
lives on the Railway volume and `railway run` executes locally.

Trades tighter than the cap (low-ATR names where sl_frac*lev*100 < 20) have
their own -1R somewhere above -20%, so this UNDERCOUNTS breaches. It is a floor
on the problem, not a full census.

ERA SPLIT. PMT-era trades ran leverage 15-25 with a different stop design and
are not comparable. The convex sleeves took over 2026-07-13.

READ-ONLY. Never places or modifies an order.

RESULTS 2026-08-25 (273 closes, 2026-05-28 -> 2026-08-25).

  CONVEX ERA (since 07-13), n=76, 43 losers (57%)
    min -29.2%  p1 -29.2%  p5 -20.4%  p10 -19.8%  p25 -17.8%  p50 -5.8%
    beyond the -20% cap:  7 of 76 (9.2%)
    worse than -25%:      1 (1.3%)
    worse than -30%:      0
    DOLLARS LOST BEYOND DESIGN: -1.37 over 7 trades (avg -0.20)
    worst: BTW 07-27 at -29.2% = 1.46x design. Five of the seven breaches are
    1.00-1.07x design -- fees nudging past -20%, not slippage.

  PMT ERA (before 07-13), n=197, 118 losers (60%)
    min -67.9%  p1 -50.7%  p5 -22.9%
    beyond the -20% cap: 19 of 197 (9.6%), worse than -50%: 2 (1.0%)
    DOLLARS LOST BEYOND DESIGN: -32.82 over 19 trades (avg -1.73)
    worst: SIREN -67.9% (3.40x design), ETH lev=50 -42.4%, BTC lev=50 -40.8%

THE 20% MARGIN CAP WORKS. The catastrophic left tail is a PMT-era artifact of
leverage 15-50. Under the convex sleeves the worst outcome in 76 trades is
1.46x design and the TOTAL cost of every breach combined is $1.37. The breach
RATE is similar across eras (9.2% vs 9.6%) but the SEVERITY collapsed.

CORRECTION THIS FORCES. I argued the replays were materially flattered by
filling stops at the stop price, and that this undermined the 6h/12% comparison.
For the convex era that is WRONG BY A FACTOR OF ~25: the true cost of the
missing left tail is $1.37 over 76 trades, against a $10/run noise floor. The
replay's downside model is close enough to reality to compare cells with.

WHAT THIS DOES *NOT* SETTLE. This measures breaches of the 20% CAP, not
R-multiples. A trade whose DESIGNED stop was 10% of margin and closed at -18%
is -1.8R while sitting inside the cap and going uncounted here. The
[[futures-bot-trial8-state]] figure of "13% beyond -1.1R, worst -3.79R" is most
likely PMT-era or such a tight-stop case; distinguishing them needs the feature
store's per-trade sl_margin_pct, which lives on the Railway volume and cannot
be read via `railway run` (it executes LOCALLY with injected env). Do that from
a Telegram command or a deployed probe before treating -3.79R as convex-era.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient

CONVEX_START = 1783900808.0     # 2026-07-13 00:00 UTC (anchored to trial16 start 1787395448)
CAP = -0.20                     # designed worst case, fraction of margin


def main() -> int:
    cl = MexcFuturesClient(FuturesConfig.from_env())
    rows, page = [], 1
    while page <= 12:
        p = cl.private_get("/api/v1/private/position/list/history_positions",
                           {"page_num": page, "page_size": 100})
        d = p.get("data", {}) if isinstance(p, dict) else {}
        b = d if isinstance(d, list) else (d.get("resultList") or [])
        if not b:
            break
        rows.extend(b)
        page += 1
    seen, uniq = set(), []
    for r in rows:
        k = r.get("positionId")
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    uniq.sort(key=lambda r: float(r.get("updateTime") or 0))
    print("closes fetched: %d" % len(uniq))
    if uniq:
        print("span: %s -> %s" % (
            time.strftime("%Y-%m-%d", time.gmtime(float(uniq[0].get("updateTime") or 0) / 1000)),
            time.strftime("%Y-%m-%d", time.gmtime(float(uniq[-1].get("updateTime") or 0) / 1000))))

    def era(r):
        return float(r.get("updateTime") or 0) / 1000 >= CONVEX_START

    for label, sel in (("CONVEX ERA (since 2026-07-13)", [r for r in uniq if era(r)]),
                       ("PMT ERA (before 07-13)", [r for r in uniq if not era(r)])):
        n = len(sel)
        if not n:
            continue
        pr = [float(r.get("profitRatio") or 0.0) for r in sel]
        losers = [x for x in pr if x < 0]
        breach = [r for r in sel if float(r.get("profitRatio") or 0.0) < CAP]
        print("")
        print("=== %s : n=%d ===" % (label, n))
        print("  losers %d (%.0f%%)  winners %d" % (len(losers), 100.0 * len(losers) / n,
                                                    n - len(losers)))
        ys = sorted(pr)
        for q, lab in ((0.00, "min"), (0.01, "p1"), (0.05, "p5"), (0.10, "p10"),
                       (0.25, "p25"), (0.50, "p50")):
            print("  %-4s %+7.1f%% of margin" % (lab, 100.0 * ys[min(n - 1, int(q * n))]))
        print("  BEYOND THE -20%% DESIGNED CAP: %d of %d (%.1f%%)"
              % (len(breach), n, 100.0 * len(breach) / n))
        for lvl in (-0.25, -0.30, -0.40, -0.50, -0.75):
            k = sum(1 for x in pr if x < lvl)
            print("     worse than %+.0f%%: %3d (%.1f%%)" % (100 * lvl, k, 100.0 * k / n))
        if breach:
            excess = 0.0
            for r in breach:
                ratio = float(r.get("profitRatio") or 0.0)
                realised = float(r.get("realised") or 0.0)
                margin = abs(realised / ratio) if ratio else 0.0
                excess += (ratio - CAP) * margin        # negative = money lost past design
            print("  DOLLARS LOST BEYOND DESIGN: %+.2f over %d trades (avg %+.2f)"
                  % (excess, len(breach), excess / len(breach)))
            print("  worst breaches:")
            for r in sorted(breach, key=lambda r: float(r.get("profitRatio") or 0.0))[:8]:
                ratio = float(r.get("profitRatio") or 0.0)
                print("    %s %-14s lev=%-3s %+7.1f%% of margin  net %+7.2f  (%.2fx design)"
                      % (time.strftime("%m-%d %H:%M", time.gmtime(float(r.get("updateTime") or 0) / 1000)),
                         r.get("symbol"), r.get("leverage"), 100.0 * ratio,
                         float(r.get("realised") or 0.0), ratio / CAP))
    print("")
    print("NOTE: -20%% is the convex cap. Trades with tighter designed stops breach")
    print("their own -1R sooner, so these counts are a FLOOR on the true rate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
