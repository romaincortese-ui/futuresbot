"""Is the UNIVERSE producing extended moves? The opportunity set, not a proxy.

    railway ssh --service Futures-bot -> /opt/venv/bin/python tools/pit_universe_followthrough.py

WHY THIS EXISTS. Sixteen regime formulations have now been refuted, and every one
of them measured the wrong thing. They measured either:

  * BTC/ETH/SOL - a proxy for a universe the bot does not trade, or
  * the bot's own closes - ~2.5 a day, far too few to detect a change in
    follow-through before the drought is already over.

The 7-day post-mortem (2026-09-02) described the actual failure precisely: the
entries were unchanged (3h ROC 12.9 -> 13.2), the losses were unchanged
(-1.04R both weeks), the win rate barely moved - but mean peak_r fell
1.487 -> 0.948 and take-profits went 5 -> 0. The moves stopped EXTENDING.

So measure that, universe-wide. Of every 8% three-hour move across the ~170
tradeable symbols, what fraction reaches 1R, 3R, 5R? That is the literal
definition of "the market is producing the moves this bot monetises", and it
carries perhaps 10-50x the daily sample of the bot's own book.

STRICTLY BACKWARD-LOOKING. For a trade entered at t, follow-through is computed
only from universe signals that had already RESOLVED before t. A signal fired at
t-2h has not finished its 24h horizon and contributes nothing. Without that rule
this measure would trivially "predict" outcomes it had already seen.

COMPLETED BARS, deliberately. The intra-bar phase grids exist to reproduce the
bot's FILL timing; here the question is how many distinct moves occurred, and
three phase grids would count one move up to three times.

READ-ONLY.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_placebo import placebo_test  # noqa: E402

STORE = "/data/futures_feature_store.jsonl"
TAIL = 260
HORIZON = 24 * 3600.0


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    now = int(time.time())
    days, pool_n = _env("PJ_DAYS", 220), int(_env("PJ_POOL", 170))
    floor_to = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    min_roc = _env("FUTURES_WILDCARD_MIN_ROC", 0.08)

    tk = cl.get_all_tickers() or []
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 2e5)][:pool_n]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    frames, rep = fetch_frames(cl, cand, days=days, workers=6, min_bars=300, now_ts=now)
    print(rep)

    # ---- census: every qualifying move in the universe, and how far it went ----
    SIG = []
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
        ts_all = [float(x.timestamp()) for x in df.index]
        hi = [float(x) for x in df["high"]]
        lo = [float(x) for x in df["low"]]
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < floor_to:
                continue
            if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                continue
            sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
            if sig is None:
                continue
            e, sl = float(sig.entry_price), float(sig.sl_price)
            one = abs(e - sl)
            if one <= 0 or e <= 0:
                continue
            sgn = 1.0 if sig.side == "LONG" else -1.0
            t0 = ts_all[i]
            if now - t0 < HORIZON:
                continue                       # unresolved; must not be counted
            peak, stopped = 0.0, False
            for k in range(i + 1, len(c)):
                if ts_all[k] - t0 > HORIZON:
                    break
                adverse = ((lo[k] if sgn > 0 else hi[k]) - e) * sgn / one
                fav = ((hi[k] if sgn > 0 else lo[k]) - e) * sgn / one
                peak = max(peak, fav)
                if adverse <= -1.0:
                    stopped = True
                    break
            SIG.append({"ts": t0, "resolved": t0 + HORIZON, "peak": peak,
                        "stopped": stopped})
    SIG.sort(key=lambda z: z["resolved"])
    print("universe signals resolved: %d over %.0f days (%.1f/day)\n"
          % (len(SIG), days, len(SIG) / days))
    if len(SIG) < 200:
        print("too few to analyse")
        return 1

    def followthrough(t, window_h=24.0):
        """Fraction reaching 1R, among signals RESOLVED in the window before t."""
        lo_t = t - window_h * 3600.0
        g = [z for z in SIG if lo_t <= z["resolved"] < t]
        if len(g) < 5:
            return None
        return (sum(1 for z in g if z["peak"] >= 1.0) / len(g), len(g),
                statistics.mean(z["peak"] for z in g))

    print("=" * 92)
    print("A. THE UNIVERSE'S OWN FOLLOW-THROUGH, by day (last 21)")
    print("=" * 92)
    print("  %-12s %7s %8s %8s %8s %8s"
          % ("day", "signals", "reach1R", "reach3R", "reach5R", "mean pk"))
    byday = {}
    for z in SIG:
        k = dt.datetime.fromtimestamp(z["ts"], dt.UTC).strftime("%Y-%m-%d")
        byday.setdefault(k, []).append(z)
    for k in sorted(byday)[-21:]:
        g = byday[k]
        print("  %-12s %7d %7.0f%% %7.0f%% %7.0f%% %8.2f"
              % (k, len(g), 100 * sum(1 for z in g if z["peak"] >= 1) / len(g),
                 100 * sum(1 for z in g if z["peak"] >= 3) / len(g),
                 100 * sum(1 for z in g if z["peak"] >= 5) / len(g),
                 statistics.mean(z["peak"] for z in g)))

    daily = [(k, 100 * sum(1 for z in byday[k] if z["peak"] >= 1) / len(byday[k]))
             for k in sorted(byday) if len(byday[k]) >= 5]
    print()
    print("=" * 92)
    print("B. IS IT AUTOCORRELATED? does yesterday's follow-through predict today's")
    print("=" * 92)
    for lag in (1, 2, 3):
        xs = [daily[i][1] for i in range(len(daily) - lag)]
        ys = [daily[i + lag][1] for i in range(len(daily) - lag)]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        sx, sy = statistics.pstdev(xs), statistics.pstdev(ys)
        cor = (sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / len(xs) / (sx * sy)) \
            if sx and sy else 0.0
        print("  lag %d day: correlation %+.3f  (n=%d days)" % (lag, cor, len(xs)))
    print("  daily reach-1R: mean %.0f%%  sd %.0f%%  min %.0f%%  max %.0f%%"
          % (statistics.mean(v for _, v in daily), statistics.pstdev(v for _, v in daily),
             min(v for _, v in daily), max(v for _, v in daily)))

    # ---- does it predict the BOT? ----
    rows = []
    for line in open(STORE, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("pnl_usdt") is None or not r.get("risk_usdt"):
            continue
        r["_in"] = float(r["ts"]) - float(r.get("hold_hours") or 0) * 3600.0
        rows.append(r)
    base = sum(float(r["pnl_usdt"]) for r in rows)
    print()
    print("=" * 92)
    print("C. DOES IT PREDICT THE BOT? gate on LAGGED universe follow-through")
    print("=" * 92)
    print("  bot closes: %d  ungated net $%+.2f" % (len(rows), base))
    print("  %-42s %5s %10s %10s  %s"
          % ("gate", "kept", "net $", "vs ungated", "verdict"))
    fts = [followthrough(r["_in"]) for r in rows]
    have = [f[0] for f in fts if f is not None]
    if len(have) < 20:
        print("  only %d closes have a resolved universe window - too few" % len(have))
        return 0
    med = statistics.median(have)
    for lbl, thr in (("median %.2f" % med, med), ("0.40", 0.40), ("0.50", 0.50)):
        def mk(threshold):
            def g(t):
                f = followthrough(t)
                return f is not None and f[0] >= threshold
            return g
        res = placebo_test(rows, mk(thr), time_of=lambda x: x["_in"],
                           value_of=lambda x: float(x["pnl_usdt"]), min_n=5)
        print("  %-42s %5d %+10.2f %+10.2f  %s"
              % ("universe reach-1R >= %s" % lbl, res.real_n, res.real,
                 res.real - base, res.verdict.split(" - ")[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
