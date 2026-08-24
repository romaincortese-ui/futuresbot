"""Should entry lateness GATE, not just rank?

    railway run --service Futures-bot python tools/lateness_gate_ab.py

`_entry_lateness` measures how far into the 3h move an entry sits: 0 at the
move's origin, 1 at its extreme. Its docstring calls it "a feature column for the
learning engine, deliberately NOT a gate", and `_wildcard_rank_key` uses it only
to order candidates when several compete for a slot.

Trial 16 gave a reason to revisit that. Five of its first seven entries were at
lateness 1.0 — the exact top of the move — and four of those five stopped out:

    TUT  late=1.0  R=+5.09      ZEN  late=1.0    R=-1.06
    ZEC  late=1.0  R=+0.28      STX  late=1.0    R=-1.05
                                 SPK  late=0.833  R=-1.06

The ranking code already carries a prior: 247 fires over 60 days, both halves
consistent, deep-pullback entries (0.50-0.70) averaging +1.55R against +0.12R at
the extreme. If that holds on 208 days and the current exit stack, then the
sensible thing is to stop TAKING the extreme entries rather than merely
preferring others — and that is an ENTRY lever, which is where the live flat-tape
diagnosis said any improvement has to come from (90% of flat trades never reach
+1R, so exits and sizing cannot reach them).

The obvious cost is supply. The book already runs mostly idle, and a gate that
removes the most common entry shape may simply trade less for the same money.
Both arms therefore share slots, candidates, funding and the live ratchet trail;
only the gate differs.

RESULT, 2026-08-24 -- 73 symbols, 208 days, 1450 candidates.
NO. GATING ON LATENESS DESTROYS THE BOOK. The observation was base-rate neglect.

    band                 n    mean R     net R    win%
    0.40-0.60            4    +0.178     +0.71     25%
    0.60-0.75 deep      20    +0.420     +8.41     70%
    0.75-0.90           43    -0.310    -13.34     37%
    0.90-0.99           40    +0.220     +8.82     52%
    1.00 AT THE TOP   1335    +0.237   +316.83     58%

    gate                    net $   vs live   trades   pos wk   both halves?
    none (LIVE)           +277.81     +0.00      472   17/29    (null)
    <= 0.99                +17.87   -259.94       98   11/29    no
    <= 0.95                 -5.30   -283.11       77    9/29    no
    <= 0.90                -10.10   -287.90       64    9/29    no
    <= 0.85                 +8.28   -269.52       51   11/29    no
    <= 0.75                +32.34   -245.46       22    6/29    no

1335 OF 1450 CANDIDATES ARE AT LATENESS 1.00 -- 92% of them. It is not a rare
warning sign, it is the NORMAL state, because a pullback-resume detector fires by
construction when price resumes to a new extreme. And those entries average
+0.237R at a 58% win rate: perfectly healthy.

So "five of seven trial-16 trades entered at lateness 1.0" was base-rate neglect.
Five of seven is 71%; the base rate is 92%. The live sample was, if anything,
UNDER-represented at the extreme.

Every gate is catastrophic and every one fails both halves. The mildest, <= 0.99,
removes 374 of 472 trades and -$259.94 of the -$277.81 total: 94% of the P&L, to
avoid a band that was never losing money.

The prior in _wildcard_rank_key ("deep-pullback +1.55R vs +0.12R at the extreme",
247 fires, 60 days) is not contradicted so much as put in proportion: the
deep-pullback band really is the best per trade here too (+0.420R on 20 samples),
but it is 1.4% of the supply. Preferring it when candidates COMPETE, which is
what the rank key does, is right. Refusing everything else is not.

THE COST OF NOT TESTING THIS WOULD HAVE BEEN ABOUT $260 over 208 days, on an idea
that had a real mechanism, a prior study behind it, and live evidence that looked
like confirmation.

Read-only. Places nothing.

Env: LG_DAYS (190) LG_POOL (70) LG_SLOTS (3)
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
LIVE_TRAIL = ratchet(3.0, 0.75)


def lateness(closes, i, side):
    """Mirror of FuturesRuntime._entry_lateness, on a raw close list."""
    c = closes[max(0, i - W.ROC_BARS):i + 1]
    if len(c) < 2:
        return None
    lo, hi = min(c), max(c)
    if hi <= lo:
        return None
    cur = c[-1]
    return (cur - lo) / (hi - lo) if side == "LONG" else (hi - cur) / (hi - lo)


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
    days, pool_n = _env("LG_DAYS", 190), int(_env("LG_POOL", 70))
    slots = int(_env("LG_SLOTS", 3))
    eq = rt._last_known_equity() or 173.0
    now = int(time.time())
    min_turn = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    ranked = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wc = [s for a, s in ranked if s not in majors and a >= min_turn][:pool_n]
    syms = sorted(set(wc) | set(TREND_SYMS))
    print(f"equity ${eq:.2f} | {len(syms)} symbols | {slots} slots")

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
    print("generating candidates, tagging each with its entry lateness...")
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
                if sig is not None and sig.side == "LONG":
                    cands.append((ts[i], s, sig, i, bars, "TREND",
                                  lateness(c, i, sig.side)))
        if s in wc:
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or roll[i] < min_turn:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    cands.append((ts[i], s, sig, i, bars, "WILDCARD",
                                  lateness(c, i, sig.side)))
    cands.sort(key=lambda x: x[0])
    print(f"candidates: {len(cands)}")
    if not cands:
        return 0

    def outcome(c_):
        _ts, _s, sig, i, bars, _k, _l = c_
        row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
               "tp": float(sig.tp_price), "side": sig.side}
        return resolve(bars, i, row["entry"], row["sl"], row["tp"],
                       shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                       shadow.cost_r(row), LIVE_TRAIL,
                       float(getattr(sig, "atr_pct", 0.0) or 0.0), now)

    # --- does lateness predict at all, on THIS window? -------------------
    print()
    print("=== OUTCOME BY ENTRY LATENESS (unconstrained, no slot competition) ===")
    print(f"{'band':<16} {'n':>5} {'mean R':>9} {'net R':>9} {'win%':>7}")
    bands = [("0.00-0.40 early", 0.0, 0.40), ("0.40-0.60", 0.40, 0.60),
             ("0.60-0.75 deep", 0.60, 0.75), ("0.75-0.90", 0.75, 0.90),
             ("0.90-0.99", 0.90, 0.99), ("1.00 AT THE TOP", 0.99, 1.01)]
    scored = []
    for c_ in cands:
        lat = c_[6]
        if lat is None:
            continue
        g = outcome(c_)
        if g is None:
            continue
        scored.append((lat, g[0]))
    for lab, lo, hi in bands:
        sub = [r for lat, r in scored if lo <= lat < hi]
        if not sub:
            continue
        w = sum(1 for x in sub if x > 0)
        print(f"{lab:<16} {len(sub):5d} {sum(sub)/len(sub):+9.3f} {sum(sub):+9.2f} "
              f"{100*w/len(sub):6.0f}%")

    # --- and does gating on it earn money on the shared book? ------------
    win_s = 7 * 86400
    n_win = max(1, int(span // 7))
    mid = n_win // 2

    def book(gate, k_lo=0, k_hi=None):
        tot = 0.0
        n = 0
        pos = 0
        for k in range(k_lo, n_win if k_hi is None else k_hi):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            live, per, wt = [], {}, 0.0
            for c_ in cands:
                ts0, sym, sig, i, bars, kind, lat = c_
                if not (lo_t <= ts0 < hi_t):
                    continue
                if gate is not None and lat is not None and lat > gate:
                    continue
                live[:] = [x for x in live if x > ts0]
                per[sym] = [x for x in per.get(sym, []) if x > ts0]
                if per[sym] or len(live) >= slots:
                    continue
                g = outcome(c_)
                if g is None:
                    continue
                live.append(g[1])
                per[sym].append(g[1])
                wt += g[0] * eq * 0.12 * float(sig.sl_margin_pct) / 100.0
                n += 1
            tot += wt
            pos += 1 if wt > 0 else 0
        return tot, n, pos

    print()
    print("=== GATING: skip entries later than X ===")
    print(f"{'gate':<18} {'net $':>10} {'vs live':>9} {'trades':>8} {'pos wk':>8} "
          f"{'recent':>9} {'older':>9}  both halves?")
    base, base_n, base_pos = book(None)
    b_rec = book(None, 0, mid)[0]
    b_old = book(None, mid, n_win)[0]
    print(f"{'none (LIVE)':<18} {base:+10.2f} {0.0:+9.2f} {base_n:8d} "
          f"{base_pos:4d}/{n_win:<3d} {0.0:+9.2f} {0.0:+9.2f}  (null)")
    for gate in (0.99, 0.95, 0.90, 0.85, 0.75):
        tot, n, pos = book(gate)
        rec = book(gate, 0, mid)[0] - b_rec
        old = book(gate, mid, n_win)[0] - b_old
        ok = "YES" if rec > 0 and old > 0 else ("no" if rec < 0 and old < 0 else "one half only")
        print(f"{'<= ' + format(gate, '.2f'):<18} {tot:+10.2f} {tot-base:+9.2f} {n:8d} "
              f"{pos:4d}/{n_win:<3d} {rec:+9.2f} {old:+9.2f}  {ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
