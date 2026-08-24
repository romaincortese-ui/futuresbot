"""The whole retention-ratchet family, on the point-in-time pool.

    railway run --service Futures-bot python tools/pit_ratchet.py

The ratchet shipped 2026-08-22 on tools/peak_fate_ab.py, where every variant was
positive and every one passed the half-split. tools/pit_rerun.py then found that
those studies scored a pool covering 30% of the symbols the bot actually trades,
and on the rebuilt pool the shipped setting (3.0R -> 0.75) is worth -$1.07 and
fails the split.

Two live trades since have made the question concrete rather than academic. TUT
peaked at 5.56R and banked 5.09 at its target; VIRTUAL peaked at 2.02R and banked
0.51 to the 0.30 floor. VIRTUAL is the owner's original complaint repeating, and
the shipped trigger CANNOT reach it: 2.02R sits below 3.0R, so retention never
ratcheted. Of the three armed trades in trial 16, two peaked at 1.16R and 2.02R —
both inside the band the live setting ignores.

So the question is not "is 3.0/0.75 right" but "does ANY member of this family
survive the corrected pool". If none does, giveback in the 1-3R band is a cost of
running a convex sleeve rather than a defect to engineer away, and that is worth
knowing definitively instead of relitigating every time it happens.

Same point-in-time construction as pit_rerun: wide candidate set, each symbol's
own rolling 24h turnover computed bar by bar from its contractSize, eligibility
judged AT THE BAR. All arms share candidates, slots, funding and costs; only the
retention floor differs.

RESULT, 2026-08-24 -- 150 symbols, 208 days, 1817 candidates, point-in-time pool.
THE FAMILY IS REAL. THE SHIPPED SETTING IS ONE OF ITS FAILURES.

    where armed trades peak        n     % of armed
      1.0-2.0R                   435          38.1%
      2.0-3.0R                   255          22.3%   <- live trigger misses both
      3.0-5.0R                   224          19.6%
      >= 5.0R                    227          19.9%
      armed 1141 of 1817 (63%)

    rule                            net $   vs flat   pos wk    recent     older  halves
    flat 0.30 (no ratchet)        +319.97     +0.00   18/29      +0.00     +0.00  (null)
    peak>=1.5 -> 0.50             +287.94    -32.04   19/29     -38.77     +6.74  one half
    peak>=1.5 -> 0.60             +311.99     -7.99   17/29      -7.49     -0.50  no
    peak>=1.5 -> 0.75             +272.83    -47.14   17/29     -69.92    +22.78  one half
    peak>=2.0 -> 0.50             +352.50    +32.52   18/29     +22.19    +10.33  YES
    peak>=2.0 -> 0.60             +373.55    +53.58   18/29     +38.29    +15.29  YES
    peak>=2.0 -> 0.75             +319.28     -0.69   16/29      -1.96     +1.27  one half
    peak>=2.5 -> 0.50             +374.05    +54.08   19/29     +31.64    +22.44  YES
    peak>=2.5 -> 0.60             +371.48    +51.51   17/29     +35.74    +15.77  YES
    peak>=2.5 -> 0.75             +345.88    +25.91   16/29     -11.21    +37.12  one half
    peak>=3.0 -> 0.50             +342.77    +22.79   18/29     +15.47     +7.33  YES
    peak>=3.0 -> 0.60             +351.87    +31.89   18/29     +18.48    +13.42  YES
    peak>=3.0 -> 0.75             +318.10     -1.87   18/29     -15.75    +13.88  one half  <-LIVE
    peak>=4.0 -> 0.50             +327.82     +7.84   18/29      +1.85     +5.99  YES
    peak>=4.0 -> 0.60             +339.53    +19.56   19/29     +10.57     +8.99  YES
    peak>=4.0 -> 0.75             +328.74     +8.77   20/29      -1.70    +10.47  one half

EIGHT OF FIFTEEN SURVIVE THE HALF-SPLIT, and the pattern is coherent rather than
scattered, which is what separates a real family from multiple-comparison luck:

  - RETENTION 0.50-0.60 WORKS, 0.75 DOES NOT. Every 0.75 variant fails. Taking
    three quarters of the peak cuts runners that were still developing; taking
    half or three fifths does not.
  - A 1.5R TRIGGER IS TOO EARLY. All three fail, the deepest at -$47.14. That is
    the same "do not tax the growth phase" mechanism that killed the blanket
    tiered trail.
  - THE SWEET SPOT IS TRIGGER 2.0-2.5 WITH RETAIN 0.50-0.60. Best is 2.5/0.50 at
    +$54.08 with halves of +31.64 and +22.44.

If the effect were zero, a variant would pass both halves about 25% of the time.
Eight of fifteen is 53%, which is not what noise looks like.

THE SHIPPED SETTING (3.0 -> 0.75) IS -$1.87 AND FAILS THE SPLIT. It sits at the
intersection of the two things that do not work: a retention that is too tight
and a trigger above the band where most armed trades live. 60.4% of armed trades
peak below 3.0R, so the live rule cannot reach them — which is exactly what
happened to VIRTUAL_USDT on 2026-08-24 (peak 2.02R, banked 0.51R to the 0.30
floor) and to two of the three armed trades in trial 16.

WHICH ONE TO PREFER, AND WHY IT IS NOT SIMPLY THE BIGGEST. Replay peaks are
biased HIGH -- tools/replay_vs_live.py measures 63% of replay trades arming
against 24% live, because the replay reads bar highs while the bot samples on a
45-60s cycle. So a trigger tuned to 2.5R here corresponds to something lower in
live terms, and a trigger set too high fails silently by never firing.
peak>=2.0 -> 0.60 is +$53.58, statistically indistinguishable from the 2.5/0.50
best, passes both halves more evenly on the recent side, and WOULD have caught
VIRTUAL at 2.02R. It is the more defensible live choice.

NOT CHANGED. Trial 16 is mid-flight with 9 closes and the standing agreement is
to hold. Recorded as the trial-17 candidate.

Read-only. Places nothing.

Env: PR_DAYS (190) PR_POOL (150) PR_SLOTS (3) PR_MIN_TODAY (300000)
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


def ratchet(trigger, hi, base=0.30, arm=1.0):
    def f(peak, atr, slf):
        if peak < arm:
            return None
        return (hi if peak >= trigger else base) * peak
    return f


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars over the window, NOT account P&L.")
    print("    The real account is DOWN lifetime; /report has the true figure. ***")
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PR_DAYS", 190), int(_env("PR_POOL", 150))
    slots = int(_env("PR_SLOTS", 3))
    min_today = _env("PR_MIN_TODAY", 3e5)
    eq = rt._last_known_equity() or 172.0
    now = int(time.time())
    live_floor = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    wide = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                   if str(t.get("symbol") or "").endswith("_USDT")
                   and rt._is_tradeable_crypto(str(t.get("symbol") or ""))
                   and str(t.get("symbol") or "") not in majors
                   and float(t.get("amount24") or 0) >= min_today), reverse=True)
    cand_syms = [s for _a, s in wide[:pool_n]]
    syms = sorted(set(cand_syms) | set(TREND_SYMS))
    print(f"equity ${eq:.2f} | wide set {len(cand_syms)} | floor ${live_floor/1e6:.0f}M "
          f"(judged per bar)")

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

    print("fetching...")
    with ThreadPoolExecutor(max_workers=6) as p:
        frames = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 300}
    span = len(next(iter(frames.values()))) * BAR / 86400
    print(f"frames: {len(frames)} symbols, {span:.0f}d")

    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))
    print("generating candidates (point-in-time eligibility)...")
    cands = []
    for s, df in frames.items():
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
        bars = list(zip([float(x.timestamp()) for x in df.index], h, lo, c))
        ts = [b[0] for b in bars]
        if s in TREND_SYMS:
            for i in range(400, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None and sig.side == "LONG":
                    cands.append((ts[i], s, sig, i, bars, h, lo, c))
        if s in cand_syms:
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or roll[i] < live_floor:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    cands.append((ts[i], s, sig, i, bars, h, lo, c))
    cands.sort(key=lambda x: x[0])
    print(f"candidates: {len(cands)}")
    if not cands:
        return 0

    # ---- where do peaks actually land? ---------------------------------
    peaks = []
    for _ts, _s, sig, i, bars, h, lo, c in cands:
        e = float(sig.entry_price)
        slf = abs(e - float(sig.sl_price)) / e
        if slf <= 0:
            continue
        sgn = 1.0 if sig.side == "LONG" else -1.0
        end_ts = bars[i][0] + shadow.CONVEX_HORIZON_S
        pk = 0.0
        for k in range(i + 1, len(c)):
            if bars[k][0] > end_ts:
                break
            fav = (h[k] - e) / e if sgn > 0 else (e - lo[k]) / e
            pk = max(pk, fav / slf)
        peaks.append(pk)
    armed = [p for p in peaks if p >= 1.0]
    print()
    print("=== WHERE ARMED TRADES PEAK (the band the trigger has to cover) ===")
    for lab, a, b in (("1.0-2.0R", 1.0, 2.0), ("2.0-3.0R", 2.0, 3.0),
                      ("3.0-5.0R", 3.0, 5.0), (">= 5.0R", 5.0, 9e9)):
        n = sum(1 for p in armed if a <= p < b)
        print(f"  {lab:<10} {n:5d}  {100*n/max(1,len(armed)):5.1f}% of armed")
    print(f"  armed total {len(armed)} of {len(peaks)} "
          f"({100*len(armed)/max(1,len(peaks)):.0f}%)")

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
            for ts0, sym, sig, i, bars, h, lo, c in cands:
                if not (lo_t <= ts0 < hi_t):
                    continue
                live[:] = [x for x in live if x > ts0]
                per[sym] = [x for x in per.get(sym, []) if x > ts0]
                if per[sym] or len(live) >= slots:
                    continue
                row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
                       "tp": float(sig.tp_price), "side": sig.side}
                g = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                            shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                            shadow.cost_r(row), floor_fn,
                            float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if g is None:
                    continue
                live.append(g[1])
                per[sym].append(g[1])
                wt += g[0] * eq * 0.12 * float(sig.sl_margin_pct) / 100.0
            tot += wt
            pos += 1 if wt > 0 else 0
        return tot, pos

    flat = make_floor("flat", 0.30, 1.0)
    b_all, b_pos = book(flat)
    b_rec = book(flat, 0, mid)[0]
    b_old = book(flat, mid, n_win)[0]
    print()
    print("=== THE WHOLE RATCHET FAMILY, POINT-IN-TIME POOL ===")
    print(f"{'rule':<26} {'net $':>10} {'vs flat':>9} {'pos wk':>8} "
          f"{'recent':>9} {'older':>9}  both halves?")
    print(f"{'flat 0.30 (no ratchet)':<26} {b_all:+10.2f} {0.0:+9.2f} "
          f"{b_pos:4d}/{n_win:<3d} {0.0:+9.2f} {0.0:+9.2f}  (null)")
    survivors = []
    for trig in (1.5, 2.0, 2.5, 3.0, 4.0):
        for hi in (0.50, 0.60, 0.75):
            fn = ratchet(trig, hi)
            tot, pos = book(fn)
            rec = book(fn, 0, mid)[0] - b_rec
            old = book(fn, mid, n_win)[0] - b_old
            ok = "YES" if rec > 0 and old > 0 else (
                "no" if rec < 0 and old < 0 else "one half only")
            star = "  <-live cfg" if (trig, hi) == (3.0, 0.75) else ""
            if ok == "YES":
                survivors.append((tot - b_all, trig, hi, rec, old))
            print(f"{'peak>=' + format(trig,'.1f') + ' -> ' + format(hi,'.2f'):<26} "
                  f"{tot:+10.2f} {tot-b_all:+9.2f} {pos:4d}/{n_win:<3d} "
                  f"{rec:+9.2f} {old:+9.2f}  {ok}{star}")
    print()
    if survivors:
        survivors.sort(reverse=True)
        d, trig, hi, rec, old = survivors[0]
        print(f"SURVIVORS: {len(survivors)} of 15. Best peak>={trig:.1f} -> {hi:.2f} "
              f"at {d:+.2f} (recent {rec:+.2f}, older {old:+.2f}).")
    else:
        print("NO VARIANT SURVIVES. Giveback in the armed band is a cost of the")
        print("strategy, not a defect — and the shipped ratchet should come out.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
