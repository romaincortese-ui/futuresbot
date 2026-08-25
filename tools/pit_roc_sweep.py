"""ROC trigger window x threshold sweep on the corrected point-in-time pool.

WHY. The live wildcard trigger is |3h ROC| >= 8% (W.ROC_BARS=12 on 15m bars).
On 2026-08-25 a live gate run over all 90 scanned symbols returned ZERO signals,
87 of them rejected `roc_below_min` -- including CATE at +74% on the day, which
never moved 8% in any single 3h window. The trigger is blind to GRINDING
advances; it only sees vertical 3h spikes.

That is an observation about SILENCE, not about profitability. A gate that
declines mature moves may be declining them correctly. This sweep asks the only
question that settles it: which (window, threshold) pair would have made the
most DOLLARS on the corrected pool?

METHOD. Identical to tools/pit_rejections.py -- same PIT eligibility (turnover
judged per bar), same resolve, same slot/dedup occupancy model, same weekly
half-split. TREND candidates are generated once and held fixed (live config:
long-only, ETH/XRP/ZEC) so the only thing varying is the wildcard trigger.

MULTIPLICITY WARNING, READ BEFORE QUOTING ANY CELL. This sweep tests 15 cells.
Picking the best of 15 on one dataset WILL find a winner by chance; that is what
a sweep does. The half-split is the guard, but with 15 cells even a both-halves
pass is no longer strong evidence on its own. Treat any winner as a CANDIDATE to
be pre-registered and retested, not as a result. The live cell (12 bars / 0.08)
is in the grid as the control.

SPEED NOTE. detect_wildcard_signal is fed a trailing TAIL-bar slice instead of
df.iloc[:i+1], turning an O(n) copy per bar into O(1). This is NOT free: RSI and
ATR use EWM warmup, so too short a tail shifts borderline `rsi_exhausted` and
`vertical_blowoff` decisions. TAIL=300 inflated candidates ~17%. TAIL=2000 was
verified EXACT by PJ_TAILCHECK=1 (190 vs 190 candidates over 15 symbols, all
5278 evaluated bars agreeing). Re-run that check if TAIL or the detector changes.

DO NOT SELF-CHECK ACROSS RUNS. The first version compared the live cell to a
prior run's 813 candidates / +425.94 and "failed". That target was invalid: the
pool is re-ranked by LIVE turnover on every run and the 208d window rolls daily,
so the level moves for reasons unrelated to the thing under test. Only
within-run, cross-cell comparisons mean anything here.

RESULTS 2026-08-25 (208d, 152 symbols, pool 150, $2M/bar floor).
LIVE CELL 3h/8%: +378.09 over 775 trades, 19/29 positive weeks. 15 cells.

THE DIRECTION IS THE OPPOSITE OF THE HYPOTHESIS THAT MOTIVATED THIS TOOL.
The operator's read -- and mine -- was that the trigger misses grinding
advances, so a SHORTER window at a LOWER threshold (1h>=2%, 2h>=5%) would catch
them. It is the worst region of the entire grid:

    1h >= 2%    +15.03   -363.06 vs live   1426 trades   12/29 weeks
    2h >= 3%   +227.74   -150.35 vs live   1376 trades   18/29 weeks
    1h >= 5%   +233.49   -144.60 vs live    734 trades   14/29 weeks

Loosening the trigger buys churn, not participation. 1h/2% nearly doubles the
trade count and destroys the book. Fee drag plus entering noise, not moves.

TWO CELLS BEAT LIVE IN BOTH HALVES BY MORE THAN THE $10 NOISE FLOOR:

    6h >= 12%  +440.25  **+62.16**  690 trades  22/29 wk  (+39.17 / +22.99)
    3h >=  5%  +404.51    +26.42   1128 trades  20/29 wk  (+17.62 /  +8.80)

The winner is a LONGER window with a HIGHER bar -- and it does it on FEWER
trades than live (690 vs 775) with MORE positive weeks (22 vs 19). That is a
selectivity gain, not a participation gain.

MECHANISM, offered as a reading and not as a measurement: live 3h/8% demands
2.67%/hour. 6h/12% demands 2.00%/hour sustained twice as long. It is not a
looser gate, it is a gate tuned to PERSISTENCE instead of VELOCITY -- which is
what a grinding advance is. The operator's diagnosis was right; the proposed
remedy pointed the wrong way.

EARLINESS, MEASURED DIRECTLY (PJ_EARLY=1, 2026-08-25). "Can we catch the move
earlier -- 2h/3%?" Lowering the threshold changes earliness AND selectivity at
once, so its -$150.35 cannot be blamed on earliness alone. Isolating it: hold
the trigger FIXED and split its own candidates into terciles by prior 24h move.

  LIVE 3h/8%, n=1034      prior24h    FWD24h     meanR    win%
    FRESH (early)            -1.2%     12.7%    +0.083   53.2%
    MIDDLE                   21.3%     12.4%    +0.098   56.4%
    EXTENDED (late)          45.6%     22.7%    +0.118   51.7%

  6h/12%, n=869           prior24h    FWD24h     meanR    win%
    FRESH (early)             7.4%     13.6%    +0.163   57.1%
    MIDDLE                   26.4%     15.5%    +0.062   55.7%
    EXTENDED (late)          51.2%     24.2%    +0.232   55.3%

EARLIER IS WORSE, on both triggers. The more a symbol has already moved over
24h, the MORE it moves over the next 24h -- forward room nearly DOUBLES from the
fresh tercile to the extended one (12.7 -> 22.7, 13.6 -> 24.2). Realised meanR is
highest in the EXTENDED tercile both times. Win rates are flat (51-57%), so the
edge is in MAGNITUDE, not hit rate.

Note the live cell's FRESH tercile sits at prior24h of -1.2%: a symbol flat or
down on the day that spiked 8% in 3h. That is the "spike from nowhere" case --
worst forward room of any bucket. It is what the live trigger buys that 6h/12%
declines.

FOUR INDEPENDENT MEASUREMENTS NOW AGREE that later + more selective beats
earlier + looser: this sweep, the PJ_COMPARE population split, these terciles,
and the twice-rejected lateness gate (skipping late entries costs $195-260).
Treat "enter earlier" as a settled-negative direction absent new evidence.

The genuine early-entry mechanism is the SQUEEZE sleeve (volatility ignition,
enters BEFORE the move rather than looser-after). It is OFF, and its rejection
was re-confirmed on this same corrected pool at -$30.22. The early-entry idea
already has a dedicated implementation and it does not pay.

CAVEAT ON THE TERCILES: 6h/12% MIDDLE meanR (+0.062) breaks monotonicity at
n=289 -- do not read the meanR column as a clean gradient. The FWD24h column is
the robust one. Both are medians/means, not tail measurements.

TAIL CHECK (PJ_TAIL=1, 2026-08-25). Wildcard-only booking (TREND is fixed
across cells and books separately), live slot + per-symbol occupancy.

                        n     total   mean R   <=-1R   top5% share   EX-TOP-5%
  LIVE 3h/8%          676   +216.78   +0.112   41.7%          202%     -220.40
  6h/12%              574   +251.26   +0.139   39.9%          133%      -82.90

  6h/12% minus live:  full book +34.47 | ex-top-5% +137.50 | ex-top-10% +164.19

THE EDGE IS IN THE BODY, NOT THE TAIL. Stripping the top 5% of trades from both
cells does not erase 6h/12%'s advantage -- it QUADRUPLES it. The live trigger is
the more tail-dependent of the two, so the +62 is not one lucky runner. This is
the single strongest piece of evidence the candidate has.

BUT READ THE ABSOLUTE COLUMN. Top 5% of trades = 202% of total P&L for live and
133% for 6h/12%, and BOTH books are NET NEGATIVE ex-top-5% (-220.40, -82.90).
The strategy is: bleed on ~95% of trades and make it all back on the top 5%.
That is the true risk profile of this sleeve, and it is not visible in any
headline net figure. 6h/12% is materially less fragile on this axis but is not
a different kind of animal.

THE REPLAY CANNOT SEE THE LEFT TAIL. Both cells report min -1.05R and 0.0% of
trades below -1.1R. The LIVE record has 13% of trades beyond -1.1R and a worst
of -3.79R. The replay fills every stop AT the stop price -- no slippage, no gap,
no cascade. So the downside here is fiction for BOTH cells, and the comparison
between them holds only if slippage hits them equally. It may NOT: 6h/12%
selects more extended symbols (prior24h 51% in its top tercile), which is
plausibly MORE gap-prone, not less. Unverified and material.
[[futures-bot-trial8-state]] records tail losses as still-unstudied; this run
does not change that -- it confirms the instrument cannot answer it.

DO NOT DEPLOY OFF THIS RUN:
  - 15 cells. Best-of-15 finds winners by chance; the half-split is a guard,
    not a proof, at this width.
  - Replay dollars. +62.16/208d is ~$9/mo at replay LEVELS, which are inflated
    by shared bias. Only the relative +16.4% vs baseline carries.
  - Trial 16 is open.
  - Next step is PRE-REGISTRATION of 6h/12% and a retest on an independently
    drawn pool, exactly as the trend-short gate earned its standing.
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
from futuresbot.risk_controls import trend_efficiency
from futuresbot.runtime import FuturesRuntime
from futuresbot.trend import detect_trend_signal
from pit_ratchet import ratchet
from retention_trail_ab import resolve

CHUNK, BAR = 2000, 900
TREND_SYMS = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
LIVE_TRAIL = ratchet(3.0, 0.75)
TAIL = 2000                     # trailing bars fed to the detector (see SPEED NOTE)

# (window_bars, thresholds). 15m bars: 4=1h, 8=2h, 12=3h(live), 24=6h, 48=12h
GRID = (
    (4,  (0.02, 0.03, 0.05)),
    (8,  (0.03, 0.05, 0.08)),
    (12, (0.05, 0.08, 0.12)),           # 0.08 = LIVE
    (24, (0.08, 0.12, 0.20)),
    (48, (0.12, 0.20, 0.30)),
)
LIVE_CELL = (12, 0.08)
NOISE = 10.0


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
    days, pool_n = _env("PJ_DAYS", 190), int(_env("PJ_POOL", 150))
    min_today = _env("PJ_MIN_TODAY", 3e5)
    eq0 = rt._last_known_equity() or 172.0
    now = int(time.time())
    floor = W.wildcard_min_turnover_usdt()
    eff_win = max(4, int(rt._env_float("FUTURES_REGIME_EFF_WINDOW", 24.0)))

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wide = [(a, s) for a, s in crypto if s not in majors and a >= min_today]
    cand_syms = [s for _a, s in wide[:pool_n]]
    syms = sorted(set(cand_syms) | set(TREND_SYMS))
    print("equity $%.2f | wildcard pool %d | floor $%.0fM per bar"
          % (eq0, len(cand_syms), floor / 1e6))

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
    print("frames: %d symbols, %.0fd" % (len(frames), span))

    PRE = {}
    for s, df in frames.items():
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
        PRE[s] = (df, c, roll, bars)

    if os.environ.get("PJ_TAIL"):
        # Does 6h/12%'s edge live in the BODY or the TAIL? A convex book earns
        # from its right tail, so a mean/median gain can be one lucky runner.
        # The decisive test is ex-tail: strip the top 5% of trades from BOTH
        # cells and see whether the advantage survives. If it vanishes, the
        # +$62.16 is one or two trades and the cell is fragile.
        # Analysed on the trades ACTUALLY BOOKED (slot + per-symbol occupancy),
        # wildcard-only -- TREND is fixed across cells and books separately.
        import statistics as st
        win_s = 7 * 86400
        n_win = max(1, int(span // 7))

        def resolve_all(C):
            out = {}
            for idx, x in enumerate(C):
                sg = x["sig"]
                row = {"entry": float(sg.entry_price), "sl": float(sg.sl_price),
                       "tp": float(sg.tp_price), "side": sg.side}
                g = resolve(x["bars"], x["i"], row["entry"], row["sl"], row["tp"],
                            shadow.signal_tp_r(sg), sg.side, shadow.CONVEX_HORIZON_S,
                            shadow.cost_r(row), LIVE_TRAIL,
                            float(getattr(sg, "atr_pct", 0.0) or 0.0), now)
                if g is not None:
                    out[idx] = g
            return out

        def pct(xs, q):
            if not xs:
                return float("nan")
            ys = sorted(xs)
            return ys[min(len(ys) - 1, max(0, int(q * len(ys))))]

        stats = {}
        for w, thr in ((12, 0.08), (24, 0.12)):
            W.ROC_BARS = w
            os.environ["FUTURES_WILDCARD_MIN_ROC"] = str(thr)
            WC = []
            for s in cand_syms:
                if s not in PRE:
                    continue
                df, c, roll, bars = PRE[s]
                ts = [b[0] for b in bars]
                for i in range(250, len(c)):
                    if i <= w or roll[i] < floor:
                        continue
                    if abs(c[i] / c[i - w] - 1.0) < thr:
                        continue
                    sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                    if sig is not None:
                        WC.append({"ts": ts[i], "sym": s, "sig": sig, "i": i,
                                   "bars": bars, "kind": "WILDCARD"})
            WC.sort(key=lambda x: x["ts"])
            res = resolve_all(WC)
            # book with live occupancy, collecting per-trade R and dollars
            trades = []
            for k in range(n_win):
                hi_t = now - k * win_s
                lo_t = hi_t - win_s
                wcl, per = [], {}
                for idx, x in enumerate(WC):
                    if not (lo_t <= x["ts"] < hi_t) or idx not in res:
                        continue
                    wcl[:] = [q for q in wcl if q > x["ts"]]
                    per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
                    if per[x["sym"]] or len(wcl) >= 3:
                        continue
                    g = res[idx]
                    wcl.append(g[1])
                    per[x["sym"]].append(g[1])
                    trades.append((float(g[0]),
                                   g[0] * eq0 * 0.12 * float(x["sig"].sl_margin_pct) / 100.0))
            stats[(w, thr)] = trades

        print("")
        for (w, thr), tr in stats.items():
            tag = "LIVE 3h/8%" if w == 12 else "6h/12%"
            rs = [t[0] for t in tr]
            ds = [t[1] for t in tr]
            tot = sum(ds)
            n = len(rs)
            print("=== %s : n=%d  total %+.2f ===" % (tag, n, tot))
            print("  R percentiles  p5 %+.2f  p25 %+.2f  p50 %+.2f  p75 %+.2f  "
                  "p90 %+.2f  p95 %+.2f  p99 %+.2f  max %+.2f"
                  % (pct(rs, .05), pct(rs, .25), pct(rs, .50), pct(rs, .75),
                     pct(rs, .90), pct(rs, .95), pct(rs, .99), max(rs) if rs else 0))
            for lvl in (1.0, 2.0, 3.0, 5.0):
                print("  reached %+.0fR: %5.1f%%" % (lvl, 100.0 * sum(1 for r in rs if r >= lvl) / max(n, 1)))
            print("  LEFT TAIL  min %+.2f   <=-1.0R %5.1f%%   <=-1.1R %5.1f%%   mean %+.3f"
                  % (min(rs) if rs else 0,
                     100.0 * sum(1 for r in rs if r <= -1.0) / max(n, 1),
                     100.0 * sum(1 for r in rs if r <= -1.1) / max(n, 1),
                     st.mean(rs) if rs else 0))
            srt = sorted(ds, reverse=True)
            k5 = max(1, n // 20)
            k10 = max(1, n // 10)
            print("  top 5%% of trades = %+.2f (%.0f%% of total) | top 10%% = %+.2f (%.0f%%)"
                  % (sum(srt[:k5]), 100.0 * sum(srt[:k5]) / tot if tot else 0,
                     sum(srt[:k10]), 100.0 * sum(srt[:k10]) / tot if tot else 0))
            print("  EX-TOP-5%%: %+.2f   EX-BEST-TRADE: %+.2f"
                  % (tot - sum(srt[:k5]), tot - srt[0] if srt else 0))
            print("")
        a = stats[(12, 0.08)]
        b = stats[(24, 0.12)]

        def ex(tr, frac):
            ds = sorted([t[1] for t in tr], reverse=True)
            return sum(ds) - sum(ds[:max(1, len(ds) * frac // 100)])
        print("VERDICT")
        print("  full book   6h/12%% - live = %+.2f" % (sum(t[1] for t in b) - sum(t[1] for t in a)))
        print("  ex-top-5%%   6h/12%% - live = %+.2f" % (ex(b, 5) - ex(a, 5)))
        print("  ex-top-10%%  6h/12%% - live = %+.2f" % (ex(b, 10) - ex(a, 10)))
        print("  If the advantage survives ex-top-5%, it is a BODY improvement.")
        print("  If it collapses, +62.16 was one or two runners and is FRAGILE.")
        return 0

    if os.environ.get("PJ_EARLY"):
        # "Is there a way to catch the move EARLIER?"
        # Lowering the threshold (2h/3%) changes earliness AND selectivity at
        # once -- it fires on far more bars, so its -$150 cannot be attributed
        # to earliness alone. This isolates earliness: hold the trigger FIXED,
        # then split its own candidates into terciles by how much the symbol had
        # already moved over the prior 24h. If catching moves early paid, the
        # FRESH tercile would show the best forward room and the best realised R.
        import statistics as st
        for w, thr in ((12, 0.08), (24, 0.12)):
            W.ROC_BARS = w
            os.environ["FUTURES_WILDCARD_MIN_ROC"] = str(thr)
            rows = []
            for s in cand_syms:
                if s not in PRE:
                    continue
                df, c, roll, bars = PRE[s]
                hi_s = [b[1] for b in bars]
                lo_s = [b[2] for b in bars]
                for i in range(250, len(c) - 96):
                    if i <= w or roll[i] < floor:
                        continue
                    if abs(c[i] / c[i - w] - 1.0) < thr:
                        continue
                    sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                    if sig is None:
                        continue
                    d = 1.0 if sig.side == "LONG" else -1.0
                    prior = d * (c[i] / c[i - 96] - 1.0) * 100
                    nxt = range(i + 1, min(i + 97, len(c)))
                    ex = (max(hi_s[j] for j in nxt) if d > 0 else min(lo_s[j] for j in nxt))
                    fwd = d * (ex / c[i] - 1.0) * 100
                    row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
                           "tp": float(sig.tp_price), "side": sig.side}
                    g = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                                shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                                shadow.cost_r(row), LIVE_TRAIL,
                                float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                    if g is None:
                        continue
                    rows.append((prior, fwd, float(g[0])))
            rows.sort(key=lambda r: r[0])
            n = len(rows)
            k = max(1, n // 3)
            print("")
            print("=== %s : does entering EARLY (small prior 24h move) pay? n=%d ==="
                  % ("LIVE 3h/8%" if w == 12 else "6h/12%", n))
            print("%-16s %6s %10s %10s %9s %8s" %
                  ("tercile", "n", "prior24h", "FWD24h", "meanR", "win%"))
            for lab, part in (("FRESH (early)", rows[:k]),
                              ("MIDDLE", rows[k:2 * k]),
                              ("EXTENDED (late)", rows[2 * k:])):
                if not part:
                    continue
                pr = st.median([x[0] for x in part])
                fw = st.median([x[1] for x in part])
                mr = sum(x[2] for x in part) / len(part)
                wr = 100.0 * sum(1 for x in part if x[2] > 0) / len(part)
                print("%-16s %6d %9.1f%% %9.1f%% %+9.3f %7.1f%%"
                      % (lab, len(part), pr, fw, mr, wr))
        print("")
        print("meanR is the realised convex outcome, not the excursion.")
        return 0

    if os.environ.get("PJ_COMPARE"):
        # "Doesn't 6h/12% just enter LATER? What is left to move after a symbol
        # has already run 12% in 6 hours?" -- measure it instead of arguing.
        # Both populations are scored on the SAME yardsticks (prior move over a
        # common 24h window, position in the 24h range, and FORWARD max
        # favourable excursion over the next 24h), so the comparison is fair.
        import statistics as st

        def med(xs):
            return st.median(xs) if xs else float("nan")

        print("%-12s %6s %9s %9s %9s %9s %9s"
              % ("cell", "n", "prior3h", "prior6h", "prior24h", "late24h", "FWD24h"))
        for w, thr in ((12, 0.08), (24, 0.12)):
            W.ROC_BARS = w
            os.environ["FUTURES_WILDCARD_MIN_ROC"] = str(thr)
            p3, p6, p24, late, fwd = [], [], [], [], []
            for s in cand_syms:
                if s not in PRE:
                    continue
                df, c, roll, bars = PRE[s]
                hi_s = [b[1] for b in bars]
                lo_s = [b[2] for b in bars]
                for i in range(250, len(c) - 96):
                    if i <= w or roll[i] < floor:
                        continue
                    if abs(c[i] / c[i - w] - 1.0) < thr:
                        continue
                    sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                    if sig is None:
                        continue
                    d = 1.0 if sig.side == "LONG" else -1.0
                    p3.append(d * (c[i] / c[i - 12] - 1.0) * 100)
                    p6.append(d * (c[i] / c[i - 24] - 1.0) * 100)
                    p24.append(d * (c[i] / c[i - 96] - 1.0) * 100)
                    wl, wh = min(lo_s[i - 96:i + 1]), max(hi_s[i - 96:i + 1])
                    if wh > wl:
                        late.append((c[i] - wl) / (wh - wl) if d > 0 else (wh - c[i]) / (wh - wl))
                    nxt = range(i + 1, min(i + 97, len(c)))
                    if nxt:
                        ex = (max(hi_s[j] for j in nxt) if d > 0 else min(lo_s[j] for j in nxt))
                        fwd.append(d * (ex / c[i] - 1.0) * 100)
            tag = "LIVE 3h/8%" if w == 12 else "6h/12%"
            print("%-12s %6d %8.1f%% %8.1f%% %8.1f%% %9.2f %8.1f%%"
                  % (tag, len(p3), med(p3), med(p6), med(p24), med(late), med(fwd)))
        print("")
        print("prior*  = move already made at entry, signed toward the trade")
        print("late24h = position in the trailing 24h range (1.00 = at the extreme)")
        print("FWD24h  = max favourable excursion over the NEXT 24h = what was left")
        return 0

    if os.environ.get("PJ_TAILCHECK"):
        # Is the trailing-slice optimisation EXACT? Compare it against the full
        # history on the same symbols in the same run -- the only fair test.
        # (The 2026-08-25 cross-run check against a prior run's 813 was invalid:
        # the pool is re-ranked by live turnover every run and the 208d window
        # rolls daily, so the target moved for reasons unrelated to TAIL.)
        W.ROC_BARS = 12
        os.environ["FUTURES_WILDCARD_MIN_ROC"] = "0.08"
        nf = nt = agree = 0
        for s in cand_syms[:15]:
            if s not in PRE:
                continue
            df, c, roll, _bars = PRE[s]
            for i in range(250, len(c)):
                if i <= 12 or roll[i] < floor:
                    continue
                if abs(c[i] / c[i - 12] - 1.0) < 0.08:
                    continue
                a = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                b = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                nf += 1 if a is not None else 0
                nt += 1 if b is not None else 0
                agree += 1 if (a is None) == (b is None) else 0
        print("TAILCHECK TAIL=%d over 15 symbols: full=%d trailing=%d  bar-level agreement %d"
              % (TAIL, nf, nt, agree))
        print("EXACT" if nf == nt else "NOT EXACT - drop the optimisation")
        return 0

    print("generating TREND candidates (fixed across every cell)...")
    TREND = []
    for s in TREND_SYMS:
        if s not in PRE:
            continue
        df, c, roll, bars = PRE[s]
        ts = [b[0] for b in bars]
        for i in range(400, len(c)):
            if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                continue
            sig = detect_trend_signal(df.iloc[:i + 1], s)
            if sig is not None and sig.side == "LONG":
                TREND.append({"ts": ts[i], "sym": s, "sig": sig, "i": i,
                              "bars": bars, "kind": "TREND", "roc": 0.0})
    print("  TREND: %d" % len(TREND))

    win_s = 7 * 86400
    n_win = max(1, int(span // 7))
    mid = n_win // 2

    def resolve_all(C):
        res = {}
        for idx, x in enumerate(C):
            sig = x["sig"]
            row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
                   "tp": float(sig.tp_price), "side": sig.side}
            g = resolve(x["bars"], x["i"], row["entry"], row["sl"], row["tp"],
                        shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                        shadow.cost_r(row), LIVE_TRAIL,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is not None:
                res[idx] = g
        return res

    def book(C, res, keep, k_lo=0, k_hi=None, wc=3, tr=2):
        tot, n, pos = 0.0, 0, 0
        for k in range(k_lo, n_win if k_hi is None else k_hi):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            wcl, trl, per, wt = [], [], {}, 0.0
            for idx, x in enumerate(C):
                if not (lo_t <= x["ts"] < hi_t) or idx not in res or not keep(x):
                    continue
                wcl[:] = [q for q in wcl if q > x["ts"]]
                trl[:] = [q for q in trl if q > x["ts"]]
                per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
                bk = trl if x["kind"] == "TREND" else wcl
                cap = tr if x["kind"] == "TREND" else wc
                if per[x["sym"]] or len(bk) >= cap:
                    continue
                g = res[idx]
                bk.append(g[1])
                per[x["sym"]].append(g[1])
                wt += g[0] * eq0 * 0.12 * float(x["sig"].sl_margin_pct) / 100.0
                n += 1
            tot += wt
            pos += 1 if wt > 0 else 0
        return tot, n, pos

    base = {}
    out = []
    grid = ((12, (0.08,)),) if os.environ.get("PJ_VALIDATE") else GRID
    for w, thrs in grid:
        lo = min(thrs)
        W.ROC_BARS = w
        # THE DETECTOR APPLIES ITS OWN FLOOR. detect_wildcard_signal reads
        # FUTURES_WILDCARD_MIN_ROC at call time and rejects `roc_below_min`
        # below it. Without this line every threshold under the live 8% is a
        # silent no-op and the sweep only ever tests thresholds >= 8% -- which
        # is exactly the half of the question worth asking. (Defect found by
        # the 2026-08-25 first run: cells within a window returned IDENTICAL
        # dollars, the tell that the filter was doing nothing.)
        os.environ["FUTURES_WILDCARD_MIN_ROC"] = str(lo)
        print("generating WILDCARD w=%d bars (%.0fh) at thr>=%.0f%% (detector floor %.0f%%) ..."
              % (w, w / 4.0, lo * 100, lo * 100))
        WC = []
        for s in cand_syms:
            if s not in PRE:
                continue
            df, c, roll, bars = PRE[s]
            ts = [b[0] for b in bars]
            for i in range(250, len(c)):
                if i <= w or roll[i] < floor:
                    continue
                roc = c[i] / c[i - w] - 1.0
                if abs(roc) < lo:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                if sig is not None:
                    WC.append({"ts": ts[i], "sym": s, "sig": sig, "i": i, "bars": bars,
                               "kind": "WILDCARD", "roc": roc,
                               "eff": trend_efficiency(c[:i + 1], eff_win)})
        C = sorted(TREND + WC, key=lambda x: x["ts"])
        res = resolve_all(C)
        print("  wildcard cands %d | total %d | resolved %d" % (len(WC), len(C), len(res)))

        for thr in thrs:
            def keep(x, t=thr):
                return x["kind"] != "WILDCARD" or abs(x["roc"]) >= t
            tot, n, pos = book(C, res, keep)
            r = book(C, res, keep, 0, mid)[0]
            o = book(C, res, keep, mid, n_win)[0]
            nwc = sum(1 for x in WC if abs(x["roc"]) >= thr)
            if (w, thr) == LIVE_CELL:
                base = {"tot": tot, "r": r, "o": o, "n": n, "cands": nwc}
                print("  LIVE CELL (internal baseline): %d wildcard candidates, %+.2f"
                      % (nwc, tot))
                print("  Do NOT compare this to a prior run's level -- the pool is re-ranked"
                      " by live turnover and the window rolls daily.")
            out.append({"w": w, "thr": thr, "tot": tot, "r": r, "o": o,
                        "n": n, "pos": pos, "cands": nwc})

    if not base:
        print("LIVE CELL MISSING - cannot compare. Aborting.")
        return 1

    print("")
    print("*** MULTIPLICITY: 15 cells. Best-of-15 finds winners by chance.")
    print("    A both-halves pass here is a CANDIDATE, not a result. ***")
    print("")
    print("%8s %7s %10s %9s %7s %8s %9s %9s  both?"
          % ("window", "thresh", "net $", "vs live", "trades", "pos wk", "recent", "older"))
    winners = []
    for e in sorted(out, key=lambda e: -e["tot"]):
        dr, do = e["r"] - base["r"], e["o"] - base["o"]
        both = "YES" if dr > 0 and do > 0 else ("no" if dr < 0 and do < 0 else "one half")
        tag = "  <-- LIVE" if (e["w"], e["thr"]) == LIVE_CELL else ""
        print("%7.0fh %6.0f%% %+10.2f %+9.2f %7d %4d/%-3d %+9.2f %+9.2f  %s%s"
              % (e["w"] / 4.0, e["thr"] * 100, e["tot"], e["tot"] - base["tot"],
                 e["n"], e["pos"], n_win, dr, do, both, tag))
        if both == "YES" and e["tot"] - base["tot"] > NOISE:
            winners.append(e)

    print("")
    if winners:
        print("CELLS BEATING LIVE IN BOTH HALVES BY MORE THAN THE $%.0f NOISE FLOOR:" % NOISE)
        for e in winners:
            print("  - %.0fh ROC >= %.0f%%  %+.2f vs live  (%d trades)"
                  % (e["w"] / 4.0, e["thr"] * 100, e["tot"] - base["tot"], e["n"]))
        print("  PRE-REGISTER AND RETEST. Do not deploy off this run.")
    else:
        print("NO CELL BEATS LIVE IN BOTH HALVES BY MORE THAN $%.0f." % NOISE)
        print("The 3h/8% trigger survives the sweep.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
