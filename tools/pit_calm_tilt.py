"""Majors-calm as a SIZE TILT, not a gate. And can it be its own sleeve?

    railway run --service Futures-bot python tools/pit_calm_tilt.py

WHY. Three independent studies now agree that CALM MAJORS SELECT BETTER TRADES:
tools/pit_regime_gate.py (calm<5% surplus +11.06), its breadth arm (+62.14
surplus, best in that run), and tools/pit_major_union.py (calm surplus +57.81
at 68% kept, +76.07 at 11% kept, positive in both halves). And all three fail
the same way: wired as a VETO, the throttling costs more than the selection
earns. The best union cell nets +173.71 against no-gate's +169.71 -- four
dollars for throttling a third of the book.

tools/pit_tut_class.py established the general law on this book: on every one
of eight features, a veto loses or kills tail trades while a 0.5/1.0/1.5 size
tilt is positive. So the pre-registered question is whether calm behaves like
that too. Set against it: tools/pit_breadth_tilt.py tested the OTHER good
classifier as a tilt and it lost on all three schemes (-36 to -78 vs flat).
Two priors point opposite ways, which is the only reason this is worth a run.

WHY A TILT IS A CLEANER MEASUREMENT THAN ANY GATE HERE. Sizing does not change
WHICH trades the live bot takes -- slots are per-position, not per-dollar -- so
every arm below books the IDENTICAL trade sequence and differs only in dollar
weight. That removes the slot-occupancy lottery entirely. It is worth stating
plainly because that lottery is what manufactured the +$41 stop-width finding
retracted in 9c8e4c7: 68% of that result was one arm not taking 27 losing
trades because changed exit times reshuffled slot occupancy. Nothing of the
kind can happen here, and the paired per-trade effect is exact.

CALM SCORE. For each candidate bar, take the majors' |return| at 12h/24h/72h
and express each as a fraction of the owner's thresholds (2%/5%/10%), then
take the WORST (max) across horizons and tickers. score <= 1.0 means every
major is inside every threshold -- "calm" as pit_major_union defined it.
Fails OPEN (score 1.0, i.e. neutral) when major data is missing, so a tilt is
never credited for a bar it could not see.

ALSO ANSWERS THE SLEEVE QUESTION the owner raised: would "Calm Major Trades"
be better as its own sleeve? A sleeve in this codebase is a distinct ENTRY
STRATEGY with its own detector and slots (WILDCARD/TREND/SQUEEZE/SNIPER). Calm
is not an entry strategy -- it is a CONDITION on wildcard entries, so a "calm
sleeve" would be the wildcard sleeve with a veto in front, which is exactly the
losing construction above. The attribution the owner actually wants is answered
by the per-tercile table at the bottom: it reports what the calm and non-calm
populations earn separately, on the same 999 candidates, without splitting the
book or halving the sample of either arm.

READ-ONLY. Never places or modifies an order.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

BAR = 900
CHUNK = 1900
TAIL = 260
MAJORS = ("BTC_USDT", "ETH_USDT", "SOL_USDT")
HORIZ = ((48, 0.02), (96, 0.05), (288, 0.10))   # (bars, owner threshold)


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - linear dollars (R x fixed risk), NOT account P&L. ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 190), int(_env("PJ_POOL", 150))
    now = int(time.time())
    floor = W.wildcard_min_turnover_usdt()
    eq0 = rt._last_known_equity() or 162.0
    dollar_r = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241) * eq0
    print("equity $%.2f -> 1R = $%.2f" % (eq0, dollar_r))

    tk = cl.get_all_tickers() or []
    band = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand_syms = [s for a, s in crypto if s not in band
                 and a >= _env("PJ_MIN_TODAY", 3e5)][:pool_n]
    syms = sorted(set(cand_syms) | set(MAJORS))
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}

    frames, _rep = fetch_frames(cl, syms, days=days, workers=6,
                                min_bars=300, now_ts=now)
    print(_rep)

    # calm score per bar: worst (|ret| / threshold) across majors and horizons
    SCORE = {}
    for m in MAJORS:
        df = frames.get(m)
        if df is None:
            print("  WARNING: %s missing - contributes nothing (tilt fails neutral)" % m)
            continue
        c = [float(x) for x in df["close"]]
        ts = [float(x.timestamp()) for x in df.index]
        for h, thr in HORIZ:
            for i in range(h, len(c)):
                if c[i - h] <= 0:
                    continue
                v = abs(c[i] / c[i - h] - 1.0) / thr
                t = ts[i]
                if v > SCORE.get(t, 0.0):
                    SCORE[t] = v
    print("calm score computed on %d bars" % len(SCORE))

    live_floor = ratchet(3.0, 0.75)
    C = []
    for s in cand_syms:
        df = frames.get(s)
        if df is None:
            continue
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
        bars = list(zip([float(x.timestamp()) for x in df.index],
                        [float(x) for x in df["high"]],
                        [float(x) for x in df["low"]], c))
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < floor:
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
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), live_floor,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is None:
                continue
            C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                      "exit_ts": float(g[1]), "score": SCORE.get(bars[i][0], 1.0)})
    C.sort(key=lambda x: x["ts"])
    span = (C[-1]["ts"] - C[0]["ts"]) if C else 1.0
    mid_ts = C[0]["ts"] + span / 2.0 if C else 0.0
    print("candidates: %d over %.0f days" % (len(C), span / 86400.0))

    # The trade SEQUENCE is fixed once: sizing never changes which trades the
    # live bot takes, so every arm below books exactly these fills.
    slots, per, TAKEN = [], {}, []
    for x in C:
        slots[:] = [q for q in slots if q > x["ts"]]
        per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
        if per[x["sym"]] or len(slots) >= 3:
            continue
        slots.append(x["exit_ts"])
        per[x["sym"]].append(x["exit_ts"])
        TAKEN.append(x)
    print("fills after 3-slot / one-per-symbol: %d\n" % len(TAKEN))

    def book(mult, normalise=False):
        """normalise=True rescales so the AVERAGE deployed size equals flat.

        Without it a tilt that simply sizes up everything scores better purely
        by leverage: the book has a positive mean, so multiplying it by 1.25 on
        average adds 25% of the P&L and none of it is selection. The normalised
        column is the only one that answers "does knowing the majors' state
        help ME PICK", as opposed to "does trading bigger make more money"."""
        k = 1.0
        if normalise:
            avg = sum(mult(x) for x in TAKEN) / max(1, len(TAKEN))
            k = (1.0 / avg) if avg > 0 else 1.0
        tot = older = recent = 0.0
        for x in TAKEN:
            d = k * mult(x) * x["net"] * dollar_r
            tot += d
            if x["ts"] < mid_ts:
                older += d
            else:
                recent += d
        return tot, older, recent

    base, b_o, b_r = book(lambda x: 1.0)
    print("FLAT (live): $%+.2f | older $%+.2f | recent $%+.2f" % (base, b_o, b_r))
    print("\ncalm score <=1.0 means every major is inside every owner threshold.\n")
    print("%-34s %6s %9s %9s | %12s %9s %9s %9s"
          % ("tilt", "avgX", "net $", "vs flat", "SIZE-NEUTRAL", "vs flat",
             "sn older", "sn recent"))

    def step(lo, hi, cut_lo=1.0, cut_hi=2.0):
        def f(x):
            s = x["score"]
            return hi if s <= cut_lo else (lo if s >= cut_hi else 1.0)
        return f

    for lbl, fn in (
            ("calm 1.5 / moving 0.5", step(0.5, 1.5)),
            ("calm 1.25 / moving 0.75", step(0.75, 1.25)),
            ("calm 1.5 / moving 1.0 (up only)", step(1.0, 1.5)),
            ("calm 1.0 / moving 0.5 (down only)", step(0.5, 1.0)),
            ("calm 2.0 / moving 0.5", step(0.5, 2.0)),
            ("3-band 1.5/1.0/0.5 at 0.7/1.3", step(0.5, 1.5, 0.7, 1.3)),
            ("linear clamp 1.5-0.5 in score", lambda x: max(0.5, min(1.5, 1.5 - 0.5 * x["score"]))),
            ("inverse: calm 0.5 / moving 1.5", step(1.5, 0.5)),
    ):
        t, o, r = book(fn)
        avg = sum(fn(x) for x in TAKEN) / max(1, len(TAKEN))
        tn, on, rn = book(fn, normalise=True)
        print("%-34s %6.3f %+9.2f %+9.2f | %+12.2f %+9.2f %+9.2f %+9.2f"
              % (lbl, avg, t, t - base, tn, tn - base, on, rn))

    print("\nWHY - the population the tilt acts on, by calm tercile:")
    srt = sorted(TAKEN, key=lambda x: x["score"])
    k = len(srt) // 3
    for name, g in (("calmest third", srt[:k]), ("middle third", srt[k:2 * k]),
                    ("most-moving third", srt[2 * k:])):
        if not g:
            continue
        tot = sum(x["net"] for x in g) * dollar_r
        wins = sum(1 for x in g if x["net"] > 0)
        print("  %-18s n=%3d  net $%+8.2f  $%+0.4f/trade  win %4.1f%%  score %.2f-%.2f"
              % (name, len(g), tot, tot / len(g), 100.0 * wins / len(g),
                 g[0]["score"], g[-1]["score"]))
    print("\nThat table is the sleeve question answered without splitting the book:")
    print("it is what a 'Calm Major Trades' sleeve would have earned, measured on")
    print("the same fills, with neither arm's sample halved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
