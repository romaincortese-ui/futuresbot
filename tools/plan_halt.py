"""Would a -10% intra-week halt have helped or hurt? Measured, not argued.

    railway run --service Futures-bot python tools/plan_halt.py

THE PROPOSAL (owner, 2026-08-29): during the funded week, if the bot loses 10% of
account balance, close all open trades and stop until manual restart.

It splits into two mechanisms with very different risk:

  A. HALT NEW ENTRIES at -X%. This already exists - USE_DRAWDOWN_KILL is on and
     _drawdown_size_multiplier returns 0 past DRAWDOWN_HALT_PCT - it is simply not
     wired into the convex sleeves (FUTURES_CONVEX_DRAWDOWN_BRAKE defaults False).
     Turning it on is a config change to tested machinery.

  B. FORCE-CLOSE the open book at -X%. This does NOT exist. It would be a new exit
     path in the trading loop, written days before real money goes in, and it fires
     on PORTFOLIO state rather than trade state - it can close a position that is
     most of the way to its target because two others lost.

This measures both against the replay.

WHAT IS EXACT AND WHAT IS NOT. (A) is exact: halting entries only removes fills that
would have started after the halt, and the replay knows every fill's start. (B) is
NOT exactly computable here, because a resolved replay fill has an entry, an exit and
a net - not the intra-trade path - so the mark at the halt instant is unknown. What
IS computable, and is the question that actually decides it, is the EVENTUAL outcome
of the positions that were open when the halt fired. If those went on to make money,
force-closing them destroyed value; if they went on to lose, it saved it. That is
reported as FORCE-CLOSE DELTA and is a directional answer, not a precise one.

Drawdown is measured from the WINDOW START, which is what "loses 10% of the account
balance" means for a funded week that begins on a known date. Peak-to-trough is
reported alongside because it triggers earlier and is the stricter reading.

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

BAR, TAIL, DAY = 900, 260, 86400
WINDOW_D = 7.0
THRESHOLDS = (0.05, 0.08, 0.10, 0.15)


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def pct(v, q):
    if not v:
        return 0.0
    s = sorted(v)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars, NOT account P&L. ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 220), int(_env("PJ_POOL", 170))
    now = int(time.time())
    eq_now = rt._last_known_equity() or 172.0
    eq = eq_now + _env("PLAN_ADD", 900.0)
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    lo, hi = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    floor_live = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band_live = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    print("funded equity $%.2f | 1R $%.2f | scaler floor %.2f\n" % (eq, risk_pct * eq, flm))

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
    PIT = pit_majors(daily_turnover(ROLLS), n=band_live)

    live_floor_fn = ratchet(3.0, 0.75)
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
            C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]), "exit_ts": float(g[1]),
                      "day": day_key(bars[i][0]),
                      "mult": regime_size_multiplier(eff, lo=lo, hi=hi, floor_mult=flm)})
    C.sort(key=lambda x: x["ts"])

    slots, per, TAKEN = [], {}, []
    for x in C:
        if band_live and x["sym"] in PIT.get(x["day"], ()):
            continue
        slots[:] = [q for q in slots if q > x["ts"]]
        per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
        if per[x["sym"]] or len(slots) >= 3:
            continue
        slots.append(x["exit_ts"])
        per[x["sym"]].append(x["exit_ts"])
        TAKEN.append(x)
    for x in TAKEN:
        x["usd"] = x["net"] * risk_pct * eq * x["mult"]
    t0, t1 = TAKEN[0]["ts"], TAKEN[-1]["ts"]
    print("live cell: %d fills over %.0f days\n" % (len(TAKEN), (t1 - t0) / DAY))

    def window(d):
        return [x for x in TAKEN if d <= x["ts"] < d + WINDOW_D * DAY]

    def run(fills, thr, from_peak):
        """Return (final_usd, halted_at_or_None, open_at_halt list)."""
        cum, peak, limit = 0.0, 0.0, -thr * eq
        order = sorted(fills, key=lambda x: x["exit_ts"])
        halt_t = None
        for x in order:
            cum += x["usd"]
            peak = max(peak, cum)
            ref = (cum - peak) if from_peak else cum
            if ref <= limit:
                halt_t = x["exit_ts"]
                break
        if halt_t is None:
            return sum(x["usd"] for x in fills), None, []
        # entries after the halt never happen; positions already open still resolve
        kept = [x for x in fills if x["ts"] <= halt_t]
        openat = [x for x in fills if x["ts"] <= halt_t < x["exit_ts"]]
        return sum(x["usd"] for x in kept), halt_t, openat

    for from_peak in (False, True):
        label = "PEAK-TO-TROUGH" if from_peak else "FROM WINDOW START"
        print("=== HALT ON DRAWDOWN %s, funded equity $%.0f ===" % (label, eq))
        print("%-8s %7s %10s %10s %10s %10s %11s"
              % ("thresh", "fires", "med no-halt", "med halted", "worst n/h",
                 "worst halt", "force-close"))
        base = []
        d = t0
        while d + WINDOW_D * DAY <= t1:
            base.append(sum(x["usd"] for x in window(d)))
            d += DAY
        for thr in THRESHOLDS:
            res, fired, fc = [], 0, 0.0
            d = t0
            while d + WINDOW_D * DAY <= t1:
                f = window(d)
                v, ht, openat = run(f, thr, from_peak)
                res.append(v)
                if ht is not None:
                    fired += 1
                    fc += sum(x["usd"] for x in openat)
                d += DAY
            print("%-8s %6.0f%% %+10.2f %+10.2f %+10.2f %+10.2f %+11.2f"
                  % ("-%.0f%%" % (100 * thr), 100.0 * fired / len(res),
                     pct(base, 0.5), pct(res, 0.5), min(base), min(res),
                     fc / max(1, fired)))
        print("")
    print("fires       = %% of 7-day windows in which the halt triggers")
    print("med halted  = median window $ with entries halted (positions still resolve)")
    print("force-close = mean $ the still-open positions went on to make AFTER the")
    print("              halt fired. POSITIVE means closing them destroys that much;")
    print("              NEGATIVE means closing them saves it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
