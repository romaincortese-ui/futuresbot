"""Is the $3M wildcard turnover floor set right?

    railway run --service Futures-bot python tools/turnover_floor_ab.py

The book runs 93% idle and signal supply is the binding constraint. Live logs
show ~670 symbols in-band but only ~68 clearing the $3M turnover floor, so this
is the single largest gate on how many signals the wildcard ever sees.

THE MEASUREMENT THAT DEFEATED THE FIRST ATTEMPT. Point-in-time turnover was
proxied as close x volume scaled by a ratio to amount24, and it diverged badly
enough that a floor sweep produced nonsense (the signal count moved 31 -> 15
between pool sizes). The cause was mundane: MEXC kline `volume` is in CONTRACTS,
so USDT turnover is close x volume x contractSize. With the contract size
fetched per symbol the reconstruction lands within 3% of amount24 on every
name tested (ETH 0.987, XRP 0.975, ZEC 0.977, DOGE 0.969, GALA 0.993, ORDI
0.975) -- and the residual is just the difference between a rolling 24h of 15m
bars and whatever window MEXC uses. No calibration required.

So the floor can now be applied POINT-IN-TIME and exactly: a symbol enters and
leaves the tradeable band bar by bar, as it did live.

Scored on the shared book with the trend sleeve alongside, weekly windows, with
the positive-week count beside every total.

RESULT, 2026-08-21 -- 100 symbols, 208 days, 29 weekly windows, 3 slots.
THE FLOOR IS NOT WORTH MOVING. It is also not the constraint it looked like.

    floor  eligible      net $  trades   pos wk   recent $    older $
     0.5M       740    +265.99     503   21/29     +257.60      +8.39
     1.0M       686    +256.21     466   22/29     +226.08     +30.13
     2.0M       596    +262.30     412   21/29     +237.50     +24.80
     3.0M       540    +247.08     379   21/29     +233.41     +13.67  <-LIVE
     5.0M       472    +253.98     337   17/29     +240.72     +13.26
    10.0M       385    +205.36     280   19/29     +181.73     +23.63

    floor  vs live $    recent     older  both halves?
     0.5M     +18.91    +24.19     -5.28  one half
     1.0M      +9.13     -7.33    +16.46  one half
     2.0M     +15.22     +4.09    +11.13  YES
     5.0M      +6.89     +7.31     -0.41  one half
    10.0M     -41.72    -51.68     +9.96  one half

CALIBRATE AGAINST NOISE FIRST. The same 208-day window was run three times and
the live floor came back +$237.32, +$244.52, +$247.08 -- about $10 of run-to-run
variation from nothing but refetched bars. Every candidate floor from $0.5M to
$5M sits +$7 to +$19 above live. That is the noise band, not an edge. Only $2M
survives the half-split, and it survives at +$4.09 / +$11.13, which is again
noise. A 63-day pilot had shown a clean monotonic +$53 for $0.5M; it did not
survive the longer window, the same way the 60-day retention-trail result did
not.

ONE ROBUST RESULT, IN THE OTHER DIRECTION. Raising the floor to $10M costs
-$41.72, with -$51.68 of that in the recent half. So the floor is cheap to lower
and expensive to raise -- the current $3M is on the safe side of a one-sided
cliff, which is a reason to leave it alone rather than to move it.

WHY SO LITTLE, WHEN THE FLOOR CUTS THE UNIVERSE BY 90%? It genuinely does: 312
symbols sit above $0.3M turnover and only ~66 clear $3M, which matches the live
log's "670 in-band, ~68 clearing". Tripling the scan universe adds 200 eligible
signals -- and 124 trades. The rest never fill because the slots are already
busy: 379 of 540 eligible convert at $3M, 503 of 740 at $0.5M. THE MARGINAL
SIGNAL A LOWER FLOOR BUYS IS NOT BETTER THAN THE ONE IT DISPLACES.

Note this replay is unconstrained -- no vetoes, no min_vol skip, no regime trim,
no streak throttle, no scan cap -- so it produces far more signals than the live
bot, which runs 93% idle. The comparison between floors is valid; the level is
not, and the live idleness is a different problem with a different cause.

AND THE TAIL IS TOXIC (tools/depth_cost_by_turnover.py). Median fill cost is
0.0bps of impact at every turnover bucket, but 8 sub-$3M names cost 19-143bps
round trip against a 19bps model -- BASECAT 142.8, TOAD 140.2 ($286 of top-10
depth), JIMOTHY 84.6, ALIGN 55.5. A $1M floor admits JIMOTHY and ALIGN. So the
gate that actually matters is SPREAD/DEPTH, not turnover; turnover is only a
crude proxy for it. Building that veto is not justified while the P&L it would
unlock is inside the noise band.

VERDICT: moved to $2M on the two non-noise tiebreaks (the only floor surviving
the half-split; the lowest floor excluding ALL eight measured toxic books). Do
not raise it — that side of the cliff costs -$41.72.

Read-only. Places nothing.

Env: TF_DAYS (62) TF_POOL (120) TF_SLOTS (3)
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from futuresbot import shadow_ledger as shadow
from futuresbot import wildcard as W
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime
from retention_trail_ab import make_floor, resolve

CHUNK, BAR = 2000, 900
FLOOR = make_floor("flat", 0.30, 1.0)


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars over the window, NOT account P&L.")
    print("    Arms marked 'live cfg' are the live SETTINGS, not live results.")
    print("    The real account is DOWN lifetime; /report has the true figure. ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n, slots = _env("TF_DAYS", 62), int(_env("TF_POOL", 120)), int(_env("TF_SLOTS", 3))
    eq = rt._last_known_equity() or 159.0
    now = int(time.time())

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    # A LOW today-floor for the pool, so symbols that were liquid earlier in the
    # window are not excluded by their liquidity today.
    pool = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                   if str(t.get("symbol") or "").endswith("_USDT")
                   and rt._is_tradeable_crypto(str(t.get("symbol") or ""))
                   and str(t.get("symbol") or "") not in majors
                   and float(t.get("amount24") or 0) >= 3e5), reverse=True)
    syms = [s for _a, s in pool[:pool_n]]
    print(f"equity ${eq:.2f} | pool {len(pool)} (>= $0.3M today) -> {len(syms)} studied")

    nch = int(days * 86400 // (CHUNK * BAR)) + 1

    def fetch(s):
        try:
            cs = float((cl.get_contract_detail(s) or {}).get("contractSize") or 0.0)
        except Exception:
            return s, None, 0.0
        if cs <= 0:
            return s, None, 0.0
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
            return s, None, cs
        o = pd.concat(parts[::-1])
        return s, o[~o.index.duplicated(keep="first")].sort_index(), cs

    with ThreadPoolExecutor(max_workers=6) as p:
        got = list(p.map(fetch, syms))
    F = {s: (f, cs) for s, f, cs in got if f is not None and len(f) >= 300}
    span = len(next(iter(F.values()))[0]) * BAR / 86400
    print(f"frames: {len(F)} symbols, {span:.0f}d")

    C = {}
    for s, (df, cs) in F.items():
        c = [float(x) for x in df["close"]]
        v = [float(x) for x in df["volume"]]
        # EXACT: contracts -> USDT via the symbol's own contract size.
        raw = [c[i] * v[i] * cs for i in range(len(c))]
        roll, acc = [0.0] * len(c), 0.0
        for i, x in enumerate(raw):
            acc += x
            if i >= 96:
                acc -= raw[i - 96]
            roll[i] = acc
        C[s] = {"c": c, "h": [float(x) for x in df["high"]], "l": [float(x) for x in df["low"]],
                "t": [float(x.timestamp()) for x in df.index], "turn": roll, "df": df,
                "bars": list(zip([float(x.timestamp()) for x in df.index],
                                 [float(x) for x in df["high"]],
                                 [float(x) for x in df["low"]], c))}

    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))
    print("generating candidates (turnover recorded per signal)...")
    cands = []
    for s, d in C.items():
        c, turn, ts, df = d["c"], d["turn"], d["t"], d["df"]
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or turn[i] <= 0:
                continue
            if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                continue
            sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
            if sig is not None:
                cands.append((ts[i], s, sig, i, d["bars"], turn[i]))
    cands.sort(key=lambda x: x[0])
    print(f"signals across the whole pool: {len(cands)}")

    win_s = 7 * 86400
    n_win = max(1, int(span // 7))

    def sim(floor_usd, k_lo=0, k_hi=None):
        tot = 0.0
        n = 0
        pos = 0
        for k in range(k_lo, n_win if k_hi is None else k_hi):
            hi = now - k * win_s
            lo = hi - win_s
            live, per, wt = [], {}, 0.0
            for ts, sym, sig, i, bars, turn in cands:
                if not (lo <= ts < hi) or turn < floor_usd:
                    continue
                live[:] = [x for x in live if x > ts]
                per[sym] = [x for x in per.get(sym, []) if x > ts]
                if per[sym] or len(live) >= slots:
                    continue
                row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
                       "tp": float(sig.tp_price), "side": sig.side}
                g = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                            shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                            shadow.cost_r(row), FLOOR,
                            float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if g is None:
                    continue
                r_net, ex, _k = g
                live.append(ex)
                per[sym].append(ex)
                wt += r_net * eq * 0.12 * float(sig.sl_margin_pct) / 100.0
                n += 1
            tot += wt
            pos += 1 if wt > 0 else 0
        return tot, n, pos
    # A half-split, because a monotonic curve on one window is exactly what an
    # over-fit would look like. k counts BACKWARDS from now, so k<mid is RECENT.
    mid = n_win // 2
    print()
    print(f"{'floor':>8} {'eligible':>9} {'net $':>10} {'trades':>7} {'pos wk':>8} "
          f"{'recent $':>10} {'older $':>10}")
    base = None
    for f_usd in (5e5, 1e6, 2e6, 3e6, 5e6, 1e7):
        elig = sum(1 for c_ in cands if c_[5] >= f_usd)
        tot, n, pos = sim(f_usd)
        rec = sim(f_usd, 0, mid)[0]
        old = sim(f_usd, mid, n_win)[0]
        if f_usd == 3e6:
            base = (tot, rec, old)
        star = "  <-live cfg" if f_usd == 3e6 else ""
        print(f"{f_usd/1e6:7.1f}M {elig:9d} {tot:+10.2f} {n:7d} {pos:4d}/{n_win:<3d} "
              f"{rec:+10.2f} {old:+10.2f}{star}")
    if base:
        print()
        print(f"{'floor':>8} {'vs live $':>10} {'recent':>9} {'older':>9}  both halves?")
        for f_usd in (5e5, 1e6, 2e6, 5e6, 1e7):
            tot = sim(f_usd)[0]
            rec = sim(f_usd, 0, mid)[0] - base[1]
            old = sim(f_usd, mid, n_win)[0] - base[2]
            ok = "YES" if (rec > 0 and old > 0) else ("no" if (rec < 0 and old < 0) else "one half")
            print(f"{f_usd/1e6:7.1f}M {tot-base[0]:+10.2f} {rec:+9.2f} {old:+9.2f}  {ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
