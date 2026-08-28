"""Does the BTC72 effect repeat ACROSS EPISODES, or was the fortnight one draw?

    railway run --service Futures-bot python tools/pit_btc72_episodes.py

WHY. tools/live_fortnight_regime.py found the 36 live fills since 2026-08-14
split hard on BTC's 72h move at entry: >=10% gave $+44.29 over 17 trades at a
71% win rate, <10% gave $-24.93 over 19 at 21%. TUT, the best trade of the
fortnight, entered with BTC24 at +0.1% and BTC72 at +19.2%, so the 24h move
the owner's proposed rule leans on does not separate them at all.

The objection that blocks acting on it is not the sample SIZE, it is the
sample STRUCTURE: BTC72 >= 10% happened ONCE, for three days. Seventeen trades
from one episode is n=1 for a regime question - "BTC72 was high" and "it was
08-20 to 08-22" are the same fact, and no amount of trades inside that window
separates them.

THIS FILE ATTACKS EXACTLY THAT. It finds every BTC72 >= 10% EPISODE in the
replay window, scores the book separately inside each one, and asks whether
the effect repeats. Pooling (which tools/pit_major_union.py did, scoring the
condition at +$0.23 surplus over 32 trades) cannot answer it either: pooled
trades from one good episode and three bad ones average to nothing while
hiding the fact that they disagree.

WHAT WOULD SETTLE IT, stated before the run:
  - Effect present in most episodes, same sign  -> real, worth a trial.
  - Effect in one episode, absent in the rest   -> the fortnight was a draw.
  - Too few episodes to tell                    -> say so, keep instrumenting.

The owner's objections to replay data are noted and partly correct: the pool
is survivorship-selected on today's liquidity, and the bot's config drifted
across trials 5-17. The first genuinely biases this; the second does not,
because every arm here uses the SAME (current) config, so a config difference
cannot produce a difference between episodes. Stated, not solved.

RESULT 2026-08-28, on the CORRECTED point-in-time pool (tools/pit_pool.py).

The pool fix mattered and is now verified by its own output: TUT_USDT sits in
the majors band on 3 of 361 days (1%) under a point-in-time band, against
100% under the old today-snapshot band. It was excluded from every prior
replay for the entire history because of turnover it earned AFTER the move
the bot caught. ENA_USDT is genuinely a major (in band 84% of days), so its
exclusion was mostly correct; FARTCOIN 44%.

Re-scoring the August episode with TUT admitted flips the sign:

    broken pool   08-19..08-23   n=17   $ -7.01   $-0.412/trade  win 53%
    corrected     08-19..08-23   n=20   $+22.98   $+1.149/trade  win 60%
    live actual   08-20..08-22   n=17   $+44.29   $+2.605/trade  win 71%

Inside episodes $+1.149/trade vs outside $+0.194 - about 6x. That is the
direction the owner's fortnight review claimed, now reproduced on replay
rather than only on the live book.

AND IT STILL DOES NOT ANSWER THE QUESTION. Of three BTC72 >= 10% episodes in
400 days, two are too short to contain a single trade (0.3 and 0.9 days). So
this remains ONE episode with trades: n=1 for the regime question, exactly as
before, and the 6x figure is that one episode against everything else. The
correction improved the measurement, not the sample.

WHAT THIS MEANS FOR THE OTHER STUDIES. Every pit_* study in this family used
the broken pool. Their ARM-VS-ARM comparisons are less affected (both arms
drew from the same pool), but any conclusion about REGIME is materially
exposed, because the symbols the band wrongly excluded are precisely the ones
that move most. Re-running the regime studies on the corrected pool is the
outstanding work.

READ-ONLY. Never places or modifies an order.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_pool import day_key, daily_turnover, describe, pit_majors  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

BAR = 900
CHUNK = 1900
TAIL = 260
H72 = 288
THR = 0.10
GAP_S = 12 * 3600      # stretches closer than this are one episode


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
    days, pool_n = _env("PJ_DAYS", 360), int(_env("PJ_POOL", 120))
    now = int(time.time())
    floor = W.wildcard_min_turnover_usdt()
    eq0 = rt._last_known_equity() or 162.0
    dollar_r = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241) * eq0
    print("equity $%.2f -> 1R = $%.2f | window %.0fd" % (eq0, dollar_r, days))

    tk = cl.get_all_tickers() or []
    N_BAND = int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0))
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    # Today's ranking chooses only WHAT TO FETCH. Eligibility - both the floor
    # and the majors band - is decided per bar below. Today's majors are
    # INCLUDED in the fetch set precisely because they were not majors for most
    # of the window: excluding them is the defect this run exists to fix.
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 3e5)][:pool_n]
    syms = sorted(set(cand) | {"BTC_USDT"})
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    nch = int(days * 86400 // (CHUNK * BAR)) + 1

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

    print("fetching %d symbols..." % len(syms))
    with ThreadPoolExecutor(max_workers=6) as p:
        frames = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 300}
    print("frames: %d" % len(frames))

    btc = frames.get("BTC_USDT")
    if btc is None:
        print("FATAL: no BTC data")
        return 1
    bc = [float(x) for x in btc["close"]]
    bts = [float(x.timestamp()) for x in btc.index]
    B72 = {}
    for i in range(H72, len(bc)):
        if bc[i - H72] > 0:
            B72[bts[i]] = bc[i] / bc[i - H72] - 1.0

    # contiguous stretches where BTC72 >= THR, merged across short gaps
    hot = sorted(t for t, v in B72.items() if v >= THR)
    eps = []
    for t in hot:
        if eps and t - eps[-1][1] <= GAP_S:
            eps[-1][1] = t
        else:
            eps.append([t, t])
    eps = [(a, b) for a, b in eps if b - a >= 6 * 3600]      # ignore blips
    span_d = (bts[-1] - bts[0]) / 86400.0
    print("BTC72 >= %.0f%%: %d episodes over %.0f days (%.1f%% of the window)\n"
          % (THR * 100, len(eps), span_d,
             100.0 * sum(b - a for a, b in eps) / max(1.0, bts[-1] - bts[0])))

    ROLLS = {}
    for s in cand:
        df = frames.get(s)
        if df is None:
            continue
        cs = sizes.get(s, 0.0)
        c = [float(x) for x in df["close"]]
        v = [float(x) for x in df["volume"]]
        raw = [c[k] * v[k] * cs for k in range(len(c))]
        acc, ser = 0.0, []
        ts_all = [float(x.timestamp()) for x in df.index]
        for k, x in enumerate(raw):
            acc += x
            if k >= 96:
                acc -= raw[k - 96]
            if k >= 96:
                ser.append((ts_all[k], acc))
        ROLLS[s] = ser
    PIT = pit_majors(daily_turnover(ROLLS), n=N_BAND)
    print(describe(PIT, watch=("TUT_USDT", "ENA_USDT", "FARTCOIN_USDT")))
    print()

    live_floor = ratchet(3.0, 0.75)
    C = []
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
        bars = list(zip([float(x.timestamp()) for x in df.index],
                        [float(x) for x in df["high"]],
                        [float(x) for x in df["low"]], c))
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < floor:
                continue
            # POINT-IN-TIME BAND: was this symbol a major ON THIS DAY?
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
            C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]), "exit_ts": float(g[1])})
    C.sort(key=lambda x: x["ts"])

    slots, per, T = [], {}, []
    for x in C:
        slots[:] = [q for q in slots if q > x["ts"]]
        per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
        if per[x["sym"]] or len(slots) >= 3:
            continue
        slots.append(x["exit_ts"])
        per[x["sym"]].append(x["exit_ts"])
        T.append(x)
    print("fills: %d\n" % len(T))

    import datetime as _dt

    def fm(t):
        return _dt.datetime.utcfromtimestamp(t).strftime("%m-%d")

    inside_all, outside_all = [], []
    print("EPISODE BY EPISODE  (the question: does the sign repeat?)")
    print("  %-16s %5s %5s %9s %9s %6s" % ("episode", "days", "n", "net $", "$/trade", "win%"))
    for a, b in eps:
        g = [x for x in T if a <= x["ts"] <= b]
        inside_all += g
        if not g:
            print("  %-16s %5.1f %5d        -" % (fm(a) + ".." + fm(b), (b - a) / 86400.0, 0))
            continue
        tot = sum(x["net"] for x in g) * dollar_r
        w = sum(1 for x in g if x["net"] > 0)
        print("  %-16s %5.1f %5d %+9.2f %+9.3f %5.0f%%"
              % (fm(a) + ".." + fm(b), (b - a) / 86400.0, len(g), tot,
                 tot / len(g), 100.0 * w / len(g)))
    ins = {id(x) for x in inside_all}
    outside_all = [x for x in T if id(x) not in ins]

    def line(lbl, g):
        if not g:
            print("  %-22s      -" % lbl)
            return
        tot = sum(x["net"] for x in g) * dollar_r
        w = sum(1 for x in g if x["net"] > 0)
        print("  %-22s n=%4d  $%+9.2f  $%+7.3f/trade  win %4.1f%%"
              % (lbl, len(g), tot, tot / len(g), 100.0 * w / len(g)))

    print("\nPOOLED")
    line("inside BTC72 episodes", inside_all)
    line("outside", outside_all)
    pos = sum(1 for a, b in eps
              if sum(x["net"] for x in T if a <= x["ts"] <= b) > 0)
    nonempty = sum(1 for a, b in eps if any(a <= x["ts"] <= b for x in T))
    print("\nEPISODES WITH A POSITIVE BOOK: %d of %d" % (pos, nonempty))
    print("The live fortnight is ONE such episode. If the sign does not repeat")
    print("across the rest, that fortnight was a draw and not a regime effect.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
