"""How much ROOM should a TREND trade get? The stop width, swept.

    railway ssh --service Futures-bot -> /opt/venv/bin/python tools/pit_trend_stop.py

WHY THIS EXISTS. tools/pit_stop_width.py answered this for WILDCARD on
2026-08-28 and says so in its own header: "WILDCARD only -- TREND has its own
stop policy and three fixed symbols." So the TREND stop has never been swept.
Owner asked for it directly on 2026-09-01.

THE FRAMING, restated because the request names R values. R is DEFINED as the
distance to the stop, so every stop-out is -1R by construction and "-0.5R stop"
relabels the same trade rather than configuring anything. The dial is
FUTURES_TREND_SL_ATR_MULT, live 3.0, and the request maps onto it as MULTIPLES
of the current distance:

    "-0.25R"  ->  0.25x today's stop  ->  mult 0.75
    "-0.5R"   ->  0.50x               ->  mult 1.5
    "-1R"     ->  LIVE                ->  mult 3.0
    "-1.5R"   ->  1.50x               ->  mult 4.5
    "-2R"     ->  2.00x               ->  mult 6.0

READ DOLLARS, NEVER R. Under the risk dial, margin = risk_pct x avail x 100 /
sl_margin_pct, so 1R IN DOLLARS IS INVARIANT to stop width - a wider stop buys a
SMALLER position, not more risk. Net R is therefore NOT comparable across cells
(the same price move is worth fewer R at a wider stop) while net $ is.

WHAT ELSE MOVES WITH THE STOP, so the result can be read rather than guessed:
  * THE TARGET. tp_dist = sl_frac x tp_r (trend.py:190). Widening the stop
    widens the TP by the same factor - this is NOT "more room to the same
    target", it is a proportional rescale of the whole trade.
  * LEVERAGE, and it moves the WRONG WAY. leverage starts at
    FUTURES_TREND_LEVERAGE_MAX (10) and is trimmed only when
    sl_frac x leverage x 100 breaches FUTURES_TREND_MAX_SL_MARGIN_PCT (20).
    A TIGHTER stop breaches less, so leverage stays pinned at 10. The
    conditional-expectancy engine found leverage >= 7 reliably loses, so the
    tight cells are expected to run straight into that - and the per-cell
    leverage diagnostic below is there to show whether they do.
  * cost_r = cost / sl_frac, so tight stops are MORE expensive per R.
  * the trail. It arms at 1R and floors at 0.50 x peak, both of which rescale
    with the stop, so the exit geometry is not held fixed either.

The honest prior: tightening trades many small losses for a few small wins and
pays more fees per R at higher leverage; widening trades fewer, larger losses for
fewer, larger wins. Which side wins in DOLLARS is the whole question.

REPORTED in the owner's terms: net $, the STOP-OUT COUNT (the "number of losses"
actually being asked about), win rate, $/fill, and - because the standing
objective is withdrawable profit - ex-top-5%. Boundary-swept half-split on every
cell against the live 3.0.

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
from pit_book import take  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

TAIL = 300
# (label as the owner framed it, FUTURES_TREND_SL_ATR_MULT)
CELLS = (("0.25x  (asked as -0.25R)", 0.75),
         ("0.50x  (asked as -0.5R)", 1.5),
         ("1.00x  LIVE", 3.0),
         ("1.50x  (asked as -1.5R)", 4.5),
         ("2.00x  (asked as -2R)", 6.0))


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
    slmp = _env("FUTURES_TREND_MAX_SL_MARGIN_PCT", 20.0)
    lo_, hi_ = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    syms = tuple(s.strip() for s in
                 (os.environ.get("FUTURES_TREND_SYMBOLS") or
                  "ETH_USDT,XRP_USDT,ZEC_USDT").split(",") if s.strip())
    horizon = shadow.CONVEX_HORIZON_S
    fn = ratchet(_env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0),
                 _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75),
                 base=_env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50), arm=1.0)

    print("universe %s | %d slots | TP %.1fR | horizon %.0fh | long only"
          % (",".join(s.replace("_USDT", "") for s in syms), slots, tp_r,
             horizon / 3600.0))
    print("live FUTURES_TREND_SL_ATR_MULT=3.0 | margin cap %.0f%% | lev max %.0f\n"
          % (slmp, _env("FUTURES_TREND_LEVERAGE_MAX", 10.0)))

    frames, rep = fetch_frames(cl, syms, days=days, workers=3, min_bars=2000,
                               now_ts=now, strict=False)
    print(rep)
    if not frames:
        print("no frames")
        return 1

    PREP = {}
    for s, df in frames.items():
        c = [float(x) for x in df["close"]]
        ts_all = [float(x.timestamp()) for x in df.index]
        PREP[s] = (df, list(zip(ts_all, [float(x) for x in df["high"]],
                                [float(x) for x in df["low"]], c)), c)

    def run(mult):
        os.environ["FUTURES_TREND_SL_ATR_MULT"] = str(mult)
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
                            horizon, shadow.cost_r(row), fn,
                            float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if g is None:
                    continue
                eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
                designed = float(getattr(sig, "sl_frac_designed", 0.0) or 0.0)
                actual = abs(e - sl) / e
                C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                          "exit_ts": float(g[1]), "kind": str(g[2]),
                          "lev": float(getattr(sig, "leverage", 0) or 0),
                          "slf": actual, "capped": 1.0 if designed > actual * 1.001 else 0.0,
                          "mult": regime_size_multiplier(eff, lo=lo_, hi=hi_,
                                                         floor_mult=flm)})
        C.sort(key=lambda z: z["ts"])
        return take(C, slots=slots, equity=eq0, risk_pct=risk_pct,
                    sl_margin_pct=slmp, scan_s=scan_s, one_per_scan=True,
                    calm_max=0.0)

    books = {}
    for label, m in CELLS:
        books[m] = run(m)
        print("  %-26s %4d fills" % (label, len(books[m])))
    print()

    BASE = books[3.0]
    if not BASE:
        print("no fills at the live width")
        return 1
    t0, t1 = BASE[0]["ts"], BASE[-1]["ts"]
    base_usd = sum(z["usd"] for z in BASE)

    def halves(f, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(z["usd"] for z in f if z["ts"] < cut),
                sum(z["usd"] for z in f if z["ts"] >= cut))

    print("=" * 116)
    print("TREND STOP WIDTH - dollars, because R rescales with the stop and is NOT comparable")
    print("=" * 116)
    print("%-26s %6s %7s %6s %9s %9s %9s %8s %6s"
          % ("stop width", "fills", "stopped", "win%", "net $", "vs live",
             "ex-top5", "$/fill", "both?"))
    for label, m in CELLS:
        f = books[m]
        if not f:
            print("%-26s   no fills" % label)
            continue
        u = sum(z["usd"] for z in f)
        vals = sorted((z["usd"] for z in f), reverse=True)
        ex5 = sum(vals[max(1, len(vals) // 20):])
        stopped = sum(1 for z in f if z["kind"] == "stop")
        wins = sum(1 for z in f if z["net"] > 0)
        ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                    *halves(f, fr), *halves(BASE, fr))
                 for fr in (0.35, 0.425, 0.5, 0.575, 0.65))
        print("%-26s %6d %7d %5.0f%% %+9.2f %+9.2f %+9.2f %8.3f %6s"
              % (label, len(f), stopped, 100.0 * wins / len(f), u, u - base_usd,
                 ex5, u / len(f), "base" if m == 3.0 else ("YES" if ok else "no")))

    print()
    print("=" * 116)
    print("MECHANICS PER CELL - why the dial does what it does")
    print("=" * 116)
    print("%-26s %10s %10s %10s %10s   %s"
          % ("stop width", "mean lev", "mean stop%", "cap binds", "mean $risk", "exit mix"))
    for label, m in CELLS:
        f = books[m]
        if not f:
            continue
        import collections
        mix = collections.Counter(z["kind"] for z in f)
        print("%-26s %10.2f %9.2f%% %9.0f%% %10.2f   %s"
              % (label, sum(z["lev"] for z in f) / len(f),
                 100.0 * sum(z["slf"] for z in f) / len(f),
                 100.0 * sum(z["capped"] for z in f) / len(f),
                 sum(z["risk_usdt"] for z in f) / len(f),
                 dict(mix.most_common())))
    print()
    print("The conditional-expectancy engine found leverage >= 7 reliably loses.")
    print("Read the mean-leverage column against that before reading net $:")
    print("a tight stop does not merely cut sooner, it pins leverage at the cap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
