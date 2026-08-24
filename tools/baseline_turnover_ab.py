"""Does the turnover floor measure LIQUIDITY, or does the pump clear it itself?

    railway run --service Futures-bot python tools/baseline_turnover_ab.py

ZAMA_USDT, 2026-08-22, is the case that prompted this. It sat at $0.69-0.89M of
24h turnover for twenty hours, then pumped +25% in three hours; the pump itself
carried turnover to $2.90M by the time the wildcard signal fired and $3.22M
fifteen minutes later. The bot went LONG at 0.06413 and the name gave back -18%
in forty minutes, stopping out at -1R.

Execution was not the problem — spread 3.7bps, $54k of top-10 depth. The GATE was
the problem, and in a way no floor LEVEL can fix: a trailing-24h turnover floor is
cleared by the very spike the detector exists to trade. The floor is supposed to
say "this name is liquid enough to trade"; on a pump it only says "this name is
being pumped right now".

So this measures the obvious repair: judge liquidity from BEFORE the impulse.
For every wildcard signal, record turnover as usual AND the same 24h turnover as
it stood 6 HOURS EARLIER — outside the 3h window the ROC gate looks at, so the
impulse cannot manufacture it. Then compare outcomes by that baseline, and by the
RATIO of live turnover to baseline, which is a direct measure of "how much of
this name's liquidity is the event itself".

If pump-cleared names are systematically worse, a baseline gate raises the whole
sleeve's average and is worth more than any floor level. If they are not, ZAMA
was one bad trade and the risk stack already handled it.

RESULT, 2026-08-22 -- 80 symbols, 208 days, 459 resolved wildcard trades.
THE HYPOTHESIS IS WRONG. DO NOT BUILD THE GATE.

    by PRE-IMPULSE (6h-lagged) 24h turnover
    bucket                 n      net $   $/trade     netR    win%
    under $1M             21      -3.07    -0.146    -0.46   66.7%
    $1-2M                 24     +17.22    +0.718    +4.05   62.5%
    $2-3M                 29     +23.12    +0.797    +9.62   51.7%
    $3-5M                 53     -12.29    -0.232    -2.88   54.7%
    $5-10M                56      +4.86    +0.087    +1.76   46.4%
    $10M+                276    +131.46    +0.476   +45.39   56.5%

    by live/baseline RATIO -- how much of the liquidity IS the event
    <= 1.2x quiet        270     +84.65    +0.314   +31.48   55.6%
    1.2-1.5x              75     +27.65    +0.369   +11.42   54.7%
    1.5-2x                55      -8.80    -0.160    -3.61   45.5%
    2-3x                  28     +61.28    +2.189   +20.05   71.4%
    > 3x pump-fed         31      -3.49    -0.113    -1.84   61.3%

    a baseline floor ON TOP of the live floor
      baseline floor   kept  dropped     kept $   dropped $  $/trade kept
                1.0M    438       21    +164.37       -3.07        +0.375
                2.0M    414       45    +147.15      +14.15        +0.355
                3.0M    385       74    +124.03      +37.27        +0.322
                5.0M    332      127    +136.32      +24.98        +0.411
      (no gate: 459 trades, +161.30, +0.351/trade)

NEITHER CUT ORDERS. Pre-impulse turnover is not monotonic in anything: $2-3M is
the best bucket (+0.797) and $3-5M is the worst (-0.232), with $10M+ in between.
The ratio is worse still for the story -- the "2-3x" bucket, which is exactly the
partially-event-driven case the hypothesis says to avoid, is the BEST bucket in
the whole study at +2.189/trade, while ">3x pump-fed" is -0.113, i.e. zero.

And the gate loses money at every level that would matter. A $1M baseline floor
drops 21 trades worth -$3.07 -- about $0.44/month, inside noise. Every higher
floor throws away PROFIT: $2M forfeits +$14.15, $3M forfeits +$37.27.

WHAT IS TRUE, AND EXPLAINS ZAMA WITHOUT JUSTIFYING A CHANGE: the thin-baseline
and pump-fed buckets have HIGH win rates and negative totals -- 66.7% and 61.3%
win, both net negative. They win often and lose big. That is a fatter left tail,
not a lower expectancy, and a convex sleeve with a -1R stop is built to absorb
exactly that. ZAMA lost 0.9% of equity on an 18% collapse.

So the ZAMA post-mortem ends: the risk stack worked, the signal was unlucky
rather than systematically identifiable, and the gate that would have caught it
would have cost more than it saved.

Read-only. Places nothing.

Env: BT_DAYS (190) BT_POOL (80) BT_LAG_H (6)
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
from retention_trail_ab import make_floor, resolve

CHUNK, BAR = 2000, 900
FLOOR = make_floor("flat", 0.30, 1.0)


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars over the window, NOT account P&L.")
    print("    Arms marked 'live cfg' are the live SETTINGS, not live results.")
    print("    The real account is DOWN lifetime; /report has the true figure. ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("BT_DAYS", 190), int(_env("BT_POOL", 80))
    lag = int(_env("BT_LAG_H", 6) * 4)          # bars of 15m
    eq = rt._last_known_equity() or 166.0
    now = int(time.time())
    min_turn = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    ranked = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))
                     and str(t.get("symbol") or "") not in majors
                     and float(t.get("amount24") or 0) >= 5e5), reverse=True)
    syms = [s for _a, s in ranked[:pool_n]]
    print(f"equity ${eq:.2f} | {len(syms)} symbols | live floor ${min_turn/1e6:.0f}M "
          f"| baseline lag {lag/4:.0f}h")

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
    print("generating candidates, tagging each with its PRE-IMPULSE turnover...")
    trades = []
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
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < min_turn:
                continue
            if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                continue
            sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
            if sig is None:
                continue
            row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
                   "tp": float(sig.tp_price), "side": sig.side}
            g = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                        shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                        shadow.cost_r(row), FLOOR,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is None:
                continue
            r_net, _ex, _k = g
            usd = r_net * eq * 0.12 * float(sig.sl_margin_pct) / 100.0
            baseline = roll[max(0, i - lag)]
            trades.append({"sym": s, "usd": usd, "r": r_net, "side": sig.side,
                           "live": roll[i], "base": baseline,
                           "ratio": (roll[i] / baseline) if baseline > 0 else 99.0})
    print(f"resolved trades: {len(trades)}")
    if not trades:
        return 0

    def report(title, key, buckets):
        print()
        print(f"=== {title} ===")
        print(f"{'bucket':<18} {'n':>5} {'net $':>10} {'$/trade':>9} {'netR':>8} {'win%':>7}")
        for label, fn in buckets:
            sub = [t for t in trades if fn(t[key])]
            if not sub:
                print(f"{label:<18} {0:5d}         --        --       --      --")
                continue
            u = sum(t["usd"] for t in sub)
            r = sum(t["r"] for t in sub)
            w = 100 * sum(1 for t in sub if t["usd"] > 0) / len(sub)
            print(f"{label:<18} {len(sub):5d} {u:+10.2f} {u/len(sub):+9.3f} "
                  f"{r:+8.2f} {w:6.1f}%")

    report("BY PRE-IMPULSE (6h-lagged) 24h TURNOVER", "base", [
        ("under $1M", lambda x: x < 1e6),
        ("$1-2M", lambda x: 1e6 <= x < 2e6),
        ("$2-3M", lambda x: 2e6 <= x < 3e6),
        ("$3-5M", lambda x: 3e6 <= x < 5e6),
        ("$5-10M", lambda x: 5e6 <= x < 1e7),
        ("$10M+", lambda x: x >= 1e7),
    ])

    report("BY live/baseline RATIO (how much is the event itself)", "ratio", [
        ("<= 1.2x quiet", lambda x: x <= 1.2),
        ("1.2-1.5x", lambda x: 1.2 < x <= 1.5),
        ("1.5-2x", lambda x: 1.5 < x <= 2.0),
        ("2-3x", lambda x: 2.0 < x <= 3.0),
        ("> 3x pump-fed", lambda x: x > 3.0),
    ])

    print()
    print("=== WHAT A BASELINE FLOOR WOULD DO (applied ON TOP of the live floor) ===")
    total = sum(t["usd"] for t in trades)
    print(f"{'baseline floor':>16} {'kept':>6} {'dropped':>8} {'kept $':>10} "
          f"{'dropped $':>11} {'$/trade kept':>13}")
    for f_usd in (0, 1e6, 2e6, 3e6, 5e6):
        keep = [t for t in trades if t["base"] >= f_usd]
        drop = [t for t in trades if t["base"] < f_usd]
        ku = sum(t["usd"] for t in keep)
        du = sum(t["usd"] for t in drop)
        print(f"{f_usd/1e6:15.1f}M {len(keep):6d} {len(drop):8d} {ku:+10.2f} "
              f"{du:+11.2f} {ku/len(keep) if keep else 0:+13.3f}")
    print(f"  (no baseline gate: {len(trades)} trades, {total:+.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
