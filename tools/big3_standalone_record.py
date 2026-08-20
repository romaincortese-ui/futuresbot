"""BTC vs ETH vs SOL: each name's FULL standalone trend record over 188 days.

    railway run --service Futures-bot python tools/big3_standalone_record.py

The correlation study found BTC losing -$0.44/trade over 30 multi-name trigger
episodes, against ETH +$0.60 and SOL +$0.53 — and flagged that as a lead, not a
verdict, because n=14 and it was CONDITIONAL on two or more names firing at
once. This is the unconditional version: every trigger each symbol produced,
scored as if that symbol were the only thing being traded.

THE TRAP THIS TOOL EXISTS TO AVOID. Over 188 days the three names did not drift
equally. If ETH doubled while BTC added 20%, then ETH longs win on beta alone
and "BTC is the weak name" is a statement about the tape, not the detector. So
every symbol is scored against ITS OWN random-entry baseline — same sizing, same
convex exits, same funding, same symbol, entries at random bars. The number that
decides anything is trend MINUS random, per name.

RESULT, 2026-08-20 — 20,009 Min15 bars (208d), LONG only, one position at a
time per name:

  DRIFT: every name FELL over the window — BTC -20.4%, ETH -23.1%, SOL -32.3%.
  So this is a long-only rule measured in a BEAR tape, and the "ETH won on beta"
  worry is dead: ETH fell harder than BTC and still made money.

  sym  trades   net $   $/trade  win%    maxDD
  BTC     26   -15.33    -0.59   53.8%  -22.93
  ETH     41   +21.17    +0.52   51.2%  -13.70
  SOL     44    -1.75    -0.04   54.5%  -13.57

  vs each name's OWN random-entry baseline (900 draws, same sizing/exits):
  sym  random $/trade   EDGE (trend - random)   over the trend sample
  BTC     -0.2894           -0.300/trade             -$7.81
  ETH     -0.3261           +0.842/trade            +$34.54
  SOL     -0.2414           +0.202/trade             +$8.87

VERDICT: the conditional n=14 lead is CONFIRMED unconditionally and with drift
controlled. The detector has NEGATIVE edge on BTC — trend entries there do worse
than entering BTC at random. ETH carries the sleeve; SOL is mildly positive.

Win rates are 51-55% across all three, so the difference is in the SIZE of wins
and losses, not the hit rate.

CAVEAT ON THE WEEKLY COLUMN the tool prints: trades are sparse, so a week with
NO trade scores as "not positive". Read 7-9/29 as "weeks with a winning trade",
not as a consistency ratio.

Materiality: dropping BTC removes -$15.33 over 208d, about -$2.2/month, which is
UNDER the standing $10/mo bar. The case for it is structural (stop trading a
measured negative edge), not a big dollar win.

Read-only. Places nothing.

Env: SR_DAYS (188) SR_WINDOW_D (7) SR_RANDOM (900)
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
SYMS = ("BTC_USDT", "ETH_USDT", "SOL_USDT")


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
    days = _env("SR_DAYS", 188)
    win_d = _env("SR_WINDOW_D", 7)
    n_rand = int(_env("SR_RANDOM", 900))
    eq = rt._last_known_equity() or 138.0
    now = int(time.time())

    C = {}
    for s in SYMS:
        parts, end = [], now
        for _ in range(int(days * 86400 // (CHUNK * BAR)) + 1):
            try:
                d = cl.get_klines(s, interval="Min15", start=end - CHUNK * BAR, end=end)
            except Exception:
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
                "t": [float(x.timestamp()) for x in o.index], "df": o, "idx": list(o.index)}
    n = min(len(C[s]["c"]) for s in SYMS)
    for s in SYMS:
        for k in ("c", "h", "l", "t", "idx"):
            C[s][k] = C[s][k][-n:]
        C[s]["df"] = C[s]["df"].iloc[-n:]
    print(f"{n} bars ({n*BAR/86400:.0f}d) per symbol | equity ${eq:.2f}")
    fund = {s: rt._funding_settlements(s) for s in SYMS}

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
        row = shadow.candidate_row(
            Sig(sym, "LONG", e, e * (1 - slf), e * (1 + slf * 3.0), lev, slf * lev * 100.0),
            sleeve="TREND", reject_reason="standalone")
        row["ts"] = d["t"][i]
        done = shadow.resolve_outcome(row, list(zip(d["t"], d["h"], d["l"], d["c"])), now,
                                      horizon_s=shadow.CONVEX_HORIZON_S, convex=True)
        if done is None:
            return None
        u = shadow.net_usd(done, eq, funding_r=shadow.funding_cost_r(done, fund.get(sym) or []))
        return None if u is None else (u, float(done.get("resolved_ts") or d["t"][i]))

    # ---- drift ------------------------------------------------------------
    print("\n=== DRIFT over the window (the reason per-symbol baselines matter) ===")
    for s in SYMS:
        print(f"  {s.replace('_USDT',''):4s} buy & hold {(C[s]['c'][-1]/C[s]['c'][0]-1)*100:+7.1f}%")

    # ---- standalone trend record -------------------------------------------
    print("\n=== STANDALONE TREND RECORD (LONG, one position at a time per name) ===")
    print(f"{'sym':>5} {'trades':>7} {'net $':>9} {'$/trade':>8} {'win%':>6} "
          f"{'maxDD':>8} {'wins/win':>9}")
    trend = {}
    for s in SYMS:
        closes = C[s]["c"]
        i = 400
        fills = []
        while i < n:
            if abs(closes[i] / closes[i - 96] - 1.0) < 0.04:
                i += 1
                continue
            sig = detect_trend_signal(C[s]["df"].iloc[:i + 1], s)
            if sig is None or sig.side != "LONG":
                i += 1
                continue
            got = score(s, i)
            if got is None:
                i += 1
                continue
            u, exit_ts = got
            fills.append((C[s]["t"][i], u))
            j = i + 1
            while j < n and C[s]["t"][j] <= exit_ts:
                j += 1
            i = max(j, i + 1)
        net = sum(u for _t, u in fills)
        wins = sum(1 for _t, u in fills if u > 0)
        run = pk = dd = 0.0
        for _t, u in fills:
            run += u
            pk = max(pk, run)
            dd = min(dd, run - pk)
        # weekly consistency
        nw = int(n * BAR / 86400 // win_d)
        pos = 0
        for k in range(nw):
            hi = now - k * win_d * 86400
            lo = hi - win_d * 86400
            w = sum(u for t, u in fills if lo <= t < hi)
            pos += 1 if w > 0 else 0
        trend[s] = (len(fills), net, wins, dd, pos, nw)
        print(f"{s.replace('_USDT',''):>5} {len(fills):7d} {net:+9.2f} "
              f"{(net/len(fills) if fills else 0):+8.2f} "
              f"{(100*wins/len(fills) if fills else 0):5.1f}% {dd:8.2f} {pos:5d}/{nw}")

    # ---- per-symbol random baseline ----------------------------------------
    print(f"\n=== RANDOM-ENTRY BASELINE, same symbol/sizing/exits ({n_rand} draws) ===")
    print(f"{'sym':>5} {'fills':>7} {'$/trade':>8} {'win%':>6}   -> EDGE per trade, "
          f"and over the trend sample")
    for s in SYMS:
        random.seed(1234)
        tot = 0.0
        cnt = 0
        w = 0
        for _ in range(n_rand):
            i = random.randrange(400, n - 1)
            got = score(s, i)
            if got is None:
                continue
            tot += got[0]
            cnt += 1
            w += 1 if got[0] > 0 else 0
        base = tot / cnt if cnt else 0.0
        t_n, t_net, _tw, _dd, _p, _nw = trend[s]
        edge = (t_net / t_n - base) if t_n else 0.0
        print(f"{s.replace('_USDT',''):>5} {cnt:7d} {base:+8.4f} "
              f"{(100*w/cnt if cnt else 0):5.1f}%   edge {edge:+.3f}/trade "
              f"-> {edge*t_n:+7.2f} over {t_n} trades")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
