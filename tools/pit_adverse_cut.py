"""Cut a losing trade before it reaches the stop. Does it pay?

    railway run --service Futures-bot python tools/pit_adverse_cut.py

THE PROPOSAL (owner, 2026-09-01): once a trade is ~0.3R underwater, arm something
on the losing side so it does not have to travel the full -1R. Trial 18's four
losses averaged -$3.11 against +$1.30 for the eight wins; capping the loss at
0.5R instead of 1R would halve that arm.

WHY THIS IS NOT THE RETRACTED STOP-WIDTH STUDY. That one moved SL_ATR_MULT at
entry, which changes leverage and margin so that 1R stays a constant dollar
amount - a different stop but the same risk. This keeps entry sizing untouched
and exits early, so a loss costs 0.5R instead of 1R in real dollars. The price is
paid in trades that would have recovered and now cannot.

IT DOES NOT INTERACT WITH THE PROFIT TRAIL. The trail arms at +1R and floors at
>= 0.5 x peak, so an armed trade can never subsequently print -0.3R - the trail
would have closed it first. The adverse cut therefore only ever touches trades
that never armed. Pure loser-mitigation, cleanly separable.

CELLS: cut at -0.3R / -0.4R / -0.5R / -0.7R against the live -1.0R stop. Plus a
DELAYED variant that requires the trade to still be under water one bar later,
to test whether the damage is intrabar noise rather than a real move.

Resolution is adverse-first within a bar, the same pessimistic convention the
shipped resolver uses. Live sizing, continuous slot book, half-split swept
35-65%, and net $ per third.

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

BAR, TAIL = 900, 260
CELLS = [("live: stop at -1.0R", None, False),
         ("cut at -0.3R", 0.3, False),
         ("cut at -0.4R", 0.4, False),
         ("cut at -0.5R", 0.5, False),
         ("cut at -0.7R", 0.7, False),
         ("cut -0.3R, 1 bar delay", 0.3, True),
         ("cut -0.5R, 1 bar delay", 0.5, True)]


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def walk(bars, i0, entry, sl, tp, side, horizon_s, cost_r, now_ts,
         arm_r, retain, ratchet_r, ratchet_hi, cut_r, delayed):
    """Resolve one trade. R is always in units of the ORIGINAL stop distance."""
    sgn = 1.0 if side == "LONG" else -1.0
    one = abs(entry - sl)
    if one <= 0:
        return None
    t0 = bars[i0][0]
    peak = 0.0
    last = entry
    seen = False
    pending_cut = None
    floor_min = 1.5 * cost_r
    for k in range(i0 + 1, len(bars)):
        ts, hi, lo, close = bars[k]
        if ts - t0 > horizon_s:
            break
        seen = True
        adverse = ((lo if sgn > 0 else hi) - entry) * sgn / one
        favour = ((hi if sgn > 0 else lo) - entry) * sgn / one

        # 1. profit trail, checked before the hard stop exactly as live does
        if peak >= arm_r:
            frac = ratchet_hi if (ratchet_r > 0 and peak >= ratchet_r) else retain
            level = max(frac * peak, floor_min)
            if level < peak and adverse <= level:
                return (level - cost_r, ts, "trail")

        # 2. a cut confirmed on the previous bar's CLOSE. It exits at that
        # close, NOT at the -cut_r threshold. The first version of this booked
        # exactly -cut_r regardless of where price actually was, which credits a
        # fill above the market on every trade that closed below the level - the
        # same optimistic-fill error that inflated the near-TP study. On this
        # data it was worth about $96, i.e. the entire apparent finding.
        if pending_cut is not None:
            return (pending_cut - cost_r, ts, "cut_close")

        # 3. the hard stop
        if adverse <= -1.0:
            return (-1.0 - cost_r, ts, "stop")

        # 4. the adverse cut. Two triggers, deliberately distinguished:
        #    intrabar - the LOW touches -cut_r; a resting order would fill there
        #    on-close - the bar CLOSES below -cut_r; exit at that close, wherever
        #               it is. This is the honest model of a software cut that
        #               waits for confirmation instead of chasing wicks.
        if cut_r is not None:
            close_r = (close - entry) * sgn / one
            if not delayed:
                if adverse <= -cut_r:
                    return (-cut_r - cost_r, ts, "cut")
            elif close_r <= -cut_r:
                pending_cut = close_r

        # 5. target
        if favour >= (abs(tp - entry) / one):
            return (abs(tp - entry) / one - cost_r, ts, "tp")
        peak = max(peak, favour)
        last = close
    if not seen:
        return None
    if now_ts - t0 < horizon_s:
        return None
    return (((last - entry) * sgn / one) - cost_r, t0 + horizon_s, "timeout")


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
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    floor_live = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    arm_r = _env("FUTURES_CONVEX_TRAIL_ARM_R", 1.0)
    retain = _env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50)
    rr = _env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0)
    rh = _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75)
    print("equity $%.2f | trail arm %.1fR retain %.2f ratchet %.1fR->%.2f\n"
          % (eq0, arm_r, retain, rr, rh))

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

    SIG = []
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
            eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
            SIG.append({"ts": bars[i][0], "sym": s, "bars": bars, "i": i, "e": e, "sl": sl,
                        "tp": float(sig.tp_price), "side": sig.side,
                        "day": day_key(bars[i][0]),
                        "cost": shadow.cost_r({"entry": e, "sl": sl,
                                               "tp": float(sig.tp_price), "side": sig.side}),
                        "mult": regime_size_multiplier(eff, lo=lo, hi=hi, floor_mult=flm)})
    SIG.sort(key=lambda z: z["ts"])
    print("signals: %d\n" % len(SIG))

    def cell(cut_r, delayed):
        out = []
        for x in SIG:
            g = walk(x["bars"], x["i"], x["e"], x["sl"], x["tp"], x["side"],
                     shadow.CONVEX_HORIZON_S, x["cost"], now, arm_r, retain, rr, rh,
                     cut_r, delayed)
            if g is None:
                continue
            out.append({**x, "net": float(g[0]), "exit_ts": float(g[1]), "kind": str(g[2])})
        out.sort(key=lambda z: z["ts"])
        slots, per, taken = [], {}, []
        for z in out:
            if band and z["sym"] in PIT.get(z["day"], ()):
                continue
            slots[:] = [q for q in slots if q > z["ts"]]
            per[z["sym"]] = [q for q in per.get(z["sym"], []) if q > z["ts"]]
            if per[z["sym"]] or len(slots) >= 3:
                continue
            slots.append(z["exit_ts"])
            per[z["sym"]].append(z["exit_ts"])
            taken.append(z)
        return taken

    def usd(f):
        return sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f)

    BASE = cell(None, False)
    t0, t1 = BASE[0]["ts"], BASE[-1]["ts"]
    bu = usd(BASE)

    def halves(f, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f if z["ts"] < cut),
                sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f if z["ts"] >= cut))

    print("BASE: $%+.2f over %d fills\n" % (bu, len(BASE)))
    print("%-24s %6s %9s %9s %9s %6s  %s"
          % ("cell", "fills", "net $", "vs live", "ex-top5", "both?", "exits"))
    for name, cr, dl in CELLS:
        f = cell(cr, dl)
        if not f:
            continue
        u = usd(f)
        vals = sorted((z["net"] * risk_pct * eq0 * z["mult"] for z in f), reverse=True)
        ex5 = sum(vals[max(1, len(vals) // 20):])
        ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                    *halves(f, fr), *halves(BASE, fr))
                 for fr in (0.35, 0.425, 0.5, 0.575, 0.65))
        kinds = {}
        for z in f:
            kinds[z["kind"]] = kinds.get(z["kind"], 0) + 1
        base = cr is None
        print("%-24s %6d %+9.2f %+9.2f %+9.2f %6s  %s"
              % (name, len(f), u, u - bu, ex5,
                 "base" if base else ("YES" if ok else "no"),
                 " ".join("%s:%d" % (k, v) for k, v in sorted(kinds.items()))))
    print("\nA cut can only ever convert a -1R stop into a smaller loss, at the cost")
    print("of trades that would have recovered. If net $ falls, the recoveries were")
    print("worth more than the saved stop distance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
