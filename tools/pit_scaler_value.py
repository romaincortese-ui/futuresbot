"""Does the regime size scaler ADD value, or just add variance?

    railway run --service Futures-bot python tools/pit_scaler_value.py

WHY NOW. Trial 18 is netR +0.16 and net -$2.01. Those disagree because the four
losing trades were sized 27% larger than the eight winners (mean risk 1.928% vs
1.523%), and the sizing is the regime scaler: mean multiplier 0.840 on the
losses against 0.707 on the wins. It sized UP into the losers, the reverse of
its premise. n=12, so that is an observation and not a finding - this is the
220-day test of the premise itself.

The scaler multiplies margin by a Kaufman-efficiency reading of the traded
symbol: full size in clean trend, FUTURES_REGIME_FLOOR_MULT in chop. The claim
is that trend efficiency at entry predicts trade quality. If it does not, the
scaler is pure variance - it moves position sizes around for no expected return,
and on a fat-tailed book that is strictly harmful.

CELLS
  scaler live       floor 0.50, as running
  scaler floor 0.25 the pre-trial-18 setting
  scaler OFF        every trade the same size
  scaler INVERTED   1.5 - mult: big in chop, small in trend. If this BEATS the
                    live scaler then the signal is real but pointed the wrong
                    way, which is a different and far more actionable defect
                    than the signal being absent.

SIZE-NEUTRAL. Every cell is normalised to deploy the same TOTAL risk across the
book, so a cell cannot win merely by trading bigger. That separates SELECTION -
does efficiency predict quality - from LEVERAGE. Without it the comparison is
meaningless, which is the defect that invalidated every gate study in this repo
before 2026-08-28.

READ-ONLY.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_pool import day_key, daily_turnover, pit_majors  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

BAR, TAIL = 900, 260


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
    days, pool_n = _env("PJ_DAYS", 220), int(_env("PJ_POOL", 170))
    now = int(time.time())
    eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    lo, hi = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    floor_live = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    tp_r = _env("FUTURES_WILDCARD_TP_R", 5.0)

    tk = cl.get_all_tickers() or []
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 2e5)][:pool_n]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    frames, rep = fetch_frames(cl, cand, days=days, workers=6, min_bars=300, now_ts=now)
    print(rep)

    ROLLS, PREP = {}, {}
    for s, df in frames.items():
        cs = sizes.get(s, 0.0)
        c = [float(x) for x in df["close"]]
        v = [float(x) for x in df["volume"]]
        raw = [c[k] * v[k] * cs for k in range(len(c))]
        roll, acc = [0.0] * len(c), 0.0
        for k, x in enumerate(raw):
            acc += x
            if k >= 96:
                acc -= raw[k - 96]
            roll[k] = acc
        ts_all = [float(x.timestamp()) for x in df.index]
        ROLLS[s] = [(ts_all[k], roll[k]) for k in range(96, len(c))]
        PREP[s] = (df, list(zip(ts_all, [float(x) for x in df["high"]],
                                [float(x) for x in df["low"]], c)), roll, c)
    PIT = pit_majors(daily_turnover(ROLLS), n=band)
    fn = ratchet(3.0, 0.75, base=_env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50), arm=1.0)

    C = []
    for s, (df, bars, roll, c) in PREP.items():
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < floor_live:
                continue
            if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < 0.08:
                continue
            sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
            if sig is None:
                continue
            e, sl = float(sig.entry_price), float(sig.sl_price)
            if abs(e - sl) <= 0 or e <= 0:
                continue
            row = {"entry": e, "sl": sl, "tp": float(sig.tp_price), "side": sig.side}
            g = resolve(bars, i, e, sl, float(sig.tp_price), tp_r, sig.side,
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), fn,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is None:
                continue
            eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
            C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                      "exit_ts": float(g[1]), "day": day_key(bars[i][0]), "eff": eff})
    C.sort(key=lambda x: x["ts"])

    slots, per, TAKEN = [], {}, []
    for x in C:
        if band and x["sym"] in PIT.get(x["day"], ()):
            continue
        slots[:] = [q for q in slots if q > x["ts"]]
        per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
        if per[x["sym"]] or len(slots) >= 3:
            continue
        slots.append(x["exit_ts"])
        per[x["sym"]].append(x["exit_ts"])
        TAKEN.append(x)
    print("fills: %d\n" % len(TAKEN))
    t0, t1 = TAKEN[0]["ts"], TAKEN[-1]["ts"]

    CELLS = [
        ("scaler live (floor 0.50)",
         lambda e: regime_size_multiplier(e, lo=lo, hi=hi, floor_mult=0.50)),
        ("scaler floor 0.25",
         lambda e: regime_size_multiplier(e, lo=lo, hi=hi, floor_mult=0.25)),
        ("scaler OFF (flat)", lambda e: 1.0),
        ("scaler INVERTED",
         lambda e: 1.5 - regime_size_multiplier(e, lo=lo, hi=hi, floor_mult=0.50)),
    ]

    print("%-26s %9s %9s %9s %6s   %s"
          % ("cell", "raw $", "norm $", "ex-top5", "both?", "thirds (normalised)"))
    base_h = None
    for name, f in CELLS:
        m = [f(x["eff"]) for x in TAKEN]
        mean_m = sum(m) / len(m)
        raw = sum(x["net"] * risk_pct * eq0 * mm for x, mm in zip(TAKEN, m))
        norm = raw / mean_m
        vals = sorted((x["net"] * risk_pct * eq0 * mm / mean_m
                       for x, mm in zip(TAKEN, m)), reverse=True)
        ex5 = sum(vals[max(1, len(vals) // 20):])

        def halves(frac):
            cut = t0 + (t1 - t0) * frac
            return (sum(x["net"] * risk_pct * eq0 * mm / mean_m
                        for x, mm in zip(TAKEN, m) if x["ts"] < cut),
                    sum(x["net"] * risk_pct * eq0 * mm / mean_m
                        for x, mm in zip(TAKEN, m) if x["ts"] >= cut))

        th = []
        for k in range(3):
            a = t0 + k * (t1 - t0) / 3.0
            b = t0 + (k + 1) * (t1 - t0) / 3.0 + (1 if k == 2 else 0)
            th.append(sum(x["net"] * risk_pct * eq0 * mm / mean_m
                          for x, mm in zip(TAKEN, m) if a <= x["ts"] < b))
        hs = [halves(fr) for fr in (0.35, 0.425, 0.5, 0.575, 0.65)]
        if base_h is None:
            base_h, tag = hs, "base"
        else:
            tag = "YES" if all(h[0] - z[0] > 0 and h[1] - z[1] > 0
                               for h, z in zip(hs, base_h)) else "no"
        print("%-26s %+9.2f %+9.2f %+9.2f %6s   %+7.1f %+7.1f %+7.1f  mult %.3f"
              % (name, raw, norm, ex5, tag, th[0], th[1], th[2], mean_m))

    print("\nnorm $ = size-neutral: every cell deploys the same TOTAL risk, so this")
    print("isolates SELECTION (does efficiency predict quality?) from LEVERAGE.")
    print("If 'scaler OFF' matches the live scaler on norm $, the scaler is")
    print("moving size around for nothing. If INVERTED beats it, the signal is")
    print("real and pointed the wrong way.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
