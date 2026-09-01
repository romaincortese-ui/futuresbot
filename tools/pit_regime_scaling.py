"""Does a change's dollar value scale with the market, or is $4/month all there is?

    railway ssh --service Futures-bot -> /opt/venv/bin/python tools/pit_regime_scaling.py

THE OWNER'S QUESTION (2026-09-01): "$4/month. What would the impact be if the
market goes up like a rocket or down superfast? Wouldn't the missed amounts
increase a lot?"

It is the right question, because $4.04/month is a MEAN over 231 days that
contains both dead and violent regimes, and a mean is the wrong summary if the
effect is regime-borne. This measures the dispersion instead of arguing about it.

METHOD. Rebuild the best TREND cell from pit_trend_factorial (5.0% trigger /
3.0x stop / 48h clock / 3 slots, +$31.12 over 231d) and the live cell on
identical bars, then bucket every fill by CALENDAR MONTH and by the market
regime prevailing in that month, measured on BTC as trailing 30d return and
realised volatility. Report the ADVANTAGE per bucket, not the level.

WHAT WOULD SUPPORT THE OWNER'S CASE: advantage concentrated in the hot months
and rising with |BTC 30d|, which would mean $4/month understates what the change
is worth when it matters and the annual mean is a misleading summary.

WHAT WOULD UNDERMINE IT: advantage flat across regimes, or - worse - the SAME
months carrying both the advantage and the base sleeve's profit, which would
mean the change adds nothing the base does not already capture and merely rides
the same few weeks.

THE TRAP THIS IS BUILT TO AVOID. In a hot regime EVERYTHING earns more, the base
strategy included. A change is only worth more in a rocket if its advantage grows
FASTER than the base does, so the ratio (advantage / base) is reported beside the
dollars. Reading raw dollars alone would confirm the hypothesis by construction.

READ-ONLY.
"""
from __future__ import annotations

import datetime as dt
import os
import statistics
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
from pit_book import take  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

TAIL = 300
LIVE = (0.04, 3.0, 24, 2)
BEST = (0.05, 3.0, 48, 3)


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars, not P&L ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    now = int(time.time())
    days = _env("PJ_DAYS", 220)
    eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    tp_r = _env("FUTURES_TREND_TP_R", 3.0)
    scan_s = _env("FUTURES_TREND_SCAN_INTERVAL_SECONDS", 900.0)
    slmp = _env("FUTURES_TREND_MAX_SL_MARGIN_PCT", 20.0)
    lo_, hi_ = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    syms = tuple(s.strip() for s in
                 (os.environ.get("FUTURES_TREND_SYMBOLS") or
                  "ETH_USDT,XRP_USDT,ZEC_USDT").split(",") if s.strip())
    fn = ratchet(_env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0),
                 _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75),
                 base=_env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50), arm=1.0)

    frames, rep = fetch_frames(cl, tuple(syms) + ("BTC_USDT",), days=days,
                               workers=4, min_bars=2000, now_ts=now, strict=False)
    print(rep)
    if "BTC_USDT" not in frames:
        print("no BTC frame - cannot classify regime")
        return 1

    # --- market regime per calendar month, from BTC ---
    btc = frames["BTC_USDT"]
    bt = [float(x.timestamp()) for x in btc.index]
    bc = [float(x) for x in btc["close"]]
    MONTH: dict[str, dict] = {}
    for k in range(len(bc)):
        key = dt.datetime.fromtimestamp(bt[k], dt.UTC).strftime("%Y-%m")
        m = MONTH.setdefault(key, {"first": bc[k], "last": bc[k], "px": []})
        m["last"] = bc[k]
        m["px"].append(bc[k])
    for key, m in MONTH.items():
        rets = [m["px"][i] / m["px"][i - 1] - 1.0
                for i in range(1, len(m["px"])) if m["px"][i - 1]]
        m["ret"] = (m["last"] / m["first"] - 1.0) * 100.0 if m["first"] else 0.0
        # 15m realised vol annualised to a monthly-comparable %
        m["vol"] = (statistics.pstdev(rets) * 100.0 * (96 ** 0.5)) if len(rets) > 2 else 0.0

    PREP = {}
    for s in syms:
        if s not in frames:
            continue
        df = frames[s]
        c = [float(x) for x in df["close"]]
        ts_all = [float(x.timestamp()) for x in df.index]
        PREP[s] = (df, list(zip(ts_all, [float(x) for x in df["high"]],
                                [float(x) for x in df["low"]], c)), c)

    def build(trig, stop, clock, slots):
        os.environ["FUTURES_TREND_SL_ATR_MULT"] = str(stop)
        os.environ["FUTURES_TREND_MIN_ROC"] = str(trig)
        from futuresbot.trend import detect_trend_signal, lookback_bars
        lb = lookback_bars()
        C = []
        for s, (df, bars, c) in PREP.items():
            for i in range(lb + 40, len(c)):
                sig = detect_trend_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                if sig is None or sig.side != "LONG":
                    continue
                e, sl = float(sig.entry_price), float(sig.sl_price)
                if abs(e - sl) <= 0 or e <= 0:
                    continue
                row = {"entry": e, "sl": sl, "tp": float(sig.tp_price), "side": "LONG"}
                g = resolve(bars, i, e, sl, float(sig.tp_price), tp_r, "LONG",
                            clock * 3600, shadow.cost_r(row), fn,
                            float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if g is None:
                    continue
                eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
                C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                          "exit_ts": float(g[1]),
                          "mult": regime_size_multiplier(eff, lo=lo_, hi=hi_,
                                                         floor_mult=flm)})
        C.sort(key=lambda z: z["ts"])
        return take(C, slots=slots, equity=eq0, risk_pct=risk_pct,
                    sl_margin_pct=slmp, scan_s=scan_s, one_per_scan=True,
                    calm_max=0.0)

    A = build(*LIVE)
    B = build(*BEST)
    print("\nlive cell  %s : %d fills, $%+.2f"
          % (str(LIVE), len(A), sum(z["usd"] for z in A)))
    print("best cell  %s : %d fills, $%+.2f\n"
          % (str(BEST), len(B), sum(z["usd"] for z in B)))

    def bymonth(f):
        out: dict[str, float] = {}
        for z in f:
            key = dt.datetime.fromtimestamp(z["ts"], dt.UTC).strftime("%Y-%m")
            out[key] = out.get(key, 0.0) + z["usd"]
        return out

    ma, mb = bymonth(A), bymonth(B)
    keys = sorted(set(ma) | set(mb))
    print("=" * 96)
    print("PER MONTH - does the ADVANTAGE grow when the market moves?")
    print("=" * 96)
    print("%-9s %10s %9s %10s %10s %11s %10s"
          % ("month", "BTC 30d %", "BTC vol", "live $", "best $", "advantage", "adv/live"))
    tot_a = tot_b = 0.0
    hot, cold = [], []
    for k in keys:
        m = MONTH.get(k, {})
        a, b = ma.get(k, 0.0), mb.get(k, 0.0)
        tot_a += a
        tot_b += b
        adv = b - a
        ratio = (adv / abs(a)) if abs(a) > 1e-9 else float("nan")
        print("%-9s %+10.1f %9.1f %+10.2f %+10.2f %+11.2f %10s"
              % (k, m.get("ret", 0.0), m.get("vol", 0.0), a, b, adv,
                 "-" if ratio != ratio else "%+.2f" % ratio))
        if abs(m.get("ret", 0.0)) >= 10.0:
            hot.append((adv, a))
        else:
            cold.append((adv, a))
    print("%-9s %10s %9s %+10.2f %+10.2f %+11.2f"
          % ("TOTAL", "", "", tot_a, tot_b, tot_b - tot_a))

    print()
    print("=" * 96)
    print("THE TEST THAT MATTERS: does the advantage OUTPACE the base, or just ride it?")
    print("=" * 96)
    for label, g in (("months with |BTC 30d| >= 10%%", hot),
                     ("quiet months  |BTC 30d| < 10%%", cold)):
        if not g:
            continue
        adv = sum(x for x, _ in g)
        base = sum(y for _, y in g)
        print("  %-30s n=%2d   base $%+8.2f   advantage $%+8.2f   adv/base %s"
              % (label, len(g), base, adv,
                 "n/a" if abs(base) < 1e-9 else "%+.3f" % (adv / abs(base))))
    print()
    print("  If adv/base is HIGHER in the hot bucket, the change is worth more")
    print("  than its mean when the market moves and $4/month understates it.")
    print("  If adv/base is FLAT or LOWER, the change merely rides the same few")
    print("  weeks the base already captures, and the mean is the honest number.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
