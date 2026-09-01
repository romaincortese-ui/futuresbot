"""Re-decide slots and the exit stack on the CORRECTED harness.

    railway run --service Futures-bot python tools/pit_corrected.py

Every conclusion in this repo was reached on a book that sized off full equity,
never applied the calm filter, and refilled slots ~2.3x faster than the live bot
can. tools/pit_book.py fixes all three. This re-runs the two live decisions that
those gaps bear on most:

  SLOTS  the old sweep put 4 ahead of 3 by +$45.88 - but sizing off full equity
         is exactly what inflates a marginal slot, so that cell was measured by
         the defect it was testing.
  EXITS  including 7R / 0.50, which has never been tested: the 7R cell that
         passed the half-split three times ran retention 0.30, the PREVIOUS live
         setting, so its result was never against the current base.

Both are reported OLD vs NEW so the size of each correction is visible rather
than asserted.

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
from pit_book import take, usd  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_pool import day_key, daily_turnover, pit_majors  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import make_floor, resolve  # noqa: E402

BAR, TAIL = 900, 260
EXITS = [
    ("LIVE 5R / 0.50 / ratchet", 5.0, 0.50, 3.0, 0.75),
    ("5R / 0.30 / ratchet", 5.0, 0.30, 3.0, 0.75),
    ("5R / 0.70 / ratchet", 5.0, 0.70, 3.0, 0.75),
    ("7R / 0.50 / ratchet **", 7.0, 0.50, 3.0, 0.75),
    ("7R / 0.30 / ratchet", 7.0, 0.30, 3.0, 0.75),
    ("9R / 0.50 / ratchet", 9.0, 0.50, 3.0, 0.75),
    ("5R / NO TRAIL", 5.0, None, None, None),
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
    eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    slm = _env("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", 20.0)
    scan_s = _env("FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS", 900.0)
    calm = _env("FUTURES_WILDCARD_MAX_CALM_RATIO", 0.75)
    lo, hi = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    floor_live = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    live_slots = int(_env("FUTURES_WILDCARD_MAX_POSITIONS", 3))
    print("equity $%.2f | risk %.4f of AVAILABLE | scan %ds | calm cap %.2f | %d slots\n"
          % (eq0, risk_pct, int(scan_s), calm, live_slots))

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
            SIG.append({"ts": bars[i][0], "sym": s, "side": sig.side, "bars": bars, "i": i,
                        "e": e, "sl": sl, "slf": abs(e - sl) / e,
                        "atr": float(getattr(sig, "atr_pct", 0.0) or 0.0),
                        "calm_ratio": getattr(sig, "calm_ratio", None),
                        "day": day_key(bars[i][0]),
                        "mult": regime_size_multiplier(eff, lo=lo, hi=hi, floor_mult=flm)})
    SIG.sort(key=lambda z: z["ts"])
    n_calm = sum(1 for x in SIG if x["calm_ratio"] is not None and x["calm_ratio"] >= calm)
    print("signals: %d  (of which %d would be refused by the calm filter the old "
          "harness ignored)\n" % (len(SIG), n_calm))

    def resolved(tp_r, retain, rat_r, rat_hi):
        fl = (make_floor("none", 0.0, 1.0) if retain is None
              else ratchet(rat_r, rat_hi, base=retain, arm=1.0))
        out = []
        for x in SIG:
            dist = tp_r * x["slf"]
            tp = x["e"] * (1 + dist) if x["side"] == "LONG" else x["e"] * (1 - dist)
            row = {"entry": x["e"], "sl": x["sl"], "tp": tp, "side": x["side"]}
            g = resolve(x["bars"], x["i"], x["e"], x["sl"], tp, tp_r, x["side"],
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), fl, x["atr"], now)
            if g is None:
                continue
            out.append({**x, "net": float(g[0]), "exit_ts": float(g[1]), "kind": str(g[2])})
        out.sort(key=lambda z: z["ts"])
        return out

    def old_book(rows, slots):
        """The PREVIOUS model: full-equity sizing, no calm filter, instant refill."""
        occ, per, taken = [], {}, []
        for x in rows:
            if band and x["sym"] in PIT.get(x["day"], ()):
                continue
            occ[:] = [q for q in occ if q > x["ts"]]
            per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
            if per[x["sym"]] or len(occ) >= slots:
                continue
            occ.append(x["exit_ts"])
            per[x["sym"]].append(x["exit_ts"])
            taken.append({**x, "usd": x["net"] * risk_pct * eq0 * x["mult"]})
        return taken

    def new_book(rows, slots):
        return take(rows, slots=slots, equity=eq0, risk_pct=risk_pct,
                    sl_margin_pct=slm, scan_s=scan_s, calm_max=calm,
                    exclude=lambda z: bool(band and z["sym"] in PIT.get(z["day"], ())))

    LIVE_ROWS = resolved(5.0, 0.50, 3.0, 0.75)
    span = (LIVE_ROWS[-1]["ts"] - LIVE_ROWS[0]["ts"]) / 86400.0

    print("=== 1. SLOTS, old model vs corrected ===")
    print("%-6s | %6s %9s %7s | %6s %9s %7s %8s"
          % ("slots", "OLDn", "old $", "old/day", "NEWn", "new $", "new/day", "avail%"))
    base_new = None
    for n in (1, 2, 3, 4, 5, 6):
        o = old_book(LIVE_ROWS, n)
        w = new_book(LIVE_ROWS, n)
        if n == 3:
            base_new = usd(w)
        af = 100 * sum(f["avail_frac"] for f in w) / max(1, len(w))
        print("%-6d | %6d %+9.2f %7.2f | %6d %+9.2f %7.2f %7.0f%%"
              % (n, len(o), sum(z["usd"] for z in o), len(o) / span,
                 len(w), usd(w), len(w) / span, af))
    print("  live actual, same period: 2.58 wildcard fills/day\n")

    print("=== 2. EXIT STACK on the corrected book, %d slots ===" % live_slots)
    print("%-26s %6s %9s %9s %9s %6s" % ("cell", "fills", "net $", "vs live",
                                         "ex-top5", "both?"))
    BASE = new_book(LIVE_ROWS, live_slots)
    bu = usd(BASE)
    t0, t1 = BASE[0]["ts"], BASE[-1]["ts"]

    def halves(f, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(z["usd"] for z in f if z["ts"] < cut),
                sum(z["usd"] for z in f if z["ts"] >= cut))

    for label, tp_r, retain, rr, rh in EXITS:
        f = new_book(resolved(tp_r, retain, rr, rh), live_slots)
        if not f:
            continue
        u = usd(f)
        vals = sorted((z["usd"] for z in f), reverse=True)
        ex5 = sum(vals[max(1, len(vals) // 20):])
        ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                    *halves(f, fr), *halves(BASE, fr))
                 for fr in (0.35, 0.425, 0.5, 0.575, 0.65))
        is_base = label.startswith("LIVE")
        print("%-26s %6d %+9.2f %+9.2f %+9.2f %6s"
              % (label, len(f), u, u - bu, ex5,
                 "base" if is_base else ("YES" if ok else "no")))
    print("\nThe corrected book sizes off AVAILABLE margin, applies the calm filter,")
    print("and takes at most one entry per %ds scan window. The external gate is"
          % int(scan_s))
    print("still absent and cannot be reconstructed - it refuses at -0.565R live, so")
    print("its omission biases these numbers DOWN, which is the safe direction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
