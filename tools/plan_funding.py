"""What does a SEVEN-DAY funded window actually look like? Distribution, not point estimate.

    railway run --service Futures-bot python tools/plan_funding.py

THE QUESTION. The owner wants to add ~$900 on Friday 2026-09-04, run 7 days, then
withdraw back to ~$169. Sizing is proportional to equity, so this is a 6.3x scale-up of
every position for one week.

WHY A DISTRIBUTION AND NOT A MEAN. The 220-day replay's entire dollar edge sits in a
handful of trades: ex-top-5% is negative in 19 of 20 universe cells. A 7-day window holds
roughly 20 fills. Whether that window pays is therefore mostly a question of whether a
tail winner happens to land in it, which is luck rather than edge. The mean of a
fat-tailed book is a promise the median does not keep, so this reports the whole spread
and the probability of each outcome the owner actually cares about.

METHOD. One detector pass (guarded fetch), the live continuous slot book, live sizing.
Then slide a 7-day window one DAY at a time across the replay and price each window at
the proposed equity. Every window is a real, contiguous, slot-respecting stretch of the
book, not a bootstrap - resampling would break the 3-slot coupling between trades and the
serial correlation of a trending market, both of which are exactly what makes a bad week
bad.

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
    eq_now = rt._last_known_equity() or 169.0
    add = _env("PLAN_ADD", 900.0)
    eq_fund = eq_now + add
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    slm = _env("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", 20.0)
    lev = _env("FUTURES_WILDCARD_LEVERAGE", 5.0)
    lo, hi = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.25)
    floor_live = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band_live = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))

    for tag, eq in (("NOW", eq_now), ("FUNDED", eq_fund)):
        margin = risk_pct * eq * 100.0 / slm
        print("%-7s equity $%8.2f | 1R $%6.2f | margin $%7.2f | notional $%8.2f"
              " | 3 open $%9.2f"
              % (tag, eq, risk_pct * eq, margin, margin * lev, 3 * margin * lev))
    stop_pct = slm / lev
    print("stop sits %.1f%% away in price, so slippage of X%% of price costs %.2f R per X\n"
          % (stop_pct, 1.0 / stop_pct))

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
    t0, t1 = TAKEN[0]["ts"], TAKEN[-1]["ts"]
    span_d = (t1 - t0) / DAY
    print("live cell: %d fills over %.0f days = %.2f fills/day\n"
          % (len(TAKEN), span_d, len(TAKEN) / span_d))

    order = sorted(range(len(TAKEN)), key=lambda i: TAKEN[i]["net"] * TAKEN[i]["mult"],
                   reverse=True)
    tset = {TAKEN[i]["ts"] for i in order[:max(1, len(TAKEN) // 20)]}

    def windows(eq):
        out, cnt, tw, nw = [], [], [], []
        d = t0
        while d + WINDOW_D * DAY <= t1:
            sl_ = [x for x in TAKEN if d <= x["ts"] < d + WINDOW_D * DAY]
            net = sum(x["net"] * risk_pct * eq * x["mult"] for x in sl_)
            out.append(net)
            cnt.append(len(sl_))
            (tw if any(x["ts"] in tset for x in sl_) else nw).append(net)
            d += DAY
        return out, cnt, tw, nw

    print("=== ROLLING 7-DAY WINDOWS, stepped one day ===")
    print("%-9s %6s %9s %9s %9s %9s %9s %7s %7s"
          % ("equity", "n win", "median", "mean", "P10", "P25", "P90", "P(neg)", "P(tail)"))
    for tag, eq in (("$%.0f" % eq_now, eq_now), ("$%.0f" % eq_fund, eq_fund)):
        w, c_, tw, _nw = windows(eq)
        print("%-9s %6d %+9.2f %+9.2f %+9.2f %+9.2f %+9.2f %6.0f%% %6.0f%%"
              % (tag, len(w), pct(w, 0.5), sum(w) / len(w), pct(w, 0.10), pct(w, 0.25),
                 pct(w, 0.90), 100.0 * sum(1 for x in w if x < 0) / len(w),
                 100.0 * len(tw) / len(w)))

    w, cnt, tw, nw = windows(eq_fund)
    print("\nfills per 7d window: median %d, range %d-%d"
          % (sorted(cnt)[len(cnt) // 2], min(cnt), max(cnt)))
    print("worst 7d window $%+.2f | best $%+.2f" % (min(w), max(w)))
    for thr in (-100, -200, -300, -450):
        print("  P(lose more than $%d) = %.0f%%"
              % (-thr, 100.0 * sum(1 for x in w if x < thr) / len(w)))

    print("\nTHE TAIL IS THE EDGE:")
    print("  windows CONTAINING a top-5%% trade (n=%d): median $%+.2f" % (len(tw), pct(tw, 0.5)))
    print("  windows WITHOUT one              (n=%d): median $%+.2f" % (len(nw), pct(nw, 0.5)))
    recent = sum(x["net"] * risk_pct * eq_fund * x["mult"]
                 for x in TAKEN if x["ts"] >= t1 - 7 * DAY)
    print("\nmost recent 7d of the replay, priced at $%.0f: $%+.2f" % (eq_fund, recent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
