"""Does the TREND sleeve's 4% trigger admit a band that loses money?

    railway ssh --service Futures-bot -> /opt/venv/bin/python tools/pit_trend_trigger.py

THE LIVE OBSERVATION (2026-09-01, tools/pit_loss_context.py). Of 17 TREND closes
in the trailing 28 days, the five that fired at a 24h ROC of 4.0-5.0% went 0 for
5 and cost $10.77 - more than the whole sleeve's +$4.77 net. Four of the five
were ZEC. n=5 is not a finding, it is a reason to look.

THE CONFLICT THIS MUST RESOLVE. On 2026-08-27 the replay recommended moving the
trigger the OTHER way, to 3.0% paired with a 48h clock (+$12.19/220d, best joint
cell). That test predates the three fill-rate corrections now in pit_book.py, and
was never re-run against them. So this sweep is not a second opinion - it is the
first opinion computed on a book that matches how the bot actually fills.

METHOD
  detect once with FUTURES_TREND_MIN_ROC forced to 1.5%, so nothing is gated
  away, and keep the detector's own roc_pct on each signal. Filtering that in
  Python is EXACTLY equivalent to re-detecting per threshold (trend.py:148 is a
  pure rejection gate and the side comes from the sign of the same roc), and it
  keeps every cell on one identical set of bars.

  Each threshold then gets its own candidate stream through pit_book.take() with
  the TREND sleeve's real parameters: 2 slots, long-only, one entry per 900s
  scan, sizing off AVAILABLE margin. calm_max is 0 because the calm-shock filter
  is WILDCARD-only (runtime.py:5881) - applying it here would be a fidelity bug
  in the opposite direction.

WHAT WOULD MAKE THIS ACTIONABLE. Raising a threshold REMOVES trades, and removing
the worst trades in-sample always looks good. The screen that matters is whether
5% beats 4% in BOTH halves at EVERY boundary from 35% to 65%. A cell that only
wins on the full sample has told you nothing you can trade.

READ-ONLY.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ["FUTURES_TREND_MIN_ROC"] = "0.015"      # before any trend import

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from futuresbot.trend import detect_trend_signal, lookback_bars  # noqa: E402
from pit_book import take  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

TAIL = 300
SWEEP = (0.030, 0.035, 0.040, 0.045, 0.050, 0.055, 0.060, 0.070, 0.080)
BANDS = ((0.030, 0.040), (0.040, 0.050), (0.050, 0.060), (0.060, 0.080),
         (0.080, 0.160), (0.160, 9.99))


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY on the CORRECTED book - model dollars, not P&L ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    now = int(time.time())
    days = _env("PJ_DAYS", 220)
    eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    slots = int(_env("FUTURES_TREND_MAX_POSITIONS", 2))
    tp_r = _env("FUTURES_TREND_TP_R", 3.0)
    scan_s = _env("FUTURES_TREND_SCAN_INTERVAL_SECONDS", 900.0)
    slmp = _env("FUTURES_MAX_SL_MARGIN_PCT", 20.0)
    lo_, hi_ = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    base_thr = _env("FUTURES_TREND_MIN_ROC_LIVE", 0.04)
    syms = tuple(s.strip() for s in
                 (os.environ.get("FUTURES_TREND_SYMBOLS") or
                  "ETH_USDT,XRP_USDT,ZEC_USDT").split(",") if s.strip())
    horizon = shadow.CONVEX_HORIZON_S
    fn = ratchet(_env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0),
                 _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75),
                 base=_env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50), arm=1.0)

    print("universe %s | %d slots | TP %.1fR | horizon %.0fh | long only"
          % (",".join(s.replace("_USDT", "") for s in syms), slots, tp_r, horizon / 3600.0))
    print("equity $%.2f | risk %.3f%% of AVAILABLE | sl margin %.0f%% | scan %.0fs"
          % (eq0, risk_pct * 100, slmp, scan_s))
    print("live trigger %.1f%%\n" % (base_thr * 100))

    frames, rep = fetch_frames(cl, syms, days=days, workers=3, min_bars=2000,
                               now_ts=now, strict=False)
    print(rep)
    if not frames:
        print("no frames")
        return 1

    lb = lookback_bars()
    C = []
    for s, df in frames.items():
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
            row = {"entry": e, "sl": sl, "tp": float(sig.tp_price), "side": "LONG"}
            g = resolve(bars, i, e, sl, float(sig.tp_price), tp_r, "LONG",
                        horizon, shadow.cost_r(row), fn,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is None:
                continue
            eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
            C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                      "exit_ts": float(g[1]), "kind": str(g[2]),
                      "roc": abs(float(getattr(sig, "roc_pct", 0.0) or 0.0)),
                      "mult": regime_size_multiplier(eff, lo=lo_, hi=hi_, floor_mult=flm)})
    C.sort(key=lambda z: z["ts"])
    print("LONG signals detected at a 1.5%% floor: %d\n" % len(C))

    def book(thr):
        return take([z for z in C if z["roc"] >= thr], slots=slots, equity=eq0,
                    risk_pct=risk_pct, sl_margin_pct=slmp, scan_s=scan_s,
                    one_per_scan=True, calm_max=0.0)

    BASE = book(base_thr)
    if not BASE:
        print("no fills at the live trigger")
        return 1
    t0, t1 = BASE[0]["ts"], BASE[-1]["ts"]
    base_usd = sum(f["usd"] for f in BASE)

    print("=" * 92)
    print("A. THE DIRECT TEST - what each ROC band earns among trades LIVE ACTUALLY TAKES")
    print("   (filled at the live 4.0%% trigger, %d fills over %.0f days)"
          % (len(BASE), (t1 - t0) / 86400.0))
    print("=" * 92)
    print("  %-16s %6s %6s %10s %10s %10s" % ("band", "fills", "wins", "net $",
                                              "$/fill", "mean R"))
    for a, b in BANDS:
        g = [f for f in BASE if a <= f["roc"] < b]
        if not g:
            continue
        print("  %-16s %6d %6d %+10.2f %+10.3f %+10.3f"
              % ("%.1f - %.1f%%" % (a * 100, b * 100) if b < 9
                 else ">= %.1f%%" % (a * 100),
                 len(g), sum(1 for z in g if z["net"] > 0),
                 sum(z["usd"] for z in g),
                 sum(z["usd"] for z in g) / len(g),
                 sum(z["net"] for z in g) / len(g)))
    print("  %-16s %6d %6d %+10.2f %+10.3f %+10.3f"
          % ("ALL (live)", len(BASE), sum(1 for z in BASE if z["net"] > 0), base_usd,
             base_usd / len(BASE), sum(z["net"] for z in BASE) / len(BASE)))

    def halves(f, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(z["usd"] for z in f if z["ts"] < cut),
                sum(z["usd"] for z in f if z["ts"] >= cut))

    print()
    print("=" * 92)
    print("B. THE THRESHOLD SWEEP through the corrected book")
    print("=" * 92)
    print("%-9s %6s %10s %10s %10s %8s %6s   %s"
          % ("trigger", "fills", "net $", "vs live", "ex-top5", "$/fill", "both?", "thirds"))
    rowsout = []
    for thr in SWEEP:
        f = book(thr)
        if not f:
            continue
        u = sum(z["usd"] for z in f)
        vals = sorted((z["usd"] for z in f), reverse=True)
        ex5 = sum(vals[max(1, len(vals) // 20):])
        ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                    *halves(f, fr), *halves(BASE, fr))
                 for fr in (0.35, 0.425, 0.5, 0.575, 0.65))
        th = []
        for k in range(3):
            a = t0 + k * (t1 - t0) / 3.0
            b = t0 + (k + 1) * (t1 - t0) / 3.0 + (1 if k == 2 else 0)
            th.append(sum(z["usd"] for z in f if a <= z["ts"] < b))
        tag = "base" if abs(thr - base_thr) < 1e-9 else ("YES" if ok else "no")
        rowsout.append((thr, u - base_usd, tag, ex5))
        print("%-9s %6d %+10.2f %+10.2f %+10.2f %8.3f %6s   %+6.1f %+6.1f %+6.1f"
              % ("%.1f%%" % (thr * 100), len(f), u, u - base_usd, ex5,
                 u / len(f), tag, *th))

    print()
    print("=" * 92)
    print("C. VERDICT")
    print("=" * 92)
    band45 = [f for f in BASE if 0.040 <= f["roc"] < 0.050]
    if band45:
        print("  the 4-5%% band on the corrected book: %d fills, %d wins, $%+.2f"
              % (len(band45), sum(1 for z in band45 if z["net"] > 0),
                 sum(z["usd"] for z in band45)))
        print("  live observation was          : 5 fills, 0 wins, $-10.77")
    else:
        print("  the 4-5% band takes no fills on the corrected book")
    cands = [r for r in rowsout if r[2] == "YES" and r[1] > 0]
    if cands:
        best = max(cands, key=lambda r: r[1])
        print("  best threshold clearing the boundary-swept screen: %.1f%% (%+.2f vs live)"
              % (best[0] * 100, best[1]))
        print("  over %.0f days that is $%.2f/month." % (days, best[1] / (days / 30.0)))
    else:
        print("  NO threshold beats the live 4.0% in both halves at every boundary.")
        print("  The in-sample gain, if any, does not survive the split - which is")
        print("  exactly what an overfit subtraction looks like.")
    print()
    print("=" * 92)
    print("D. WHY THE BAND'S LOSS DOES NOT TRANSFER TO THE BOTTOM LINE")
    print("   The 4-5%% band is worth $%+.2f in isolation, yet excising it via a 5.0%%"
          % sum(z["usd"] for z in BASE if 0.040 <= z["roc"] < 0.050))
    print("   trigger moves net $ by only %+.2f. The slot book is why."
          % (sum(z["usd"] for z in book(0.050)) - base_usd))
    print("=" * 92)
    F4 = book(base_thr)
    F5 = book(0.050)
    k4 = {(z["sym"], z["ts"]): z for z in F4}
    k5 = {(z["sym"], z["ts"]): z for z in F5}
    dropped = [z for k, z in k4.items() if k not in k5]
    added = [z for k, z in k5.items() if k not in k4]
    kept4 = [z for k, z in k4.items() if k in k5]
    kept5 = [z for k, z in k5.items() if k in k4]
    print("  %-46s %6s %11s" % ("", "fills", "net $"))
    print("  %-46s %6d %+11.2f" % ("dropped by the 5.0% trigger", len(dropped),
                                   sum(z["usd"] for z in dropped)))
    print("     of which actually in the 4-5%% band          %6d %+11.2f"
          % (len([z for z in dropped if z["roc"] < 0.050]),
             sum(z["usd"] for z in dropped if z["roc"] < 0.050)))
    print("     of which >= 5%% but DISPLACED by slot timing  %6d %+11.2f"
          % (len([z for z in dropped if z["roc"] >= 0.050]),
             sum(z["usd"] for z in dropped if z["roc"] >= 0.050)))
    print("  %-46s %6d %+11.2f" % ("NEWLY ADMITTED once slots were freed", len(added),
                                   sum(z["usd"] for z in added)))
    print("  %-46s %6d %+11.2f" % ("present in both books", len(kept4),
                                   sum(z["usd"] for z in kept4)))
    print("  %-46s %6s %+11.2f" % ("   the same trades, RESIZED at 5.0%", "",
                                   sum(z["usd"] for z in kept5)))
    print("     resizing alone is worth                     %6s %+11.2f"
          % ("", sum(z["usd"] for z in kept5) - sum(z["usd"] for z in kept4)))
    print()
    print("  mean risk per fill: %.3f at 4.0%%  ->  %.3f at 5.0%%  (%+.1f%%)"
          % (sum(z["risk_usdt"] for z in F4) / len(F4),
             sum(z["risk_usdt"] for z in F5) / len(F5),
             100.0 * (sum(z["risk_usdt"] for z in F5) / len(F5)
                      / (sum(z["risk_usdt"] for z in F4) / len(F4)) - 1.0)))
    tot = (sum(z["usd"] for z in added) - sum(z["usd"] for z in dropped)
           + sum(z["usd"] for z in kept5) - sum(z["usd"] for z in kept4))
    print("  reconciliation: %+.2f - %+.2f + %+.2f = %+.2f (sweep says %+.2f)"
          % (sum(z["usd"] for z in added), sum(z["usd"] for z in dropped),
             sum(z["usd"] for z in kept5) - sum(z["usd"] for z in kept4), tot,
             sum(z["usd"] for z in F5) - base_usd))
    print()
    print("=" * 92)
    print("E. THE LEVER THAT DOES NOT RESHUFFLE: size the band down, do not exclude it")
    print("   The trade still opens and still holds its slot, so the fill SCHEDULE is")
    print("   byte-identical to live. Only the dollar weight of the 4-5%% band moves.")
    print("   Caveat: like the regime scaler in pit_book, this re-weights P&L without")
    print("   releasing margin, so it IGNORES the extra headroom a smaller position")
    print("   would give later fills - the estimate is conservative by that amount.")
    print("=" * 92)
    print("%-26s %10s %10s %10s %8s %6s   %s"
          % ("4-5% band sized at", "net $", "vs live", "ex-top5", "$/fill", "both?", "thirds"))
    for m in (1.00, 0.75, 0.50, 0.25, 0.00):
        f = [dict(z) for z in BASE]
        for z in f:
            if 0.040 <= z["roc"] < 0.050:
                z["usd"] = z["usd"] * m
        u = sum(z["usd"] for z in f)
        vals = sorted((z["usd"] for z in f), reverse=True)
        ex5 = sum(vals[max(1, len(vals) // 20):])
        ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                    *halves(f, fr), *halves(BASE, fr))
                 for fr in (0.35, 0.425, 0.5, 0.575, 0.65))
        th = []
        for k in range(3):
            a = t0 + k * (t1 - t0) / 3.0
            b = t0 + (k + 1) * (t1 - t0) / 3.0 + (1 if k == 2 else 0)
            th.append(sum(z["usd"] for z in f if a <= z["ts"] < b))
        print("%-26s %+10.2f %+10.2f %+10.2f %8.3f %6s   %+6.1f %+6.1f %+6.1f"
              % ("%.0f%% of normal%s" % (m * 100, "  (LIVE)" if m == 1.0 else ""),
                 u, u - base_usd, ex5, u / len(f),
                 "base" if m == 1.0 else ("YES" if ok else "no"), *th))
    print()
    d30 = (t1 - t0) / 86400.0 / 30.0
    half = -sum(z["usd"] for z in BASE if 0.040 <= z["roc"] < 0.050) * 0.5
    print("  at 50%% sizing the band contributes $%+.2f instead of $%+.2f, worth"
          % (sum(z["usd"] for z in BASE if 0.040 <= z["roc"] < 0.050) * 0.5,
             sum(z["usd"] for z in BASE if 0.040 <= z["roc"] < 0.050)))
    print("  $%+.2f over %.0f days = $%+.2f/month at $%.0f equity."
          % (half, (t1 - t0) / 86400.0, half / d30, eq0))
    print("  the standing bar is $10/month either way.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
