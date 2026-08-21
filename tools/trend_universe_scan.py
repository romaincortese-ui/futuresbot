"""Which majors deserve a place in the TREND sleeve? Currently ETH + SOL only.

    railway run --service Futures-bot python tools/trend_universe_scan.py

The 2nd trend slot was worth 3.7x the 3rd wildcard slot, and the book runs 93%
idle, so trend signals are both the scarcer and the more valuable kind. The
sleeve trades two names. This asks which of the liquid majors — the band the
wildcard deliberately excludes — carry a real trend edge.

THE DISCIPLINE THAT CAUGHT BTC. Raw P&L per symbol is a statement about the
tape, not the detector: a name that drifted up will show profitable longs
whatever the rule. So every symbol is scored against ITS OWN random-entry
baseline — same symbol, same sizing, same convex exits, same funding, entries at
random bars. The number that decides is EDGE = trend minus random. BTC looked
merely weak on raw P&L (-$15.33) and turned out to be genuinely NEGATIVE against
its own baseline (-$0.300/trade), which is why it was dropped.

Long-only, one position at a time per symbol, the shipped detector, 200+ days.

RESULT, 2026-08-21 — 16 majors, ~200d, long-only, one position per name.

Full-window edge (trend $/trade minus that symbol's own random baseline) put 13
of 16 names "positive". That is a LOW BAR, not 13 edges: random entry with a
-1R stop, a 3R target, a 24h clock and costs bleeds by construction, so beating
it mostly means "avoids the worst entries". Several names beat random while
still LOSING money outright (DOGE -$4.08, SUI -$4.70, ADA -$5.40, TAO -$18.39).

So every candidate was re-tested on BOTH HALVES of the window separately. A name
that only works in one half is a fitted artifact:

    sym    first half        second half       verdict
           n   net$  edge     n   net$  edge
    XRP   22   +4.9 +0.60    18  +29.9 +1.84   BOTH +
    ETH   23  +13.6 +0.92    18  +19.8 +1.20   BOTH +   (live)
    ZEC   51  +71.6 +1.60    50  +22.0 +0.54   BOTH +
    BTW   24  +14.7 +0.21    47  +81.1 +0.54   BOTH +   (but +2494% drift)
    PEPE  38  -17.0 +0.19    26  +31.2 +1.28   fails
    BEAT  70   +5.2 -0.34    79  +99.1 +0.79   one half only
    SOL   25   +2.5 +0.40    20   -2.1 +0.10   fails    (LIVE)
    BTC   18  -12.4 -0.37     8  +14.0 +1.87   one half only
    DOGE  36  +10.4 +0.47    19  -14.5 -0.33   one half only
    HYPE  46  -30.7 -0.29    54  +38.4 +0.97   one half only

BEAT's headline +$104 was ENTIRELY the second half. BTW passes both halves but
drifted +2494% -- a 25x mover makes any statistic on it fragile, so it is
excluded on judgement, not on its number.

SOL, WHICH IS LIVE, FAILS. Its full-window net is +$0.43 over 200 days -- a zero
-- and the second half is negative.

BTC's earlier "-0.300 edge" verdict does NOT reproduce here (+0.390 on this
window). The split explains why: BTC is -0.37 then +1.87, i.e. UNSTABLE rather
than reliably negative. Dropping it remains right, but for instability, not for
a negative edge. That correction is recorded rather than quietly dropped.

JOINT VALIDATION on the shared book, 208d, 29 weekly windows, wildcard at 3
slots alongside:

    trend universe        tr     net $  trades  pos wk
    ETH+SOL (LIVE)         2   +136.99     201  13/29
    ETH+SOL                3   +136.99     201  13/29   (inert)
    ETH+SOL+XRP            2   +164.08     220  12/29
    ETH+XRP+ZEC            2   +271.53     281  17/29   <- BEST
    ETH+XRP+ZEC            3   +259.79     303  16/29
    ETH+SOL+XRP+ZEC        2   +211.78     299  17/29
    ETH+SOL+XRP+ZEC        3   +269.67     333  17/29

ETH+XRP+ZEC at 2 slots nearly DOUBLES the live universe (+$134.54) and lifts
weekly consistency 13/29 -> 17/29. Adding SOL back COSTS $59.75 (+271.53 ->
+211.78): it crowds out better signals rather than adding any. Three slots is
worse than two even with three symbols.

CAVEATS. Symbols were selected from a 16-name scan, so selection bias is real
and the half-split mitigates it rather than removing it. ZEC drifted +87.9% and
its edge decays across halves (+1.60 -> +0.54). And the absolute figures are an
UNCONSTRAINED replay -- no vetoes, no min_vol skip, no regime trim, no streak
throttle -- so the live sleeve will earn far less. The COMPARISON is what is
valid, not the level.

Read-only. Places nothing.

Env: TU_DAYS (200) TU_RANDOM (700) TU_SYMS (optional comma list)
"""
from __future__ import annotations

import os
import random
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
from futuresbot.wildcard import _atr_pct

CHUNK, BAR = 2000, 900
LIVE = {"ETH_USDT", "SOL_USDT"}
DROPPED = {"BTC_USDT"}


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


class Sig:
    def __init__(s_, sym, side, e, sl, tp, lev, slm):
        s_.symbol, s_.side, s_.entry_price = sym, side, e
        s_.sl_price, s_.tp_price, s_.leverage, s_.sl_margin_pct = sl, tp, lev, slm
        s_.roc_pct, s_.rsi = 0.0, 50.0


def main() -> int:
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days = _env("TU_DAYS", 200)
    n_rand = int(_env("TU_RANDOM", 700))
    eq = rt._last_known_equity() or 157.0
    now = int(time.time())

    raw = (os.environ.get("TU_SYMS") or "").strip()
    if raw:
        syms = [x.strip().upper() for x in raw.split(",") if x.strip()]
    else:
        tk = cl.get_all_tickers() or []
        # The MAJORS band: liquid, crypto, and exactly what the wildcard excludes.
        majors = rt._major_symbols(tk, int(rt._env_float(
            "FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
        ranked = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or ""))
                         for t in tk if str(t.get("symbol") or "") in majors
                         and rt._is_tradeable_crypto(str(t.get("symbol") or ""))),
                        reverse=True)
        syms = [s for _a, s in ranked][:16]
    print(f"equity ${eq:.2f} | testing {len(syms)} majors over ~{days:.0f}d")
    print("  " + ", ".join(s.replace("_USDT", "") for s in syms))

    nch = int(days * 86400 // (CHUNK * BAR)) + 1
    rows = []
    for sym in syms:
        parts, end = [], now
        for _ in range(nch):
            try:
                d = cl.get_klines(sym, interval="Min15", start=end - CHUNK * BAR, end=end)
            except Exception:
                break
            if d is None or not len(d):
                break
            parts.append(d)
            end = int(d.index[0].timestamp()) - BAR
            time.sleep(0.2)
        if not parts:
            print(f"  {sym}: no data")
            continue
        o = pd.concat(parts[::-1])
        o = o[~o.index.duplicated(keep="first")].sort_index()
        if len(o) < 800:
            print(f"  {sym}: only {len(o)} bars, skipped")
            continue
        c = [float(x) for x in o["close"]]
        h = [float(x) for x in o["high"]]
        lo_ = [float(x) for x in o["low"]]
        ts = [float(x.timestamp()) for x in o.index]
        bars = list(zip(ts, h, lo_, c))
        fund = rt._funding_settlements(sym)
        n = len(c)

        def score(i):
            a = _atr_pct(o.iloc[:i + 1])
            if not a or a <= 0:
                return None
            slf = 3.0 * a
            lev = min(10, max(1, int(20.0 / (slf * 100.0))))
            if slf * lev * 100.0 > 20.0:
                slf = 20.0 / 100.0 / lev
            e = c[i]
            row = shadow.candidate_row(
                Sig(sym, "LONG", e, e * (1 - slf), e * (1 + slf * 3.0), lev, slf * lev * 100.0),
                sleeve="TREND", reject_reason="uni")
            row["ts"] = ts[i]
            done = shadow.resolve_outcome(row, bars, now,
                                          horizon_s=shadow.CONVEX_HORIZON_S, convex=True)
            if done is None:
                return None
            u = shadow.net_usd(done, eq, funding_r=shadow.funding_cost_r(done, fund))
            return None if u is None else (u, float(done.get("resolved_ts") or ts[i]))

        # --- the sleeve's own record, one position at a time ---------------
        i, fills = 400, []
        while i < n:
            if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                i += 1
                continue
            sig = detect_trend_signal(o.iloc[:i + 1], sym)
            if sig is None or sig.side != "LONG":
                i += 1
                continue
            got = score(i)
            if got is None:
                i += 1
                continue
            u, ex = got
            fills.append(u)
            j = i + 1
            while j < n and ts[j] <= ex:
                j += 1
            i = max(j, i + 1)

        # --- that symbol's OWN random baseline -----------------------------
        random.seed(4242)
        r_tot = r_n = 0
        r_sum = 0.0
        for _ in range(n_rand):
            k = random.randrange(400, n - 1)
            got = score(k)
            if got is None:
                continue
            r_sum += got[0]
            r_n += 1
        base = r_sum / r_n if r_n else 0.0
        net = sum(fills)
        per = net / len(fills) if fills else 0.0
        edge = per - base
        drift = (c[-1] / c[0] - 1.0) * 100
        rows.append((sym, len(fills), net, per, base, edge, edge * len(fills), drift,
                     100 * sum(1 for u in fills if u > 0) / len(fills) if fills else 0))
        print(f"  {sym.replace('_USDT',''):<8} done: {len(fills):3d} trades, "
              f"edge {edge:+.3f}/trade")

    rows.sort(key=lambda r: -r[5])
    print(f"\n{'sym':<8} {'n':>4} {'net $':>9} {'$/trade':>8} {'random':>8} "
          f"{'EDGE':>8} {'edge tot':>9} {'win%':>6} {'drift':>8}  status")
    for sym, n_, net, per, base, edge, tot, drift, win in rows:
        tag = "LIVE" if sym in LIVE else ("DROPPED" if sym in DROPPED else "")
        print(f"{sym.replace('_USDT',''):<8} {n_:4d} {net:+9.2f} {per:+8.3f} "
              f"{base:+8.3f} {edge:+8.3f} {tot:+9.2f} {win:5.1f}% {drift:+7.1f}%  {tag}")
    good = [r for r in rows if r[5] > 0 and r[1] >= 15]
    print(f"\nPOSITIVE EDGE with n>=15: "
          f"{', '.join(r[0].replace('_USDT','') for r in good) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
