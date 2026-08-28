"""Can a $169 account even EXPRESS this strategy? Contract discretisation, measured.

    railway run --service Futures-bot python tools/plan_capacity.py

THE DEFECT THIS PRICES. Every replay in this project sizes trades with FRACTIONAL
contracts (tools/pit_size.py). The live bot cannot:

    contracts = int((margin * leverage / entry_price) / contract_size)   # runtime.py:7097
    if contracts < min_vol:  ->  skip, "min_vol_skip"                    # runtime.py:7107

Two things follow, and neither appears anywhere in the 220-day tables.

  1. TRUNCATION. int() floors. A trade wanting 1.9 contracts gets 1 - it is sized at
     53% of intent. This is symmetric in direction (it shrinks winners and losers
     alike) so it does not by itself destroy edge, but it makes REALISED risk per
     trade wander far below the configured 2.41%, which is exactly the symptom trial
     16 was voided for and trial 17 is currently showing (mean realised risk 1.10%
     against a 1.6-2.2% target).

  2. MIN_VOL SKIP. Below one minimum lot the trade does not happen at all. This is
     NOT symmetric - it deletes trades from the book, and it deletes them on a
     criterion (price x contract_size, i.e. how expensive one lot is) that has
     nothing to do with edge. The replay counts those trades; live never took them.

Both effects shrink as equity grows, because margin scales with equity while the lot
size does not. So the question the owner is really asking - "does adding $900 help?" -
has a mechanical component that is measurable today and is independent of whether the
edge is real. That is what this measures.

Reported at the CURRENT equity and at the FUNDED equity, and separately at the regime
scaler's 0.25 floor, because chop is where notional is smallest and the floor bites
hardest.

READ-ONLY. Touches no config.
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
    eq_fund = eq_now + _env("PLAN_ADD", 900.0)
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    slm = _env("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", 20.0)
    lev = _env("FUTURES_WILDCARD_LEVERAGE", 5.0)
    lo, hi = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.25)
    floor_live = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band_live = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))

    tk = cl.get_all_tickers() or []
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 2e5)][:pool_n]
    details = {str(d.get("symbol") or ""): d for d in (cl.get_all_contract_details() or [])}
    sizes = {k: float(v.get("contractSize") or 0.0) for k, v in details.items()}
    minvol = {k: int(float(v.get("minVol", 1) or 1)) for k, v in details.items()}

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
                      "entry": e, "day": day_key(bars[i][0]),
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
    print("live cell: %d fills\n" % len(TAKEN))

    def discretise(eq, force_mult=None):
        """Apply the LIVE contract maths. Returns (kept, skipped, realised-fraction list,
        fractional net $, discrete net $)."""
        kept, skipped, fracs, nf, nd = 0, 0, [], 0.0, 0.0
        for x in TAKEN:
            m = force_mult if force_mult is not None else x["mult"]
            margin = risk_pct * eq * 100.0 / slm * m
            cs = sizes.get(x["sym"], 0.0)
            mv = minvol.get(x["sym"], 1)
            if cs <= 0 or x["entry"] <= 0:
                continue
            want_ct = (margin * lev / x["entry"]) / cs
            got_ct = int(want_ct)
            nf += x["net"] * risk_pct * eq * m
            if got_ct < mv:
                skipped += 1
                continue
            kept += 1
            frac = got_ct / want_ct if want_ct > 0 else 0.0
            fracs.append(frac)
            nd += x["net"] * risk_pct * eq * m * frac
        return kept, skipped, fracs, nf, nd

    print("=== WHAT THE LIVE CONTRACT MATHS DOES TO THE BOOK ===")
    print("%-24s %6s %7s %8s %8s %10s %10s %8s"
          % ("scenario", "kept", "skipped", "medSize", "P10size", "frac $", "live $", "lost"))
    rows = []
    for tag, eq, fm in (("$%.0f  live scaler" % eq_now, eq_now, None),
                        ("$%.0f  chop floor .25" % eq_now, eq_now, flm),
                        ("$%.0f  clean trend" % eq_now, eq_now, 1.0),
                        ("$%.0f live scaler" % eq_fund, eq_fund, None),
                        ("$%.0f chop floor .25" % eq_fund, eq_fund, flm),
                        ("$%.0f clean trend" % eq_fund, eq_fund, 1.0)):
        k, sk, fr, nf, nd = discretise(eq, fm)
        rows.append((tag, k, sk, fr, nf, nd))
        print("%-24s %6d %6.0f%% %7.0f%% %7.0f%% %+10.2f %+10.2f %7.0f%%"
              % (tag, k, 100.0 * sk / max(1, k + sk), 100.0 * pct(fr, 0.5),
                 100.0 * pct(fr, 0.10), nf, nd,
                 100.0 * (1 - nd / nf) if nf else 0.0))

    print("\nmedSize = realised contracts as %% of intended (int() truncation)")
    print("skipped = trades the live bot would NOT have taken (contracts < minVol)")
    print("frac $  = the number every replay table in this project reports")
    print("live $  = the same book after truncation and min_vol skips")

    a = rows[0]
    b = rows[3]
    print("\n=== THE FUNDING ANSWER, MECHANICALLY ===")
    print("at $%.0f the replay's $%+.2f becomes $%+.2f  (%.0f%% of the book lost to lot maths)"
          % (eq_now, a[4], a[5], 100.0 * (1 - a[5] / a[4]) if a[4] else 0))
    print("at $%.0f the replay's $%+.2f becomes $%+.2f  (%.0f%% lost)"
          % (eq_fund, b[4], b[5], 100.0 * (1 - b[5] / b[4]) if b[4] else 0))
    print("\nscaling %.1fx recovers %.0f%% -> %.0f%% of intended size and takes %d more"
          " trades over the window" % (eq_fund / eq_now, 100.0 * pct(a[3], 0.5),
                                       100.0 * pct(b[3], 0.5), b[1] - a[1]))
    print("\nNOTE: this is a MECHANICAL argument. It says the bigger account expresses the"
          "\nstrategy more faithfully. It says NOTHING about whether the strategy is"
          "\nprofitable - if edge is negative, faithful expression loses money faster.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
