"""TUT-class potential: can any ENTRY feature see it coming, and at what price?

    railway run --service Futures-bot python tools/pit_tut_class.py

WHY. Owner request 2026-08-26, after five clean -1R stops in three days: score
every trade against TUT (peak 4.137R = 100), find what admitted the sub-75s,
"so that we don't have the kind of losing streak we just saw". The live ledger
cannot answer it: only 35 fills carry peak_r and exactly THREE are TUT-class --
and those three paid +$34.48 while the other 32 summed to -$3.30. The book IS
the tail; the question is whether the tail is visible at entry.

WHAT IS ALREADY KNOWN, so this does not re-litigate it: triggers move magnitude,
never frequency (tools/pit_roc_sweep.py -- win rate flat 51-57% in every cell);
market-regime entry gates are worse than randomly dropping the same trades
(tools/pit_regime_gate.py); entry efficiency DOES predict R (+0.401R top bucket
vs +0.103R bottom, tools/regime_scaler_ab.py, n=516) and trial 16 already
exploits it as a SIZE TILT. The open question is narrower: does any entry
feature predict specifically the TUT-CLASS tail (peak >= 3.103R = 75 on the
owner's scale), and if so, is the right instrument a gate or a tilt?

METHOD. Point-in-time pool per tools/pit_rerun.py (wide candidate set, per-bar
rolling-24h turnover floor). WILDCARD sleeve only -- TREND is three fixed
majors with different mechanics. Candidates at the live trigger, deduped to one
per symbol per 2h so events are quasi-independent. Features, all computable at
the entry bar: |3h ROC|, RSI, calm_ratio, ATR%, Kaufman efficiency (24 bars --
the scaler's own input), rolling turnover, designed stop width, side, UTC hour.
Outcomes: (a) peak R before the adverse-first stop within the 24h clock --
"potential", the owner's scale; (b) net R under the LIVE exit stack (0.30
retention trail, 3.0->0.75 ratchet, per-sleeve TP, cost_r) -- "price".
Every split is judged on quintile monotonicity AND an older/recent half-split,
the two filters that killed the scale-out and calm-shock false positives.

Also answers, from the same resolved sequence: does a losing STREAK predict the
next trade? That is the assumption inside both the cold-streak throttle (trial
17's subject) and the owner's framing, and it has never been measured here.
"""
from __future__ import annotations

import os
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

BAR = 900
CHUNK = 1900
TAIL = 260
TUT_PEAK = 4.1374
CLASS_R = 0.75 * TUT_PEAK          # 3.103R = "75" on the owner's scale
DEDUP_S = 7200


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model R over the window, NOT account P&L. ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 190), int(_env("PJ_POOL", 150))
    now = int(time.time())
    floor = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    syms = [s for a, s in crypto if s not in majors and a >= _env("PJ_MIN_TODAY", 3e5)][:pool_n]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}

    frames, _rep = fetch_frames(cl, syms, days=days, workers=6,
                                min_bars=300, now_ts=now)
    print(_rep)

    live_floor = ratchet(3.0, 0.75)
    rows = []
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
        last = -1e18
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < floor:
                continue
            if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < 0.08:
                continue
            if bars[i][0] - last < DEDUP_S:
                continue
            sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
            if sig is None:
                continue
            last = bars[i][0]
            e, sl, tp = float(sig.entry_price), float(sig.sl_price), float(sig.tp_price)
            one = abs(e - sl)
            if one <= 0 or e <= 0:
                continue
            sgn = 1.0 if sig.side == "LONG" else -1.0
            peak, j = 0.0, i + 1
            while j < len(bars) and bars[j][0] - bars[i][0] <= 86400:
                t, hi, lo, _cl = bars[j]
                if (lo <= sl) if sgn > 0 else (hi >= sl):
                    break
                peak = max(peak, ((hi if sgn > 0 else lo) - e) * sgn / one)
                j += 1
            row = {"entry": e, "sl": sl, "tp": tp, "side": sig.side}
            g = resolve(bars, i, e, sl, tp, abs(tp - e) / one, sig.side,
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), live_floor,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is None:
                continue
            rows.append({
                "ts": bars[i][0], "sym": s, "side": sig.side,
                "peak": peak, "cls": peak >= CLASS_R, "net": float(g[0]),
                "abs_roc": abs(c[i] / c[i - W.ROC_BARS] - 1.0),
                "rsi": float(getattr(sig, "rsi", 0.0) or 0.0),
                "calm": float(getattr(sig, "calm_ratio", 0.0) or 0.0),
                "atr_pct": float(getattr(sig, "atr_pct", 0.0) or 0.0),
                "eff24": trend_efficiency(c[:i + 1], 24),
                "turn": roll[i],
                "slf": abs(e - sl) / e,
                "hour": time.gmtime(int(bars[i][0])).tm_hour,
            })
    rows.sort(key=lambda r: r["ts"])
    n = len(rows)
    ncls = sum(1 for r in rows if r["cls"])
    mid_ts = rows[n // 2]["ts"] if n else 0
    print("\ncandidates resolved: %d | TUT-class (peak>=%.2fR): %d = %.1f%%"
          % (n, CLASS_R, ncls, 100.0 * ncls / max(1, n)))
    print("net R, whole book, live exit stack: %+.1f (mean %+.3f)"
          % (sum(r["net"] for r in rows), sum(r["net"] for r in rows) / max(1, n)))

    feats = ["abs_roc", "rsi", "calm", "atr_pct", "eff24", "turn", "slf", "hour"]
    print("\nP(TUT-class) BY QUINTILE  (older-half | recent-half % in brackets)")
    print("%-9s %s   mono?" % ("feature", " ".join("%13s" % ("Q%d" % (q + 1)) for q in range(5))))
    for f in feats:
        h = sorted(rows, key=lambda r: r[f])
        q5 = [h[k * (n // 5):(k + 1) * (n // 5) if k < 4 else n] for k in range(5)]
        cells, halves = [], []
        for g in q5:
            p = 100.0 * sum(1 for r in g if r["cls"]) / max(1, len(g))
            a = [r for r in g if r["ts"] < mid_ts]
            b = [r for r in g if r["ts"] >= mid_ts]
            pa = 100.0 * sum(1 for r in a if r["cls"]) / max(1, len(a))
            pb = 100.0 * sum(1 for r in b if r["cls"]) / max(1, len(b))
            cells.append(p)
            halves.append((pa, pb))
        d = [cells[k + 1] - cells[k] for k in range(4)]
        mono = "YES" if all(x >= 0 for x in d) or all(x <= 0 for x in d) else "no"
        print("%-9s %s   %s" % (f, " ".join("%4.1f[%3.0f|%3.0f]" % (c, ha, hb)
                                            for c, (ha, hb) in zip(cells, halves)), mono))

    print("\nGATE vs TILT, priced in net R under the live stack")
    print("%-26s %8s %8s %8s   %s" % ("policy", "dNetR", "older", "recent", "TUT-class killed"))
    base = sum(r["net"] for r in rows)
    for f in feats:
        h = sorted(rows, key=lambda r: r[f])
        hq = [h[k * (n // 5):(k + 1) * (n // 5) if k < 4 else n] for k in range(5)]
        qmean = [sum(r["net"] for r in g) / max(1, len(g)) for g in hq]
        worst = qmean.index(min(qmean))
        best = qmean.index(max(qmean))
        for lbl, tilt in (("veto worst Q of " + f, False),
                          ("tilt 0.5/1.0/1.5 " + f, True)):
            tot = tota = totb = 0.0
            killed = 0
            for k, g in enumerate(hq):
                if tilt:
                    m = 1.5 if k == best else (0.5 if k == worst else 1.0)
                else:
                    m = 0.0 if k == worst else 1.0
                    if k == worst:
                        killed += sum(1 for r in g if r["cls"])
                for r in g:
                    tot += m * r["net"]
                    if r["ts"] < mid_ts:
                        tota += (m - 1.0) * r["net"]
                    else:
                        totb += (m - 1.0) * r["net"]
            print("%-26s %+8.1f %+8.1f %+8.1f   %s" % (
                lbl, tot - base, tota, totb,
                "none (sizing)" if tilt else "%d of %d" % (killed, ncls)))

    print("\nDOES A LOSING STREAK PREDICT THE NEXT TRADE? (sequential, whole pool)")
    streak = 0
    bucket = defaultdict(list)
    for r in rows:
        bucket[min(streak, 4)].append(r)
        streak = streak + 1 if r["net"] < 0 else 0
    for k in sorted(bucket):
        g = bucket[k]
        print("  after %d consecutive losses: n=%4d  next mean %+0.3fR  P(win) %4.1f%%  P(TUT-class) %4.1f%%"
              % (k, len(g), sum(r["net"] for r in g) / len(g),
                 100.0 * sum(1 for r in g if r["net"] > 0) / len(g),
                 100.0 * sum(1 for r in g if r["cls"]) / len(g)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
