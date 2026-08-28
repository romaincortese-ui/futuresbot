"""Point-in-time universe, and the key studies rerun on it.

    railway run --service Futures-bot python tools/pit_rerun.py

tools/replay_vs_live.py found that every replay this session scored a pool of
"top-N by turnover TODAY", and that such a pool contained only 12 of the 30
symbols the bot actually traded in 30 days. Turnover rankings churn: a name that
cleared the floor while it was moving sits far outside today's ranking weeks
later. So the studies were grading a different symbol set than the bot trades.

THE FIX. Take a much wider candidate set, compute each symbol's own rolling 24h
turnover bar by bar with its contractSize, and let a symbol ENTER and LEAVE the
tradeable band over time exactly as it did live. A signal counts only if that
symbol's turnover cleared the floor AT THAT BAR. The machinery already existed --
tools/turnover_floor_ab.py proved close x volume x contractSize reconstructs
amount24 within 3% -- it was simply never used to build the pool itself.

WHAT THIS CANNOT FIX: symbols delisted before today are absent from
get_all_tickers entirely, so they cannot enter any pool. That residual
survivorship is stated, not solved.

Four questions on one fetch, because the data is the expensive part:
  1. Does coverage of the live-traded symbols actually improve?
  2. The turnover floor sweep, which is literally a question about eligibility
     and therefore the most exposed to the old bug.
  3. Peak fate and the retention ratchet, whose magnitude was flagged as
     overstated when live reached 3R on 5% of trades against the replay's 27%.
  4. The wildcard short arm by regime, which decided a live setting.

RESULT, 2026-08-24 -- 154 symbols, 208 days, 1913 candidates, 904 wildcard.
THE REBUILD CHANGES THREE CONCLUSIONS, TWO OF THEM MINE FROM THIS WEEK.

    coverage of the 33 symbols the bot actually traded
      OLD pool (top-70 today) : 10/33 = 30%
      NEW wide + point-in-time: 20/33 = 61%
      still absent (13): BILL BTW ENA ERA ESPORTS HEI HFT INX NIL ONDO O PRL

    point-in-time eligibility: 38.6% of symbol-bars cleared $2M

1. THE TURNOVER FLOOR SHOULD GO BACK TO $3M.

    floor      net $   vs live  trades   pos wk    recent     older  both halves?
     2.0M    +305.96     +0.00     733   17/29      +0.00     +0.00  (null, live)
     3.0M    +367.56    +61.60     688   20/29     +31.12    +30.49  YES
     5.0M    +349.06    +43.10     626   20/29      -2.51    +45.61  one half only

   $3M beats the live $2M by +$61.60 with the two halves almost perfectly
   balanced (+31.12 / +30.49) and weekly consistency rising 17/29 -> 20/29. That
   is a cleaner result than the one that moved the floor DOWN to $2M two days ago
   (+$15.22, halves +4.09/+11.13), and it was measured on a pool covering 30% of
   the traded symbols. Six times the ~$10 run-to-run noise band.

   NOTE THE STUDY'S OWN BUG: candidates are generated with the live $2M floor
   applied, so the 1.0M row is identical to 2.0M and is MEANINGLESS -- a sweep
   cannot test a floor below its generation floor. Only 3M and 5M are valid here.

2. THE RETENTION RATCHET NO LONGER EARNS ITS KEEP.

     flat 0.30 (the rule before 08-22): +307.03
     ratchet 3.0R -> 0.75 (live now)  : +305.96
     delta -1.07 | recent -7.11 | older +6.03 | ONE HALF ONLY

   It measured +$25.33 passing both halves on the old pool. On the rebuilt pool
   it is worth nothing and fails the half-split. Read alongside the peak bias
   this tool confirms -- replay reaches +1R 62% of the time against a live 24%,
   and +3R 24% against a live 5% -- the ratchet fires on roughly a fifth as many
   live trades as the replay implies. Shipped on 2026-08-22; now UNSUPPORTED.

3. THE WILDCARD SHORT ARM IS MUCH WEAKER THAN MEASURED, THOUGH STILL POSITIVE.

    bucket            weeks  long-only $  both-sides $   delta $
    DOWN -15..-5%         6      +135.92       +194.06    +58.14
    FLAT  -5..+5%        21      +186.65       +138.93    -47.72
    UP    +5..+15%        2       -21.48        -27.03     -5.55
    TOTAL                29      +301.10       +305.96     +4.86

   +$4.86 against the +$54.09 measured before. The down-week case survives and
   strengthens (+$58.14 over six weeks); the flat-week case reverses to -$47.72.
   CAVEAT: this tool buckets by BTC's TRAILING 7d at the window START, whereas
   the earlier study bucketed by the move DURING the window. Those are different
   questions, so the bucket rows are not directly comparable -- only the total is.

WHAT THIS TOOL STILL CANNOT DO. Thirteen of the 33 traded symbols sit below
$0.3M turnover today and are absent from any pool; several are likely delisted
and are not in get_all_tickers at all. Coverage of 61% is a large improvement on
30% and is not the same as correct. And this is a single run with no repeat, so
the ~$10 noise band applies to every figure above.

Read-only. Places nothing.

Env: PIT_DAYS (190) PIT_POOL (150) PIT_SLOTS (3) PIT_MIN_TODAY (300000)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from pit_fetch import fetch_frames  # noqa: E402

from futuresbot import shadow_ledger as shadow
from futuresbot import wildcard as W
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime
from futuresbot.trend import detect_trend_signal
from peak_fate_ab import ratchet
from retention_trail_ab import make_floor, resolve

CHUNK, BAR = 2000, 900
TREND_SYMS = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
LIVE_TRAIL = ratchet(3.0, 0.75)
FLAT_TRAIL = make_floor("flat", 0.30, 1.0)

BUCKETS = [
    ("CRASH <=-15%", lambda m: m <= -0.15),
    ("DOWN -15..-5%", lambda m: -0.15 < m <= -0.05),
    ("FLAT  -5..+5%", lambda m: -0.05 < m < 0.05),
    ("UP    +5..+15%", lambda m: 0.05 <= m < 0.15),
    ("SURGE  >=+15%", lambda m: m >= 0.15),
]


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
    days, pool_n = _env("PIT_DAYS", 190), int(_env("PIT_POOL", 150))
    slots = int(_env("PIT_SLOTS", 3))
    min_today = _env("PIT_MIN_TODAY", 3e5)
    eq = rt._last_known_equity() or 175.0
    now = int(time.time())
    live_floor = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    # A WIDE candidate set on a LOW today-floor, so names that were liquid during
    # the window but are quiet now can still enter the pool at the bars where
    # they actually qualified.
    wide = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                   if str(t.get("symbol") or "").endswith("_USDT")
                   and rt._is_tradeable_crypto(str(t.get("symbol") or ""))
                   and str(t.get("symbol") or "") not in majors
                   and float(t.get("amount24") or 0) >= min_today), reverse=True)
    cand_syms = [s for _a, s in wide[:pool_n]]
    syms = sorted(set(cand_syms) | set(TREND_SYMS) | {"BTC_USDT"})
    print(f"equity ${eq:.2f} | wide candidate set {len(cand_syms)} "
          f"(>= ${min_today/1e6:.1f}M today) | live floor ${live_floor/1e6:.0f}M")

    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}

    frames, _rep = fetch_frames(cl, syms, days=days, workers=6,
                                min_bars=300, now_ts=now)
    print(_rep)
    span = len(frames.get("BTC_USDT", next(iter(frames.values())))) * BAR / 86400
    print(f"frames: {len(frames)} symbols, {span:.0f}d")

    btc = frames.get("BTC_USDT")
    btc_t = [float(x.timestamp()) for x in btc.index]
    btc_c = [float(x) for x in btc["close"]]

    def btc7(ts):
        k = min(range(len(btc_t)), key=lambda i: abs(btc_t[i] - ts))
        j = max(0, k - 672)
        return (btc_c[k] / btc_c[j] - 1.0) if btc_c[j] > 0 else 0.0

    # ---- generate candidates with POINT-IN-TIME eligibility --------------
    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))
    print("generating candidates (turnover judged AT EACH BAR)...")
    cands = []
    elig_bars = 0
    total_bars = 0
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
                    cands.append((ts[i], s, sig, i, bars, "TREND", roll[i], h, lo, c))
        if s in cand_syms:
            for i in range(250, len(c)):
                total_bars += 1
                if roll[i] >= live_floor:
                    elig_bars += 1
                if i <= W.ROC_BARS or roll[i] < live_floor:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    cands.append((ts[i], s, sig, i, bars, "WILDCARD", roll[i], h, lo, c))
    cands.sort(key=lambda x: x[0])
    wc_n = sum(1 for x in cands if x[5] == "WILDCARD")
    pit_syms = {x[1] for x in cands if x[5] == "WILDCARD"}
    print(f"candidates: {len(cands)} (wildcard {wc_n} across {len(pit_syms)} distinct symbols)")
    print(f"point-in-time eligibility: {100*elig_bars/max(1,total_bars):.1f}% of "
          f"symbol-bars cleared ${live_floor/1e6:.0f}M")

    # ---- 1. coverage against the live record -----------------------------
    live_path = sys.argv[1] if len(sys.argv) > 1 else None
    if live_path and os.path.exists(live_path):
        live_syms = set()
        for line in open(live_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if str(r.get("kind") or "").upper() == "WILDCARD":
                live_syms.add(str(r.get("symbol") or ""))
        old_pool = set(s for _a, s in wide[:70])
        print()
        print("=== 1. COVERAGE OF SYMBOLS THE BOT ACTUALLY TRADED ===")
        print(f"  live wildcard symbols: {len(live_syms)}")
        print(f"  OLD pool (top-70 today) : {len(live_syms & old_pool)}/{len(live_syms)} "
              f"= {100*len(live_syms & old_pool)/max(1,len(live_syms)):.0f}%")
        print(f"  NEW wide+PIT pool       : {len(live_syms & pit_syms)}/{len(live_syms)} "
              f"= {100*len(live_syms & pit_syms)/max(1,len(live_syms)):.0f}%")
        missing = sorted(live_syms - set(cand_syms))
        if missing:
            print(f"  still absent ({len(missing)}): {', '.join(m.replace('_USDT','') for m in missing[:12])}")

    def outcome(c_, floor_fn=LIVE_TRAIL):
        _ts, _s, sig, i, bars, _k, _t, _h, _l, _c = c_
        row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
               "tp": float(sig.tp_price), "side": sig.side}
        return resolve(bars, i, row["entry"], row["sl"], row["tp"],
                       shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                       shadow.cost_r(row), floor_fn,
                       float(getattr(sig, "atr_pct", 0.0) or 0.0), now)

    win_s = 7 * 86400
    n_win = max(1, int(span // 7))
    mid = n_win // 2

    def book(keep, floor_fn=LIVE_TRAIL, k_lo=0, k_hi=None):
        tot = 0.0
        n = 0
        pos = 0
        for k in range(k_lo, n_win if k_hi is None else k_hi):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            live, per, wt = [], {}, 0.0
            for c_ in cands:
                ts0, sym, sig = c_[0], c_[1], c_[2]
                if not (lo_t <= ts0 < hi_t) or not keep(c_):
                    continue
                live[:] = [x for x in live if x > ts0]
                per[sym] = [x for x in per.get(sym, []) if x > ts0]
                if per[sym] or len(live) >= slots:
                    continue
                g = outcome(c_, floor_fn)
                if g is None:
                    continue
                live.append(g[1])
                per[sym].append(g[1])
                wt += g[0] * eq * 0.12 * float(sig.sl_margin_pct) / 100.0
                n += 1
            tot += wt
            pos += 1 if wt > 0 else 0
        return tot, n, pos

    # ---- 2. turnover floor, now genuinely point-in-time -------------------
    print()
    print("=== 2. TURNOVER FLOOR, POINT-IN-TIME (live = $2M) ===")
    print(f"{'floor':>8} {'net $':>10} {'vs live':>9} {'trades':>7} {'pos wk':>8} "
          f"{'recent':>9} {'older':>9}  both halves?")
    base = None
    for f_usd in (1e6, 2e6, 3e6, 5e6):
        def keep(c_, f=f_usd):
            return c_[5] != "WILDCARD" or c_[6] >= f
        tot, n, pos = book(keep)
        rec = book(keep, LIVE_TRAIL, 0, mid)[0]
        old = book(keep, LIVE_TRAIL, mid, n_win)[0]
        if abs(f_usd - live_floor) < 1:
            base = (tot, rec, old)
        star = "  <-live cfg" if abs(f_usd - live_floor) < 1 else ""
        d_r = rec - (base[1] if base else rec)
        d_o = old - (base[2] if base else old)
        ok = "(null)" if star else ("YES" if d_r > 0 and d_o > 0 else
                                    ("no" if d_r < 0 and d_o < 0 else "one half only"))
        print(f"{f_usd/1e6:7.1f}M {tot:+10.2f} {tot-(base[0] if base else tot):+9.2f} "
              f"{n:7d} {pos:4d}/{n_win:<3d} {d_r:+9.2f} {d_o:+9.2f}  {ok}{star}")

    # ---- 3. peak fate and the ratchet ------------------------------------
    print()
    print("=== 3. PEAK FATE (does the ratchet still earn its keep?) ===")
    peaks = []
    for c_ in cands:
        _ts, _s, sig, i, bars, _k, _t, h, lo, c = c_
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
    if peaks:
        print(f"  reach +1R: {100*sum(1 for p in peaks if p>=1)/len(peaks):.0f}% "
              f"| reach +3R: {100*sum(1 for p in peaks if p>=3)/len(peaks):.0f}% "
              f"(live: 24% and 5%)")
    tot_r, n_r, pos_r = book(lambda c_: True, LIVE_TRAIL)
    tot_f, n_f, pos_f = book(lambda c_: True, FLAT_TRAIL)
    r_rec = book(lambda c_: True, LIVE_TRAIL, 0, mid)[0] - book(lambda c_: True, FLAT_TRAIL, 0, mid)[0]
    r_old = book(lambda c_: True, LIVE_TRAIL, mid, n_win)[0] - book(lambda c_: True, FLAT_TRAIL, mid, n_win)[0]
    print(f"  flat 0.30 (live cfg before 08-22): {tot_f:+.2f}")
    print(f"  ratchet 3.0R->0.75 (live now)    : {tot_r:+.2f}  "
          f"delta {tot_r-tot_f:+.2f}  recent {r_rec:+.2f} older {r_old:+.2f}  "
          f"{'YES' if r_rec>0 and r_old>0 else ('no' if r_rec<0 and r_old<0 else 'one half only')}")

    # ---- 4. the short arm by regime --------------------------------------
    print()
    print("=== 4. WILDCARD SHORT ARM BY REGIME ===")
    print(f"{'bucket':<16} {'weeks':>6} {'long-only $':>12} {'both-sides $':>13} {'delta $':>9}")
    rows = []
    for k in range(n_win):
        hi_t = now - k * win_s
        lo_t = hi_t - win_s
        res = {}
        for allow in (False, True):
            live_s, per, wt = [], {}, 0.0
            for c_ in cands:
                ts0, sym, sig = c_[0], c_[1], c_[2]
                if not (lo_t <= ts0 < hi_t):
                    continue
                if sig.side == "SHORT" and not allow:
                    continue
                live_s[:] = [x for x in live_s if x > ts0]
                per[sym] = [x for x in per.get(sym, []) if x > ts0]
                if per[sym] or len(live_s) >= slots:
                    continue
                g = outcome(c_)
                if g is None:
                    continue
                live_s.append(g[1])
                per[sym].append(g[1])
                wt += g[0] * eq * 0.12 * float(sig.sl_margin_pct) / 100.0
            res[allow] = wt
        rows.append((btc7(lo_t), res[False], res[True]))
    for lab, fn in BUCKETS:
        sub = [r for r in rows if fn(r[0])]
        if not sub:
            print(f"{lab:<16} {0:6d}           --            --        --")
            continue
        L = sum(r[1] for r in sub)
        B = sum(r[2] for r in sub)
        print(f"{lab:<16} {len(sub):6d} {L:+12.2f} {B:+13.2f} {B-L:+9.2f}")
    L = sum(r[1] for r in rows)
    B = sum(r[2] for r in rows)
    print(f"{'TOTAL':<16} {len(rows):6d} {L:+12.2f} {B:+13.2f} {B-L:+9.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
