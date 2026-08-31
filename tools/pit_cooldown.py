"""Should a symbol be frozen after it closes? Measured, in dollars.

    railway run --service Futures-bot python tools/pit_cooldown.py

THE OBSERVATION (owner, 2026-08-31). ZEC_USDT closed on the convex retention trail
at 15:11 for +$1.15, and the trend sleeve re-entered the SAME symbol at 16:48 -
1h37m later and 2.1% HIGHER - then lost $4.55 on a hard stop. The trail's whole
purpose is to protect built profit; re-entering immediately at a worse price
converts a protected gain into a fresh unprotected position and pays a second
round trip for the privilege.

THE GAP IS REAL. `_pmt_stop_chase_blocked` (runtime.py:354) is the only cooldown
in the bot and it is reachable only from PMT paths (7949, 10075). A
CONVEX_RETENTION_TRAIL or CONVEX_TIME_STOP close imposes no cooldown at all, so
the same symbol can be re-entered on the very next scan.

BUT THE PROPOSED SCOPE MAY BE WRONG. ZEC's six trades to 08-31 read:
    +1.00 trail | -2.11 stop | -3.63 stop | -1.94 stop | +1.15 trail | -4.55 stop
Net -$10.08. The re-entries that followed a STOP lost too, so the pattern might
be "this symbol keeps losing" or "re-entry generally loses", not "trail re-entry
loses". A rule shaped by the one case that was noticed is exactly how this
project has previously shipped things that measured negative.

So this sweeps the scope as well as the duration:
    trail-only  - the owner's proposal
    any-exit    - freeze after every convex close
    loss-only   - freeze only after a losing close
    win-only    - freeze only after a winning close (the control that says whether
                  'protect the banked profit' is really the mechanism)

METHOD. One detector pass, the live continuous slot book, live sizing, and a
half-split swept across boundaries 35-65% - a single midpoint passed the retracted
stop-width finding. Scored at the trial-18 scaler floor of 0.50.

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

BAR, TAIL, DAY, HOUR = 900, 260, 86400, 3600

# (label, scope, hours) - scope decides WHICH closes start a freeze
CELLS = [
    ("base - no cooldown",        None,      0),
    ("trail-only  2h",            "trail",   2),
    ("trail-only  6h",            "trail",   6),
    ("trail-only 12h",            "trail",  12),
    ("trail-only 24h",            "trail",  24),
    ("any exit    6h",            "any",     6),
    ("any exit   12h",            "any",    12),
    ("any exit   24h",            "any",    24),
    ("loss-only   6h",            "loss",    6),
    ("loss-only  12h",            "loss",   12),
    ("loss-only  24h",            "loss",   24),
    ("win-only   12h",            "win",    12),
    # The owner's exact proposal (2026-08-31): same SYMBOL and same DIRECTION,
    # frozen after a retention-trail close. Swept because the duration he named
    # (6h) is a guess, and a rule that only works at one duration is a lucky pick.
    ("trail SAME-DIR  2h",        "trail_dir",   2),
    ("trail SAME-DIR  4h",        "trail_dir",   4),
    ("trail SAME-DIR  6h",        "trail_dir",   6),
    ("trail SAME-DIR 12h",        "trail_dir",  12),
    ("trail SAME-DIR 24h",        "trail_dir",  24),
    ("any   SAME-DIR  6h",        "any_dir",     6),
]


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
    days, pool_n = _env("PJ_DAYS", 220), int(_env("PJ_POOL", 170))
    now = int(time.time())
    eq0 = rt._last_known_equity() or 172.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    lo, hi = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    floor_live = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band_live = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    print("equity $%.2f | risk %.4f | scaler floor %.2f\n" % (eq0, risk_pct, flm))

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
                      "kind": str(g[2]), "day": day_key(bars[i][0]), "side": str(sig.side),
                      "mult": regime_size_multiplier(eff, lo=lo, hi=hi, floor_mult=flm)})
    C.sort(key=lambda x: x["ts"])
    print("candidates: %d\n" % len(C))

    def book(scope, hours):
        """The live slot book plus a per-symbol freeze after a qualifying close."""
        slots, per, frozen, out = [], {}, {}, []
        for x in C:
            if band_live and x["sym"] in PIT.get(x["day"], ()):
                continue
            key = (x["sym"], x["side"]) if scope and scope.endswith("_dir") else x["sym"]
            if frozen.get(key, 0.0) > x["ts"]:
                continue
            slots[:] = [q for q in slots if q > x["ts"]]
            per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
            if per[x["sym"]] or len(slots) >= 3:
                continue
            slots.append(x["exit_ts"])
            per[x["sym"]].append(x["exit_ts"])
            out.append(x)
            if scope and hours > 0:
                base_scope = scope[:-4] if scope.endswith("_dir") else scope
                fire = (base_scope == "any"
                        or (base_scope == "trail" and x["kind"] == "trail")
                        or (base_scope == "loss" and x["net"] < 0)
                        or (base_scope == "win" and x["net"] > 0))
                if fire:
                    frozen[key] = x["exit_ts"] + hours * HOUR
        return out

    def usd(fills):
        return sum(f["net"] * risk_pct * eq0 * f["mult"] for f in fills)

    BASE = book(None, 0)
    t0, t1 = BASE[0]["ts"], BASE[-1]["ts"]
    base_usd = usd(BASE)

    def halves(fills, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(f["net"] * risk_pct * eq0 * f["mult"] for f in fills if f["ts"] < cut),
                sum(f["net"] * risk_pct * eq0 * f["mult"] for f in fills if f["ts"] >= cut))

    print("BASE (live rules, no cooldown): $%+.2f over %d fills\n" % (base_usd, len(BASE)))
    print("%-22s %6s %9s %9s %9s %6s" % ("cell", "fills", "net $", "vs base", "ex-top5", "both?"))
    for label, scope, hours in CELLS:
        fills = book(scope, hours)
        if not fills:
            continue
        u = usd(fills)
        vals = sorted((f["net"] * risk_pct * eq0 * f["mult"] for f in fills), reverse=True)
        ex5 = sum(vals[max(1, len(vals) // 20):])
        ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                    *halves(fills, fr), *halves(BASE, fr))
                 for fr in (0.35, 0.425, 0.5, 0.575, 0.65))
        base = scope is None
        print("%-22s %6d %+9.2f %+9.2f %+9.2f %6s"
              % (label, len(fills), u, u - base_usd, ex5,
                 "base" if base else ("YES" if ok else "no")))

    # How often does the pattern the owner saw actually occur?
    print("\n=== HOW OFTEN IS A SYMBOL RE-ENTERED SOON AFTER ITS OWN CLOSE? ===")
    last_close = {}
    for h in (2, 6, 12, 24):
        n_all = n_trail = 0
        pnl_all = pnl_trail = 0.0
        last_close = {}
        for x in BASE:
            prev = last_close.get(x["sym"])
            if prev and x["ts"] - prev[0] <= h * HOUR:
                n_all += 1
                pnl_all += x["net"] * risk_pct * eq0 * x["mult"]
                if prev[1] == "trail":
                    n_trail += 1
                    pnl_trail += x["net"] * risk_pct * eq0 * x["mult"]
            last_close[x["sym"]] = (x["exit_ts"], x["kind"])
        print("  within %2dh: %3d re-entries worth $%+8.2f | of which after a TRAIL: "
              "%3d worth $%+8.2f" % (h, n_all, pnl_all, n_trail, pnl_trail))
    print("\nA freeze can only ever remove the fills counted above. If those dollars are")
    print("POSITIVE, freezing costs money however sensible the rule sounds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
