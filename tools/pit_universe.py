"""Where does the tradeable universe start and stop? Floor x band, corrected.

    railway run --service Futures-bot python tools/pit_universe.py

WHY. These two settings decide ELIGIBILITY, and the defect found on 2026-08-28
was an eligibility bug: the majors band was a single snapshot of today applied
to the whole history, so TUT_USDT - the live fortnight's best trade - was
excluded from all 237 days of every replay. Every study that touched
eligibility was measured through that. They are also the two settings with the
largest untested exposure in the live config:

    FUTURES_WILDCARD_MIN_TURNOVER_USDT    2_000_000   (turnover_floor_ab, flat)
    FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER 24          (never re-tested at all)

And there is an unactioned recommendation: tools/pit_rerun.py concluded on
2026-08-24 that "THE TURNOVER FLOOR SHOULD GO BACK TO $3M" (+61.60, both
halves). Live is still 2M. That verdict was measured on the broken pool with
flat sizing, so it needs redoing before it is either actioned or dropped.

THEY MUST BE SWEPT TOGETHER. The floor removes symbols from below, the band
removes them from above; raising one changes what raising the other does. The
stop-width study learned this the hard way - its ATR multiplier looked inert
until the margin cap moved with it, because the cap was the binding
constraint. Testing either dial alone here would answer the wrong question.

METHOD. Candidates are generated ONCE at the loosest setting (floor 1M, no
band) because detect_wildcard_signal does not read either dial - they are
eligibility filters applied around it. Each candidate carries its own
point-in-time rolling turnover and its symbol, so every cell is a filter over
one detector pass rather than a re-scan. That also guarantees all 20 cells
score the identical underlying signal set.

Scored with the corrections this month produced: point-in-time band
(pit_pool), live sizing (pit_size), continuous slot book, and a half-split
swept across boundaries 35-65% - a single midpoint would have passed the
retracted stop-width finding.

READ-ONLY.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_pool import day_key, daily_turnover, pit_majors  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from pit_size import price  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

BAR, CHUNK, TAIL = 900, 1900, 260
FLOORS = (1e6, 2e6, 3e6, 5e6)
BANDS = (0, 12, 24, 36, 48)
LIVE_FLOOR, LIVE_BAND = 2e6, 24


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
    eq0 = rt._last_known_equity() or 158.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    lo = _env("FUTURES_REGIME_EFF_LO", 0.20)
    hi = _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.25)
    print("equity $%.2f | risk %.4f | live cell = floor $%.0fM band %d"
          % (eq0, risk_pct, LIVE_FLOOR / 1e6, LIVE_BAND))

    tk = cl.get_all_tickers() or []
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 2e5)][:pool_n]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    nch = int(days * 86400 // (CHUNK * BAR)) + 1

    def fetch(s):
        parts, end = [], now
        for _ in range(nch):
            try:
                d = cl.get_klines(s, interval="Min15", start=end - CHUNK * BAR, end=end)
            except Exception:
                break
            if d is None or not len(d):
                break
            parts.append(d)
            end = int(d.index[0].timestamp()) - BAR
        if not parts:
            return s, None
        o = pd.concat(parts[::-1])
        return s, o[~o.index.duplicated(keep="first")].sort_index()

    print("fetching %d symbols..." % len(cand))
    with ThreadPoolExecutor(max_workers=6) as p:
        frames = {s: f for s, f in p.map(fetch, cand) if f is not None and len(f) >= 300}
    print("frames: %d" % len(frames))

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
    DAILY = daily_turnover(ROLLS)
    PITS = {n: (pit_majors(DAILY, n=n) if n else {}) for n in BANDS}
    print("bands built: %s" % ", ".join("N=%d" % n for n in BANDS if n))

    live_floor_fn = ratchet(3.0, 0.75)
    C = []
    for s, (df, bars, roll, c) in PREP.items():
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < min(FLOORS):
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
            C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                      "exit_ts": float(g[1]), "roll": roll[i],
                      "day": day_key(bars[i][0]),
                      "mult": regime_size_multiplier(eff, lo=lo, hi=hi, floor_mult=flm)})
    C.sort(key=lambda x: x["ts"])
    print("candidates at the loosest setting: %d\n" % len(C))
    t0, t1 = C[0]["ts"], C[-1]["ts"]

    def cell(fl, band):
        pit = PITS.get(band) or {}
        slots, per, out = [], {}, []
        for x in C:
            if x["roll"] < fl:
                continue
            if band and x["sym"] in pit.get(x["day"], ()):
                continue
            slots[:] = [q for q in slots if q > x["ts"]]
            per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
            if per[x["sym"]] or len(slots) >= 3:
                continue
            slots.append(x["exit_ts"])
            per[x["sym"]].append(x["exit_ts"])
            out.append(x)
        return out

    def halves(taken, frac):
        cut = t0 + (t1 - t0) * frac
        o = sum(x["net"] * risk_pct * eq0 * x["mult"] for x in taken if x["ts"] < cut)
        r = sum(x["net"] * risk_pct * eq0 * x["mult"] for x in taken if x["ts"] >= cut)
        return o, r

    BASE = cell(LIVE_FLOOR, LIVE_BAND)
    base_net = price(BASE, risk_pct=risk_pct, equity0=eq0, model="scaler")["net"]
    print("LIVE CELL (floor $2M, band 24): $%+.2f over %d fills\n" % (base_net, len(BASE)))
    print("%-18s %6s %9s %9s %7s %9s %6s"
          % ("floor x band", "fills", "net $", "vs live", "maxDD", "ex-top5", "both?"))
    rows = []
    for fl in FLOORS:
        for band in BANDS:
            taken = cell(fl, band)
            if len(taken) < 30:
                continue
            s = price(taken, risk_pct=risk_pct, equity0=eq0, model="scaler")
            c2 = price(taken, risk_pct=risk_pct, equity0=eq0, model="compound")
            vals = sorted((t["net"] * risk_pct * eq0 * t["mult"] for t in taken), reverse=True)
            ex5 = sum(vals[max(1, len(vals) // 20):])
            ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                        *halves(taken, f), *halves(BASE, f))
                     for f in (0.35, 0.425, 0.5, 0.575, 0.65))
            live = (fl == LIVE_FLOOR and band == LIVE_BAND)
            rows.append((s["net"] - base_net, fl, band))
            print("%-18s %6d %+9.2f %+9.2f %6.1f%% %+9.2f %6s%s"
                  % ("$%.0fM x %s" % (fl / 1e6, band or "none"), len(taken), s["net"],
                     s["net"] - base_net, 100 * c2["max_dd"], ex5,
                     "base" if live else ("YES" if ok else "no"),
                     "  <- LIVE" if live else ""))
        print("")
    rows.sort(reverse=True)
    print("best 3 by net $: %s" % ", ".join(
        "$%.0fM x %s (%+.2f)" % (f / 1e6, b or "none", d) for d, f, b in rows[:3]))
    print("both? = beats live in BOTH halves at EVERY boundary 35-65%.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
