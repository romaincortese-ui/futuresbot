"""Of the trades that reach +5R, how far do they actually go?

    railway run --service Futures-bot python tools/pit_tp_reach.py

Raising the TP cap can only affect trades that REACH the old cap. Everything
else - every stop, every trail exit below 5R, every timeout - is identical. So
the honest test is not a full re-simulation but a census of the affected
population, which is what the owner asked for on 2026-09-01.

THE MECHANISM THAT MAKES IT NON-OBVIOUS. With the ratchet floor at 0.75 x peak
above 3R, a trade that peaks at P and does NOT reach the new cap banks 0.75P
instead of the old 5R:

    P = 6.00R -> 4.50R   loses 0.50R against the 5R cap
    P = 6.67R -> 5.00R   break-even
    P = 7.00R -> 7.00R   hits the new cap, gains 2.00R

So raising 5R -> 7R is a bet that trades clearing 5R keep going PAST 6.67R more
often than they stall between 5 and 6.67. This counts both populations.

Method: resolve every signal with the cap set effectively out of reach (99R) so
the trail and clock decide the exit, then record each trade's PEAK R. Trades
whose peak >= 5R are the affected set.

READ-ONLY.
"""
from __future__ import annotations
import os, sys, time
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
BAR, TAIL = 900, 260


def _env(n, d):
    try: return float(os.environ.get(n) or d)
    except (TypeError, ValueError): return float(d)


def walk_peak(bars, i0, entry, sl, side, horizon_s, arm, retain, rr, rh, cost_r, now_ts):
    """Return (peak_r, banked_r_under_trail_only) with NO tp cap binding."""
    sgn = 1.0 if side == "LONG" else -1.0
    one = abs(entry - sl)
    if one <= 0: return None
    t0 = bars[i0][0]
    peak = 0.0
    last = entry
    seen = False
    floor_min = 1.5 * cost_r
    for k in range(i0 + 1, len(bars)):
        ts, hi, lo, close = bars[k]
        if ts - t0 > horizon_s: break
        seen = True
        adverse = ((lo if sgn > 0 else hi) - entry) * sgn / one
        favour = ((hi if sgn > 0 else lo) - entry) * sgn / one
        if peak >= arm:
            frac = rh if (rr > 0 and peak >= rr) else retain
            level = max(frac * peak, floor_min)
            if level < peak and adverse <= level:
                return (peak, level - cost_r)
        if adverse <= -1.0:
            return (peak, -1.0 - cost_r)
        peak = max(peak, favour)
        last = close
    if not seen or now_ts - t0 < horizon_s: return None
    return (peak, ((last - entry) * sgn / one) - cost_r)


def main() -> int:
    cfg = FuturesConfig.from_env(); cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 220), int(_env("PJ_POOL", 170))
    now = int(time.time())
    lo_, hi_ = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    fl = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    arm = _env("FUTURES_CONVEX_TRAIL_ARM_R", 1.0)
    retain = _env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50)
    rr = _env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0)
    rh = _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75)
    print("*** peak-R census. trail arm %.1f retain %.2f ratchet %.1f->%.2f ***\n"
          % (arm, retain, rr, rh))
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
        c = [float(x) for x in df["close"]]; v = [float(x) for x in df["volume"]]
        raw = [c[k]*v[k]*cs for k in range(len(c))]
        roll, acc = [0.0]*len(c), 0.0
        for k, x in enumerate(raw):
            acc += x
            if k >= 96: acc -= raw[k-96]
            roll[k] = acc
        ts_all = [float(x.timestamp()) for x in df.index]
        ROLLS[s] = [(ts_all[k], roll[k]) for k in range(96, len(c))]
        PREP[s] = (df, list(zip(ts_all, [float(x) for x in df["high"]],
                                [float(x) for x in df["low"]], c)), roll, c)
    PIT = pit_majors(daily_turnover(ROLLS), n=band)
    peaks = []
    for s, (df, bars, roll, c) in PREP.items():
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < fl: continue
            if abs(c[i]/c[i-W.ROC_BARS] - 1.0) < 0.08: continue
            if band and s in PIT.get(day_key(bars[i][0]), ()): continue
            sig = W.detect_wildcard_signal(df.iloc[max(0, i-TAIL):i+1], s)
            if sig is None: continue
            e, sl = float(sig.entry_price), float(sig.sl_price)
            if abs(e-sl) <= 0 or e <= 0: continue
            cr = shadow.cost_r({"entry": e, "sl": sl, "tp": float(sig.tp_price), "side": sig.side})
            g = walk_peak(bars, i, e, sl, sig.side, shadow.CONVEX_HORIZON_S,
                          arm, retain, rr, rh, cr, now)
            if g is None: continue
            peaks.append(g[0])
    peaks.sort(reverse=True)
    n = len(peaks)
    print("signals resolved: %d\n" % n)
    print("=== HOW FAR DO TRADES GO? (peak R, no cap binding) ===")
    for th in (1, 2, 3, 4, 5, 6, 6.67, 7, 8, 9, 10):
        k = sum(1 for p in peaks if p >= th)
        print("  peak >= %5.2fR : %4d  (%5.2f%% of all signals)" % (th, k, 100.0*k/max(1,n)))
    reach5 = [p for p in peaks if p >= 5.0]
    print("\n=== THE AFFECTED POPULATION: trades reaching +5R ===")
    print("  n = %d of %d signals (%.2f%%)" % (len(reach5), n, 100.0*len(reach5)/max(1,n)))
    if reach5:
        stall = [p for p in reach5 if p < 6.67]
        past = [p for p in reach5 if p >= 6.67]
        print("  stall between 5R and 6.67R : %3d  -> each LOSES %s"
              % (len(stall), "5.00R - 0.75*peak"))
        print("  reach 6.67R or beyond      : %3d  -> each GAINS up to 2.00R" % len(past))
        loss = sum(5.0 - rh*p for p in stall)
        gain = sum(min(7.0, rh*p if p < 7.0 else 7.0) - 5.0 for p in past)
        print("\n  RAISING 5R -> 7R, summed over the affected trades:")
        print("    lost to stalls  %+8.2fR" % (-loss))
        print("    gained by runs  %+8.2fR" % (+gain))
        print("    NET             %+8.2fR" % (gain - loss))
    print("\nEverything not in the affected population is byte-identical between")
    print("the two caps. This is the whole of the 5R -> 7R decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
