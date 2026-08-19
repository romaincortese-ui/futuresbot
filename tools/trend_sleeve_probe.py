"""Is there edge in a SUSTAINED TREND on liquid majors? Hypothesis probe.

BTC ran +8.34% in 12h on 2026-08-19 and no sleeve could touch it: the wildcard
excludes majors by design and triggers on a 3h impulse (BTC's 3h was +2.05%);
the squeeze needs a Bollinger-inside-Keltner coil to release and BTC was already
expanded (0 signals in 5 days, 630/660 bars "no_active_coil"); PMT is
decommissioned. The gap is real.

This does NOT build a sleeve. It asks whether the thesis pays at all, before a
line of sleeve code exists, on the universe the wildcard deliberately excludes.

Entry     LONG when the N-hour return clears THRESH and the bar closes at the
          window high (trend intact, not a fade).
Sizing    the wildcard's own: ATR stop, 20%-of-margin cap re-deriving leverage.
Exits     the live convex stack via resolve_outcome(convex=True).
Discipline one position per symbol, live slot cap, funding charged, and the FULL
          parameter grid printed -- reporting the best cell of a grid is how you
          get a backtest that never survives contact.

Read-only. Places nothing.
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from futuresbot import shadow_ledger as shadow
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime
from futuresbot.wildcard import _atr_pct

CHUNK, BAR = 2000, 900


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


class Sig:
    def __init__(self, sym, side, entry, sl, tp, lev, slm):
        self.symbol, self.side, self.entry_price = sym, side, entry
        self.sl_price, self.tp_price, self.leverage, self.sl_margin_pct = sl, tp, lev, slm
        self.roc_pct, self.rsi = 0.0, 50.0


def main():
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    span_d, win_d = _env("TS_SPAN_D", 56), _env("TS_WINDOW_D", 7)
    slots = int(_env("TS_SLOTS", 2))
    n_maj = int(_env("TS_MAJORS", 30))
    eq = rt._last_known_equity() or 140.0
    now = int(time.time())

    tk = cl.get_all_tickers() or []
    liq = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                  if str(t.get("symbol") or "").endswith("_USDT")
                  and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    syms = [s for _a, s in liq[:n_maj]]
    print(f"equity ${eq:.2f} | MAJORS universe = top {len(syms)} crypto by turnover "
          f"(the band the wildcard excludes) | span {span_d:.0f}d | {slots} slots")
    print("  " + ", ".join(s.replace('_USDT', '') for s in syms[:14]) + " ...")

    nch = int((span_d * 86400) // (CHUNK * BAR)) + 1

    def fetch(s):
        parts, end = [], now
        for _ in range(nch):
            try:
                d = cl.get_klines(s, interval="Min15", start=end - CHUNK * BAR, end=end)
            except Exception:
                break
            if d is None or not len(d):
                break
            parts.append(d)
            end = int(d.index[0].timestamp()) - BAR
        if not parts:
            return s, None
        o = pd.concat(parts[::-1])
        return s, o[~o.index.duplicated(keep="first")].sort_index()

    with ThreadPoolExecutor(max_workers=8) as p:
        F = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) > 400}
    print(f"frames: {len(F)} symbols, {len(next(iter(F.values())))} bars "
          f"({len(next(iter(F.values())))*BAR/86400:.0f}d)")
    fund = {s: rt._funding_settlements(s) for s in F}

    C = {}
    for s, df in F.items():
        C[s] = {"c": [float(x) for x in df["close"]], "h": [float(x) for x in df["high"]],
                "l": [float(x) for x in df["low"]],
                "t": [float(x.timestamp()) for x in df.index], "df": df}

    def run(look_h, thresh, tp_r, horizon_h):
        lb = int(look_h * 4)
        cands = []
        for s, d in C.items():
            c, h, t, df = d["c"], d["h"], d["t"], d["df"]
            for i in range(400, len(c)):
                if c[i] / c[i - lb] - 1.0 < thresh:
                    continue
                if c[i] < max(h[i - lb:i + 1]) * 0.999:   # still at the window high
                    continue
                a = _atr_pct(df.iloc[:i + 1])
                if not a or a <= 0:
                    continue
                slf = 3.0 * a
                lev = max(1, int(20.0 / (slf * 100.0))) if slf * 100 > 0 else 1
                lev = min(lev, 10)
                if slf * lev * 100.0 > 20.0:
                    slf = 20.0 / 100.0 / lev
                e = c[i]
                cands.append((t[i], s, Sig(s, "LONG", e, e * (1 - slf), e * (1 + slf * tp_r),
                                           lev, slf * lev * 100.0)))
        cands.sort(key=lambda x: x[0])
        out = []
        for k in range(int(span_d // win_d)):
            hi = now - k * win_d * 86400
            lo = hi - win_d * 86400
            openq, live, net, n, w = {}, [], 0.0, 0, 0
            for ts, s, sg in cands:
                if not (lo <= ts < hi):
                    continue
                live[:] = [x for x in live if x > ts]
                if openq.get(s, 0) > ts or len(live) >= slots:
                    continue
                row = shadow.candidate_row(sg, sleeve="WILDCARD", reject_reason="probe")
                row["ts"] = ts
                done = shadow.resolve_outcome(row, list(zip(C[s]["t"], C[s]["h"], C[s]["l"], C[s]["c"])),
                                              hi, horizon_s=horizon_h * 3600, convex=True)
                if done is None:
                    continue
                u = shadow.net_usd(done, eq, funding_r=shadow.funding_cost_r(
                    done, fund.get(s) or [], horizon_s=horizon_h * 3600))
                if u is None:
                    continue
                net += u
                n += 1
                w += 1 if u > 0 else 0
                openq[s] = float(done.get("resolved_ts") or ts)
                live.append(openq[s])
            out.append((net, n, w))
        return len(cands), out

    print(f"\n{'look':>5} {'thr':>5} {'tpR':>4} {'horiz':>6} {'sig':>5} {'trades':>7} "
          f"{'net $':>9} {'win%':>6} {'wins/8':>7}")
    for look in (6, 12, 24):
        for thresh in (0.04, 0.06, 0.08):
            for tp_r, hz in ((3.0, 24), (5.0, 24), (3.0, 72)):
                nsig, res = run(look, thresh, tp_r, hz)
                tot = sum(r[0] for r in res)
                nt = sum(r[1] for r in res)
                wn = sum(r[2] for r in res)
                pos = sum(1 for r in res if r[0] > 0)
                print(f"{look:5d} {thresh*100:4.0f}% {tp_r:4.1f} {hz:5d}h {nsig:5d} {nt:7d} "
                      f"{tot:+9.2f} {(100*wn/nt if nt else 0):5.1f}% {pos:4d}/8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
