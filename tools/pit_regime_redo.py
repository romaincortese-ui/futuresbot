"""The four regime studies, re-run on the CORRECTED point-in-time pool.

    railway run --service Futures-bot python tools/pit_regime_redo.py

WHY. tools/pit_pool.py (2026-08-28) found that every pit_* study computed its
majors band ONCE from today's tickers and applied it to the whole history. The
turnover floor was point-in-time; the band was not. TUT_USDT sits in today's
band, so it was excluded from all 361 days of every replay - and TUT is the
symbol that made the live fortnight's money (+$18.73). Nine of the 19 wildcard
symbols the bot actually traded were missing from the pool, carrying +$15.78
of live P&L against a +$9.07 total. The replay was blind to the profitable
tail and kept the losing body.

Arm-vs-arm comparisons are only mildly exposed (both arms shared the pool),
but REGIME conclusions are directly exposed, because the wrongly-excluded
symbols are exactly the ones that move most. Four studies told the owner that
majors-based rules do not work. All four ran on that pool. This re-runs them.

ONE FETCH, ONE POOL, FOUR ANALYSES - deliberately. Running them as four
separate tools would draw four slightly different symbol sets (turnover
rankings churn hourly) and the verdicts would not be comparable with each
other or with the originals. Everything below scores the identical candidate
set.

WHAT IS RE-RUN, and the number each produced on the broken pool:
  A  majors-movement GATES      any>=5%/24h -246.19; btc>=3% -270.40;
                                all-three>=3% -267.79; calm<5% +11.06
  B  multi-horizon UNION gates  owner 2/12+5/24+10/72 on BTC: surplus -73.88
  C  breadth as a size TILT     -36.14 to -78.06 vs flat
  D  calm as a size TILT        +41.16 size-neutral (1.5/0.5)

METHOD NOTES, all of them lessons from this month's retractions:
  - CONTINUOUS slot book. A weekly-reset book manufactured the +$41 stop-width
    finding retracted in 9c8e4c7; the boundary was an arbitrary wall-clock
    anchor and sweeping it moved the result by $78.
  - PROPORTIONAL BENCHMARK for gates. surplus = actual - (no-gate $/trade x
    trades kept). A gate carrying no information scores 0 by construction;
    without this, "keeps fewer trades" reads as "loses money".
  - SIZE-NEUTRAL control for tilts. Normalising each arm to the same average
    deployed size separates SELECTION from LEVERAGE. Raw, the calm tilt looked
    worth +$159 and was monotone in aggressiveness - the signature of measuring
    leverage. Normalised it was +$45 and the monotonicity vanished.
  - Gates FAIL OPEN on missing major data, so no gate is credited for dropping
    a bar it could not see.

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
from pit_pool import day_key, daily_turnover, describe, pit_majors  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

BAR, CHUNK, TAIL = 900, 1900, 260
MAJORS = ("BTC_USDT", "ETH_USDT", "SOL_USDT")
H12, H24, H72 = 48, 96, 288


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - linear dollars, NOT account P&L. ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 220), int(_env("PJ_POOL", 140))
    now = int(time.time())
    floor = W.wildcard_min_turnover_usdt()
    eq0 = rt._last_known_equity() or 158.0
    dollar_r = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241) * eq0
    N_BAND = int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0))
    print("equity $%.2f -> 1R = $%.2f | %.0fd | band N=%d" % (eq0, dollar_r, days, N_BAND))

    tk = cl.get_all_tickers() or []
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    # today's ranking picks only WHAT TO FETCH; eligibility is per-bar below
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 3e5)][:pool_n]
    syms = sorted(set(cand) | set(MAJORS))
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}

    frames, _rep = fetch_frames(cl, syms, days=days, workers=6,
                                min_bars=300, now_ts=now)
    print(_rep)

    ROLLS, PREP = {}, {}
    for s in cand:
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
        ts_all = [float(x.timestamp()) for x in df.index]
        ROLLS[s] = [(ts_all[k], roll[k]) for k in range(96, len(c))]
        PREP[s] = (df, list(zip(ts_all, [float(x) for x in df["high"]],
                                [float(x) for x in df["low"]], c)), roll, c)
    PIT = pit_majors(daily_turnover(ROLLS), n=N_BAND)
    print(describe(PIT, watch=("TUT_USDT", "ENA_USDT")))

    MRET = {h: {} for h in (H12, H24, H72)}
    BREADTH = {}
    up, tot_ct = {}, {}
    for m in MAJORS:
        df = frames.get(m)
        if df is None:
            continue
        c = [float(x) for x in df["close"]]
        ts = [float(x.timestamp()) for x in df.index]
        for h in (H12, H24, H72):
            d = MRET[h]
            for i in range(h, len(c)):
                if c[i - h] > 0:
                    d.setdefault(ts[i], {})[m] = abs(c[i] / c[i - h] - 1.0)
    for s, (df, bars, roll, c) in PREP.items():
        ts = [b[0] for b in bars]
        for i in range(96, len(c)):
            if c[i - 96] <= 0:
                continue
            tot_ct[ts[i]] = tot_ct.get(ts[i], 0) + 1
            if c[i] > c[i - 96]:
                up[ts[i]] = up.get(ts[i], 0) + 1
    BREADTH = {t: up.get(t, 0) / n for t, n in tot_ct.items() if n >= 20}

    live_floor = ratchet(3.0, 0.75)
    C = []
    for s, (df, bars, roll, c) in PREP.items():
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < floor:
                continue
            if s in PIT.get(day_key(bars[i][0]), ()):      # point-in-time band
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
            b = BREADTH.get(bars[i][0])
            sc = 0.0
            for h, thr in ((H12, 0.02), (H24, 0.05), (H72, 0.10)):
                dd = MRET[h].get(bars[i][0]) or {}
                for mv in dd.values():
                    sc = max(sc, mv / thr)
            C.append({"ts": bars[i][0], "sym": s, "side": sig.side, "net": float(g[0]),
                      "exit_ts": float(g[1]), "score": sc,
                      "b": (b if sig.side == "LONG" else (None if b is None else 1.0 - b))})
    C.sort(key=lambda x: x["ts"])
    span = (C[-1]["ts"] - C[0]["ts"]) if C else 1.0
    mid = C[0]["ts"] + span / 2.0 if C else 0.0
    print("candidates: %d over %.0f days\n" % (len(C), span / 86400.0))

    def book(keep=None, mult=None, normalise=False):
        k = 1.0
        sel = [x for x in C if (keep is None or keep(x))]
        if normalise and mult:
            taken_probe = _fills(sel)
            avg = sum(mult(x) for x in taken_probe) / max(1, len(taken_probe))
            k = (1.0 / avg) if avg > 0 else 1.0
        taken = _fills(sel)
        tot = o = r = 0.0
        for x in taken:
            d = k * (mult(x) if mult else 1.0) * x["net"] * dollar_r
            tot += d
            if x["ts"] < mid:
                o += d
            else:
                r += d
        return tot, len(taken), o, r

    def _fills(sel):
        slots, per, out = [], {}, []
        for x in sel:
            slots[:] = [q for q in slots if q > x["ts"]]
            per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
            if per[x["sym"]] or len(slots) >= 3:
                continue
            slots.append(x["exit_ts"])
            per[x["sym"]].append(x["exit_ts"])
            out.append(x)
        return out

    base, base_n, base_o, base_r = book()
    per_trade = base / max(1, base_n)
    print("NO GATE / FLAT (live): $%+.2f over %d fills | $%+.4f/trade | older %+.2f recent %+.2f"
          % (base, base_n, per_trade, base_o, base_r))

    def gates(title, rows):
        print("\n%s" % title)
        print("  %-30s %6s %6s %9s %9s | %9s %9s"
              % ("rule", "kept", "keep%", "net $", "SURPLUS", "older", "recent"))
        for lbl, fn, old in rows:
            t, n, o, r = book(keep=fn)
            print("  %-30s %6d %5.0f%% %+9.2f %+9.2f | %+9.2f %+9.2f   was %s"
                  % (lbl, n, 100.0 * n / max(1, base_n), t, t - per_trade * n, o, r, old))

    def mret(x, tickers, h, thr):
        d = MRET[h].get(x["ts"])
        if not d:
            return None
        vals = [d[t] for t in tickers if t in d]
        return max(vals) if vals else None

    def g_any(x, thr):
        v = mret(x, MAJORS, H24, thr)
        return True if v is None else v >= thr

    def g_btc(x, thr):
        v = mret(x, ("BTC_USDT",), H24, thr)
        return True if v is None else v >= thr

    def g_all(x, thr):
        d = MRET[H24].get(x["ts"])
        if not d or len(d) < 3:
            return True
        return min(d.values()) >= thr

    def g_calm(x, thr):
        v = mret(x, MAJORS, H24, thr)
        return True if v is None else v < thr

    def g_union(x, tickers, conds):
        seen = False
        for h, thr in conds:
            d = MRET[h].get(x["ts"])
            if not d:
                continue
            for t in tickers:
                if t in d:
                    seen = True
                    if d[t] >= thr:
                        return True
        return not seen

    gates("A. MAJORS-MOVEMENT GATES (was: every variant loses)",
          [("any-major >= 5%% /24h", lambda x: g_any(x, 0.05), "-246.19"),
           ("any-major >= 3%% /24h", lambda x: g_any(x, 0.03), "-234.73"),
           ("btc >= 3%% /24h", lambda x: g_btc(x, 0.03), "-270.40"),
           ("all-three >= 3%% /24h", lambda x: g_all(x, 0.03), "-267.79"),
           ("calm: majors < 5%% /24h", lambda x: g_calm(x, 0.05), "+11.06")])

    U = [(H12, 0.02), (H24, 0.05), (H72, 0.10)]
    gates("B. MULTI-HORIZON UNION (was: owner's rule surplus -73.88 on BTC)",
          [("owner 2/12 5/24 10/72 BTC", lambda x: g_union(x, ("BTC_USDT",), U), "-73.88"),
           ("owner, BTC|ETH|SOL", lambda x: g_union(x, MAJORS, U), "-56.51"),
           ("72h only >= 10%% BTC", lambda x: g_union(x, ("BTC_USDT",), [(H72, 0.10)]), "+0.23"),
           ("NOT owner (majors quiet)", lambda x: not g_union(x, ("BTC_USDT",), U), "+57.81")])

    print("\nC+D. SIZE TILTS - raw and SIZE-NEUTRAL (the control that decides them)")
    print("  %-30s %9s %9s | %12s %9s   %s"
          % ("tilt", "net $", "vs flat", "SIZE-NEUTRAL", "vs flat", "was"))

    def step(getter, lo, hi, cut_lo, cut_hi):
        def f(x):
            v = getter(x)
            if v is None:
                return 1.0
            return hi if v <= cut_lo else (lo if v >= cut_hi else 1.0)
        return f

    for lbl, fn, old in (
            ("breadth 0.5/1.0/1.5", step(lambda x: x["b"], 0.5, 1.5, 0.4, 0.6), "-78.06"),
            ("breadth 0.75/1.0/1.25", step(lambda x: x["b"], 0.75, 1.25, 0.4, 0.6), "-39.03"),
            ("calm 1.5 / moving 0.5", step(lambda x: x["score"], 0.5, 1.5, 1.0, 2.0), "+41.16"),
            ("calm 1.0 / moving 0.5", step(lambda x: x["score"], 0.5, 1.0, 1.0, 2.0), "+34.86"),
            ("INVERSE calm 0.5/moving 1.5", step(lambda x: x["score"], 1.5, 0.5, 1.0, 2.0), "-70.94"),
    ):
        t, n, o, r = book(mult=fn)
        tn, _n2, on, rn = book(mult=fn, normalise=True)
        print("  %-30s %+9.2f %+9.2f | %+12.2f %+9.2f   %s"
              % (lbl, t, t - base, tn, tn - base, old))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
