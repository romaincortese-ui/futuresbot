"""Do the live ROC / stop-width bands hold at n=620 instead of n=95?

    railway run --service Futures-bot python tools/pit_bands.py

Four weeks of live signals (taken + shadow, 155 rows) show an INVERTED-U in both
the 3h ROC magnitude and the stop width: the middle bands pay and both tails
lose. The live buckets hold 9-29 rows each, which is not enough to act on. This
re-cuts the same two variables over the 220-day replay, where the same detector
produces ~620 fills, and reports whether the shape survives.

If it does, it is the basis of an entry score. If it does not, it was noise and
the current unbounded ">= 8% ROC" filter is fine as it stands.

READ-ONLY.
"""
from __future__ import annotations
import os, sys, time
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


def _env(n, d):
    try: return float(os.environ.get(n) or d)
    except (TypeError, ValueError): return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars, NOT account P&L. ***")
    cfg = FuturesConfig.from_env(); cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 220), int(_env("PJ_POOL", 170))
    now = int(time.time()); eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    lo, hi = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    fl = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
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
        c = [float(x) for x in df["close"]]; v = [float(x) for x in df["volume"]]
        raw = [c[k]*v[k]*cs for k in range(len(c))]
        roll, acc = [0.0]*len(c), 0.0
        for k, x in enumerate(raw):
            acc += x
            if k >= 96: acc -= raw[k-96]
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
            if i <= W.ROC_BARS or roll[i] < fl: continue
            r3 = abs(c[i]/c[i-W.ROC_BARS] - 1.0)
            if r3 < 0.08: continue
            sig = W.detect_wildcard_signal(df.iloc[max(0, i-TAIL):i+1], s)
            if sig is None: continue
            e, sl = float(sig.entry_price), float(sig.sl_price)
            if abs(e-sl) <= 0 or e <= 0: continue
            row = {"entry": e, "sl": sl, "tp": float(sig.tp_price), "side": sig.side}
            g = resolve(bars, i, e, sl, float(sig.tp_price), tp_r, sig.side,
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), fn,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is None: continue
            eff = trend_efficiency(c[:i+1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
            C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]), "exit_ts": float(g[1]),
                      "day": day_key(bars[i][0]), "side": sig.side, "roc": r3*100,
                      "slm": float(getattr(sig, "sl_margin_pct", 0.0) or 0.0),
                      "mult": regime_size_multiplier(eff, lo=lo, hi=hi, floor_mult=flm)})
    C.sort(key=lambda x: x["ts"])
    slots, per, T = [], {}, []
    for x in C:
        if band and x["sym"] in PIT.get(x["day"], ()): continue
        slots[:] = [q for q in slots if q > x["ts"]]
        per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
        if per[x["sym"]] or len(slots) >= 3: continue
        slots.append(x["exit_ts"]); per[x["sym"]].append(x["exit_ts"]); T.append(x)
    print("fills: %d\n" % len(T))
    t0, t1 = T[0]["ts"], T[-1]["ts"]

    def show(key, edges, label):
        print("=== %s ===" % label)
        print("  %-14s %6s %9s %8s %10s   %s" % ("bucket","n","mean R","win%","net $","thirds net R"))
        for a, b in zip([None]+edges, edges+[None]):
            sel = [x for x in T if (a is None or x[key] >= a) and (b is None or x[key] < b)]
            if len(sel) < 5: continue
            rs = [x["net"] for x in sel]
            th = []
            for k in range(3):
                p = t0 + k*(t1-t0)/3.0; q = t0 + (k+1)*(t1-t0)/3.0 + (1 if k == 2 else 0)
                th.append(sum(x["net"] for x in sel if p <= x["ts"] < q))
            nm = ("<%g" % b) if a is None else (">=%g" % a if b is None else "%g-%g" % (a, b))
            print("  %-14s %6d %+9.3f %7.0f%% %+10.2f   %+6.1f %+6.1f %+6.1f"
                  % (nm, len(sel), sum(rs)/len(rs), 100*sum(1 for v in rs if v > 0)/len(rs),
                     sum(x["net"]*risk_pct*eq0*x["mult"] for x in sel), *th))
        print()
    L = [x for x in T if x["side"] == "LONG"]
    print("longs %d / shorts %d\n" % (len(L), len(T)-len(L)))
    show_key = show
    globals()["T"] = L
    show_key("roc", [10, 14, 20, 28], "3h ROC magnitude, LONGS (live shape: 10-20 pays, tails lose)")
    show_key("slm", [12, 16, 19], "SL margin %, LONGS (live shape: 12-19 pays, tails lose)")
    globals()["T"] = T
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
