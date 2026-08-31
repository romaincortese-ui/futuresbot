"""Trail x cooldown, swept JOINTLY. The two decisions the owner wants before Friday.

    railway run --service Futures-bot python tools/pit_trail_cooldown.py

WHY JOINTLY. They are not independent. The cooldown only fires on a TRAIL exit,
so changing the trail changes how often the cooldown can fire and on which
trades; and if the trail is removed entirely the cooldown has almost nothing to
trigger on. Measuring them separately - which is what pit_cooldown.py and
pit_exits_sized.py did - cannot see that interaction. This sweeps the surface.

WHAT IS ALREADY KNOWN, so this run is judged against it rather than in a vacuum:
  - Removing the trail costs ~$113 over 220 days and takes maxDD 43% -> 60%.
  - Arming later (1.5R/2R/3R) is monotonically worse and by 3R is indistinguishable
    from no trail at all - so few trades reach 3R that the floor never engages.
  - A same-direction trail cooldown scored +$68 at 6h in the wildcard replay but
    failed the boundary-swept half-split, and the census showed the fills it
    removes are net POSITIVE - the gain was slot-book reshuffling, not avoided
    losses.
  - On the TREND sleeve the same 6h cooldown scored NEGATIVE.

THE HONEST DIFFICULTY. The base has moved $173-208 across runs this week on the
same config, purely from the window sliding a day. A $20-60 cell difference is
inside that. So this reports, for every cell:
  both?   beats base in BOTH halves at EVERY boundary 35-65%
  thirds  net $ in each third of the window - a cell that is positive in one
          third and negative in two is a lucky slice, not an edge
A cell must survive both screens to be worth a live change four days before a
funded week.

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
from retention_trail_ab import make_floor, resolve  # noqa: E402

BAR, TAIL, HOUR = 900, 260, 3600

TRAILS = [
    ("no trail",          None),
    ("0.30 flat",         ("flat", 0.30, 1.0, None, None)),
    ("0.30 + ratchet",    ("rat",  0.30, 1.0, 3.0, 0.75)),
    ("0.50 + ratchet **", ("rat",  0.50, 1.0, 3.0, 0.75)),   # LIVE
    ("0.70 + ratchet",    ("rat",  0.70, 1.0, 3.0, 0.75)),
]
COOLS = [0, 2, 6, 12]


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def floor_fn(spec):
    if spec is None:
        return make_floor("none", 0.0, 1.0)
    kind, retain, arm, trig, hi = spec
    if kind == "flat":
        return make_floor("flat", retain, arm)
    return ratchet(trig, hi, base=retain, arm=arm)


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
    band_live = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    tp_r = _env("FUTURES_WILDCARD_TP_R", 5.0)
    print("equity $%.2f | risk %.4f | scaler floor %.2f | TP %.1fR\n" % (eq0, risk_pct, flm, tp_r))

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
            one = abs(e - sl)
            if one <= 0 or e <= 0:
                continue
            eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
            SIG.append({"ts": bars[i][0], "sym": s, "side": sig.side, "bars": bars, "i": i,
                        "e": e, "sl": sl, "tp": float(sig.tp_price),
                        "atr": float(getattr(sig, "atr_pct", 0.0) or 0.0),
                        "day": day_key(bars[i][0]),
                        "mult": regime_size_multiplier(eff, lo=lo, hi=hi, floor_mult=flm)})
    SIG.sort(key=lambda z: z["ts"])
    print("signals: %d\n" % len(SIG))

    def resolved(spec):
        fn = floor_fn(spec)
        out = []
        for x in SIG:
            row = {"entry": x["e"], "sl": x["sl"], "tp": x["tp"], "side": x["side"]}
            g = resolve(x["bars"], x["i"], x["e"], x["sl"], x["tp"], tp_r, x["side"],
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), fn, x["atr"], now)
            if g is None:
                continue
            out.append({**x, "net": float(g[0]), "exit_ts": float(g[1]), "kind": str(g[2])})
        out.sort(key=lambda z: z["ts"])
        return out

    def book(rows, cool_h):
        slots, per, frozen, taken = [], {}, {}, []
        for x in rows:
            if band_live and x["sym"] in PIT.get(x["day"], ()):
                continue
            key = (x["sym"], x["side"])
            if frozen.get(key, 0.0) > x["ts"]:
                continue
            slots[:] = [q for q in slots if q > x["ts"]]
            per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
            if per[x["sym"]] or len(slots) >= 3:
                continue
            slots.append(x["exit_ts"])
            per[x["sym"]].append(x["exit_ts"])
            taken.append(x)
            if cool_h > 0 and x["kind"] == "trail":
                frozen[key] = x["exit_ts"] + cool_h * HOUR
        return taken

    RES = {name: resolved(spec) for name, spec in TRAILS}
    t0 = min(r[0]["ts"] for r in RES.values() if r)
    t1 = max(r[-1]["ts"] for r in RES.values() if r)

    def usd(f):
        return sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f)

    def halves(f, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f if z["ts"] < cut),
                sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f if z["ts"] >= cut))

    def thirds(f):
        a = t0 + (t1 - t0) / 3.0
        b = t0 + 2.0 * (t1 - t0) / 3.0
        return tuple(sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f
                         if loz <= z["ts"] < hiz)
                     for loz, hiz in ((t0, a), (a, b), (b, t1 + 1)))

    BASE = book(RES["0.50 + ratchet **"], 0)
    bu = usd(BASE)
    print("BASE = LIVE (0.50 + ratchet, no cooldown): $%+.2f over %d fills\n"
          % (bu, len(BASE)))
    print("%-20s %5s %6s %9s %9s %9s %6s   %s"
          % ("trail", "cool", "fills", "net $", "vs live", "ex-top5", "both?", "thirds $"))
    winners = []
    for name, _spec in TRAILS:
        rows = RES[name]
        for ch in COOLS:
            f = book(rows, ch)
            if len(f) < 30:
                continue
            u = usd(f)
            vals = sorted((z["net"] * risk_pct * eq0 * z["mult"] for z in f), reverse=True)
            ex5 = sum(vals[max(1, len(vals) // 20):])
            ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                        *halves(f, fr), *halves(BASE, fr))
                     for fr in (0.35, 0.425, 0.5, 0.575, 0.65))
            th = thirds(f)
            bth = thirds(BASE)
            beats = sum(1 for k in range(3) if th[k] > bth[k])
            live = (name == "0.50 + ratchet **" and ch == 0)
            if ok and beats == 3 and not live:
                winners.append((u - bu, name, ch))
            print("%-20s %4dh %6d %+9.2f %+9.2f %+9.2f %6s   %+7.1f %+7.1f %+7.1f  %d/3"
                  % (name, ch, len(f), u, u - bu, ex5,
                     "base" if live else ("YES" if ok else "no"),
                     th[0], th[1], th[2], beats))
        print("")
    print("both?  = beats LIVE in both halves at every boundary 35-65%")
    print("thirds = net $ per third of the window; N/3 = thirds where it beats LIVE")
    print("A cell needs BOTH screens. The base has moved $173-208 across runs this")
    print("week on identical config, so a single-number win means nothing.")
    if winners:
        winners.sort(reverse=True)
        print("\nCELLS PASSING BOTH SCREENS:")
        for d, nm, ch in winners:
            print("  %+8.2f   %s + %dh cooldown" % (d, nm, ch))
    else:
        print("\nNO CELL passes both screens. The live configuration is not beaten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
