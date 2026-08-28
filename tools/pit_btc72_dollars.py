"""The BTC72 gate priced in DOLLARS, with the live regime scaler applied.

    railway run --service Futures-bot python tools/pit_btc72_dollars.py

THE OWNER'S ARGUMENT, 2026-08-28, and it identifies a real gap in every gate
test run so far: "if the 72h gate is up, and the sizing is larger, and we get
winners during this period, doesn't it arithmetically make sense in $ to only
trade when the gate allows it?"

Every gate study in this repo priced trades at a FLAT 1R. The live bot does
not size flat. runtime._regime_size_multiplier scales each entry by the
symbol's Kaufman efficiency over 24 bars: full size at efficiency >= 0.45,
floored at 0.25 below 0.20, linear between. So chop is ALREADY quartered and
trends are ALREADY full size. A flat-1R model cannot see that, and it is
precisely the interaction the argument rests on - if losers arrive quartered
and winners arrive whole, the dollar case for a gate is different from the R
case.

The live record says the interaction is real and large. Across the 36 fills
since 2026-08-14, realised risk was 2.122% on a trade whose scaler read 0.98
and 0.577-0.620% on trades reading 0.25 - a 3.7x size difference driven by
regime, not by the gate. And the wildcard book is +$13.81 on netR -6.09: it
made money ONLY because winners were sized larger than losers.

SO THIS PRICES THREE THINGS SIDE BY SIDE, on identical fills:
  1. FLAT 1R              - what every prior gate study measured
  2. SCALER               - 1R x regime_size_multiplier(efficiency), i.e. live
  3. SCALER + COMPOUNDING - equity actually moves, so size moves with it

If the owner is right, the gate's dollar case improves as you move down that
list, because gating removes trades that were already small while keeping
trades that were already large. If the gate's advantage instead SHRINKS under
the scaler, that is the scaler having already captured the same signal - and
gating on top of it would be paying twice for one effect.

Reported per arm: net $, fills, win rate, and the older/recent half-split.
Point-in-time majors band throughout (tools/pit_pool.py) - the fixed-band
pool excluded TUT_USDT from all 237 days, which is the trade this entire
question is about.

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
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_pool import day_key, daily_turnover, describe, pit_majors  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

BAR, CHUNK, TAIL = 900, 1900, 260
H72 = 288


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
    days, pool_n = _env("PJ_DAYS", 220), int(_env("PJ_POOL", 140))
    now = int(time.time())
    floor = W.wildcard_min_turnover_usdt()
    eq0 = rt._last_known_equity() or 158.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    N_BAND = int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0))
    lo = _env("FUTURES_REGIME_EFF_LO", 0.20)
    hi = _env("FUTURES_REGIME_EFF_HI", 0.45)
    fl = _env("FUTURES_REGIME_FLOOR_MULT", 0.25)
    print("equity $%.2f | risk %.4f | scaler lo=%.2f hi=%.2f floor=%.2f"
          % (eq0, risk_pct, lo, hi, fl))

    tk = cl.get_all_tickers() or []
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 3e5)][:pool_n]
    syms = sorted(set(cand) | {"BTC_USDT", "ETH_USDT", "SOL_USDT"})
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}

    frames, _rep = fetch_frames(cl, syms, days=days, workers=6,
                                min_bars=300, now_ts=now)
    print(_rep)

    MRET = {h: {} for h in (48, 96, 288)}
    for m in ("BTC_USDT", "ETH_USDT", "SOL_USDT"):
        dfm = frames.get(m)
        if dfm is None:
            continue
        cm = [float(x) for x in dfm["close"]]
        tm = [float(x.timestamp()) for x in dfm.index]
        for h in (48, 96, 288):
            for i in range(h, len(cm)):
                if cm[i - h] > 0:
                    MRET[h].setdefault(tm[i], {})[m] = abs(cm[i] / cm[i - h] - 1.0)

    btc = frames.get("BTC_USDT")
    bc = [float(x) for x in btc["close"]]
    bts = [float(x.timestamp()) for x in btc.index]
    B72 = {bts[i]: bc[i] / bc[i - H72] - 1.0
           for i in range(H72, len(bc)) if bc[i - H72] > 0}

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
    print(describe(PIT, watch=("TUT_USDT",)))

    live_floor = ratchet(3.0, 0.75)
    C = []
    for s, (df, bars, roll, c) in PREP.items():
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < floor:
                continue
            if s in PIT.get(day_key(bars[i][0]), ()):
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
            eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
            sc = 0.0
            for hh, thr in ((48, 0.02), (96, 0.05), (288, 0.10)):
                mv = MRET.get(hh, {}).get(bars[i][0])
                if mv:
                    sc = max(sc, max(mv.values()) / thr)
            C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                      "exit_ts": float(g[1]), "score": sc,
                      "mult": regime_size_multiplier(eff, lo=lo, hi=hi, floor_mult=fl),
                      "b72": B72.get(bars[i][0])})
    C.sort(key=lambda x: x["ts"])
    span = (C[-1]["ts"] - C[0]["ts"]) if C else 1.0
    mid = C[0]["ts"] + span / 2.0

    def fills(keep):
        slots, per, out = [], {}, []
        for x in C:
            if not keep(x):
                continue
            slots[:] = [q for q in slots if q > x["ts"]]
            per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
            if per[x["sym"]] or len(slots) >= 3:
                continue
            slots.append(x["exit_ts"])
            per[x["sym"]].append(x["exit_ts"])
            out.append(x)
        return out

    def score(taken, mode):
        eq, tot, o, r = eq0, 0.0, 0.0, 0.0
        for x in taken:
            if mode == "flat":
                d = x["net"] * risk_pct * eq0
            elif mode == "scaler":
                d = x["net"] * risk_pct * eq0 * x["mult"]
            else:
                d = x["net"] * risk_pct * eq * x["mult"]
                eq += d
            tot += d
            if x["ts"] < mid:
                o += d
            else:
                r += d
        return tot, o, r, eq

    # ---- the close calls, re-priced under the LIVE sizing model ----
    from pit_size import compare, price

    ALL = fills(lambda x: True)
    GATE = fills(lambda x: x["b72"] is None or x["b72"] >= 0.10)
    QUIET = fills(lambda x: x["b72"] is None or x["b72"] < 0.10)
    print("")
    print("fills: all %d | BTC72>=10%% %d | BTC72<10%% %d"
          % (len(ALL), len(GATE), len(QUIET)))
    print("")
    print(compare({"no gate": ALL, "BTC72>=10%": GATE, "majors quiet": QUIET},
                  risk_pct=risk_pct, equity0=eq0))

    print("")
    print("SIZE TILTS - flat vs live scaler, both size-neutral")
    print("%-30s %11s %11s   %s" % ("tilt", "FLAT", "SCALER", "verdict moves?"))
    base_flat = price(ALL, risk_pct=risk_pct, equity0=eq0, model="flat")["net"]
    base_scal = price(ALL, risk_pct=risk_pct, equity0=eq0, model="scaler")["net"]

    def calm_tilt(lo, hi):
        def f(x):
            s = x.get("score") or 0.0
            return hi if s <= 1.0 else (lo if s >= 2.0 else 1.0)
        return f

    def b72_tilt(lo, hi):
        def f(x):
            v = x.get("b72")
            if v is None:
                return 1.0
            return hi if v >= 0.10 else lo
        return f

    for lbl, fn in (("calm 1.5 / moving 0.5", calm_tilt(0.5, 1.5)),
                    ("calm 1.25 / moving 0.75", calm_tilt(0.75, 1.25)),
                    ("BTC72 tilt 1.5 / 0.5", b72_tilt(0.5, 1.5)),
                    ("BTC72 tilt 1.25 / 0.75", b72_tilt(0.75, 1.25))):
        a = price(ALL, risk_pct=risk_pct, equity0=eq0, model="flat",
                  tilt=fn, normalise=True)["net"] - base_flat
        b = price(ALL, risk_pct=risk_pct, equity0=eq0, model="scaler",
                  tilt=fn, normalise=True)["net"] - base_scal
        moves = "YES - sign flips" if (a > 0) != (b > 0) else "no"
        print("%-30s %+11.2f %+11.2f   %s" % (lbl, a, b, moves))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
