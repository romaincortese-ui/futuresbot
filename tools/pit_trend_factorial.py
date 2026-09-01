"""Do the REJECTED TREND changes rescue each other in combination?

    railway ssh --service Futures-bot -> /opt/venv/bin/python tools/pit_trend_factorial.py

THE OWNER'S INTUITION (2026-09-01), and it is a fair one: everything rejected on
this sleeve was tested one dial at a time. A change that loses alone can win
alongside another - the stop-width sweep already showed a concrete mechanism for
it, where widening the stop cut stop-outs 81 -> 32 but converted them into
timeouts because the 24h clock never moved.

FULL FACTORIAL, 2^4 = 16 cells:
    trigger   4.0% (live)  |  5.0%       the near-trigger band is the only
                                         negative band of six
    stop      3.0x (live)  |  4.5x       fewer stop-outs, more timeouts
    clock     24h  (live)  |  48h        the remedy the stop sweep implied
    slots     2    (live)  |  3          swept alone, 3 lost by -$17.65

WHY NOT ON TRIALS 17-18, WHICH IS WHAT WAS ASKED. That window is 2026-08-27 to
2026-09-01 - five days, ~17 closes. A 16-cell search over 17 trades finds a
winner with near-certainty and none of them are real. The search therefore runs
on the 220-day corrected book, and the trial window is reported afterwards as a
DESCRIPTIVE check on the survivors with no statistical power of its own.

THE MULTIPLICITY PROBLEM IS THE POINT, not a caveat. A cell with NO true edge
still clears the boundary-swept half-split roughly a quarter of the time, so
among 16 cells about 4 spurious passes are expected. A result is only evidence
if the pass count runs well ABOVE that null, or if one cell wins by a margin
the others do not approach. Section C states the null explicitly so the reader
cannot skip it.

READ DOLLARS. Stop width rescales R (1R in dollars is invariant, the same price
move is worth fewer R at a wider stop), so net R is not comparable across cells.

READ-ONLY.
"""
from __future__ import annotations

import datetime as dt
import itertools
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
from pit_book import take  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

TAIL = 300
TRIGGERS = (0.04, 0.05)       # live first
STOPS = (3.0, 4.5)
CLOCKS = (24, 48)
SLOTS = (2, 3)
LIVE = (0.04, 3.0, 24, 2)
TRIAL_START = dt.datetime(2026, 8, 27, tzinfo=dt.UTC).timestamp()



def decompose(by, LIVE, alt):
    """FULL 2^k factorial decomposition by Yates' method - every main effect AND
    every interaction up to k-way, not just pairs.

    effect(S) = sum over subsets T of S of (-1)^(|S|-|T|) * y(T), where y(T) is
    the cell with exactly the factors in T switched away from live. A 3-way term
    is what the trio is worth BEYOND its three main effects and three pairwise
    interactions - so a large one means the combination does something none of
    its parts or pairs predicts.
    """
    k = len(LIVE)
    out = []
    for r in range(1, k + 1):
        for S in itertools.combinations(range(k), r):
            eff, ok = 0.0, True
            for r2 in range(0, r + 1):
                for T in itertools.combinations(S, r2):
                    cell = list(LIVE)
                    for t in T:
                        cell[t] = alt[t]
                    v = by.get(tuple(cell))
                    if v is None:
                        ok = False
                        break
                    eff += ((-1) ** (r - r2)) * v
                if not ok:
                    break
            if ok:
                out.append((r, S, eff))
    return out


def print_decomposition(by, LIVE, alt, names):
    terms = decompose(by, LIVE, alt)
    label = {1: "MAIN EFFECT", 2: "2-WAY", 3: "3-WAY", 4: "4-WAY"}
    for order in sorted({t[0] for t in terms}):
        rows = sorted([t for t in terms if t[0] == order], key=lambda t: -abs(t[2]))
        print("  --- %s ---" % label.get(order, "%d-WAY" % order))
        for _, S, eff in rows:
            print("  %-46s %+10.2f" % (" + ".join(names[i] for i in S), eff))
    print()
    print("  Higher orders are SURPRISE: what a combination is worth beyond")
    print("  everything its parts and pairs already explain. Large higher-order")
    print("  terms on 16 cells are ALSO the classic signature of overfitting,")
    print("  so magnitude alone is not evidence - the screen still rules.")


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY on the CORRECTED book - model dollars, not P&L ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    now = int(time.time())
    days = _env("PJ_DAYS", 220)
    eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    tp_r = _env("FUTURES_TREND_TP_R", 3.0)
    scan_s = _env("FUTURES_TREND_SCAN_INTERVAL_SECONDS", 900.0)
    slmp = _env("FUTURES_TREND_MAX_SL_MARGIN_PCT", 20.0)
    lo_, hi_ = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    syms = tuple(s.strip() for s in
                 (os.environ.get("FUTURES_TREND_SYMBOLS") or
                  "ETH_USDT,XRP_USDT,ZEC_USDT").split(",") if s.strip())
    fn = ratchet(_env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0),
                 _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75),
                 base=_env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50), arm=1.0)

    print("universe %s | TP %.1fR | long only | 16 cells\n"
          % (",".join(s.replace("_USDT", "") for s in syms), tp_r))
    frames, rep = fetch_frames(cl, syms, days=days, workers=3, min_bars=2000,
                               now_ts=now, strict=False)
    print(rep)
    if not frames:
        return 1

    PREP = {}
    for s, df in frames.items():
        c = [float(x) for x in df["close"]]
        ts_all = [float(x.timestamp()) for x in df.index]
        PREP[s] = (df, list(zip(ts_all, [float(x) for x in df["high"]],
                                [float(x) for x in df["low"]], c)), c)

    # Detection depends on stop width (it sets sl/tp) but NOT on the trigger,
    # which is a pure filter on the detector's own roc_pct - so detect once per
    # stop at the LOWEST trigger and filter afterwards. Resolution depends on
    # the clock. Booking depends on trigger and slots. 2 stops x 2 clocks = 4
    # resolve passes instead of 16.
    RESOLVED: dict[tuple, list] = {}
    for stop, clock in itertools.product(STOPS, CLOCKS):
        os.environ["FUTURES_TREND_SL_ATR_MULT"] = str(stop)
        os.environ["FUTURES_TREND_MIN_ROC"] = str(min(TRIGGERS))
        from futuresbot.trend import detect_trend_signal, lookback_bars
        lb = lookback_bars()
        out = []
        for s, (df, bars, c) in PREP.items():
            for i in range(lb + 40, len(c)):
                sig = detect_trend_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                if sig is None or sig.side != "LONG":
                    continue
                e, sl = float(sig.entry_price), float(sig.sl_price)
                if abs(e - sl) <= 0 or e <= 0:
                    continue
                row = {"entry": e, "sl": sl, "tp": float(sig.tp_price), "side": "LONG"}
                g = resolve(bars, i, e, sl, float(sig.tp_price), tp_r, "LONG",
                            clock * 3600, shadow.cost_r(row), fn,
                            float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if g is None:
                    continue
                eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
                out.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                            "exit_ts": float(g[1]), "kind": str(g[2]),
                            "roc": abs(float(getattr(sig, "roc_pct", 0.0) or 0.0)),
                            "mult": regime_size_multiplier(eff, lo=lo_, hi=hi_,
                                                           floor_mult=flm)})
        out.sort(key=lambda z: z["ts"])
        RESOLVED[(stop, clock)] = out
        print("  resolved stop %.1fx clock %dh: %d candidates" % (stop, clock, len(out)))
    print()

    def book(trig, stop, clock, slots):
        pool = [z for z in RESOLVED[(stop, clock)] if z["roc"] >= trig]
        return take(pool, slots=slots, equity=eq0, risk_pct=risk_pct,
                    sl_margin_pct=slmp, scan_s=scan_s, one_per_scan=True,
                    calm_max=0.0)

    BASE = book(*LIVE)
    if not BASE:
        print("no fills at live")
        return 1
    t0, t1 = BASE[0]["ts"], BASE[-1]["ts"]
    base_usd = sum(z["usd"] for z in BASE)

    def halves(f, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(z["usd"] for z in f if z["ts"] < cut),
                sum(z["usd"] for z in f if z["ts"] >= cut))

    rows = []
    for trig, stop, clock, slots in itertools.product(TRIGGERS, STOPS, CLOCKS, SLOTS):
        f = book(trig, stop, clock, slots)
        if not f:
            continue
        u = sum(z["usd"] for z in f)
        vals = sorted((z["usd"] for z in f), reverse=True)
        ex5 = sum(vals[max(1, len(vals) // 20):])
        ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                    *halves(f, fr), *halves(BASE, fr))
                 for fr in (0.35, 0.425, 0.5, 0.575, 0.65))
        tw = [z for z in f if z["ts"] >= TRIAL_START]
        rows.append({"cell": (trig, stop, clock, slots), "n": len(f), "usd": u,
                     "d": u - base_usd, "ex5": ex5, "pf": u / len(f), "ok": ok,
                     "live": (trig, stop, clock, slots) == LIVE,
                     "tw_n": len(tw), "tw_usd": sum(z["usd"] for z in tw)})

    rows.sort(key=lambda r: -r["usd"])
    print("=" * 112)
    print("A. ALL 16 CELLS, best net $ first.  LIVE = 4.0%% / 3.0x / 24h / 2 slots")
    print("=" * 112)
    print("%-9s %-7s %-6s %-6s %6s %10s %10s %10s %8s %6s"
          % ("trigger", "stop", "clock", "slots", "fills", "net $", "vs live",
             "ex-top5", "$/fill", "both?"))
    for r in rows:
        tg, st, ck, sl_ = r["cell"]
        print("%-9s %-7s %-6s %-6s %6d %+10.2f %+10.2f %+10.2f %8.3f %6s%s"
              % ("%.1f%%" % (tg * 100), "%.1fx" % st, "%dh" % ck, sl_, r["n"],
                 r["usd"], r["d"], r["ex5"], r["pf"],
                 "base" if r["live"] else ("YES" if r["ok"] else "no"),
                 "   <- LIVE" if r["live"] else ""))

    passes = [r for r in rows if r["ok"] and not r["live"] and r["d"] > 0]
    print()
    print("=" * 112)
    print("B. SINGLE-DIAL EFFECTS vs INTERACTION - is any pair worth more than its parts?")
    print("=" * 112)
    by = {r["cell"]: r["d"] for r in rows}
    names = {0: "trigger 5%", 1: "stop 4.5x", 2: "clock 48h", 3: "slots 3"}
    alt = {0: 0.05, 1: 4.5, 2: 48, 3: 3}
    print("  %-26s %10s" % ("change, applied ALONE", "vs live"))
    solo = {}
    for k in range(4):
        cell = list(LIVE)
        cell[k] = alt[k]
        d = by.get(tuple(cell))
        solo[k] = d
        print("  %-26s %+10.2f" % (names[k], d if d is not None else float("nan")))
    print()
    print("  %-26s %10s %10s %10s   %s"
          % ("PAIR", "actual", "sum alone", "interaction", "verdict"))
    for a, b in itertools.combinations(range(4), 2):
        cell = list(LIVE)
        cell[a], cell[b] = alt[a], alt[b]
        act = by.get(tuple(cell))
        if act is None or solo[a] is None or solo[b] is None:
            continue
        exp = solo[a] + solo[b]
        inter = act - exp
        print("  %-26s %+10.2f %+10.2f %+11.2f   %s"
              % ("%s + %s" % (names[a], names[b]), act, exp, inter,
                 "RESCUES" if (act > 0 and exp <= 0) else
                 ("synergy" if inter > 0 else "no")))

    print()
    print("=" * 112)
    print("B2. FULL DECOMPOSITION TO %d-WAY - pairs were not the whole story" % len(LIVE))
    print("=" * 112)
    print_decomposition(by, LIVE, alt, names)

    print()
    print("=" * 112)
    print("C. IS THIS SIGNAL OR SEARCH? the multiplicity null")
    print("=" * 112)
    n_cells = len(rows) - 1
    print("  non-live cells tested            : %d" % n_cells)
    print("  cells beating live AND screening : %d" % len(passes))
    print("  expected by CHANCE at ~25%%        : %.1f" % (0.25 * n_cells))
    if len(passes) <= 0.25 * n_cells:
        print("  -> AT OR BELOW the null. Nothing here is distinguishable from search.")
    else:
        print("  -> above the null; read the margin, not the rank")
    print()
    print("=" * 112)
    print("D. THE TRIAL 17-18 WINDOW (from 2026-08-27) - DESCRIPTIVE ONLY, no power")
    print("=" * 112)
    print("  ~5 days. Reported because it was asked for; it cannot confirm or")
    print("  refute anything and must not be used to break a tie.")
    print("  %-34s %6s %10s" % ("cell", "fills", "net $"))
    for r in rows[:6]:
        tg, st, ck, sl_ = r["cell"]
        print("  %-34s %6d %+10.2f%s"
              % ("%.1f%% / %.1fx / %dh / %d slots" % (tg * 100, st, ck, sl_),
                 r["tw_n"], r["tw_usd"], "   <- LIVE" if r["live"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
