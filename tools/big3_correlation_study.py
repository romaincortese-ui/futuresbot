"""Six months of BTC / ETH / SOL: is there a relationship the bot can trade?

    railway run --service Futures-bot python tools/big3_correlation_study.py

The 83-day lead-lag study (tools/btc_lead_study.py) already killed the timing
version of this question: correlation peaks at lag ZERO, and entering an alt on
BTC's trigger was worse per trade than waiting for its own. This asks the
remaining forms, over 180 days:

  1. IS THE CORRELATION EVEN STABLE? A single full-period r hides everything.
     Rolling 30d windows say whether "they move together" is a fact or an
     average of regimes.
  2. BETA — do ETH/SOL AMPLIFY BTC rather than follow it? A beta of 1.4 is
     tradeable through symbol SELECTION even with zero lead, because the same
     signal buys a bigger move.
  3. LEAD-LAG at 180d, to confirm the 83d finding on 2x the data.
  4. DISPERSION / CATCH-UP — the one genuinely untested form. When BTC has run
     and an alt has NOT, does the laggard converge? This is a divergence trade,
     not a timing trade, and it is what "use the correlation" usually means.
  5. SELECTION — when more than one name triggers at once, does picking by
     |roc|, by beta, or by laggard-ness pay best? The sleeve ranks by |roc|
     today and that choice has never been measured.

RESULT, 2026-08-20 — 188 days (2026-02-13 -> 2026-08-20), 18,008 Min15 bars:

1. CORRELATION IS STABLE, NOT AN AVERAGE OF REGIMES.
     BTC/ETH  full +0.889   rolling-30d range +0.796..+0.943
     BTC/SOL  full +0.853   rolling-30d range +0.728..+0.914
     ETH/SOL  full +0.868   rolling-30d range +0.696..+0.929
   Across 49 rolling windows it NEVER drops below +0.70. There is no decoupling
   regime, so there is no correlation-breakdown trade. Read this as a RISK fact:
   three trend slots are directionally close to one bet.

2. THE ALTS AMPLIFY, THEY DO NOT FOLLOW.
     ETH beta +1.20, moved 1.32x BTC's size on |BTC 24h|>=4% (n=1111 bars)
     SOL beta +1.22, moved 1.24x BTC's size

3. LEAD-LAG PEAKS AT ZERO on 188d, confirming the 83d finding on 2x the data.
   Decay is symmetric either side. Definitively no lead to trade.

4. THERE ARE NO LAGGARDS. "BTC ran >=4%/24h AND the alt did less than half of
   it" occurs 0 times for ETH and ONCE for SOL in 18,008 bars. The catch-up /
   dispersion trade does not exist, and for a mechanical reason: correlation
   0.85-0.89 with beta 1.2 means the alts move MORE when BTC runs, not less.

5. SELECTION — the one usable asymmetry. Over 30 simultaneous multi-name
   trigger episodes:
     BTC  taken 14  net  -$6.20  (-$0.44/trade)   <- the weak name
     ETH  taken 25  net +$14.89  (+$0.60/trade)
     SOL  taken 26  net +$13.86  (+$0.53/trade)
     rank-by-|roc| (what the sleeve does)  29 fills +$10.34 (+$0.36/trade)
     take all three (3-slot behaviour)     65 fills +$22.55 (+$0.35/trade)
   Ranking by |roc| UNDERPERFORMS simply taking ETH or SOL, because it
   sometimes picks BTC and BTC loses. n=14 on the BTC arm and it is a
   conditional subsample, so this is a lead, not a verdict.

Everything scored in dollars on the live convex exits and sizing where it is
scored at all. Read-only. Places nothing.

Env: BC_DAYS (180)
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
from futuresbot.wildcard import _atr_pct

CHUNK, BAR = 2000, 900
SYMS = ("BTC_USDT", "ETH_USDT", "SOL_USDT")


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def _stats(a, b):
    """(pearson r, ols beta of b on a)."""
    n = min(len(a), len(b))
    if n < 30:
        return 0.0, 0.0
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    r = cov / ((va ** 0.5) * (vb ** 0.5)) if va and vb else 0.0
    return r, (cov / va if va else 0.0)


def main() -> int:
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days = _env("BC_DAYS", 180)
    eq = rt._last_known_equity() or 139.0
    now = int(time.time())

    C = {}
    for s in SYMS:
        parts, end = [], now
        for _ in range(int(days * 86400 // (CHUNK * BAR)) + 1):
            try:
                d = cl.get_klines(s, interval="Min15", start=end - CHUNK * BAR, end=end)
            except Exception as exc:
                print(f"  {s}: fetch stopped ({str(exc)[:60]})")
                break
            if d is None or not len(d):
                break
            parts.append(d)
            end = int(d.index[0].timestamp()) - BAR
            time.sleep(0.35)
        o = pd.concat(parts[::-1])
        o = o[~o.index.duplicated(keep="first")].sort_index()
        C[s] = {"c": [float(x) for x in o["close"]], "h": [float(x) for x in o["high"]],
                "l": [float(x) for x in o["low"]],
                "t": [float(x.timestamp()) for x in o.index], "idx": list(o.index), "df": o}
        print(f"  {s:10s} {len(o)} bars  {o.index[0]:%Y-%m-%d} -> {o.index[-1]:%Y-%m-%d}")
    n = min(len(C[s]["c"]) for s in SYMS)
    for s in SYMS:                       # align to a common tail
        for k in ("c", "h", "l", "t", "idx"):
            C[s][k] = C[s][k][-n:]
        C[s]["df"] = C[s]["df"].iloc[-n:]
    print(f"aligned: {n} bars ({n*BAR/86400:.0f}d) | equity ${eq:.2f}")

    def rets(s, w):
        c = C[s]["c"]
        return [c[i] / c[i - w] - 1.0 for i in range(w, len(c))]

    # ---- 1. is the correlation stable? -------------------------------------
    print("\n=== 1. CORRELATION, full period and rolling 30d (1h returns) ===")
    R1 = {s: rets(s, 4) for s in SYMS}
    for a, b in (("BTC_USDT", "ETH_USDT"), ("BTC_USDT", "SOL_USDT"), ("ETH_USDT", "SOL_USDT")):
        r_all, _ = _stats(R1[a], R1[b])
        win = 30 * 24            # 30d of 1h returns
        roll = []
        for i in range(win, len(R1[a]), win // 2):
            r, _ = _stats(R1[a][i - win:i], R1[b][i - win:i])
            roll.append(r)
        print(f"  {a.replace('_USDT',''):4s}/{b.replace('_USDT',''):4s} full r={r_all:+.3f} | "
              f"rolling min {min(roll):+.3f} max {max(roll):+.3f} "
              f"spread {max(roll)-min(roll):.3f}  ({len(roll)} windows)")

    # ---- 2. beta / amplification -------------------------------------------
    print("\n=== 2. BETA to BTC (1h returns) and AMPLIFICATION on big BTC days ===")
    R24 = {s: rets(s, 96) for s in SYMS}
    for alt in ("ETH_USDT", "SOL_USDT"):
        _r, beta = _stats(R1["BTC_USDT"], R1[alt])
        big = [(abs(R24[alt][i]), abs(R24["BTC_USDT"][i]))
               for i in range(len(R24[alt])) if abs(R24["BTC_USDT"][i]) >= 0.04]
        amp = (sum(a / b for a, b in big) / len(big)) if big else 0.0
        print(f"  {alt.replace('_USDT',''):4s} beta {beta:+.2f} | on |BTC 24h|>=4% "
              f"(n={len(big)} bars) the alt moved {amp:.2f}x BTC's size")

    # ---- 3. lead-lag on 180d ------------------------------------------------
    print("\n=== 3. LEAD-LAG over the full window (positive lag = BTC first) ===")
    b1 = R1["BTC_USDT"]
    for alt in ("ETH_USDT", "SOL_USDT"):
        a1 = R1[alt]
        row = []
        for lag in (-4, -2, -1, 0, 1, 2, 4):
            if lag >= 0:
                x, y = b1[:len(b1) - lag], a1[lag:]
            else:
                x, y = b1[-lag:], a1[:len(a1) + lag]
            r, _ = _stats(x, y)
            row.append((lag, r))
        peak = max(row, key=lambda kv: kv[1])
        print(f"  BTC->{alt.replace('_USDT',''):4s} " +
              " ".join(f"{l:+d}:{c:+.3f}" for l, c in row) + f"   PEAK {peak[0]:+d}")

    # ---- 4. dispersion / catch-up ------------------------------------------
    print("\n=== 4. DISPERSION: BTC has run, alt has NOT — does the laggard catch up? ===")
    fwd = 48                         # 12h forward
    for alt in ("ETH_USDT", "SOL_USDT"):
        rows = []
        for i in range(96, n - fwd):
            rb = C["BTC_USDT"]["c"][i] / C["BTC_USDT"]["c"][i - 96] - 1.0
            ra = C[alt]["c"][i] / C[alt]["c"][i - 96] - 1.0
            if rb < 0.04 or ra >= rb * 0.5:      # BTC ran, alt lagged badly
                continue
            f_alt = C[alt]["c"][i + fwd] / C[alt]["c"][i] - 1.0
            f_btc = C["BTC_USDT"]["c"][i + fwd] / C["BTC_USDT"]["c"][i] - 1.0
            rows.append((f_alt, f_alt - f_btc))
        if not rows:
            print(f"  {alt.replace('_USDT','')}: no laggard episodes")
            continue
        m_abs = sum(r[0] for r in rows) / len(rows)
        m_rel = sum(r[1] for r in rows) / len(rows)
        wins = sum(1 for r in rows if r[1] > 0)
        print(f"  {alt.replace('_USDT',''):4s} n={len(rows):5d} bars | next 12h: alt "
              f"{m_abs*100:+.2f}% absolute, {m_rel*100:+.2f}% RELATIVE to BTC, "
              f"outperformed {100*wins/len(rows):.0f}% of the time")

    # ---- 5. selection: which name to take when several trigger --------------
    print("\n=== 5. SELECTION: when >1 of the big 3 triggers at once, which pays? ===")
    from futuresbot.trend import detect_trend_signal
    fund = {s: rt._funding_settlements(s) for s in SYMS}

    class Sig:
        def __init__(s_, sym, side, e, sl, tp, lev, slm):
            s_.symbol, s_.side, s_.entry_price = sym, side, e
            s_.sl_price, s_.tp_price, s_.leverage, s_.sl_margin_pct = sl, tp, lev, slm
            s_.roc_pct, s_.rsi = 0.0, 50.0

    def score(sym, i):
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
                                       lev, slf * lev * 100.0), sleeve="TREND",
                                   reject_reason="sel")
        row["ts"] = d["t"][i]
        done = shadow.resolve_outcome(row, list(zip(d["t"], d["h"], d["l"], d["c"])), now,
                                      horizon_s=shadow.CONVEX_HORIZON_S, convex=True)
        if done is None:
            return None
        return shadow.net_usd(done, eq, funding_r=shadow.funding_cost_r(done, fund.get(sym) or []))

    fires = {s: set() for s in SYMS}
    for s in SYMS:
        closes = C[s]["c"]
        for i in range(400, n):
            if abs(closes[i] / closes[i - 96] - 1.0) < 0.04:
                continue
            sig = detect_trend_signal(C[s]["df"].iloc[:i + 1], s)
            if sig is not None and sig.side == "LONG":
                fires[s].add(i)
    per = {s: [0, 0.0] for s in SYMS}
    multi = 0
    picks = {"by_roc": [0, 0.0], "all_three": [0, 0.0]}
    last = -999
    for i in range(400, n):
        live = [s for s in SYMS if i in fires[s]]
        if len(live) < 2 or i - last < 24:
            continue
        last = i
        multi += 1
        rocs = {s: C[s]["c"][i] / C[s]["c"][i - 96] - 1.0 for s in live}
        best = max(rocs, key=rocs.get)
        u = score(best, i)
        if u is not None:
            picks["by_roc"][0] += 1
            picks["by_roc"][1] += u
        for s in live:
            v = score(s, i)
            if v is not None:
                per[s][0] += 1
                per[s][1] += v
                picks["all_three"][0] += 1
                picks["all_three"][1] += v
    print(f"  simultaneous multi-name triggers (>=6h apart): {multi}")
    for s in SYMS:
        c, v = per[s]
        if c:
            print(f"    {s.replace('_USDT',''):4s} taken {c:3d}  net ${v:+7.2f}  ${v/c:+.2f}/trade")
    for k, (c, v) in picks.items():
        if c:
            print(f"  strategy {k:10s}: {c:3d} fills  net ${v:+7.2f}  ${v/c:+.2f}/trade")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
