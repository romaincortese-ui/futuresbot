"""What does THIS book do when the market falls? And how bad does it get?

    railway run --service Futures-bot python tools/downside_readiness.py

Asked before adding capital. The claim under test is the owner's: "it doesn't
lose in a flat market and it catches moves in both directions." The first two
thirds are supported; the third is the one that has never been observed live.
The account's whole history sits inside a rising market, and the last week alone
put the majors up 22-60%.

So this replays the CURRENT full config — renormalised sizing, the retention
ratchet, the $2M floor, ETH/XRP/ZEC long-only trend, both-sided wildcard — as a
COMPOUNDED equity path over 360 days, and reports the three things a capital
decision actually needs:

  1. What happens per BTC regime, with the longest window available so the DOWN
     and CRASH buckets have more than a fortnight in them.
  2. The worst week, worst month and maximum drawdown — the numbers that hurt on
     a bigger balance, and the ones a 28% week makes easy to forget.
  3. Whether the down-regime result rests on enough weeks to mean anything.

RESULT, 2026-08-23 -- 63 symbols, 361 days, 2495 candidates, 51 weekly windows.
THE "BOTH DIRECTIONS" CLAIM IS NOT SUPPORTED. DOWN IS THE WORST REGIME.

    bucket             weeks      net $    per wk   worst wk   wk > 0
    CRASH   <= -15%        1     +55.46    +55.46     +55.46    1/1
    DOWN  -15..-5%         9     -12.79     -1.42     -33.61    5/9
    FLAT   -5..+5%        34    +294.99     +8.68     -22.79   22/34
    UP     +5..+15%        6     +62.48    +10.41     -13.59    4/6
    SURGE   >= +15%        1     +87.54    +87.54     +87.54    1/1

    compounded: $181.26 -> $1800.35 (+893.2%) | MAX DRAWDOWN 48.4%
    all 51 weeks: +487.68 | 33 positive | worst -33.61 | best +87.54

    the five worst weeks:
      BTC  -7.1%   -33.61   34 trades
      BTC  -9.3%   -26.54   21 trades
      BTC  +0.4%   -22.79   14 trades
      BTC  -6.6%   -18.51    4 trades
      BTC  +1.3%   -13.82   12 trades

MODERATE DOWN WEEKS ARE THE BOOK'S WEAKEST REGIME, not its second-best. Nine of
them average -$1.42 and only 5/9 are positive, and three of the five worst weeks
in the whole year are down weeks. The wildcard short arm converts those weeks
from bad to roughly flat — that is what it was measured to do and it is doing it
— but converting a loss to a smaller loss is not "catching the move down".

THE SINGLE CRASH WEEK IS AN ANECDOTE. +$55.46 on n=1. 361 days contains exactly
one week where BTC fell more than 15%. Nothing about deep-drawdown behaviour is
established, and the pre-registered trend-short gate in docs/DECISION_RULE.md
exists precisely because that question is open.

FLAT IS THE EARNER: 34 of 51 weeks and +$294.99, 60% of the total. The strategy
is not regime-agnostic. It is a LONG-BIASED CONVEX BOOK that harvests impulses in
quiet-to-rising tape, survives falling tape, and makes its money from neither
extreme.

AND THE DRAWDOWN IS THE NUMBER A CAPITAL DECISION TURNS ON: 48.4% peak to trough
over the year, on the current config, compounding at 2.41% risk per trade. A 28.8%
week is not the shape of this thing; a halving is inside its measured range.

CAVEATS THAT ALL POINT THE SAME WAY (optimistic): the replay is unconstrained —
no vetoes, no streak throttle, no scan cap, no min_vol skip — so it takes more
trades than the live bot; only symbols with 361 days of history are included,
which is survivorship; and fills are modelled at a flat cost that ignores the
thin tail. Treat +893% as the shape, never the level.

Read-only. Places nothing.

Env: DR_DAYS (420) DR_POOL (60) DR_SLOTS (3) DR_TREND_SLOTS (2)
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
from peak_fate_ab import ratchet
from retention_trail_ab import resolve

CHUNK, BAR = 2000, 900
TREND_SYMS = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
LIVE_TRAIL = ratchet(3.0, 0.75)          # shipped 2026-08-22
BASE_RISK = 0.0241                       # renormalised, shipped 2026-08-22

BUCKETS = [
    ("CRASH   <= -15%", lambda m: m <= -0.15),
    ("DOWN  -15..-5%", lambda m: -0.15 < m <= -0.05),
    ("FLAT   -5..+5%", lambda m: -0.05 < m < 0.05),
    ("UP     +5..+15%", lambda m: 0.05 <= m < 0.15),
    ("SURGE   >= +15%", lambda m: m >= 0.15),
]


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars over the window, NOT account P&L.")
    print("    Arms marked 'live cfg' are the live SETTINGS, not live results.")
    print("    The real account is DOWN lifetime; /report has the true figure. ***")
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("DR_DAYS", 420), int(_env("DR_POOL", 60))
    slots, tr_slots = int(_env("DR_SLOTS", 3)), int(_env("DR_TREND_SLOTS", 2))
    eq0 = rt._last_known_equity() or 181.0
    now = int(time.time())
    min_turn = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    ranked = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wc = [s for a, s in ranked if s not in majors and a >= min_turn][:pool_n]
    syms = sorted(set(wc) | set(TREND_SYMS) | {"BTC_USDT"})
    print(f"start ${eq0:.2f} | {len(syms)} symbols | risk {BASE_RISK*100:.2f}%/trade "
          f"| ratchet 3.0R->0.75")

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
    print("generating candidates with the SHIPPED detectors...")
    cands = []
    for s, df in F.items():
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
        ts = [b[0] for b in bars]
        if s in TREND_SYMS:
            for i in range(400, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None and sig.side == "LONG":     # TREND_LONG_ONLY=1
                    cands.append((ts[i], s, sig, i, bars, "TREND"))
        if s in wc:
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or roll[i] < min_turn:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:                            # both sides live
                    cands.append((ts[i], s, sig, i, bars, "WILDCARD"))
    cands.sort(key=lambda x: x[0])
    print(f"candidates: {len(cands)}")
    if not cands:
        return 0

    btc = F.get("BTC_USDT")
    btc_c = [float(x) for x in btc["close"]]
    btc_t = [float(x.timestamp()) for x in btc.index]

    def btc_move(lo, hi):
        a = min(range(len(btc_t)), key=lambda i: abs(btc_t[i] - lo))
        b = min(range(len(btc_t)), key=lambda i: abs(btc_t[i] - hi))
        return (btc_c[b] / btc_c[a] - 1.0) if btc_c[a] > 0 else 0.0

    # ---- compounded path with real slots -------------------------------
    equity = eq0
    peak = eq0
    maxdd = 0.0
    open_pos = []
    weekly: dict[int, float] = {}
    for ts0, sym, sig, i, bars, kind in cands:
        for p_ in [x for x in open_pos if x[0] <= ts0]:
            equity += p_[1] * p_[2]
            open_pos.remove(p_)
            peak = max(peak, equity)
            maxdd = max(maxdd, (peak - equity) / peak if peak > 0 else 0.0)
            weekly[int(p_[0] // (7 * 86400))] = weekly.get(int(p_[0] // (7 * 86400)), 0.0) + p_[1] * p_[2]
        if equity <= 0:
            break
        book = [x for x in open_pos if x[3] == kind]
        cap = tr_slots if kind == "TREND" else slots
        if any(x[4] == sym for x in open_pos) or len(book) >= cap:
            continue
        row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
               "tp": float(sig.tp_price), "side": sig.side}
        g = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                    shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                    shadow.cost_r(row), LIVE_TRAIL,
                    float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
        if g is None:
            continue
        open_pos.append((g[1], equity * BASE_RISK, g[0], kind, sym))
    for p_ in open_pos:
        equity += p_[1] * p_[2]
        weekly[int(p_[0] // (7 * 86400))] = weekly.get(int(p_[0] // (7 * 86400)), 0.0) + p_[1] * p_[2]
    peak = max(peak, equity)
    maxdd = max(maxdd, (peak - equity) / peak if peak > 0 else 0.0)

    print()
    print("=== COMPOUNDED PATH, current config ===")
    print(f"  ${eq0:.2f} -> ${equity:.2f} over {span:.0f}d "
          f"({(equity/eq0-1)*100:+.1f}%) | max drawdown {maxdd*100:.1f}%")

    # ---- per regime, weekly --------------------------------------------
    win_s = 7 * 86400
    n_win = max(1, int(span // 7))
    rows = []
    for k in range(n_win):
        hi_t = now - k * win_s
        lo_t = hi_t - win_s
        live, per, wt = [], {}, 0.0
        n = 0
        for ts0, sym, sig, i, bars, kind in cands:
            if not (lo_t <= ts0 < hi_t):
                continue
            live[:] = [x for x in live if x[0] > ts0]
            per[sym] = [x for x in per.get(sym, []) if x > ts0]
            bk = [x for x in live if x[1] == kind]
            cap = tr_slots if kind == "TREND" else slots
            if per[sym] or len(bk) >= cap:
                continue
            row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
                   "tp": float(sig.tp_price), "side": sig.side}
            g = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                        shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                        shadow.cost_r(row), LIVE_TRAIL,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is None:
                continue
            live.append((g[1], kind))
            per[sym].append(g[1])
            wt += g[0] * eq0 * BASE_RISK
            n += 1
        rows.append((btc_move(lo_t, hi_t), wt, n))

    print()
    print("=== BY BTC REGIME (weekly, fixed size so weeks compare) ===")
    print(f"{'bucket':<17} {'weeks':>6} {'net $':>10} {'per wk':>9} {'worst wk':>10} "
          f"{'wk > 0':>8}")
    for label, fn in BUCKETS:
        sub = [r for r in rows if fn(r[0])]
        if not sub:
            print(f"{label:<17} {0:6d}         --        --         --       --")
            continue
        tot = sum(r[1] for r in sub)
        pos = sum(1 for r in sub if r[1] > 0)
        print(f"{label:<17} {len(sub):6d} {tot:+10.2f} {tot/len(sub):+9.2f} "
              f"{min(r[1] for r in sub):+10.2f} {pos:4d}/{len(sub):<3d}")

    print()
    print("=== THE WEEKS THAT HURT ===")
    for mv, wt, n in sorted(rows, key=lambda r: r[1])[:5]:
        print(f"  BTC {mv*100:+6.1f}%   {wt:+8.2f}   {n:3d} trades")
    tot = sum(r[1] for r in rows)
    print(f"\n  all {len(rows)} weeks: {tot:+.2f} | "
          f"{sum(1 for r in rows if r[1] > 0)} positive | "
          f"worst {min(r[1] for r in rows):+.2f} | best {max(r[1] for r in rows):+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
