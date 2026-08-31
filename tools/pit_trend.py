"""The TREND sleeve, replayed over 220 days. Universe, direction, slots, cooldown.

    railway run --service Futures-bot python tools/pit_trend.py

WHY. TREND is the second live sleeve and the one losing money: -$5.35 over 3
closes inside trial 18, and -$5.13 lifetime on ZEC alone across 9 trades. Every
replay tool in this repo models `detect_wildcard_signal`; none has ever modelled
`detect_trend_signal`, so every TREND decision to date rests on a 63-day probe
run before the sleeve shipped, plus 17 live closes.

Three live settings disagree with the sleeve's own recorded evidence:

  FUTURES_TREND_SYMBOLS     = ETH,XRP,ZEC   but DEFAULT_SYMBOLS is BTC,ETH,SOL
                              and trend_symbols() says the tier is "a property of
                              these three specifically" - deep books, small ATR.
  FUTURES_TREND_MAX_POSITIONS = 2           but the docstring's own table puts 3
                              slots ahead of 2 on BOTH return and drawdown.
  FUTURES_TREND_LONG_ONLY   = 1             agrees with the recorded short arm
                              (-$14 to -$34), and this re-tests it at 220 days.

WHAT THIS ANSWERS.
  1. Per symbol: which names actually pay, over 220 days rather than 17 trades.
  2. Universe: the live set vs the designed big-3 vs supersets.
  3. Direction: long / short / both - the owner asked whether the losing setups
     inverted into shorts might pay. The sleeve's own 63-day probe says no; this
     is the larger, independent test of that.
  4. Slots: 1 / 2 / 3.
  5. Cooldown after a retention-trail close, on the sleeve where the owner
     actually observed the pattern (ZEC) and which the wildcard replay could not
     see.

Live sizing throughout (risk_pct x equity x regime scaler at the trial-18 floor
of 0.50), the continuous slot book, and a half-split swept across boundaries
35-65% - a single midpoint passed the retracted stop-width finding.

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
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from futuresbot.trend import detect_trend_signal, lookback_bars  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

BAR, TAIL, HOUR = 900, 300, 3600

LIVE_SET = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
DESIGNED = ("BTC_USDT", "ETH_USDT", "SOL_USDT")
POOL = ("BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "ZEC_USDT",
        "BNB_USDT", "DOGE_USDT", "ADA_USDT", "AVAX_USDT", "LINK_USDT")


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
    days = _env("PJ_DAYS", 220)
    now = int(time.time())
    eq0 = rt._last_known_equity() or 172.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    lo, hi = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    tp_r = _env("FUTURES_TREND_TP_R", 3.0)
    print("equity $%.2f | risk %.4f | scaler floor %.2f | TP %.1fR\n" % (eq0, risk_pct, flm, tp_r))

    frames, rep = fetch_frames(cl, POOL, days=days, workers=5,
                               min_bars=lookback_bars() + 40, now_ts=now)
    print(rep)

    live_floor_fn = ratchet(3.0, 0.75)
    C = []
    for s, df in frames.items():
        c = [float(x) for x in df["close"]]
        ts_all = [float(x.timestamp()) for x in df.index]
        bars = list(zip(ts_all, [float(x) for x in df["high"]],
                        [float(x) for x in df["low"]], c))
        lb = lookback_bars()
        for i in range(lb + 40, len(c)):
            sig = detect_trend_signal(df.iloc[max(0, i - TAIL):i + 1], s)
            if sig is None:
                continue
            e, sl, tp = float(sig.entry_price), float(sig.sl_price), float(sig.tp_price)
            one = abs(e - sl)
            if one <= 0 or e <= 0:
                continue
            row = {"entry": e, "sl": sl, "tp": tp, "side": sig.side}
            g = resolve(bars, i, e, sl, tp, abs(tp - e) / one, sig.side,
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), live_floor_fn,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is None:
                continue
            eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
            C.append({"ts": bars[i][0], "sym": s, "side": sig.side, "net": float(g[0]),
                      "exit_ts": float(g[1]), "kind": str(g[2]),
                      "mult": regime_size_multiplier(eff, lo=lo, hi=hi, floor_mult=flm)})
    C.sort(key=lambda x: x["ts"])
    print("raw trend signals across the %d-name pool: %d\n" % (len(frames), len(C)))
    if not C:
        print("no signals - nothing to score")
        return 0

    def book(syms, sides, slots, cool_h=0, cool_scope=None):
        universe, taken, per, occupied, frozen = set(syms), [], {}, [], {}
        for x in C:
            if x["sym"] not in universe or x["side"] not in sides:
                continue
            key = (x["sym"], x["side"])
            if frozen.get(key, 0.0) > x["ts"]:
                continue
            occupied[:] = [q for q in occupied if q > x["ts"]]
            per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
            if per[x["sym"]] or len(occupied) >= slots:
                continue
            occupied.append(x["exit_ts"])
            per[x["sym"]].append(x["exit_ts"])
            taken.append(x)
            if cool_scope and cool_h > 0:
                fire = (cool_scope == "any") or (cool_scope == "trail" and x["kind"] == "trail")
                if fire:
                    frozen[key] = x["exit_ts"] + cool_h * HOUR
        return taken

    def usd(f):
        return sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f)

    t0, t1 = C[0]["ts"], C[-1]["ts"]

    def halves(f, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f if z["ts"] < cut),
                sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f if z["ts"] >= cut))

    BOTH, LONG, SHORT = ("LONG", "SHORT"), ("LONG",), ("SHORT",)

    print("=== 1. PER SYMBOL (long only, 3 slots, symbol traded alone) ===")
    print("%-12s %6s %10s %9s %8s" % ("symbol", "fills", "net $", "meanR", "win%"))
    for s in POOL:
        if s not in frames:
            continue
        f = book((s,), LONG, 3)
        if not f:
            print("%-12s %6d %10s" % (s, 0, "-"))
            continue
        w = 100.0 * sum(1 for z in f if z["net"] > 0) / len(f)
        print("%-12s %6d %+10.2f %+9.3f %7.0f%%"
              % (s, len(f), usd(f), sum(z["net"] for z in f) / len(f), w))

    print("\n=== 2. UNIVERSE x DIRECTION (3 slots) ===")
    print("%-26s %6s %10s %9s %8s" % ("cell", "fills", "net $", "meanR", "win%"))
    for label, syms in (("LIVE  ETH/XRP/ZEC", LIVE_SET),
                        ("DESIGNED BTC/ETH/SOL", DESIGNED),
                        ("big5  +XRP/ZEC", DESIGNED + ("XRP_USDT", "ZEC_USDT")),
                        ("all %d majors" % len(frames), tuple(frames))):
        for dlabel, sides in (("long", LONG), ("short", SHORT), ("both", BOTH)):
            f = book(syms, sides, 3)
            if not f:
                continue
            w = 100.0 * sum(1 for z in f if z["net"] > 0) / len(f)
            print("%-26s %6d %+10.2f %+9.3f %7.0f%%"
                  % ("%s %s" % (label, dlabel), len(f), usd(f),
                     sum(z["net"] for z in f) / len(f), w))

    print("\n=== 3. SLOTS (long only) ===")
    print("%-26s %6s %10s" % ("cell", "fills", "net $"))
    for label, syms in (("LIVE  ETH/XRP/ZEC", LIVE_SET), ("DESIGNED BTC/ETH/SOL", DESIGNED)):
        for n in (1, 2, 3):
            f = book(syms, LONG, n)
            print("%-26s %6d %+10.2f" % ("%s  %d slot" % (label, n), len(f), usd(f)))

    print("\n=== 4. COOLDOWN AFTER A RETENTION TRAIL (live set, long, 2 slots) ===")
    base = book(LIVE_SET, LONG, 2)
    bu = usd(base)
    print("%-26s %6s %10s %9s %6s" % ("cell", "fills", "net $", "vs base", "both?"))
    print("%-26s %6d %+10.2f %+9.2f %6s" % ("no cooldown", len(base), bu, 0.0, "base"))
    for h in (2, 6, 12, 24):
        f = book(LIVE_SET, LONG, 2, cool_h=h, cool_scope="trail")
        ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                    *halves(f, fr), *halves(base, fr))
                 for fr in (0.35, 0.425, 0.5, 0.575, 0.65))
        print("%-26s %6d %+10.2f %+9.2f %6s"
              % ("trail same-dir %2dh" % h, len(f), usd(f), usd(f) - bu,
                 "YES" if ok else "no"))

    print("\nmeanR is per fill, before the scaler. net $ is at live sizing.")
    print("A 63-day probe put LONG at +$6.45/+$14.31/+$16.12 for 1/2/3 slots and")
    print("SHORT at -$14.05/-$24.78/-$33.64. This is the 220-day re-test.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
