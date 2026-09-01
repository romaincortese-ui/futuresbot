"""How many concurrent WILDCARD slots? Never swept until now.

    railway run --service Futures-bot python tools/pit_slots.py

FUTURES_WILDCARD_MAX_POSITIONS=3 against a code default of 2, and no study in
this repo has ever varied it - the universe sweep held slots fixed at 3 while it
moved the turnover floor and the majors band. The live shadow ledger shows 11
slot_occupied refusals over 13 days at +0.674R mean, which looks like a real
capacity cost until you notice the same sustained move re-fires the trigger every
bar, so those rows are not 11 independent opportunities.

TWO THINGS TO READ, and net $ is not the first of them:
  $/fill  more slots ALWAYS take more fills, so net $ rises almost mechanically.
          The question is whether the MARGINAL fill pays. If $/fill falls as
          slots rise, the extra trades are diluting.
  risk    there is no portfolio margin or VaR cap anywhere on the convex path
          (health scan, 2026-08-29), so the slot count is the ONLY thing
          bounding concurrent exposure. Six slots at ~2.4% risk each is ~14% of
          equity live at once, with the trend sleeve's 2 on top of that.

Remember the harness takes ~2.3x more fills per day than the live bot, so slot
contention BINDS HARDER here than in reality - this sweep is if anything biased
toward finding slots valuable.

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

BAR, TAIL = 900, 260
SLOTS = (1, 2, 3, 4, 5, 6)


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
    lo, hi = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    floor_live = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    tp_r = _env("FUTURES_WILDCARD_TP_R", 5.0)

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
    fn = ratchet(3.0, 0.75, base=_env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50), arm=1.0)

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
            e, sl = float(sig.entry_price), float(sig.sl_price)
            if abs(e - sl) <= 0 or e <= 0:
                continue
            row = {"entry": e, "sl": sl, "tp": float(sig.tp_price), "side": sig.side}
            g = resolve(bars, i, e, sl, float(sig.tp_price), tp_r, sig.side,
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), fn,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is None:
                continue
            eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
            C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]), "exit_ts": float(g[1]),
                      "day": day_key(bars[i][0]),
                      "mult": regime_size_multiplier(eff, lo=lo, hi=hi, floor_mult=flm)})
    C.sort(key=lambda x: x["ts"])
    print("candidates: %d\n" % len(C))

    def book(n_slots):
        occ, per, taken = [], {}, []
        for x in C:
            if band and x["sym"] in PIT.get(x["day"], ()):
                continue
            occ[:] = [q for q in occ if q > x["ts"]]
            per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
            if per[x["sym"]] or len(occ) >= n_slots:
                continue
            occ.append(x["exit_ts"])
            per[x["sym"]].append(x["exit_ts"])
            taken.append(x)
        return taken

    def usd(f):
        return sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f)

    BASE = book(3)
    base_usd = usd(BASE)
    t0, t1 = BASE[0]["ts"], BASE[-1]["ts"]

    def halves(f, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f if z["ts"] < cut),
                sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f if z["ts"] >= cut))

    print("LIVE = 3 slots: $%+.2f over %d fills\n" % (base_usd, len(BASE)))
    print("%-6s %6s %9s %9s %9s %8s %6s   %s"
          % ("slots", "fills", "net $", "vs live", "ex-top5", "$/fill", "both?", "thirds"))
    for n in SLOTS:
        f = book(n)
        if not f:
            continue
        u = usd(f)
        vals = sorted((z["net"] * risk_pct * eq0 * z["mult"] for z in f), reverse=True)
        ex5 = sum(vals[max(1, len(vals) // 20):])
        ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                    *halves(f, fr), *halves(BASE, fr))
                 for fr in (0.35, 0.425, 0.5, 0.575, 0.65))
        th = []
        for k in range(3):
            a = t0 + k * (t1 - t0) / 3.0
            b = t0 + (k + 1) * (t1 - t0) / 3.0 + (1 if k == 2 else 0)
            th.append(sum(z["net"] * risk_pct * eq0 * z["mult"] for z in f if a <= z["ts"] < b))
        print("%-6d %6d %+9.2f %+9.2f %+9.2f %8.3f %6s   %+6.1f %+6.1f %+6.1f"
              % (n, len(f), u, u - base_usd, ex5, u / len(f),
                 "base" if n == 3 else ("YES" if ok else "no"), *th))
    print("\nRead $/fill, not net $: more slots always take more fills, so net $")
    print("rises almost mechanically. The question is whether the MARGINAL fill")
    print("pays. And with no portfolio margin cap on the convex path, the slot")
    print("count is the only thing bounding concurrent exposure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
