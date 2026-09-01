"""How many concurrent TREND slots? Never swept.

    railway ssh --service Futures-bot -> /opt/venv/bin/python tools/pit_trend_slots.py

WHY THIS EXISTS. pit_slots.py swept WILDCARD's slot count and never touched
TREND's, which sits at FUTURES_TREND_MAX_POSITIONS=2 against a code default of 3
with no measurement behind either. The trigger sweep (pit_trend_trigger.py,
section D) then produced an accidental reading on it: raising the trigger to 5%
dropped 85 band trades but ALSO displaced 29 trades at >=5% ROC worth +$61.27.
Displacement that large means the 2-slot book is turning candidates away
constantly - a bigger number than anything the trigger itself moved.

READ $/FILL, NOT NET $. More slots always take more fills, so net $ rises almost
mechanically. The question is whether the MARGINAL fill pays.

THE FIDELITY GAP THIS ONE CANNOT CLOSE, and it points AGAINST extra slots.
TREND and WILDCARD draw margin from the same account. This replay sizes TREND
off the full equity as though WILDCARD held nothing, because reconstructing the
joint book would need both sleeves replayed on one clock. Two consequences:

  1. magnitude only - TREND positions would really be smaller, scaling every
     dollar figure down without changing the ranking between slot counts.
  2. DIRECTIONAL, and it is not modelled: every extra TREND slot consumes margin
     that WILDCARD would otherwise have used. Over the trailing 28 days WILDCARD
     netted +$30.91 against TREND's +$4.77 - it is ~6.5x more productive per
     dollar of margin. Moving capacity from WILDCARD to TREND is value-
     destroying at that ratio unless the marginal TREND fill is very strong.

So a slot count that merely looks positive here is not good enough. It has to
beat the WILDCARD dollars it would displace.

READ-ONLY.
"""
from __future__ import annotations

import datetime as dt
import json
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
from pit_book import take  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

TAIL = 300
SLOTS = (1, 2, 3, 4, 5, 6)
STATE = "/data/futures_runtime_state.json"


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def _ts(rec, key):
    try:
        return dt.datetime.fromisoformat(str(rec.get(key) or "")).timestamp()
    except Exception:
        return 0.0


def live_margin_competition(eq):
    """What share of equity does WILDCARD actually hold, and when?"""
    try:
        state = json.load(open(STATE))
    except Exception:
        return None
    now = time.time()
    tr = [t for t in (state.get("trade_history") or [])
          if _ts(t, "exit_time") >= now - 28 * 86400]
    if not tr:
        return None
    ev = []
    for t in tr:
        sl = "TREND" if str(t.get("entry_signal") or "").startswith("TREND") else "WILDCARD"
        m = float(t.get("margin_usdt") or 0.0)
        if m <= 0:
            continue
        ev.append((_ts(t, "entry_time"), +m, sl))
        ev.append((_ts(t, "exit_time"), -m, sl))
    if not ev:
        return None
    ev.sort()
    cur = {"WILDCARD": 0.0, "TREND": 0.0}
    prev = ev[0][0]
    acc = {"WILDCARD": 0.0, "TREND": 0.0, "BOTH": 0.0}
    peak = 0.0
    span = 0.0
    for ts_, dm, sl in ev:
        dtt = ts_ - prev
        if dtt > 0:
            span += dtt
            acc["WILDCARD"] += cur["WILDCARD"] * dtt
            acc["TREND"] += cur["TREND"] * dtt
            acc["BOTH"] += (cur["WILDCARD"] + cur["TREND"]) * dtt
        cur[sl] += dm
        peak = max(peak, cur["WILDCARD"] + cur["TREND"])
        prev = ts_
    if span <= 0:
        return None
    return {"wild": acc["WILDCARD"] / span, "trend": acc["TREND"] / span,
            "both": acc["BOTH"] / span, "peak": peak, "eq": eq}


def main() -> int:
    print("*** SIMULATED REPLAY on the CORRECTED book - model dollars, not P&L ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    now = int(time.time())
    days = _env("PJ_DAYS", 220)
    eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    live_slots = int(_env("FUTURES_TREND_MAX_POSITIONS", 2))
    tp_r = _env("FUTURES_TREND_TP_R", 3.0)
    scan_s = _env("FUTURES_TREND_SCAN_INTERVAL_SECONDS", 900.0)
    slmp = _env("FUTURES_MAX_SL_MARGIN_PCT", 20.0)
    lo_, hi_ = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    min_roc = _env("FUTURES_TREND_MIN_ROC", 0.04)
    syms = tuple(s.strip() for s in
                 (os.environ.get("FUTURES_TREND_SYMBOLS") or
                  "ETH_USDT,XRP_USDT,ZEC_USDT").split(",") if s.strip())
    horizon = shadow.CONVEX_HORIZON_S
    fn = ratchet(_env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0),
                 _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75),
                 base=_env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50), arm=1.0)

    print("universe %s | live %d slots | TP %.1fR | trigger %.1f%% | horizon %.0fh"
          % (",".join(s.replace("_USDT", "") for s in syms), live_slots, tp_r,
             min_roc * 100, horizon / 3600.0))
    print("equity $%.2f | risk %.3f%% of AVAILABLE | sl margin %.0f%%\n"
          % (eq0, risk_pct * 100, slmp))

    comp = live_margin_competition(eq0)
    if comp:
        print("=" * 92)
        print("LIVE MARGIN COMPETITION, trailing 28 days (time-weighted)")
        print("=" * 92)
        print("  WILDCARD holds on average   $%6.2f  = %5.1f%% of equity"
              % (comp["wild"], 100 * comp["wild"] / comp["eq"]))
        print("  TREND holds on average      $%6.2f  = %5.1f%% of equity"
              % (comp["trend"], 100 * comp["trend"] / comp["eq"]))
        print("  both sleeves together       $%6.2f  = %5.1f%% of equity"
              % (comp["both"], 100 * comp["both"] / comp["eq"]))
        print("  PEAK simultaneous margin    $%6.2f  = %5.1f%% of equity"
              % (comp["peak"], 100 * comp["peak"] / comp["eq"]))
        print("  -> this replay gives TREND the whole account. Real TREND fills")
        print("     size off roughly %.0f%% of it once WILDCARD is holding."
              % (100 * (1 - comp["wild"] / comp["eq"])))
        print()

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
                      "exit_ts": float(g[1]),
                      "mult": regime_size_multiplier(eff, lo=lo_, hi=hi_, floor_mult=flm)})
    C.sort(key=lambda z: z["ts"])
    print("LONG candidates at the live %.1f%% trigger: %d\n" % (min_roc * 100, len(C)))

    def book(n):
        return take(C, slots=n, equity=eq0, risk_pct=risk_pct, sl_margin_pct=slmp,
                    scan_s=scan_s, one_per_scan=True, calm_max=0.0)

    BASE = book(live_slots)
    if not BASE:
        print("no fills at the live slot count")
        return 1
    t0, t1 = BASE[0]["ts"], BASE[-1]["ts"]
    base_usd = sum(z["usd"] for z in BASE)

    def halves(f, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(z["usd"] for z in f if z["ts"] < cut),
                sum(z["usd"] for z in f if z["ts"] >= cut))

    def exposure(f):
        """time-weighted and peak margin this book commits, as % of equity"""
        ev = []
        for z in f:
            m = z["risk_usdt"] * 100.0 / slmp if slmp > 0 else z["risk_usdt"]
            ev.append((z["ts"], +m))
            ev.append((z["exit_ts"], -m))
        ev.sort()
        cur = pk = area = 0.0
        prev = ev[0][0]
        for ts_, dm in ev:
            if ts_ > prev:
                area += cur * (ts_ - prev)
                prev = ts_
            cur += dm
            pk = max(pk, cur)
        span = t1 - t0
        return (100.0 * area / span / eq0 if span else 0.0, 100.0 * pk / eq0)

    print("=" * 108)
    print("TREND SLOT SWEEP - live is %d slots" % live_slots)
    print("=" * 108)
    print("%-6s %6s %10s %10s %10s %8s %9s %7s %7s %6s   %s"
          % ("slots", "fills", "net $", "vs live", "ex-top5", "$/fill", "marginal",
             "avg exp", "pk exp", "both?", "thirds"))
    prev_u = prev_n = None
    for n in SLOTS:
        f = book(n)
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
        marg = ("%+8.3f" % ((u - prev_u) / (len(f) - prev_n))
                if prev_u is not None and len(f) > prev_n else "       -")
        av, pk = exposure(f)
        print("%-6d %6d %+10.2f %+10.2f %+10.2f %8.3f %9s %6.1f%% %6.1f%% %6s   %+6.1f %+6.1f %+6.1f"
              % (n, len(f), u, u - base_usd, ex5, u / len(f), marg, av, pk,
                 "base" if n == live_slots else ("YES" if ok else "no"), *th))
        prev_u, prev_n = u, len(f)

    print()
    print("'marginal' is the $ per EXTRA fill that this slot count bought over the")
    print("row above it. A positive net $ with a marginal below the row above means")
    print("the extra slot is diluting - it is buying turnover, not edge.")
    if comp:
        print()
        print("AND THE COMPETITION: every extra TREND slot takes margin WILDCARD would")
        print("have used. WILDCARD netted +$30.91 in 28 days against TREND's +$4.77,")
        print("so a marginal TREND fill has to beat ~6.5x its own weight in WILDCARD")
        print("dollars before it is worth the capacity. Nothing in this table prices")
        print("that - it is the reason a merely-positive row does not justify shipping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
