"""Does BTC LEAD ETH and SOL, and can the trend sleeve trade that lead?

    railway run --service Futures-bot python tools/btc_lead_study.py

Three questions, in the order that matters:

  1. TIMING — over the recent window, when did each of the big 3 actually make
     its move? An eyeball of "BTC went first" is a hypothesis, not a finding.
  2. LEAD-LAG — cross-correlate BTC returns against ETH/SOL at lags of +/- 3h.
     If BTC genuinely leads, correlation peaks at a POSITIVE lag. If it peaks at
     zero, the two simply move together and there is nothing to trade.
  3. THE ACTIONABLE TEST — when BTC fires a trend signal, would entering ETH/SOL
     AT THAT MOMENT have beaten waiting for their own trigger? Scored on the
     live convex exits and sizing, against the sleeve's actual behaviour.

The confound to keep in view: BTC/ETH correlate at r=+0.914 contemporaneously.
A one-bar "lead" inside data that correlated is noise wearing a hypothesis, and
the only thing that separates the two is whether acting on it pays.

RESULT, 2026-08-20, 83d — THE HYPOTHESIS IS NOT SUPPORTED. Do not relearn it.

1. TIMING of the 08-19 move, biggest 6h advance: SOL peaked 15:30, BTC 16:15,
   ETH 20:45. BTC did not go first; SOL did, by 45 minutes. (n=1 event.)

2. LEAD-LAG peaks at lag ZERO for both alts:
     BTC->ETH  -1:+0.633  0:+0.862  +1:+0.652
     BTC->SOL  -1:+0.617  0:+0.839  +1:+0.628
   Near-symmetric decay either side of zero. They move TOGETHER. The +1 bar is
   a hair above -1, which on r=0.86 contemporaneous is noise, not a lead.

3. ACTIONABLE, over 8 distinct BTC LONG episodes:
     ETH  follow BTC n=7 +$6.24 ($0.89/trade) | wait for own n=5 +$5.47 ($1.09)
     SOL  follow BTC n=7 -$1.41 (-$0.20/trade)| wait for own n=5 +$1.58 ($0.32)
   Following is worse per trade on ETH and loses money on SOL.

THE DECIDING NUMBER: the alt fired its OWN trigger in 7/8 episodes at a MEDIAN
LAG OF 0 MINUTES — the same bar. There is no lead to trade. The sleeve already
catches all three simultaneously, which is exactly what the 3-slot change
(2026-08-20) unlocked: before it, one slot meant taking one of three.

Read-only. Places nothing.

Env: BL_DAYS (63) BL_LOOKAHEAD_H (12)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from futuresbot import shadow_ledger as shadow
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime
from futuresbot.trend import detect_trend_signal

CHUNK, BAR = 2000, 900
LEAD, ALTS = "BTC_USDT", ("ETH_USDT", "SOL_USDT")


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def corr(a, b):
    n = min(len(a), len(b))
    if n < 50:
        return 0.0
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a) ** 0.5
    vb = sum((y - mb) ** 2 for y in b) ** 0.5
    return cov / (va * vb) if va and vb else 0.0


def main() -> int:
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days = _env("BL_DAYS", 63)
    look_h = _env("BL_LOOKAHEAD_H", 12)
    eq = rt._last_known_equity() or 139.0
    now = int(time.time())

    F = {}
    for s in (LEAD,) + ALTS:
        parts, end = [], now
        for _ in range(int(days * 86400 // (CHUNK * BAR)) + 1):
            d = cl.get_klines(s, interval="Min15", start=end - CHUNK * BAR, end=end)
            if d is None or not len(d):
                break
            parts.append(d)
            end = int(d.index[0].timestamp()) - BAR
            time.sleep(0.25)
        o = pd.concat(parts[::-1])
        F[s] = o[~o.index.duplicated(keep="first")].sort_index()
    C = {s: {"c": [float(x) for x in d["close"]], "h": [float(x) for x in d["high"]],
             "l": [float(x) for x in d["low"]],
             "t": [float(x.timestamp()) for x in d.index], "idx": list(d.index), "df": d}
         for s, d in F.items()}
    n_bars = min(len(C[s]["c"]) for s in C)
    print(f"equity ${eq:.2f} | {n_bars} Min15 bars ({n_bars*BAR/86400:.0f}d) per symbol")

    # ---- 1. timing of the recent move --------------------------------------
    print("\n=== 1. WHEN did each name move? biggest 6h advance in the last 72h ===")
    for s in (LEAD,) + ALTS:
        d = C[s]
        best = (0.0, None)
        for i in range(len(d["c"]) - 288, len(d["c"])):
            if i - 24 < 0:
                continue
            r = d["c"][i] / d["c"][i - 24] - 1.0
            if r > best[0]:
                best = (r, d["idx"][i])
        print(f"  {s.replace('_USDT',''):5s} best 6h +{best[0]*100:5.2f}%  ending {best[1]:%m-%d %H:%M} UTC")

    # ---- 2. lead-lag -------------------------------------------------------
    print("\n=== 2. LEAD-LAG: corr(BTC ret at t, ALT ret at t+lag), 1h returns ===")
    print("     positive lag = BTC moved FIRST")
    def rets(s, w=4):
        c = C[s]["c"]
        return [c[i] / c[i - w] - 1.0 for i in range(w, len(c))]
    b = rets(LEAD)
    for alt in ALTS:
        a = rets(alt)
        row = []
        for lag in (-8, -4, -2, -1, 0, 1, 2, 4, 8):
            if lag >= 0:
                x, y = b[:len(b) - lag], a[lag:]
            else:
                x, y = b[-lag:], a[:len(a) + lag]
            row.append((lag, corr(x, y)))
        peak = max(row, key=lambda kv: kv[1])
        print(f"  BTC -> {alt.replace('_USDT',''):4s} " +
              " ".join(f"{l:+d}:{c:+.3f}" for l, c in row) +
              f"   PEAK at lag {peak[0]:+d} ({peak[0]*15}min)")

    # ---- 3. does trading the lead pay? -------------------------------------
    print(f"\n=== 3. ACTIONABLE: enter ALT when BTC triggers, vs the alt's own trigger ===")
    fund = {s: rt._funding_settlements(s) for s in C}
    from futuresbot.wildcard import _atr_pct

    class Sig:
        def __init__(s_, sym, side, e, sl, tp, lev, slm):
            s_.symbol, s_.side, s_.entry_price = sym, side, e
            s_.sl_price, s_.tp_price, s_.leverage, s_.sl_margin_pct = sl, tp, lev, slm
            s_.roc_pct, s_.rsi = 0.0, 50.0

    def score(sym, i):
        """Open a long on `sym` at bar i under live geometry; return net $."""
        d = C[sym]
        a = _atr_pct(d["df"].iloc[:i + 1])
        if not a or a <= 0:
            return None
        slf = 3.0 * a
        lev = min(10, max(1, int(20.0 / (slf * 100.0))))
        if slf * lev * 100.0 > 20.0:
            slf = 20.0 / 100.0 / lev
        e = d["c"][i]
        row = shadow.candidate_row(Sig(sym, "LONG", e, e * (1 - slf), e * (1 + slf * 3.0),
                                       lev, slf * lev * 100.0),
                                   sleeve="TREND", reject_reason="lead")
        row["ts"] = d["t"][i]
        done = shadow.resolve_outcome(row, list(zip(d["t"], d["h"], d["l"], d["c"])), now,
                                      horizon_s=shadow.CONVEX_HORIZON_S, convex=True)
        if done is None:
            return None
        return shadow.net_usd(done, eq, funding_r=shadow.funding_cost_r(done, fund.get(sym) or []))

    # BTC's own trend triggers
    btc_fires = []
    d = C[LEAD]
    for i in range(400, len(d["c"])):
        sig = detect_trend_signal(d["df"].iloc[:i + 1], LEAD)
        if sig is not None and sig.side == "LONG":
            btc_fires.append(i)
    # collapse to distinct episodes (>=6h apart)
    episodes = []
    for i in btc_fires:
        if not episodes or i - episodes[-1] > 24:
            episodes.append(i)
    print(f"  BTC LONG trigger episodes (>=6h apart): {len(episodes)}")

    look_bars = int(look_h * 4)
    for alt in ALTS:
        follow = own = 0
        f_net = o_net = 0.0
        lag_hits = []
        for i in episodes:
            if i >= len(C[alt]["c"]):
                continue
            u = score(alt, i)                       # enter ALT at BTC's trigger
            if u is not None:
                follow += 1
                f_net += u
            # did the alt fire its OWN trigger within the look-ahead?
            for k in range(i, min(i + look_bars, len(C[alt]["c"]))):
                s2 = detect_trend_signal(C[alt]["df"].iloc[:k + 1], alt)
                if s2 is not None and s2.side == "LONG":
                    lag_hits.append((k - i) * 15)
                    v = score(alt, k)
                    if v is not None:
                        own += 1
                        o_net += v
                    break
        med = sorted(lag_hits)[len(lag_hits) // 2] if lag_hits else None
        print(f"\n  {alt.replace('_USDT','')}:")
        print(f"    followed BTC immediately : n={follow:2d}  net ${f_net:+7.2f}  "
              f"(${f_net/follow:+.2f}/trade)" if follow else "    followed: none")
        print(f"    waited for its own signal: n={own:2d}  net ${o_net:+7.2f}  "
              f"(${o_net/own:+.2f}/trade)" if own else "    own signal: never fired in window")
        print(f"    alt fired its own trigger after BTC in {len(lag_hits)}/{len(episodes)} "
              f"episodes, median lag {med}min" if med is not None else
              f"    alt never followed within {look_h:.0f}h")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
