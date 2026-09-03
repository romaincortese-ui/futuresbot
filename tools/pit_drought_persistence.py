"""FORECASTING vs DETECTION. Can the bot know it is INSIDE a drought?

    railway ssh --service Futures-bot -> python tools/pit_drought_persistence.py

Reads the daily series cached by tools/pit_universe_followthrough.py, so it is
instant. Run the census first if the cache is missing.

THE DISTINCTION THIS EXISTS TO TEST. The autocorrelation in the census answered
whether yesterday predicts tomorrow - it does not (-0.188 at lag 1). The owner
then asked a sharper question: never mind forecasting, can the bot recognise
that it is CURRENTLY inside a drought? Those are different, and the second is
not answered by the first: a state can be unforecastable yet persistent enough
that recognising it has value. A drought lasting ten days is worth detecting on
day three. One lasting two days is not.

THE ANSWER, on 116 days of universe follow-through:

  A. autocorrelation at EVERY lag       lag1 -0.188 (-2.0 SE), lag3..14 ~0
  B. trailing 7d vs next 7d             -0.263
  C. below-median run lengths           mean 1.90 days, MAX 5
  D. after 1 dry day -> next day 52%    after 2 -> 58%    unconditional 50%

Detection is possible and worthless. The state does not persist long enough to
act on, and the conditional runs the WRONG WAY - after dry days conditions are
marginally BETTER, so a detector would throttle at the worst moment.

AND THE DEEPER POINT, which is why this file is worth keeping. The week that
cost the bot $40 had a universe reach-1R of 41% against a 50% baseline with a
daily sd of 22% - over 7 days that is a 1.1 STANDARD ERROR deviation. A
statistically unremarkable market produced a large P&L swing, because a 28-trade
convex book amplifies small changes in follow-through enormously:

    universe mean peak   1.66 -> 1.24   (-25%)
    bot mean peak        1.49 -> 0.95   (-36%)
    bot P&L             +$32.07 -> -$7.89

So most of this bot's P&L variance is its own sample size, not the market's.
That is not a malfunction; it is what a small convex book does. It also means
no detector can help, while more trades per unit time would - which is the one
framing the seventeen refuted regime studies never reached.

READ-ONLY.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import statistics
import sys
import time

CACHE = "/data/universe_followthrough_daily.json"


def corr(xs, ys):
    if len(xs) < 3:
        return 0.0
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sx, sy = statistics.pstdev(xs), statistics.pstdev(ys)
    if not sx or not sy:
        return 0.0
    return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / len(xs) / (sx * sy)


def main() -> int:
    try:
        d = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        print("cache missing - run tools/pit_universe_followthrough.py first")
        return 1
    daily = d["daily"]
    sig = d.get("signals") or []
    vals = [v for _, v in daily]
    med = statistics.median(vals)
    sd = statistics.pstdev(vals)
    print("daily reach-1R over %d days: mean %.0f%%  median %.0f%%  sd %.0f%%"
          % (len(daily), statistics.mean(vals), med, sd))

    print()
    print("=" * 84)
    print("A. AUTOCORRELATION AT EVERY LAG - daily may be the wrong timescale")
    print("=" * 84)
    for lag in (1, 2, 3, 5, 7, 10, 14):
        if len(vals) - lag < 20:
            continue
        c = corr(vals[:-lag], vals[lag:])
        se = 1.0 / ((len(vals) - lag) ** 0.5)
        print("  lag %2d days: %+.3f  (%.1f SE, n=%d)"
              % (lag, c, c / se, len(vals) - lag))

    print()
    print("=" * 84)
    print("B. SMOOTHED: does a trailing 7-day mean predict the NEXT 7 days?")
    print("=" * 84)
    W = 7
    roll = [statistics.mean(vals[i:i + W]) for i in range(len(vals) - W + 1)]
    if len(roll) > 2 * W:
        print("  trailing 7d vs next 7d: correlation %+.3f (n=%d)"
              % (corr(roll[:-W], roll[W:]), len(roll) - W))

    print()
    print("=" * 84)
    print("C. HOW LONG DOES A DROUGHT LAST? runs below the median")
    print("=" * 84)
    runs, cur = [], 0
    for v in vals:
        if v < med:
            cur += 1
        else:
            if cur:
                runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    c = collections.Counter(runs)
    print("  %d runs, mean length %.2f days, max %d"
          % (len(runs), statistics.mean(runs), max(runs)))
    for k in sorted(c):
        print("    %2d day(s): %2d times %s" % (k, c[k], "#" * c[k]))
    print()
    print("  A run length distribution this short and this geometric is the")
    print("  memoryless property: after N dry days the expected REMAINING length")
    print("  is still ~%.1f. Detection buys nothing from a process with no memory."
          % statistics.mean(runs))

    print()
    print("=" * 84)
    print("D. THE DECISIVE TEST: given k dry days, what comes next?")
    print("=" * 84)
    print("  %-24s %6s %10s %12s" % ("state", "n", "next day", "next 3 days"))
    for k in (1, 2, 3):
        nxt, nxt3 = [], []
        for i in range(k, len(vals) - 3):
            if all(vals[i - j - 1] < med for j in range(k)):
                nxt.append(vals[i])
                nxt3.append(statistics.mean(vals[i:i + 3]))
        if len(nxt) < 8:
            continue
        print("  after %d dry day(s)       %6d %9.0f%% %11.0f%%"
              % (k, len(nxt), statistics.mean(nxt), statistics.mean(nxt3)))
    print("  %-24s %6d %9.0f%% %11.0f%%"
          % ("unconditional", len(vals), statistics.mean(vals),
             statistics.mean(vals)))
    print()
    print("  If the conditional rows are AT or ABOVE the unconditional one, a")
    print("  detector would throttle exactly when conditions are about to improve.")

    if sig:
        now = time.time()
        print()
        print("=" * 84)
        print("E. AMPLIFICATION: how big a market move does a big P&L swing need?")
        print("=" * 84)
        for lo, hi, nm in ((now - 14 * 86400, now - 7 * 86400, "prev 7d"),
                           (now - 7 * 86400, now, "last 7d")):
            g = [z for z in sig if lo <= z["ts"] < hi]
            if not g:
                continue
            print("  %-10s %4d signals  reach1R %2.0f%%  mean peak %.2f"
                  % (nm, len(g), 100 * sum(1 for z in g if z["peak"] >= 1) / len(g),
                     statistics.mean(z["peak"] for z in g)))
        se7 = sd / (7 ** 0.5)
        print("  a 7-day window has SE %.1f points, so a week %.0f points below the"
              % (se7, se7))
        print("  %.0f%% baseline is only 1 SE. Read any weekly swing against that."
              % statistics.mean(vals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
