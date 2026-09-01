"""All four TREND studies, re-run on intra-bar detection.

    railway ssh --service Futures-bot -> /opt/venv/bin/python tools/pit_trend_intrabar.py

WHY. Every TREND result from 2026-09-01 - the trigger sweep, the slot sweep, the
stop-width sweep and the 16-cell factorial - was measured on COMPLETED 15m bars.
Re-running the WILDCARD band study on intra-bar detection inverted it: the 7-8%
band flipped from +$0.617/fill to -$0.398 and the whole "bimodal structure"
disappeared. Anything measured the same way is provisional until re-run.

Live scans every FUTURES_TREND_SCAN_INTERVAL_SECONDS and evaluates a PARTIALLY
FORMED 15m candle. tools/pit_intrabar.py emulates that with three phase-shifted
15m grids built from 5m data, each a proper non-overlapping series so ROC_BARS=12
stays a 3h lookback. Against the live book it closed 63% of the dollar error.

FOUR STUDIES, ONE FETCH. Detection depends on the stop (it sets sl and tp) but
NOT on the trigger, which is a pure filter on the detector's own roc_pct, so
detection runs once per stop per grid and everything else is filtering and
booking. The completed-bar figure is printed beside every cell: the question is
not what the intra-bar number is, it is which conclusions MOVED.

READ DOLLARS, not R - stop width rescales R and makes it incomparable.

READ-ONLY.
"""
from __future__ import annotations

import itertools
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
from pit_book import take  # noqa: E402
from pit_intrabar import fetch_grids  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

TAIL = 300
DETECT_FLOOR = 0.03
STOPS = (0.75, 1.5, 3.0, 4.5, 6.0)
LIVE_STOP, LIVE_TRIG, LIVE_CLOCK, LIVE_SLOTS = 3.0, 0.04, 24, 2

# measured on COMPLETED bars earlier today, for the "did it move?" column
CB_TRIG = {0.03: None, 0.04: 0.0, 0.05: -2.25, 0.06: None, 0.08: None}
CB_SLOTS = {1: -44.98, 2: 0.0, 3: -17.80}
CB_STOP = {0.75: -182.18, 1.5: -56.22, 3.0: 0.0, 4.5: -71.21, 6.0: -65.03}
CB_BEST3 = 31.12          # 5% / 3.0x / 48h / 3 slots


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def _cb(v):
    return "      -" if v is None else "%+7.2f" % v


def main() -> int:
    print("*** INTRA-BAR REPLAY - model dollars, not account P&L ***")
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

    GRIDS, rep = fetch_grids(cl, syms, days=days, workers=3, min_bars=2000,
                             now_ts=now)
    print(rep)
    print("phase grids: %s symbols each\n" % [len(g) for g in GRIDS])
    if not any(GRIDS):
        return 1

    # detection: once per (stop, grid). the trigger filters afterwards.
    SIG: dict[float, list] = {}
    for stop in STOPS:
        os.environ["FUTURES_TREND_SL_ATR_MULT"] = str(stop)
        os.environ["FUTURES_TREND_MIN_ROC"] = str(DETECT_FLOOR)
        from futuresbot.trend import detect_trend_signal, lookback_bars
        lb = lookback_bars()
        out = []
        for g in GRIDS:
            for s, df in g.items():
                c = [float(x) for x in df["close"]]
                ts_all = [float(x.timestamp()) for x in df.index]
                bars = list(zip(ts_all, [float(x) for x in df["high"]],
                                [float(x) for x in df["low"]], c))
                for i in range(lb + 40, len(c)):
                    sig = detect_trend_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                    if sig is None or sig.side != "LONG":
                        continue
                    e, sl = float(sig.entry_price), float(sig.sl_price)
                    if abs(e - sl) <= 0 or e <= 0:
                        continue
                    eff = trend_efficiency(c[:i + 1],
                                           int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
                    out.append((s, bars, i, e, sl, float(sig.tp_price),
                                abs(float(getattr(sig, "roc_pct", 0.0) or 0.0)),
                                float(getattr(sig, "atr_pct", 0.0) or 0.0),
                                regime_size_multiplier(eff, lo=lo_, hi=hi_,
                                                       floor_mult=flm)))
        SIG[stop] = out
        print("  stop %.2fx: %d LONG signals across 3 grids" % (stop, len(out)))
    print()

    RES: dict[tuple, list] = {}

    def resolved(stop, clock):
        key = (stop, clock)
        if key in RES:
            return RES[key]
        out = []
        for s, bars, i, e, sl, tp, roc, atr, mlt in SIG[stop]:
            row = {"entry": e, "sl": sl, "tp": tp, "side": "LONG"}
            g = resolve(bars, i, e, sl, tp, tp_r, "LONG", clock * 3600,
                        shadow.cost_r(row), fn, atr, now)
            if g is None:
                continue
            out.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                        "exit_ts": float(g[1]), "kind": str(g[2]),
                        "roc": roc, "mult": mlt})
        out.sort(key=lambda z: z["ts"])
        RES[key] = out
        return out

    def book(trig, stop, clock, slots):
        pool = [z for z in resolved(stop, clock) if z["roc"] >= trig]
        return take(pool, slots=slots, equity=eq0, risk_pct=risk_pct,
                    sl_margin_pct=slmp, scan_s=scan_s, one_per_scan=True,
                    calm_max=0.0)

    BASE = book(LIVE_TRIG, LIVE_STOP, LIVE_CLOCK, LIVE_SLOTS)
    if not BASE:
        print("no fills at live")
        return 1
    t0, t1 = BASE[0]["ts"], BASE[-1]["ts"]
    base_usd = sum(z["usd"] for z in BASE)

    def halves(f, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(z["usd"] for z in f if z["ts"] < cut),
                sum(z["usd"] for z in f if z["ts"] >= cut))

    def screen(f):
        return all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                       *halves(f, fr), *halves(BASE, fr))
                   for fr in (0.35, 0.425, 0.5, 0.575, 0.65))

    def line(label, f, cb):
        u = sum(z["usd"] for z in f)
        vals = sorted((z["usd"] for z in f), reverse=True)
        ex5 = sum(vals[max(1, len(vals) // 20):])
        print("%-24s %6d %+10.2f %+9.2f %+10.2f %8.3f %6s   cb %s"
              % (label, len(f), u, u - base_usd, ex5, u / len(f),
                 "base" if abs(u - base_usd) < 1e-9 else ("YES" if screen(f) else "no"),
                 _cb(cb)))

    print("=" * 108)
    print("LIVE on intra-bar: %d fills, $%+.2f, $%.3f/fill  (completed-bar was "
          "210 fills, $+121.55)" % (len(BASE), base_usd, base_usd / len(BASE)))
    print("=" * 108)
    hdr = ("%-24s %6s %10s %9s %10s %8s %6s   %s"
           % ("cell", "fills", "net $", "vs live", "ex-top5", "$/fill", "both?",
              "completed-bar"))

    print()
    print("A. TRIGGER SWEEP")
    print(hdr)
    for tg in (0.03, 0.04, 0.05, 0.06, 0.08, 0.16):
        f = book(tg, LIVE_STOP, LIVE_CLOCK, LIVE_SLOTS)
        if f:
            line("trigger %.0f%%" % (tg * 100), f, CB_TRIG.get(tg))

    print()
    print("B. ROC BANDS among the trades live actually takes")
    print("  %-16s %6s %6s %10s %10s" % ("band", "fills", "wins", "net $", "$/fill"))
    for a, b in ((0.04, 0.05), (0.05, 0.06), (0.06, 0.08), (0.08, 0.16), (0.16, 9.9)):
        g = [z for z in BASE if a <= z["roc"] < b]
        if len(g) < 4:
            continue
        u = sum(z["usd"] for z in g)
        print("  %-16s %6d %6d %+10.2f %+10.3f"
              % ("%.0f - %.0f%%" % (a * 100, b * 100) if b < 9 else ">= %.0f%%" % (a * 100),
                 len(g), sum(1 for z in g if z["net"] > 0), u, u / len(g)))
    print("  (completed-bar had 4-5%% at -$0.311/fill, the only negative band of six)")

    print()
    print("C. SLOT SWEEP")
    print(hdr)
    for n in (1, 2, 3, 4):
        f = book(LIVE_TRIG, LIVE_STOP, LIVE_CLOCK, n)
        if f:
            line("%d slots" % n, f, CB_SLOTS.get(n))

    print()
    print("D. STOP WIDTH")
    print(hdr)
    for st in STOPS:
        f = book(LIVE_TRIG, st, LIVE_CLOCK, LIVE_SLOTS)
        if f:
            line("stop %.2fx" % (st / LIVE_STOP), f, CB_STOP.get(st))

    print()
    print("E. THE FACTORIAL CELL that carried a +$10.97 three-way term")
    print(hdr)
    for tg, st, ck, sl_ in ((0.05, 3.0, 48, 3), (0.05, 3.0, 24, 3),
                            (0.04, 3.0, 48, 2), (0.05, 3.0, 48, 2)):
        f = book(tg, st, ck, sl_)
        if f:
            line("%.0f%%/%.1fx/%dh/%d" % (tg * 100, st, ck, sl_), f,
                 CB_BEST3 if (tg, st, ck, sl_) == (0.05, 3.0, 48, 3) else None)

    print()
    print("Read the 'completed-bar' column against 'vs live'. Where the sign or")
    print("the ranking moves, the earlier conclusion was an artifact of detecting")
    print("only on closed candles - which is what happened to every WILDCARD band.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
