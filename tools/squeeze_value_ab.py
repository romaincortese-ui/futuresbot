"""Does the SQUEEZE sleeve earn its slot? It has been off since 2026-06-26.

    railway run --service Futures-bot python tools/squeeze_value_ab.py

Live record: n=13, +$1.17 -- too few trades to conclude anything, and drawn from
a universe the sleeve was never designed for, because `_maybe_scan_squeeze` was
the one scan that never applied the crypto filter and so held XAU_USDT and
USOIL_USDT (fixed 2026-08-21, tests/test_squeeze_universe.py).

The question is not "is the squeeze profitable in isolation" -- that is the
question that flatters every sleeve. It shares the wildcard's convex slots, so
the only thing that matters is whether adding it to the CURRENT book earns more
than the wildcard/trend signals it displaces. Both arms therefore run the same
slots, the same funding, the same convex exits and the same point-in-time
turnover floor; only the presence of squeeze candidates differs.

Scored over ~208 days in weekly windows, with the positive-week count and a
half-split, because a 60-day pilot has now twice produced a result that did not
survive the longer window.

RESULT, 2026-08-22 -- 92 symbols, 208 days, 29 weekly windows, 3 shared slots.
KEEP IT OFF.

    book                        net $   pos wk  fills by sleeve
    wildcard+trend (LIVE)     +337.71   20/29   TREND 182  WILDCARD 247
    + squeeze                 +355.63   19/29   SQUEEZE 101  TREND 183  WILDCARD 239

    squeeze is worth +$17.92 over 208 days (+$2.58/month)
      recent half:  +34.35
      older  half:  -16.42
      survives both halves? ONE HALF ONLY

Three things, and they all point the same way.

1. IT FAILS THE HALF-SPLIT. All of the gain and more is in the recent half; the
   older half is NEGATIVE. That is the exact shape that has now killed BEAT in
   the trend universe scan, the tiered retention trail, and the $0.5M turnover
   floor. There is a tempting mechanism available -- the sleeve is long-biased
   and convex, so it "should" do better in the trending market of the recent
   half -- but that story was also available for the tiered trail and it did not
   hold up.

2. THE SLOTS WERE NOT THE PROBLEM, SO THE TRADES ARE. 101 squeeze fills
   displaced only 8 wildcard fills (247 -> 239), because the book has spare
   capacity. So this is very nearly a clean ADD of 101 trades -- and 101 trades
   bought +$17.92, about +$0.18 each. Against a ~$10 run-to-run noise band on
   this window, that is not distinguishable from zero.

3. IT MAKES THE BOOK LESS CONSISTENT, NOT MORE: 20/29 positive weeks becomes
   19/29. A sleeve that adds a third more trades and reduces weekly consistency
   is adding variance, not edge.

This is the FIRST CLEAN READ of the sleeve. Its live n=13/+$1.17 came from a
universe that included XAU_USDT and USOIL_USDT, because the squeeze scan never
applied the crypto filter. This study runs the fixed universe.

Read-only. Places nothing.

Env: SQ_DAYS (190) SQ_POOL (70) SQ_SLOTS (3)
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
from futuresbot.squeeze import detect_squeeze_signal
from futuresbot.trend import detect_trend_signal
from retention_trail_ab import make_floor, resolve

CHUNK, BAR = 2000, 900
FLOOR = make_floor("flat", 0.30, 1.0)
TREND_SYMS = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")


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
    days, pool_n, slots = _env("SQ_DAYS", 190), int(_env("SQ_POOL", 70)), int(_env("SQ_SLOTS", 3))
    eq = rt._last_known_equity() or 159.0
    now = int(time.time())
    min_turn = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    crypto = [t for t in tk if str(t.get("symbol") or "").endswith("_USDT")
              and rt._is_tradeable_crypto(str(t.get("symbol") or ""))]
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    ranked = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in crypto),
                    reverse=True)
    # The squeeze scans the TOP names by turnover and does NOT exclude majors.
    sq_syms = [s for _a, s in ranked[:int(rt._env_float("FUTURES_SQUEEZE_MAX_SCAN", 30.0))]]
    wc_syms = [s for a, s in ranked if s not in majors and a >= min_turn][:pool_n]
    syms = sorted(set(sq_syms) | set(wc_syms) | set(TREND_SYMS))
    print(f"equity ${eq:.2f} | squeeze scans {len(sq_syms)} | wildcard {len(wc_syms)} "
          f"| union {len(syms)}")

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
        raw = [c[i] * v[i] * cs for i in range(len(c))]
        roll, acc = [0.0] * len(c), 0.0
        for i, x in enumerate(raw):
            acc += x
            if i >= 96:
                acc -= raw[i - 96]
            roll[i] = acc
        bars = list(zip([float(x.timestamp()) for x in df.index],
                        [float(x) for x in df["high"]],
                        [float(x) for x in df["low"]], c))
        ts = [b[0] for b in bars]

        if s in TREND_SYMS:
            for i in range(400, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None and sig.side == "LONG":
                    cands.append((ts[i], s, sig, i, bars, "TREND"))
        if s in wc_syms:
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or roll[i] < min_turn:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    cands.append((ts[i], s, sig, i, bars, "WILDCARD"))
        if s in sq_syms:
            for i in range(250, len(c)):
                if roll[i] < min_turn:
                    continue
                sig = detect_squeeze_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    cands.append((ts[i], s, sig, i, bars, "SQUEEZE"))
    cands.sort(key=lambda x: x[0])
    by = {}
    for c_ in cands:
        by[c_[5]] = by.get(c_[5], 0) + 1
    print(f"signals: {len(cands)}  " + "  ".join(f"{k} {v}" for k, v in sorted(by.items())))

    win_s = 7 * 86400
    n_win = max(1, int(span // 7))

    def sim(with_squeeze, k_lo=0, k_hi=None):
        tot = 0.0
        taken = {}
        pos = 0
        for k in range(k_lo, n_win if k_hi is None else k_hi):
            hi = now - k * win_s
            lo = hi - win_s
            live, per, wt = [], {}, 0.0
            for ts, sym, sig, i, bars, kind in cands:
                if not (lo <= ts < hi):
                    continue
                if kind == "SQUEEZE" and not with_squeeze:
                    continue
                live[:] = [x for x in live if x > ts]
                per[sym] = [x for x in per.get(sym, []) if x > ts]
                if per[sym] or len(live) >= slots:
                    continue
                row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
                       "tp": float(sig.tp_price), "side": sig.side}
                g = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                            shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                            shadow.cost_r(row), FLOOR,
                            float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if g is None:
                    continue
                r_net, ex, _k = g
                live.append(ex)
                per[sym].append(ex)
                wt += r_net * eq * 0.12 * float(sig.sl_margin_pct) / 100.0
                taken[kind] = taken.get(kind, 0) + 1
            tot += wt
            pos += 1 if wt > 0 else 0
        return tot, taken, pos

    mid = n_win // 2
    print()
    print(f"{'book':<22} {'net $':>10} {'pos wk':>8}  fills by sleeve")
    off, t_off, p_off = sim(False)
    on, t_on, p_on = sim(True)
    for label, tot, tk_, pw in (("wildcard+trend (LIVE)", off, t_off, p_off),
                                ("+ squeeze", on, t_on, p_on)):
        mix = "  ".join(f"{k} {v}" for k, v in sorted(tk_.items()))
        print(f"{label:<22} {tot:+10.2f} {pw:4d}/{n_win:<3d}  {mix}")
    print()
    print(f"squeeze is worth {on - off:+.2f} over {span:.0f} days "
          f"({(on - off) / (span / 30.0):+.2f}/month)")

    r_off = sim(False, 0, mid)[0]
    r_on = sim(True, 0, mid)[0]
    o_off = sim(False, mid, n_win)[0]
    o_on = sim(True, mid, n_win)[0]
    print(f"  recent half: {r_on - r_off:+8.2f}")
    print(f"  older  half: {o_on - o_off:+8.2f}")
    ok = "YES" if (r_on - r_off > 0 and o_on - o_off > 0) else (
        "no" if (r_on - r_off < 0 and o_on - o_off < 0) else "one half only")
    print(f"  survives both halves? {ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
