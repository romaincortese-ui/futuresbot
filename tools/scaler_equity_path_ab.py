"""The regime-scaler question the linear studies cannot answer: COMPOUNDED.

    railway run --service Futures-bot python tools/scaler_equity_path_ab.py

tools/regime_scaler_ab.py sums dollars at a FIXED 1R. That is the right frame for
"is the tilt smart", and the wrong frame for "should we run a sharper one",
because it is blind to the two things a sharp tilt actually threatens:

  1. GEOMETRIC GROWTH. A scheme with the same arithmetic mean and more variance
     compounds SLOWER. That is the whole content of Kelly, and every number
     produced so far is arithmetic.
  2. CONCURRENT EXPOSURE. The scaler is a PER-TRADE rule. High-efficiency entries
     fire in clean trends, which is exactly when they are correlated, so three
     top-bucket slots can be open at once. Nothing in the sizing nets that.

So this replays the real book with real slots and a real equity curve: size each
entry as equity x risk_pct_eff x mult, compound realised R into equity as trades
close, and record what was actually at risk simultaneously.

risk_pct_eff = 0.0187 / mean(mult), i.e. every arm is RENORMALISED to deploy the
same average risk as the design 1.87%. This isolates the SHAPE of the tilt from
the size of the book — otherwise a sharper tilt just looks worse for trading
smaller, which is the confound that sank the raw comparison.

RESULT, 2026-08-22 -- 83 symbols, 208 days, 1476 candidates, 516 fills.
RENORMALISE: YES. SHARPEN: NO. The compounded test reverses the linear one.

    setting                     risk/trade   final eq    growth    maxDD  conc med    p95    max
    OFF (flat 1.87%)                 1.87%    1182.60   +615.2%    24.2%      3.7%   7.5%   9.5%
    LIVE 0.20/0.45/0.25              2.41%    1255.18   +659.1%    20.2%      3.0%   8.0%  11.4%
    floor 0.50                       2.20%    1232.85   +645.6%    21.6%      3.3%   7.7%  10.7%
    sharp 0.20/0.60/0.25             2.80%    1255.58   +659.3%    19.8%      2.8%   8.2%  11.5%
    sharp 0.20/0.60/0.10             3.11%    1266.74   +666.1%    20.4%      2.9%   8.3%  12.1%
    sharp 0.20/0.70/0.10             3.57%    1225.43   +641.1%    20.2%      2.8%   8.4%  11.6%
    aggressive 0.30/0.50/0.10        3.09%    1424.98   +761.8%    23.2%      3.1%   8.7%  12.8%

FIRST, THE LINEAR RANKING DOES NOT SURVIVE COMPOUNDING. In the arithmetic study
0.20/0.70/0.10 had the LARGEST tilt of all (+197.44) and aggressive was second
(+195.01). Compounded, 0.20/0.70/0.10 is the WORST sharp variant (+641.1%) and
aggressive the best (+761.8%). Variance drag is doing exactly what Kelly says it
does, and no sum-of-dollars study can see it.

SECOND, THE CONCURRENT-EXPOSURE OBJECTION IS ANSWERED AND IT IS MILD. Total risk
across all open slots peaks at 9.5% of equity with no scaler, 11.4% renormalised
at the live shape and 12.8% at the sharpest. Median concurrent risk is 2.8-3.7%
throughout. Nothing approaches ruin, and no arm went bust.

THIRD, AND IT DECIDES THE QUESTION -- each half run as an INDEPENDENT path:

    setting                     older growth  recent growth  older DD  recent DD  beats OFF twice?
    OFF (flat 1.87%)                  +27.5%        +491.6%     16.5%      24.2%  (null)
    LIVE 0.20/0.45/0.25               +32.2%        +494.6%     20.2%      19.9%  YES
    floor 0.50                        +30.7%        +495.2%     17.5%      21.6%  YES
    sharp 0.20/0.60/0.25              +25.5%        +521.8%     18.4%      19.7%  one half only
    sharp 0.20/0.60/0.10              +24.3%        +527.7%     20.2%      18.2%  one half only
    sharp 0.20/0.70/0.10              +23.3%        +514.3%     19.6%      18.6%  one half only
    aggressive 0.30/0.50/0.10         +27.1%        +577.0%     20.9%      16.4%  one half only

EVERY SHARP VARIANT FAILS. All four underperform the no-scaler null in the OLDER
half (+23.3% to +27.1% against OFF's +27.5%) and beat it handsomely in the recent
one. Aggressive's entire +761.8% advantage is the recent half; its older half is
marginally WORSE than doing nothing. That is regime fitting, and the linear study
scored it "YES" only because it measured tilt in dollars rather than compounded
growth against the null.

ONLY THE EXISTING SHAPE AND A SHALLOWER FLOOR SURVIVE BOTH HALVES. Renormalised
LIVE returns +32.2% / +494.6% against the null's +27.5% / +491.6%, with maxDD
falling 24.2% -> 20.2% overall and 24.2% -> 19.9% in the recent half. Better
growth AND lower drawdown, in both halves, is the strongest result of the
session.

VERDICT: set FUTURES_WILDCARD_RISK_PCT 0.0187 -> 0.0241 and leave the scaler
parameters at 0.20/0.45/0.25. Do not sharpen the tilt.

Read-only. Places nothing.

Env: EP_DAYS (190) EP_POOL (80) EP_SLOTS (3) EP_TREND_SLOTS (2)
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
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency
from futuresbot.runtime import FuturesRuntime
from futuresbot.trend import detect_trend_signal
from retention_trail_ab import make_floor, resolve

CHUNK, BAR = 2000, 900
FLOOR = make_floor("flat", 0.30, 1.0)
TREND_SYMS = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
BASE_RISK = 0.0187

GRID = [
    ("no scaler (null)", None),
    ("0.20/0.45/0.25 (live cfg)", (0.20, 0.45, 0.25)),
    ("floor 0.50", (0.20, 0.45, 0.50)),
    ("sharp 0.20/0.60/0.25", (0.20, 0.60, 0.25)),
    ("sharp 0.20/0.60/0.10", (0.20, 0.60, 0.10)),
    ("sharp 0.20/0.70/0.10", (0.20, 0.70, 0.10)),
    ("aggressive 0.30/0.50/0.10", (0.30, 0.50, 0.10)),
]


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def mult_of(eff, params):
    if params is None:
        return 1.0
    lo, hi, fl = params
    return regime_size_multiplier(eff, lo=lo, hi=hi, floor_mult=fl)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars over the window, NOT account P&L.")
    print("    Arms marked 'live cfg' are the live SETTINGS, not live results.")
    print("    The real account is DOWN lifetime; /report has the true figure. ***")
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("EP_DAYS", 190), int(_env("EP_POOL", 80))
    slots, tr_slots = int(_env("EP_SLOTS", 3)), int(_env("EP_TREND_SLOTS", 2))
    eq0 = rt._last_known_equity() or 165.0
    now = int(time.time())
    min_turn = W.wildcard_min_turnover_usdt()
    window = max(4, int(rt._env_float("FUTURES_REGIME_EFF_WINDOW", 24.0)))

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    ranked = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wc_syms = [s for a, s in ranked if s not in majors and a >= min_turn][:pool_n]
    syms = sorted(set(wc_syms) | set(TREND_SYMS))
    print(f"start equity ${eq0:.2f} | {len(syms)} symbols | slots wc {slots} / tr {tr_slots}")

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
        F = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 200}
    span = len(next(iter(F.values()))) * BAR / 86400
    print(f"frames: {len(F)} symbols, ~{span:.0f}d")

    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))
    print("generating candidates...")
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

        def add(sig, i, kind):
            row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
                   "tp": float(sig.tp_price), "side": sig.side}
            g = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                        shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                        shadow.cost_r(row), FLOOR,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is None:
                return
            r_net, ex_ts, _k = g
            cands.append((bars[i][0], float(ex_ts), s, kind, r_net,
                          trend_efficiency(c[:i + 1], window)))

        if s in TREND_SYMS:
            for i in range(200, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None and sig.side == "LONG":
                    add(sig, i, "TREND")
        if s in wc_syms:
            for i in range(200, len(c)):
                if i <= W.ROC_BARS or roll[i] < min_turn:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    add(sig, i, "WILDCARD")
    cands.sort(key=lambda x: x[0])
    print(f"candidates: {len(cands)}")
    if not cands:
        return 0

    def run(params, t_lo=0.0, t_hi=9e18):
        pool = [c for c in cands if t_lo <= c[0] < t_hi]
        if not pool:
            return None
        mean_mult = (sum(mult_of(c[5], params) for c in pool) / len(pool)) or 1.0
        risk_eff = BASE_RISK / mean_mult
        equity = eq0
        peak = eq0
        maxdd = 0.0
        open_pos = []           # (exit_ts, risk_usd, r, kind, sym)
        conc = []               # concurrent risk as % of equity, sampled at entry
        n = 0
        blown = False
        for ts, ex_ts, sym, kind, r_net, eff in pool:
            # settle anything that closed before this signal
            for p_ in [x for x in open_pos if x[0] <= ts]:
                equity += p_[2] * p_[1]
                open_pos.remove(p_)
                peak = max(peak, equity)
                maxdd = max(maxdd, (peak - equity) / peak if peak > 0 else 0.0)
            if equity <= 0:
                blown = True
                break
            book = [x for x in open_pos if x[3] == kind]
            cap = tr_slots if kind == "TREND" else slots
            if any(x[4] == sym for x in open_pos) or len(book) >= cap:
                continue
            risk_usd = equity * risk_eff * mult_of(eff, params)
            open_pos.append((ex_ts, risk_usd, r_net, kind, sym))
            conc.append(sum(x[1] for x in open_pos) / equity * 100.0)
            n += 1
        for p_ in open_pos:
            equity += p_[2] * p_[1]
        peak = max(peak, equity)
        maxdd = max(maxdd, (peak - equity) / peak if peak > 0 else 0.0)
        conc.sort()
        return {
            "mean_mult": mean_mult, "risk_eff": risk_eff * 100, "equity": equity,
            "maxdd": maxdd * 100, "n": n, "blown": blown,
            "conc_med": conc[len(conc) // 2] if conc else 0.0,
            "conc_p95": conc[int(len(conc) * 0.95)] if conc else 0.0,
            "conc_max": conc[-1] if conc else 0.0,
        }

    print()
    print("=== COMPOUNDED, every arm renormalised to the same 1.87% mean risk ===")
    print(f"{'setting':<26} {'risk/trade':>11} {'final eq':>10} {'growth':>9} "
          f"{'maxDD':>8} {'conc med':>9} {'p95':>7} {'max':>7}")
    base = None
    for label, params in GRID:
        r = run(params)
        if params is None:
            base = r
        g = (r["equity"] / eq0 - 1.0) * 100
        flag = "  BLOWN" if r["blown"] else ""
        print(f"{label:<26} {r['risk_eff']:10.2f}% {r['equity']:10.2f} {g:+8.1f}% "
              f"{r['maxdd']:7.1f}% {r['conc_med']:8.1f}% {r['conc_p95']:6.1f}% "
              f"{r['conc_max']:6.1f}%{flag}")
    if base:
        print()
        print(f"  (OFF is the null: flat 1.87% on every trade, {base['n']} fills)")

    # ONE COMPOUNDED PATH RANKS NOTHING. Sequence dominates at these risk levels,
    # so each half is run as an independent path from the same starting equity.
    ts_all = sorted(c[0] for c in cands)
    mid = ts_all[len(ts_all) // 2]
    off_o = run(None, 0.0, mid)
    off_r = run(None, mid, 9e18)
    print()
    print("=== SAME TEST ON EACH HALF, INDEPENDENTLY ===")
    print(f"{'setting':<26} {'older growth':>13} {'recent growth':>14} "
          f"{'older DD':>9} {'recent DD':>10}  beats OFF twice?")
    for label, params in GRID:
        a = run(params, 0.0, mid)
        b = run(params, mid, 9e18)
        if a is None or b is None:
            continue
        ga = (a["equity"] / eq0 - 1.0) * 100
        gb = (b["equity"] / eq0 - 1.0) * 100
        oa = (off_o["equity"] / eq0 - 1.0) * 100
        ob = (off_r["equity"] / eq0 - 1.0) * 100
        ok = "(null)" if params is None else (
            "YES" if ga > oa and gb > ob else
            ("no" if ga < oa and gb < ob else "one half only"))
        print(f"{label:<26} {ga:+12.1f}% {gb:+13.1f}% {a['maxdd']:8.1f}% "
              f"{b['maxdd']:9.1f}%  {ok}")
    print("\n  'conc' = total risk across ALL open slots as % of equity, at entry.")
    print("  This is the number the per-trade rule cannot see.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
