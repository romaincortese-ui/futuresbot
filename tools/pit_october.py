"""Would the TREND sleeve behave differently in October? And what would the
3% / 48h variant have done to trials 17-18?

    railway run --service Futures-bot python tools/pit_october.py

WHY THIS NEEDS ITS OWN FETCH. The 220-day replay covers late Jan to Aug 2026 and
contains no October at all, so every seasonal claim so far rests on daily/4h bars
rather than on the sleeve actually being run. This fetches Min15 around each
October separately and runs the real detector and resolver over them.

TWO CONFIGS, on identical bars:
    LIVE      trigger 4.0%, 24h clock
    VARIANT   trigger 3.0%, 48h clock   (the best joint cell, +$12.19/220d)

TWO WINDOWS:
    each of the last several OCTOBERS - the seasonal question, n = one month
                                        per year, which is the honest limit
    the TRIAL 17-18 window              - what the variant would have done to
                                        the trades that actually happened

Sizes are the live model at the CURRENT equity throughout, so the October cells
are comparable to each other rather than to the account as it was.

READ-ONLY.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

HOUR, TAIL = 3600, 300
LIVE_SET = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
CONFIGS = (("LIVE  4.0%/24h", 0.04, 24), ("VAR   3.0%/48h", 0.03, 48))


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars, NOT account P&L. ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    now = int(time.time())
    eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    lo, hi = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    tp_r = _env("FUTURES_TREND_TP_R", 3.0)
    slots = int(_env("FUTURES_TREND_MAX_POSITIONS", 2))
    fn = ratchet(3.0, 0.75, base=_env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50), arm=1.0)
    print("equity $%.2f | %d slots | TP %.1fR | long only\n" % (eq0, slots, tp_r))

    def window(label, end_ts, days, restrict_month=None):
        frames, rep = fetch_frames(cl, LIVE_SET, days=days, workers=3,
                                   min_bars=140, now_ts=int(end_ts), strict=False)
        if not frames:
            print("  %-14s no data" % label)
            return
        out = []
        for cname, min_roc, hours in CONFIGS:
            os.environ["FUTURES_TREND_MIN_ROC"] = str(min_roc)
            from futuresbot.trend import detect_trend_signal, lookback_bars
            lb = lookback_bars()
            cand = []
            for s, df in frames.items():
                c = [float(x) for x in df["close"]]
                ts_all = [float(x.timestamp()) for x in df.index]
                bars = list(zip(ts_all, [float(x) for x in df["high"]],
                                [float(x) for x in df["low"]], c))
                for i in range(lb + 40, len(c)):
                    if restrict_month is not None:
                        if dt.datetime.fromtimestamp(bars[i][0], dt.UTC).month != restrict_month:
                            continue
                    sig = detect_trend_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                    if sig is None or sig.side != "LONG":
                        continue
                    e, sl = float(sig.entry_price), float(sig.sl_price)
                    if abs(e - sl) <= 0 or e <= 0:
                        continue
                    row = {"entry": e, "sl": sl, "tp": float(sig.tp_price), "side": "LONG"}
                    g = resolve(bars, i, e, sl, float(sig.tp_price), tp_r, "LONG",
                                hours * HOUR, shadow.cost_r(row), fn,
                                float(getattr(sig, "atr_pct", 0.0) or 0.0), int(end_ts))
                    if g is None:
                        continue
                    eff = trend_efficiency(c[:i + 1],
                                           int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
                    cand.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                                 "exit_ts": float(g[1]), "kind": str(g[2]),
                                 "mult": regime_size_multiplier(eff, lo=lo, hi=hi,
                                                                floor_mult=flm)})
            cand.sort(key=lambda z: z["ts"])
            occ, per, taken = [], {}, []
            for z in cand:
                occ[:] = [q for q in occ if q > z["ts"]]
                per[z["sym"]] = [q for q in per.get(z["sym"], []) if q > z["ts"]]
                if per[z["sym"]] or len(occ) >= slots:
                    continue
                occ.append(z["exit_ts"])
                per[z["sym"]].append(z["exit_ts"])
                taken.append(z)
            if os.environ.get("OCT_DETAIL"):
                print("      %-14s detected %d LONG signals -> slot book took %d (%.0f%%)"
                      % (cname, len(cand), len(taken),
                         100.0 * len(taken) / max(1, len(cand))))
            u = sum(z["net"] * risk_pct * eq0 * z["mult"] for z in taken)
            R = sum(z["net"] for z in taken)
            w = (100.0 * sum(1 for z in taken if z["net"] > 0) / len(taken)) if taken else 0
            out.append((cname, len(taken), u, R, w))
        a, b = out[0], out[1]
        print("  %-14s LIVE %3d fills $%+8.2f (%+6.2fR, %2.0f%%w)  |  VAR %3d fills "
              "$%+8.2f (%+6.2fR, %2.0f%%w)  |  delta $%+7.2f"
              % (label, a[1], a[2], a[3], a[4], b[1], b[2], b[3], b[4], b[2] - a[2]))

    print("=== OCTOBERS (Min15, one fetch per year) ===")
    for yr in (2021, 2022, 2023, 2024, 2025):
        end = dt.datetime(yr, 11, 3, tzinfo=dt.UTC).timestamp()
        if end > now:
            continue
        window("Oct %d" % yr, end, 45, restrict_month=10)

    print("\n=== SEPTEMBERS, for contrast ===")
    for yr in (2021, 2022, 2023, 2024, 2025):
        end = dt.datetime(yr, 10, 3, tzinfo=dt.UTC).timestamp()
        if end > now:
            continue
        window("Sep %d" % yr, end, 45, restrict_month=9)

    print("\n=== THE LIVE TRIAL WINDOW (trials 17-18, from 2026-08-27) ===")
    window("trial 17-18", now, 12)
    print("\nOne October per year is the honest ceiling on this question. Read the")
    print("delta column for consistency of SIGN across years, not for its size.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
