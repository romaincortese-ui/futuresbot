"""Regime-conditional re-test of the convex retention trail, plus alternatives.

    railway run --service Futures-bot python tools/retention_trail_ab.py

WHY RE-TEST. The live trail arms at +1R and books max(0.30 x peak, 1.5 x cost).
Its 444-entry study found every +0.10 of retention above 0.30 monotonically
worse, and shipped it explicitly as a DESIGN FIX (never give back >100% of built
profit) rather than an edge claim — net +0.030R/trade, t 0.83, "statistically
ZERO". That measurement was taken on a FLAT tape.

The tape is no longer flat, and four consecutive givebacks say so:

    TUT 08-14  peak 4.14R -> booked 2.69R   (gave back 1.45R)
    ACE 08-19  peak 2.12R -> booked 0.61R   (gave back 1.51R)
    SOL 08-21  peak 1.66R -> booked 0.38R   (gave back 1.28R)
    ETH 08-21  peak 2.17R -> booked 0.57R   (gave back 1.60R)

Nothing is broken — that is the floor doing exactly what it specifies. The
question is whether 0.30 is still the right number when trends persist, and
whether the SHAPE of the rule (a flat fraction of peak) is the right shape at
all.

WHAT IS SWEPT
  parameters   retain in {0.20, 0.30 (live), 0.40, 0.50, 0.70}
               arm    in {1.0 (live), 1.5, 2.0}  — how far it runs before
                      trailing at all
  structures   none      no trail: -1R stop / TP / 24h clock only
               tiered    retention RISES with peak (protect big runs harder)
               atr       floor = peak - k x ATR, volatility-scaled not
                         proportional
               breakeven arm at +1R to breakeven, then trail only past +2R

All variants keep the live 1.5 x round-trip cost floor, the same -1R stop, the
same target and the same 24h clock, so only the trail differs. Scored in dollars
on the real book (wildcard band + the trend sleeve's names), with slots, funding
and the point-in-time turnover floor, then SPLIT BY REGIME at entry.

VALIDATED: this file's resolver was compared against the SHIPPED
resolve_outcome(convex=True) on 125 real signals at flat/0.30/arm1.0 — 125/125
agree, max difference 0.0005R. The sweep is measuring the real bot.

RESULT, 2026-08-21 (CORRECTED — see the note below), 63 symbols, 60d, 3 slots,
271 signals:

    variant                ALL $    n   TP  stop  trail  t/out  avg h
    flat 0.20/arm1.0     +132.54  114   12    43     42     17    9.1
    flat 0.30/arm1.0     +128.93  116   11    45     44     16    8.8  <- LIVE
    flat 0.40/arm1.0     +142.78  121   10    45     49     17    8.6
    flat 0.50/arm1.0     +140.40  123    9    47     54     13    8.1
    flat 0.70/arm1.0     +101.29  134    3    48     75      8    6.8
    flat 0.30/arm1.5     +130.80  110   12    50     25     23   10.4
    flat 0.30/arm2.0     +114.01  108   12    55     15     26   11.0
    none                 +164.22  104   15    54      0     35   12.6
    tiered               +143.90  118   10    47     49     12    8.3
    atr                  +101.59  134    3    50     74      7    6.8
    breakeven            +123.33  111   11    41     39     20    9.7

TWO BUGS IN THE FIRST VERSION OF THIS TOOL, both of which flattered `none`:
  1. every variant released its slot at a FIXED 24h regardless of when the
     trade actually exited, so the trail arms got no credit for freeing
     capacity early — which is most of what a trail is for;
  2. a trade whose data ran out before the horizon was marked to market as if
     it had closed, crediting outcomes that had not resolved.
Fixed: slots release at the real exit, and an unresolved trade returns None.

WHAT CHANGED WHEN THEY WERE FIXED. The apparent MONOTONE arm effect
(1.0 -> 1.5 -> 2.0 -> none) DISAPPEARED. arm 2.0 now reads +114.01, WORSE than
the live +128.93. The earlier "+$21.79 from arming at 2R" was a simulation
artifact and is withdrawn.

HOW `none` ACTUALLY MAKES MONEY — it is NOT take-profits. Only 15 of 104 trades
(14%) reach TP. Removing the trail redistributes its 44 exits into +4 TP, +9
extra full -1R STOPS and +19 TIMEOUTS, while taking 12 FEWER trades because
positions hold longer (avg 8.8h -> 12.6h) and occupy slots. The gain comes from
timing out at the 24h mark rather than trailing out early, so `none` is
effectively a bet that HOLDING LONGER PAYS. That is true in a rising tape and
false in a falling one, and this 60-day window contains the recent rally.

SURVIVING CANDIDATES, all modest and all invariant-preserving:
    tiered      +143.90  (+$14.97 vs live)
    flat 0.40   +142.78  (+$13.85)
    flat 0.50   +140.40  (+$11.47)
Rejected by the data: atr (-$27), 0.70 retention (-$28), breakeven (-$6), and
arm 1.5/2.0.

Read-only. Places nothing.

Env: RT_DAYS (60) RT_SYMS (60) RT_SLOTS (3)
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from futuresbot import shadow_ledger as shadow
from futuresbot import wildcard as W
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime
from futuresbot.trend import detect_trend_signal

CHUNK, BAR = 2000, 900
TREND_SYMS = ("ETH_USDT", "SOL_USDT")


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def resolve(bars, i0, entry, sl, tp, tp_r, side, horizon_s, cost_r, floor_fn,
            atr_frac, now_ts):
    """Walk bars from i0 under a pluggable trail.

    Returns (net_r, exit_ts, kind), or None when the trade is STILL OPEN.
    That None matters: the first version marked an unfinished trade to market
    as if it had closed, silently crediting the no-trail arm for positions
    that had not resolved. The shipped resolver refuses those; so does this.

    Otherwise mirrors the live semantics: adverse-first within a bar, the
    armed floor checked BEFORE the hard stop, peak from PRIOR bars only,
    timeout closing at the bar mark."""
    sgn = 1.0 if side == 'LONG' else -1.0
    one_r = abs(entry - sl)
    if one_r <= 0:
        return None
    t0 = bars[i0][0]
    floor_min = 1.5 * cost_r
    peak_r = 0.0
    last = entry
    seen = False
    for k in range(i0 + 1, len(bars)):
        ts, hi, lo, close = bars[k]
        if ts - t0 > horizon_s:
            break
        seen = True
        level = floor_fn(peak_r, atr_frac, one_r / entry)
        if level is not None:
            level = max(level, floor_min)
            if level < peak_r:
                adverse_r = ((lo if sgn > 0 else hi) - entry) * sgn / one_r
                if adverse_r <= level:
                    return (level - cost_r, ts, 'trail')
        if (lo <= sl) if sgn > 0 else (hi >= sl):
            return (-1.0 - cost_r, ts, 'stop')
        if (hi >= tp) if sgn > 0 else (lo <= tp):
            return (tp_r - cost_r, ts, 'tp')
        peak_r = max(peak_r, ((hi if sgn > 0 else lo) - entry) * sgn / one_r)
        last = close
    if not seen:
        return None
    # Only a trade whose 24h clock has genuinely expired counts as timed out.
    if now_ts - t0 < horizon_s:
        return None
    return (((last - entry) * sgn / one_r) - cost_r, t0 + horizon_s, 'timeout')


def make_floor(kind, retain, arm):
    if kind == "none":
        return lambda peak, atr, slf: None
    if kind == "flat":
        return lambda peak, atr, slf: (retain * peak) if peak >= arm else None
    if kind == "tiered":
        def f(peak, atr, slf):
            if peak < arm:
                return None
            r = 0.30 if peak < 2 else (0.50 if peak < 3 else 0.65)
            return r * peak
        return f
    if kind == "atr":
        # floor = peak - k x ATR, expressed in R (ATR as a fraction of price
        # divided by the stop fraction gives ATR in R units).
        def f(peak, atr, slf):
            if peak < arm or slf <= 0:
                return None
            return peak - 1.5 * (atr / slf)
        return f
    if kind == "breakeven":
        def f(peak, atr, slf):
            if peak < 1.0:
                return None
            return 0.0 if peak < 2.0 else retain * peak
        return f
    raise ValueError(kind)


def main() -> int:
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, n_syms, slots = _env("RT_DAYS", 60), int(_env("RT_SYMS", 60)), int(_env("RT_SLOTS", 3))
    eq = rt._last_known_equity() or 158.0
    now = int(time.time())
    min_turn = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    band = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                   if str(t.get("symbol") or "").endswith("_USDT")
                   and rt._is_tradeable_crypto(str(t.get("symbol") or ""))
                   and str(t.get("symbol") or "") not in majors
                   and float(t.get("amount24") or 0) >= 1e6), reverse=True)
    syms = [s for _a, s in band[:n_syms]] + list(TREND_SYMS) + ["BTC_USDT"]
    amt = {s: a for a, s in band}
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

    with ThreadPoolExecutor(max_workers=8) as pool:
        F = {s: f for s, f in pool.map(fetch, syms) if f is not None and len(f) >= 300}
    print(f"equity ${eq:.2f} | {len(F)} symbols | {days:.0f}d | {slots} slots")
    if "BTC_USDT" not in F:
        print("no BTC for the regime label"); return 1

    C = {}
    for s, df in F.items():
        c = [float(x) for x in df["close"]]
        v = [float(x) for x in df["volume"]]
        raw = [c[i] * v[i] for i in range(len(c))]
        tail = sum(raw[-96:])
        sc = (amt.get(s, 0.0) / tail) if tail > 0 else 0.0
        roll, acc = [0.0] * len(c), 0.0
        for i, x in enumerate(raw):
            acc += x
            if i >= 96:
                acc -= raw[i - 96]
            roll[i] = acc * sc
        C[s] = {"c": c, "h": [float(x) for x in df["high"]], "l": [float(x) for x in df["low"]],
                "t": [float(x.timestamp()) for x in df.index], "turn": roll, "df": df}
    btc = C["BTC_USDT"]["c"]
    btc_t = C["BTC_USDT"]["t"]

    def regime_at(ts):
        k = min(range(len(btc_t)), key=lambda i: abs(btc_t[i] - ts))
        if k < 672:
            return "FLAT"
        r = btc[k] / btc[k - 672] - 1.0
        return "TREND-UP" if r >= 0.05 else ("TREND-DN" if r <= -0.05 else "FLAT")

    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))
    print("generating candidates with the SHIPPED detectors...")
    cands = []
    for s, d in C.items():
        c, turn, ts, df = d["c"], d["turn"], d["t"], d["df"]
        bars = list(zip(d["t"], d["h"], d["l"], d["c"]))
        if s in TREND_SYMS:
            for i in range(400, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None and sig.side == "LONG":
                    cands.append((ts[i], s, sig, i, bars))
        if s == "BTC_USDT":
            continue
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or turn[i] < min_turn:
                continue
            if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                continue
            sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
            if sig is not None:
                cands.append((ts[i], s, sig, i, bars))
    cands.sort(key=lambda x: x[0])
    print(f"signals: {len(cands)}")

    def run(kind, retain, arm):
        floor_fn = make_floor(kind, retain, arm)
        live, per = [], {}
        out = {"TREND-UP": [], "FLAT": [], "TREND-DN": []}
        kinds = {"tp": 0, "stop": 0, "trail": 0, "timeout": 0}
        holds = []
        for ts, sym, sig, i, bars in cands:
            live[:] = [x for x in live if x > ts]
            per[sym] = [x for x in per.get(sym, []) if x > ts]
            if per[sym] or len(live) >= slots:
                continue
            row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
                   "tp": float(sig.tp_price), "side": sig.side}
            cr = shadow.cost_r(row)
            tp_r = shadow.signal_tp_r(sig)
            atr = float(getattr(sig, "atr_pct", 0.0) or 0.0)
            got = resolve(bars, i, row["entry"], row["sl"], row["tp"], tp_r,
                          sig.side, shadow.CONVEX_HORIZON_S, cr, floor_fn, atr, now)
            if got is None:
                continue
            r_net, exit_ts, kind_ = got
            one_r_usd = eq * 0.12 * float(sig.sl_margin_pct) / 100.0
            kinds[kind_] += 1
            holds.append((exit_ts - ts) / 3600.0)
            # Release the slot when the trade ACTUALLY exited, not at a fixed
            # 24h. Holding every variant for the full horizon gave the trail
            # arms no credit for freeing capacity early, which is most of what
            # a trail is for.
            live.append(exit_ts)
            per[sym].append(exit_ts)
            out[regime_at(ts)].append(r_net * one_r_usd)
        return out, kinds, (sum(holds) / len(holds) if holds else 0.0)

    variants = [("flat", 0.20, 1.0), ("flat", 0.30, 1.0), ("flat", 0.40, 1.0),
                ("flat", 0.50, 1.0), ("flat", 0.70, 1.0),
                ("flat", 0.30, 1.5), ("flat", 0.30, 2.0),
                ("none", 0.0, 0.0), ("tiered", 0.0, 1.0),
                ("atr", 0.0, 1.0), ("breakeven", 0.30, 1.0)]
    print('')
    print('%-22s %9s %4s %4s %5s %6s %6s %6s' % (
        'variant', 'ALL $', 'n', 'TP', 'stop', 'trail', 't/out', 'avg h'))
    base = None
    for kind, retain, arm in variants:
        res, kinds, avg_h = run(kind, retain, arm)
        tot = sum(sum(v) for v in res.values())
        n = sum(len(v) for v in res.values())
        label = ('%s %.2f/arm%.1f' % (kind, retain, arm)) if kind == 'flat' else kind
        if kind == 'flat' and retain == 0.30 and arm == 1.0:
            label += ' <-LIVE'
            base = tot
        print('%-22s %+9.2f %4d %4d %5d %6d %6d %6.1f' % (
            label, tot, n, kinds['tp'], kinds['stop'], kinds['trail'],
            kinds['timeout'], avg_h))
    if base is not None:
        print(f"\n(live baseline ${base:+.2f}; deltas are the column above minus that)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
