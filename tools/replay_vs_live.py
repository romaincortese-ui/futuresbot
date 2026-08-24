"""Does the replay reproduce what the bot ACTUALLY did?

    railway run --service Futures-bot python tools/replay_vs_live.py <live_rows.jsonl>

Every recommendation this session rested on a replay: the shipped detectors
applied retroactively over 208-361 days, scored on a shared book with slots. That
machinery decided the trend universe, the turnover floor, the renormalised
sizing, the retention ratchet, and it rejected the squeeze, trend shorts, sharper
size tilts and a lateness gate.

None of it was ever checked against the live record over the SAME DAYS.

That is the check. Same window, same symbols, live rows from the feature store on
one side and the replay on the other. The replay is unconstrained — no vetoes, no
streak throttle, no scan cap, no min_vol skip — so it will always take more
trades; the count is expected to differ and is not the test. The test is whether
the PER-TRADE distribution agrees: mean R, win rate, and how often a trade ever
reaches +1R.

If they agree, the replay is a fair instrument for ranking rules even though its
levels are inflated. If they disagree, every verdict built on it needs re-reading,
including the ones already shipped.

RESULT, 2026-08-24 -- 30 days, live feature store vs replay over the same days.
THE REPLAY IS FAIR FOR RANKING RULES AND WRONG IN TWO WAYS THAT MATTER.

    arm                        n    mean R     net R    win%  reach +1R
    LIVE (actual)             44    +0.256    +11.28     48%        36%
    REPLAY (same days)       123    +0.148    +18.16     53%        63%

    pool covers 12 of the 30 symbols actually traded

1. COVERAGE IS 40%, NOT ~100%. The replay pool is "top-70 by turnover TODAY",
   and the bot traded 30 distinct symbols over the window. Eighteen of them are
   not in the pool at all, because turnover rankings churn: a name that cleared
   the floor three weeks ago while it was moving can sit far outside today's top
   70. So the replay has been scoring a substantially DIFFERENT symbol set than
   the bot trades. Pools should be built from turnover AS OF each bar, which the
   point-in-time floor machinery already supports and these tools did not use.

2. PEAK IS BIASED HIGH BY 26 POINTS. Live trades reach +1R 36% of the time; the
   replay says 63%. The cause is structural: the replay reads peaks from bar
   HIGHS, so it sees every intrabar spike, while the live bot samples on a
   45-60s cycle and records only what it observed. The replay's peak is an upper
   bound, not an estimate.

   THIS MATTERS MOST FOR THE RETENTION RATCHET, shipped 2026-08-22 on the
   strength of tools/peak_fate_ab.py. That study found 378 of 1380 candidates
   (27%) reaching a 3R peak; the live record has 3 of 63 (5%). The ratchet only
   acts on trades above 3R, so its real-world effect is plausibly on the order of
   5/27 of the measured +$25.33 -- single dollars per 208 days, not tens. The
   DIRECTION of that result is unaffected (every variant passed both halves) but
   the magnitude was overstated and should be read down hard.

3. MEAN R RUNS THE OTHER WAY, which is the reassuring half: live +0.256 against
   replay +0.148. The replay is CONSERVATIVE on expectancy, so it has not been
   flattering the strategy's edge. Note the window is surge-heavy, which lifts
   the live figure.

WHAT SURVIVES. Every decision this session was a RELATIVE comparison -- rule A
against rule B on identical candidates, identical slots, identical costs. Shared
bias largely cancels in a difference, which is why the design was built that way.
What does not survive is any statement about LEVELS, and any statement resting on
how often trades reach a peak.

Read-only. Places nothing.

Env: RV_DAYS (30) RV_POOL (70) RV_SLOTS (3)
"""
from __future__ import annotations

import json
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
LIVE_TRAIL = ratchet(3.0, 0.75)


def _f(v, d=0.0):
    try:
        return float(v if v is not None else d)
    except (TypeError, ValueError):
        return d


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def _summary(label, rs, peaks):
    if not rs:
        print(f"{label:<22} no trades")
        return
    w = sum(1 for x in rs if x > 0)
    arm = sum(1 for p in peaks if p >= 1.0) if peaks else 0
    print(f"{label:<22} {len(rs):5d} {sum(rs)/len(rs):+9.3f} {sum(rs):+9.2f} "
          f"{100*w/len(rs):6.0f}% "
          f"{(100*arm/len(peaks)) if peaks else 0:9.0f}%")


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars over the window, NOT account P&L.")
    print("    Arms marked 'live cfg' are the live SETTINGS, not live results.")
    print("    The real account is DOWN lifetime; /report has the true figure. ***")
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("RV_DAYS", 30), int(_env("RV_POOL", 70))
    slots = int(_env("RV_SLOTS", 3))
    now = int(time.time())
    cut = now - days * 86400
    min_turn = W.wildcard_min_turnover_usdt()

    # ---- LIVE side -----------------------------------------------------
    path = sys.argv[1] if len(sys.argv) > 1 else "live.jsonl"
    live = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if _f(r.get("ts")) >= cut:
                    live.append(r)
    except OSError as exc:
        print(f"cannot read live rows: {exc}")
        return 1
    live_syms = sorted({str(r.get("symbol") or "") for r in live})
    print(f"LIVE: {len(live)} convex closes in the last {days:.0f}d "
          f"across {len(live_syms)} symbols")

    # ---- REPLAY side, same window --------------------------------------
    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    ranked = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wc = [s for a, s in ranked if s not in majors and a >= min_turn][:pool_n]
    syms = sorted(set(wc) | set(TREND_SYMS) | set(live_syms))
    covered = sum(1 for s in live_syms if s in wc or s in TREND_SYMS)
    print(f"REPLAY pool: {len(wc)} wildcard names + {len(TREND_SYMS)} trend | "
          f"covers {covered}/{len(live_syms)} of the symbols actually traded")

    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    nch = int((days + 12) * 86400 // (CHUNK * BAR)) + 1

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
        F = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 300}

    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))
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
        bars = list(zip([float(x.timestamp()) for x in df.index], h, lo, c))
        ts = [b[0] for b in bars]
        for i in range(250, len(c)):
            if ts[i] < cut:
                continue
            if s in TREND_SYMS and abs(c[i] / c[i - 96] - 1.0) >= 0.04:
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None and sig.side == "LONG":
                    cands.append((ts[i], s, sig, i, bars, c, h, lo))
            if s in wc and i > W.ROC_BARS and roll[i] >= min_turn \
                    and abs(c[i] / c[i - W.ROC_BARS] - 1.0) >= min_roc:
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    cands.append((ts[i], s, sig, i, bars, c, h, lo))
    cands.sort(key=lambda x: x[0])

    rep_rs, rep_peaks = [], []
    live_slots, per = [], {}
    for ts0, sym, sig, i, bars, c, h, lo in cands:
        live_slots[:] = [x for x in live_slots if x > ts0]
        per[sym] = [x for x in per.get(sym, []) if x > ts0]
        if per[sym] or len(live_slots) >= slots:
            continue
        row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
               "tp": float(sig.tp_price), "side": sig.side}
        g = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                    shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                    shadow.cost_r(row), LIVE_TRAIL,
                    float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
        if g is None:
            continue
        live_slots.append(g[1])
        per[sym].append(g[1])
        rep_rs.append(g[0])
        e = float(sig.entry_price)
        slf = abs(e - float(sig.sl_price)) / e
        sgn = 1.0 if sig.side == "LONG" else -1.0
        end_ts = ts0 + shadow.CONVEX_HORIZON_S
        pk = 0.0
        for k in range(i + 1, len(c)):
            if bars[k][0] > end_ts:
                break
            fav = (h[k] - e) / e if sgn > 0 else (e - lo[k]) / e
            pk = max(pk, fav / slf)
        rep_peaks.append(pk)

    print()
    print(f"{'arm':<22} {'n':>5} {'mean R':>9} {'net R':>9} {'win%':>7} {'reach +1R':>10}")
    _summary("LIVE (actual)", [_f(r.get("r_multiple")) for r in live],
             [_f(r.get("peak_r")) for r in live])
    _summary("REPLAY (same days)", rep_rs, rep_peaks)

    if live and rep_rs:
        lm = sum(_f(r.get("r_multiple")) for r in live) / len(live)
        rm = sum(rep_rs) / len(rep_rs)
        la = 100 * sum(1 for r in live if _f(r.get("peak_r")) >= 1.0) / len(live)
        ra = 100 * sum(1 for p in rep_peaks if p >= 1.0) / len(rep_peaks)
        print()
        print(f"  mean R   live {lm:+.3f} vs replay {rm:+.3f}   gap {rm-lm:+.3f}")
        print(f"  reach+1R live {la:.0f}% vs replay {ra:.0f}%      gap {ra-la:+.0f}pp")
        print(f"  trade count live {len(live)} vs replay {len(rep_rs)} "
              f"({len(rep_rs)/len(live):.1f}x — expected, the replay is unconstrained)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
