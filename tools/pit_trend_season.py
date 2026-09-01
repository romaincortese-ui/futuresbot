"""Does the TREND sleeve pick up October where the wildcard cannot?

    railway run --service Futures-bot python tools/pit_trend_season.py

The wildcard needs |3h ROC| >= 8% - a burst. October has the highest monthly
return in the sample and the LOWEST daily volatility, so it starves that
trigger. But TREND fires on |24h ROC| >= 4% plus a NEW 24h CLOSING EXTREME,
which is what a slow sustained grind looks like. The owner's point.

Counted on Hour4 bars over the full available history for the three majors the
sleeve was designed on, plus the two it actually trades live. 24h = 6 bars, so
the trigger is close[-1]/close[-7]-1 >= 4% AND close[-1] > max(close[-7:-1]) -
the same shape as detect_trend_signal, at coarser resolution.

READ-ONLY. Market structure only; no P&L claim.
"""
from __future__ import annotations
import os, statistics, sys, time
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
BAR = 14400          # Hour4
PER_DAY = 6


def hist(cl, sym, chunks=9):
    import pandas as pd
    parts, end = [], int(time.time())
    for _ in range(chunks):
        try:
            d = cl.get_klines(sym, interval="Hour4", start=end - 1900 * BAR, end=end)
        except Exception:
            break
        if d is None or not len(d):
            break
        parts.append(d)
        end = int(d.index[0].timestamp()) - BAR
    if not parts:
        return None
    df = pd.concat(parts[::-1])
    return df[~df.index.duplicated(keep="first")].sort_index()


def main() -> int:
    cl = MexcFuturesClient(FuturesConfig.from_env())
    syms = (os.environ.get("TS_SYMBOLS")
            or "BTC_USDT,ETH_USDT,SOL_USDT,XRP_USDT,ZEC_USDT").split(",")
    minroc = float(os.environ.get("FUTURES_TREND_MIN_ROC") or 0.04)
    print("*** TREND trigger firings by calendar month. |24h ROC| >= %.0f%% + new"
          " 24h closing extreme ***\n" % (minroc * 100))
    fire = defaultdict(lambda: defaultdict(int))
    bars = defaultdict(lambda: defaultdict(int))
    longfire = defaultdict(lambda: defaultdict(int))
    for sym in syms:
        df = hist(cl, sym.strip())
        if df is None or len(df) < PER_DAY + 2:
            print("  %-11s no history" % sym); continue
        c = [float(x) for x in df["close"]]
        idx = list(df.index)
        n = 0
        for i in range(PER_DAY + 1, len(c)):
            m = idx[i].month
            bars[sym][m] += 1
            base = c[i - PER_DAY]
            if base <= 0:
                continue
            roc = c[i] / base - 1.0
            if abs(roc) < minroc:
                continue
            win = c[i - PER_DAY:i]
            if roc > 0 and c[i] >= max(win):
                fire[sym][m] += 1; longfire[sym][m] += 1; n += 1
            elif roc < 0 and c[i] <= min(win):
                fire[sym][m] += 1; n += 1
        print("  %-11s %5d bars, %.1f years, %d trigger firings"
              % (sym, len(c), len(c) / (PER_DAY * 365.25), n))
    print()
    print("=== FIRING RATE per calendar month (%% of 4h bars that trigger) ===")
    print("%-5s %8s %8s %8s   %s" % ("month", "all", "LONG", "SHORT", "per symbol (all)"))
    tot_b, tot_f, tot_l = defaultdict(int), defaultdict(int), defaultdict(int)
    for m in range(1, 13):
        for sym in fire:
            tot_b[m] += bars[sym][m]; tot_f[m] += fire[sym][m]; tot_l[m] += longfire[sym][m]
    for m in range(1, 13):
        if not tot_b[m]:
            continue
        per = " ".join("%s %.1f%%" % (s.split("_")[0][:4],
                                      100.0 * fire[s][m] / max(1, bars[s][m])) for s in fire)
        print("%-5s %7.2f%% %7.2f%% %7.2f%%   %s"
              % (MONTHS[m - 1], 100.0 * tot_f[m] / tot_b[m], 100.0 * tot_l[m] / tot_b[m],
                 100.0 * (tot_f[m] - tot_l[m]) / tot_b[m], per))
    rates = [(100.0 * tot_f[m] / tot_b[m], m) for m in range(1, 13) if tot_b[m]]
    rates.sort(reverse=True)
    print()
    print("busiest months: %s" % ", ".join("%s %.2f%%" % (MONTHS[m - 1], r) for r, m in rates[:3]))
    print("quietest      : %s" % ", ".join("%s %.2f%%" % (MONTHS[m - 1], r) for r, m in rates[-3:]))
    lr = [(100.0 * tot_l[m] / tot_b[m], m) for m in range(1, 13) if tot_b[m]]
    lr.sort(reverse=True)
    print("busiest for LONGS (the arm that pays): %s"
          % ", ".join("%s %.2f%%" % (MONTHS[m - 1], r) for r, m in lr[:3]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
