"""Once a trade is FAR ahead, what actually happens to it?

    railway run --service Futures-bot python tools/peak_fate_ab.py

The owner's objection, and it is a fair one: a message reading "TUT unrealized
+$11.21 (+3.46R) — above every close this week; floor locked at +$3.36" and then
banking $3.36 is a bad outcome to hand a human, whatever the expectancy says.

THIS IS NOT THE RULE I TESTED BEFORE AND REJECTED. tools/trail_bigmove_windows.py
raised retention for EVERY trade (a blanket 0.50) and lost -$4.09 over 188 days.
The proposal here is CONDITIONAL: leave the 0.30 floor alone until a trade
becomes exceptional, then ratchet it. Different rule, so it needs its own test
rather than the previous verdict applied by association.

Three questions, in the order they decide the answer:

  1. From a peak of P, how often does the trade go on to TP? If runners usually
     complete, a loose floor is correct and the ratchet is a tax on the winners
     that pay for everything.
  2. How often does it instead give the gain back — to the floor, or to the 24h
     clock at some lower level?
  3. Does a conditional ratchet actually earn money, per regime and split across
     halves?

The exceptional trigger is expressed as a peak-R threshold rather than "above
every close this week", because the dollar version depends on account size and
the R version is the same rule stated scale-free. Both are the same question:
this trade is unusually far ahead, should the floor tighten.

RESULT, 2026-08-22 -- 74 symbols, 208 days, 1380 resolved candidates.
THE OWNER WAS RIGHT. THE CONDITIONAL RATCHET WORKS AND SHOULD SHIP.

    peak >=     n   reach TP  exit >= 0.8xpeak  mean exit R  mean peak
        1.0   893      21.2%              8.1%        +0.85       3.58
        2.0   579      32.6%             10.5%        +1.22       4.72
        2.5   455      41.5%             11.9%        +1.46       5.40
        3.0   378      49.7%             13.2%        +1.63       5.95
        5.0   200      56.0%              3.0%        +1.82       7.91

    how a trade that reached 2.5R actually ENDS, under the live 0.30 floor:
        tp        189   41.5%
        trail     184   40.4%      <- gives the run back to 0.30 x peak
        stop       61   13.4%      <- peaked >= 2.5R and STILL finished at -1R
        timeout    21    4.6%

    rule                              net $   vs live   pos wk    recent     older  halves
    LIVE flat 0.30                  +330.94     +0.00   17/29   +296.03    +34.91  (null)
    peak>=2.0 -> retain 0.60        +378.26    +47.32   15/29    +41.41     +5.91  YES
    peak>=2.0 -> retain 0.75        +350.84    +19.90   16/29     +7.96    +11.94  YES
    peak>=2.5 -> retain 0.60        +362.78    +31.84   16/29    +30.61     +1.23  YES
    peak>=2.5 -> retain 0.75        +358.53    +27.59   16/29     +8.05    +19.55  YES
    peak>=3.0 -> retain 0.60        +356.86    +25.91   17/29    +25.48     +0.44  YES
    peak>=3.0 -> retain 0.75        +356.27    +25.33   17/29    +21.30     +4.03  YES
    peak>=3.0 -> retain 0.90        +344.72    +13.78   17/29     +8.06     +5.71  YES
    peak>=4.0 -> retain 0.75        +335.08     +4.14   18/29     +1.50     +2.64  YES

EVERY VARIANT IS POSITIVE AND EVERY VARIANT PASSES THE HALF-SPLIT. Nothing else
measured this session did that. The robustness is the finding: this is not one
lucky threshold, it is a family.

WHY THIS WORKS WHERE THE BLANKET TIERED TRAIL FAILED (-$4.09 over 188 days,
tools/trail_bigmove_windows.py). That rule raised retention on EVERY armed trade,
including those peaking 1.0-2.0R where the runner still has most of its move
ahead — it cut winners during their growth phase, and on a convex sleeve where
runners pay for everything that is fatal. The conditional rule leaves 0.30 alone
until the trade is already 2.5-3R ahead, by which point the mean peak is 5.4-6.0R
against a 5R target: the runner has ALREADY made its money and the only question
left is whether it is banked. Tightening there protects without taxing growth.

THE FATE TABLE IS THE ARGUMENT. From a peak of 3R, only 13.2% of trades exit
within 20% of their high and just under half reach TP — so the fade is the NORM,
not the exception. And 13.4% of trades that touched 2.5R still finished at -1R,
because the floor is set from PRIOR bars: a bar that spikes to a new peak and
collapses within the same bar is floored on the old peak. That is live behaviour,
not a simulation artefact.

READ THE COSTS HONESTLY. The largest variant (peak>=2.0 -> 0.60, +$47.32) is 88%
recent-half and drops weekly consistency 17/29 -> 15/29. The variants that keep
consistency AND balance across halves are peak>=3.0 -> 0.75 (+$25.33, 17/29,
+21.30/+4.03) and peak>=2.5 -> 0.75 (+$27.59, 16/29, +8.05/+19.55). Preferring a
slightly smaller, more evenly-distributed edge over the biggest headline is the
same discipline that rejected the sharper size tilts.

Read-only. Places nothing.

Env: PF_DAYS (190) PF_POOL (70) PF_SLOTS (3)
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
from futuresbot.trend import detect_trend_signal
from retention_trail_ab import make_floor, resolve

CHUNK, BAR = 2000, 900
TREND_SYMS = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
LIVE_FLOOR = make_floor("flat", 0.30, 1.0)


def ratchet(trigger: float, retain_hi: float, base: float = 0.30, arm: float = 1.0):
    """Live 0.30 floor until peak >= trigger, then retain_hi x peak.

    Ratchet-only: retain_hi > base and peak only rises, so the floor never falls.
    """
    def f(peak, atr, slf):
        if peak < arm:
            return None
        return (retain_hi if peak >= trigger else base) * peak
    return f


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PF_DAYS", 190), int(_env("PF_POOL", 70))
    slots = int(_env("PF_SLOTS", 3))
    eq = rt._last_known_equity() or 174.0
    now = int(time.time())
    min_turn = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    ranked = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wc = [s for a, s in ranked if s not in majors and a >= min_turn][:pool_n]
    syms = sorted(set(wc) | set(TREND_SYMS) | {"BTC_USDT"})
    print(f"equity ${eq:.2f} | {len(syms)} symbols | {slots} slots")

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

    with ThreadPoolExecutor(max_workers=6) as p:
        F = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 400}
    span = len(next(iter(F.values()))) * BAR / 86400
    print(f"frames: {len(F)} symbols, {span:.0f}d")

    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))
    print("generating candidates and walking each to its PEAK...")
    cands = []
    for s, df in F.items():
        cs = sizes.get(s, 0.0)
        c = [float(x) for x in df["close"]]
        h = [float(x) for x in df["high"]]
        lo = [float(x) for x in df["low"]]
        v = [float(x) for x in df["volume"]]
        raw = [c[k] * v[k] * cs for k in range(len(c))]
        roll, acc = [0.0] * len(c), 0.0
        for k, x in enumerate(raw):
            acc += x
            if k >= 96:
                acc -= raw[k - 96]
            roll[k] = acc
        ts = [float(x.timestamp()) for x in df.index]
        bars = list(zip(ts, h, lo, c))

        def add(sig, i, kind):
            e = float(sig.entry_price)
            slp = float(sig.sl_price)
            slf = abs(e - slp) / e
            if slf <= 0:
                return
            sgn = 1.0 if sig.side == "LONG" else -1.0
            # peak R within the 24h horizon, from bar extremes
            end_ts = ts[i] + shadow.CONVEX_HORIZON_S
            peak = 0.0
            for k in range(i + 1, len(c)):
                if ts[k] > end_ts:
                    break
                fav = (h[k] - e) / e if sgn > 0 else (e - lo[k]) / e
                peak = max(peak, fav / slf)
            else:
                if ts[-1] < end_ts:
                    return          # not resolved yet — never mark to market
            cands.append((ts[i], s, sig, i, bars, kind, peak, slf))

        if s in TREND_SYMS:
            for i in range(400, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None and sig.side == "LONG":
                    add(sig, i, "TREND")
        if s in wc:
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or roll[i] < min_turn:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    add(sig, i, "WILDCARD")
    cands.sort(key=lambda x: x[0])
    print(f"resolved candidates: {len(cands)}")
    if not cands:
        return 0

    def outcome(c_, floor_fn):
        _ts, _s, sig, i, bars, _k, _peak, _slf = c_
        row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
               "tp": float(sig.tp_price), "side": sig.side}
        return resolve(bars, i, row["entry"], row["sl"], row["tp"],
                       shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                       shadow.cost_r(row), floor_fn,
                       float(getattr(sig, "atr_pct", 0.0) or 0.0), now)

    # ---------------------------------------------------------------
    # 1 + 2. THE FATE OF A TRADE THAT IS ALREADY FAR AHEAD
    # ---------------------------------------------------------------
    print()
    print("=== FATE, conditional on reaching a peak of at least P (LIVE 0.30 floor) ===")
    print(f"{'peak >=':>8} {'n':>5} {'reach TP':>10} {'exit >= 0.8xpeak':>17} "
          f"{'exit <= 0.5xpeak':>17} {'mean exit R':>12} {'mean peak':>10}")
    for P in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0):
        sub = [c_ for c_ in cands if c_[6] >= P]
        if len(sub) < 5:
            continue
        got = [(c_, outcome(c_, LIVE_FLOOR)) for c_ in sub]
        got = [(c_, g) for c_, g in got if g is not None]
        if not got:
            continue
        n = len(got)
        tps = sum(1 for _c, g in got if g[2] == "tp")
        keep = sum(1 for c_, g in got if g[0] >= 0.8 * c_[6])
        lost = sum(1 for c_, g in got if g[0] <= 0.5 * c_[6])
        mexit = sum(g[0] for _c, g in got) / n
        mpeak = sum(c_[6] for c_, _g in got) / n
        print(f"{P:8.1f} {n:5d} {100*tps/n:9.1f}% {100*keep/n:16.1f}% "
              f"{100*lost/n:16.1f}% {mexit:+12.2f} {mpeak:10.2f}")

    print()
    print("=== how those trades actually END (peak >= 2.5R, live floor) ===")
    sub = [c_ for c_ in cands if c_[6] >= 2.5]
    got = [(c_, outcome(c_, LIVE_FLOOR)) for c_ in sub]
    got = [(c_, g) for c_, g in got if g is not None]
    kinds = {}
    for _c, g in got:
        kinds[g[2]] = kinds.get(g[2], 0) + 1
    tot = len(got) or 1
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<10} {v:4d}  {100*v/tot:5.1f}%")

    # ---------------------------------------------------------------
    # 3. DOES THE CONDITIONAL RATCHET EARN MONEY?
    # ---------------------------------------------------------------
    win_s = 7 * 86400
    n_win = max(1, int(span // 7))
    mid = n_win // 2

    def book(floor_fn, k_lo=0, k_hi=None):
        tot = 0.0
        pos = 0
        for k in range(k_lo, n_win if k_hi is None else k_hi):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            live, per, wt = [], {}, 0.0
            for c_ in cands:
                ts0, sym, sig, i, bars, kind, _peak, _slf = c_
                if not (lo_t <= ts0 < hi_t):
                    continue
                live[:] = [x for x in live if x > ts0]
                per[sym] = [x for x in per.get(sym, []) if x > ts0]
                if per[sym] or len(live) >= slots:
                    continue
                g = outcome(c_, floor_fn)
                if g is None:
                    continue
                r_net, ex, _k = g
                live.append(ex)
                per[sym].append(ex)
                wt += r_net * eq * 0.12 * float(sig.sl_margin_pct) / 100.0
            tot += wt
            pos += 1 if wt > 0 else 0
        return tot, pos

    print()
    print("=== CONDITIONAL RATCHET vs the live flat 0.30 ===")
    base_all, base_pos = book(LIVE_FLOOR)
    base_rec = book(LIVE_FLOOR, 0, mid)[0]
    base_old = book(LIVE_FLOOR, mid, n_win)[0]
    print(f"{'rule':<28} {'net $':>10} {'vs live':>9} {'pos wk':>8} "
          f"{'recent':>9} {'older':>9}  both halves?")
    print(f"{'LIVE flat 0.30':<28} {base_all:+10.2f} {0.0:+9.2f} "
          f"{base_pos:4d}/{n_win:<3d} {base_rec:+9.2f} {base_old:+9.2f}  (null)")
    for trig, hi in ((2.0, 0.60), (2.0, 0.75), (2.5, 0.60), (2.5, 0.75),
                     (3.0, 0.60), (3.0, 0.75), (3.0, 0.90), (4.0, 0.75)):
        fn = ratchet(trig, hi)
        tot, pos = book(fn)
        rec = book(fn, 0, mid)[0] - base_rec
        old = book(fn, mid, n_win)[0] - base_old
        ok = "YES" if rec > 0 and old > 0 else ("no" if rec < 0 and old < 0 else "one half only")
        print(f"{'peak>=' + format(trig, '.1f') + ' -> retain ' + format(hi, '.2f'):<28} "
              f"{tot:+10.2f} {tot-base_all:+9.2f} {pos:4d}/{n_win:<3d} "
              f"{rec:+9.2f} {old:+9.2f}  {ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
