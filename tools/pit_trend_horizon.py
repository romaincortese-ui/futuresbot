"""Should TREND hold longer, and is its 4% trigger leaving trades on the table?

    railway run --service Futures-bot python tools/pit_trend_horizon.py

TWO OWNER HYPOTHESES (2026-09-01), both testable and both about the same idea:
majors move slower than the small-cap band, so the sleeve built for them may be
mis-tuned by inheriting the wildcard's settings.

  1. THE CLOCK. TREND runs the SAME 24h convex time stop as the wildcard -
     FUTURES_WILDCARD_CONVEX_EXIT_ENABLED governs WILDCARD, SQUEEZE and TREND
     alike, and CONVEX_TIME_STOP_HOURS is one global default. A sleeve whose
     docstring says "sustained multi-hour directional moves" is being closed on
     the clock designed for a 3h alt impulse. If a major's move takes two days
     to play out, the clock is cutting winners at the mark.

  2. THE TRIGGER. FUTURES_TREND_MIN_ROC=0.04 over 24h. On BTC that is a large
     move; the seasonality run showed BTC firing on only 5.8-12.1% of 4h bars
     depending on month. A lower threshold trades more often - the question is
     whether the extra signals carry the same edge or dilute it.

Swept independently at the live value of the other, then jointly on the winners.
Live sizing, 2 slots, long-only, retention 0.50 + ratchet - the live config.
Half-split swept 35-65% and net $ per third, because a single number at this
sample size means nothing.

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
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

BAR, TAIL, HOUR = 900, 300, 3600
LIVE_SET = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
POOL = ("BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "ZEC_USDT")
HORIZONS = (24, 36, 48, 72, 96)
ROCS = (0.03, 0.035, 0.04, 0.05, 0.06)


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
    eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    lo, hi = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    tp_r = _env("FUTURES_TREND_TP_R", 3.0)
    slots = int(_env("FUTURES_TREND_MAX_POSITIONS", 2))
    live_roc = _env("FUTURES_TREND_MIN_ROC", 0.04)
    print("equity $%.2f | %d slots | TP %.1fR | live trigger %.1f%% | live clock 24h\n"
          % (eq0, slots, tp_r, live_roc * 100))

    frames, rep = fetch_frames(cl, POOL, days=days, workers=5, min_bars=140, now_ts=now)
    print(rep)
    PREP = {}
    for s, df in frames.items():
        c = [float(x) for x in df["close"]]
        ts_all = [float(x.timestamp()) for x in df.index]
        PREP[s] = (df, list(zip(ts_all, [float(x) for x in df["high"]],
                                [float(x) for x in df["low"]], c)), c)
    fn = ratchet(3.0, 0.75, base=_env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50), arm=1.0)

    def signals(min_roc):
        """Regenerate the candidate list at a given trigger threshold."""
        os.environ["FUTURES_TREND_MIN_ROC"] = str(min_roc)
        from futuresbot.trend import detect_trend_signal, lookback_bars
        lb = lookback_bars()
        out = []
        for s, (df, bars, c) in PREP.items():
            for i in range(lb + 40, len(c)):
                sig = detect_trend_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                if sig is None:
                    continue
                e, sl = float(sig.entry_price), float(sig.sl_price)
                if abs(e - sl) <= 0 or e <= 0:
                    continue
                eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
                out.append({"ts": bars[i][0], "sym": s, "side": sig.side, "bars": bars,
                            "i": i, "e": e, "sl": sl, "tp": float(sig.tp_price),
                            "atr": float(getattr(sig, "atr_pct", 0.0) or 0.0),
                            "cost": shadow.cost_r({"entry": e, "sl": sl,
                                                   "tp": float(sig.tp_price),
                                                   "side": sig.side}),
                            "mult": regime_size_multiplier(eff, lo=lo, hi=hi,
                                                           floor_mult=flm)})
        out.sort(key=lambda z: z["ts"])
        return out

    CACHE = {}

    def cell(min_roc, hours, long_only=True):
        key = round(min_roc, 4)
        if key not in CACHE:
            CACHE[key] = signals(min_roc)
        res = []
        for x in CACHE[key]:
            if long_only and x["side"] != "LONG":
                continue
            g = resolve(x["bars"], x["i"], x["e"], x["sl"], x["tp"], tp_r, x["side"],
                        hours * HOUR, x["cost"], fn, x["atr"], now)
            if g is None:
                continue
            res.append({**x, "net": float(g[0]), "exit_ts": float(g[1]), "kind": str(g[2])})
        res.sort(key=lambda z: z["ts"])
        occ, per, taken = [], {}, []
        for z in res:
            if z["sym"] not in LIVE_SET:
                continue
            occ[:] = [q for q in occ if q > z["ts"]]
            per[z["sym"]] = [q for q in per.get(z["sym"], []) if q > z["ts"]]
            if per[z["sym"]] or len(occ) >= slots:
                continue
            occ.append(z["exit_ts"])
            per[z["sym"]].append(z["exit_ts"])
            taken.append(z)
        return taken

    def usd(f):
        return sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f)

    BASE = cell(live_roc, 24)
    if not BASE:
        print("no live-cell fills")
        return 0
    t0, t1 = BASE[0]["ts"], BASE[-1]["ts"]
    bu = usd(BASE)

    def halves(f, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f if z["ts"] < cut),
                sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f if z["ts"] >= cut))

    def thirds(f):
        out = []
        for k in range(3):
            a = t0 + k * (t1 - t0) / 3.0
            b = t0 + (k + 1) * (t1 - t0) / 3.0 + (1 if k == 2 else 0)
            out.append(sum(z["net"] * risk_pct * eq0 * z["mult"]
                           for z in f if a <= z["ts"] < b))
        return out

    def row(label, f, base=False):
        if not f:
            print("%-22s      (no fills)" % label)
            return
        kinds = {}
        for z in f:
            kinds[z["kind"]] = kinds.get(z["kind"], 0) + 1
        ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                    *halves(f, fr), *halves(BASE, fr))
                 for fr in (0.35, 0.425, 0.5, 0.575, 0.65))
        th = thirds(f)
        hold = sum((z["exit_ts"] - z["ts"]) for z in f) / len(f) / HOUR
        print("%-22s %5d %+9.2f %+9.2f %6.1fh %6s  %+6.1f %+6.1f %+6.1f  %s"
              % (label, len(f), usd(f), usd(f) - bu, hold,
                 "base" if base else ("YES" if ok else "no"), *th,
                 " ".join("%s:%d" % (k[:4], v) for k, v in sorted(kinds.items()))))

    print("%-22s %5s %9s %9s %7s %6s  %s"
          % ("cell", "fills", "net $", "vs live", "avg hold", "both?", "thirds / exits"))
    print("--- 1. THE CLOCK, at the live 4%% trigger ---")
    for h in HORIZONS:
        row("clock %3dh" % h, cell(live_roc, h), base=(h == 24))
    print("--- 2. THE TRIGGER, at the live 24h clock ---")
    for r in ROCS:
        row("trigger %.1f%%" % (r * 100), cell(r, 24), base=(abs(r - live_roc) < 1e-9))
    print("--- 3. JOINT: a lower trigger with a longer clock ---")
    for r in (0.03, 0.035):
        for h in (48, 72):
            row("trigger %.1f%% clock %dh" % (r * 100, h), cell(r, h))
    print("\nboth? = beats the live cell in BOTH halves at every boundary 35-65%.")
    print("avg hold is the mean time from entry to exit - if it barely moves when")
    print("the clock is extended, the clock was not the binding constraint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
