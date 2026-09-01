"""Is calendar month a factor for THIS bot? Three separate questions.

    railway run --service Futures-bot python tools/pit_seasonality.py

THE FOLK CLAIM. September is flat, October ("Uptober") trends hard. Widely
repeated; rarely measured with the sample size stated.

THREE QUESTIONS, deliberately kept apart because they have different answers:

  1. IS THE SEASONALITY REAL IN THE MARKET? Monthly BTC returns by calendar
     month, with n per month printed next to every figure. Twelve years of
     history is n=12 per month, which is a small sample for a monthly effect
     even before noting that the 2013 and 2025 markets are not the same object.

  2. DOES IT TRANSMIT TO THIS BOT'S EDGE? The bot is NOT directional on the
     market. The wildcard takes both sides on alts; the trend sleeve is long-
     only on three majors. A flat month does not invert its edge - it starves
     it of SIGNALS, because nothing clears an 8%/3h trigger. That was visible
     live on 2026-09-01: "roc_below_min 33-35" and entries fell to ~1.7/day.
     So the transmission channel is COUNT, not direction, and the right
     seasonal variable is realised volatility and trendiness, not return.

  3. WOULD ACTING ON IT PAY? The bot already carries a live regime detector -
     the Kaufman-efficiency size scaler, computed per symbol on a 6h window and
     updated every entry. A calendar prior is a strictly cruder version of a
     measurement it already takes continuously. This prints both so the
     comparison is explicit rather than asserted.

Reported with n per cell throughout, because the whole point of the exercise is
that a monthly claim rests on a dozen observations.

READ-ONLY.
"""
from __future__ import annotations

import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import trend_efficiency  # noqa: E402

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    cl = MexcFuturesClient(FuturesConfig.from_env())
    now = int(time.time())
    sym = os.environ.get("SEASON_SYMBOL", "BTC_USDT")
    print("*** MARKET DATA, not bot P&L. %s daily bars. ***\n" % sym)

    # walk back in 1900-bar chunks of Day candles for as much history as exists
    parts, end = [], now
    for _ in range(12):
        try:
            d = cl.get_klines(sym, interval=os.environ.get("SEASON_INTERVAL", "Day1"), start=end - 1900 * 86400, end=end)
        except Exception as exc:
            print("kline fetch stopped: %s" % exc)
            break
        if d is None or not len(d):
            break
        parts.append(d)
        end = int(d.index[0].timestamp()) - 86400
    if not parts:
        print("no daily history available")
        return 0
    import pandas as pd
    df = pd.concat(parts[::-1])
    df = df[~df.index.duplicated(keep="first")].sort_index()
    print("history: %d daily bars, %s -> %s (%.1f years)\n"
          % (len(df), df.index[0].date(), df.index[-1].date(), len(df) / 365.25))

    close = [float(x) for x in df["close"]]
    idx = list(df.index)

    # --- 1. monthly RETURN by calendar month -----------------------------
    by_month = defaultdict(list)
    cur_m, start_px, start_i = None, None, None
    for i, ts in enumerate(idx):
        key = (ts.year, ts.month)
        if cur_m is None:
            cur_m, start_px, start_i = key, close[i], i
        elif key != cur_m:
            by_month[cur_m[1]].append((close[i - 1] / start_px - 1.0, cur_m[0]))
            cur_m, start_px, start_i = key, close[i], i
    print("=== 1. MONTHLY RETURN by calendar month ===")
    print("%-5s %4s %9s %9s %9s %7s   %s" % ("month", "n", "mean %", "median %",
                                             "sd %", "win%", "years"))
    for m in range(1, 13):
        v = by_month.get(m, [])
        if not v:
            continue
        rs = [x[0] * 100 for x in v]
        print("%-5s %4d %+9.2f %+9.2f %9.2f %6.0f%%   %s"
              % (MONTHS[m - 1], len(rs), statistics.mean(rs), statistics.median(rs),
                 statistics.pstdev(rs) if len(rs) > 1 else 0.0,
                 100 * sum(1 for r in rs if r > 0) / len(rs),
                 ",".join(str(x[1])[2:] for x in v)))

    # --- 2. what the bot actually cares about: volatility and trendiness ---
    print("\n=== 2. WHAT THE BOT FEEDS ON: daily volatility and trend efficiency ===")
    print("    (the sleeve needs 8%/3h bursts; direction is not the input)")
    vol_m, eff_m, big_m = defaultdict(list), defaultdict(list), defaultdict(list)
    for i in range(21, len(close)):
        m = idx[i].month
        rets = [close[k] / close[k - 1] - 1.0 for k in range(i - 20, i + 1)]
        vol_m[m].append(statistics.pstdev(rets) * 100)
        eff_m[m].append(trend_efficiency(close[:i + 1], 20))
        big_m[m].append(1.0 if abs(close[i] / close[i - 1] - 1.0) >= 0.04 else 0.0)
    print("%-5s %6s %11s %11s %13s" % ("month", "n days", "daily vol %", "trend eff",
                                       ">=4% day rate"))
    for m in range(1, 13):
        if m not in vol_m:
            continue
        print("%-5s %6d %11.2f %11.3f %12.0f%%"
              % (MONTHS[m - 1], len(vol_m[m]), statistics.mean(vol_m[m]),
                 statistics.mean(eff_m[m]), 100 * statistics.mean(big_m[m])))

    # --- 3. is the effect distinguishable from noise at all? --------------
    print("\n=== 3. IS ANY OF IT DISTINGUISHABLE FROM NOISE? ===")
    allr = [x[0] * 100 for v in by_month.values() for x in v]
    gm, gsd = statistics.mean(allr), statistics.pstdev(allr)
    print("  all months pooled: mean %+.2f%%  sd %.2f%%  n=%d" % (gm, gsd, len(allr)))
    print("  %-5s %4s %9s %9s   %s" % ("month", "n", "mean %", "t-ish", "reading"))
    for m in (9, 10):
        v = [x[0] * 100 for x in by_month.get(m, [])]
        if not v:
            continue
        se = gsd / (len(v) ** 0.5)
        t = (statistics.mean(v) - gm) / se if se else 0.0
        print("  %-5s %4d %+9.2f %+9.2f   %s"
              % (MONTHS[m - 1], len(v), statistics.mean(v), t,
                 "indistinguishable from the pooled mean" if abs(t) < 2
                 else "outside 2 standard errors"))
    print("\n  A monthly claim rests on one observation per year. With sd ~%.0f%% a"
          % gsd)
    print("  month needs to differ by ~%.0f%% before %d years could detect it."
          % (2 * gsd / max(1, len(by_month.get(10, [])) ** 0.5),
             len(by_month.get(10, []))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
