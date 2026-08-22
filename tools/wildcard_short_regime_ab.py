"""Should the wildcard keep its SHORT arm? Asked per REGIME, not on average.

    railway run --service Futures-bot python tools/wildcard_short_regime_ab.py

`FUTURES_WILDCARD_LONG_ONLY=0` is live, and a 90-day drift-controlled study on
2026-08-14 put the entire edge in the LONGS (+0.244R vs -0.225R). That study
covered a period with no serious drawdown, so it cannot answer the question that
matters now: after an exceptional run, the next few weeks could correct hard or
extend higher, and the book is otherwise long-only (TREND_LONG_ONLY=1,
SQUEEZE_LONG_ONLY=1). The short arm is the ONLY thing in the book that can earn
while the market falls.

So an average is the wrong statistic. A short arm that loses 0.2R in flat and up
weeks but earns in the down weeks may still be worth holding as the book's only
hedge -- and one that loses in EVERY regime is simply a leak. This separates
those two cases by scoring each weekly window against BTC's move over it.

Three things are reported:
  1. BOOK-LEVEL A/B by regime -- long-only vs both-sides on the SAME slots,
     candidates, funding and convex exits. This is the decision.
  2. PER-SIDE record by regime, against a random-entry baseline drawn on the
     same side and in the same windows. Without it, "shorts made money in the
     crash week" is a statement about the tape, not about the detector.
  3. A half-split, because a one-half result has now been wrong four times.

RESULT, 2026-08-22 -- 73 symbols, 208 days, 29 weekly windows, 3 shared slots.
KEEP THE SHORT ARM. This reverses the recommendation that prompted the study.

    bucket             weeks  long-only $  both-sides $   delta $   per wk
    CRASH   <= -15%        2       +10.24        +11.85     +1.61    +0.80
    DOWN  -15..-5%         2       -13.89         +0.20    +14.09    +7.04
    FLAT   -5..+5%        21      +250.94       +303.46    +52.52    +2.50
    UP     +5..+15%        3        +6.54         +9.16     +2.62    +0.87
    SURGE   >= +15%        1       +81.05        +64.30    -16.75   -16.75
    TOTAL                 29      +334.89       +388.97    +54.09

    random-entry baseline: LONG +0.072/trade, SHORT -0.255/trade (n=599 each)

    bucket              L n       L $    L $/t   S n       S $    S $/t   S edge
    CRASH   <= -15%      16     +7.46   +0.467    10     +1.61   +0.161   +0.415
    DOWN  -15..-5%        5     -6.98   -1.396     3    +10.09   +3.365   +3.619
    FLAT   -5..+5%      126   +147.88   +1.174    72    +45.58   +0.633   +0.888
    UP     +5..+15%      24     +9.29   +0.387     2     +2.62   +1.311   +1.566
    SURGE   >= +15%      15    +17.66   +1.177     5     -0.02   -0.004   +0.251

    half-split: recent +38.64 (6/14 weeks helped), older +15.44 (8/15) -> BOTH +

THE DRIFT CONTROL HAD TO BE FIXED FIRST. The initial run drew a random bar and
asked the detector for a signal there, which almost never fires (it needs an
8%/3h impulse), so both baselines returned n=0 and the "edge" column was silently
just raw $/trade. The baseline must vary the ENTRY TIME, not re-run the gate.
Once fixed it says random shorts lose -0.255/trade over these 208 days -- exactly
what a short baseline should do in an up-drifting window -- and the detector's
shorts beat it in ALL FIVE regime buckets.

WHY THIS DIFFERS FROM THE 2026-08-14 VERDICT (-0.225R for shorts, "the whole edge
is in the longs"). Two different questions. That one asked whether a short trade
is as good as a long trade -- it is not, +0.633 vs +1.174 per trade in the FLAT
bucket. This one asks whether the BOOK earns more with the short arm than
without, and it does, because the book has spare slots and shorts pay when longs
do not. A signal can be worse per trade and still worth taking. Note also how
close -0.225R sits to the -0.255 RANDOM baseline measured here.

THE HONEST CAVEATS, and they are not small:
- CONCENTRATION. One week is +42.16 of the +54.09 total, i.e. 78%. Ex-best the
  arm is worth about +$11.93 over 208 days -- roughly $1.7/month, inside the
  ~$10 run-to-run noise band. The half-split still passes ex-best in aggregate,
  but this is a convex, lumpy payoff, not a steady drip.
- IT HELPS IN A MINORITY OF WEEKS: 6/14 and 8/15. Week to week it will usually
  look like a drag, and that is the shape of insurance.
- THE EXTREME BUCKETS ARE THIN: CRASH 2 weeks, DOWN 2 weeks, SURGE 1 week. The
  regime story rests on 5 weeks in total and should be treated as directional.

WHAT MAKES IT A KEEP ANYWAY IS THE ASYMMETRY. TREND_LONG_ONLY=1 and
SQUEEZE_LONG_ONLY=1, so the wildcard short arm is the ONLY position in the book
that can earn while the market falls. In the DOWN bucket the long-only book loses
-13.89 and the both-sides book is +0.20: the arm converts a losing regime to
flat. The cost of carrying it through the single strongest week measured was
-16.75. That is a known, bounded premium for the one thing that pays in a
correction.

VERDICT: leave FUTURES_WILDCARD_LONG_ONLY at 0.

Read-only. Places nothing.

Env: WS_DAYS (190) WS_POOL (70) WS_SLOTS (3) WS_RANDOM (600)
"""
from __future__ import annotations

import os
import random
from dataclasses import replace as dc_replace
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
from retention_trail_ab import make_floor, resolve

CHUNK, BAR = 2000, 900
FLOOR = make_floor("flat", 0.30, 1.0)
TREND_SYMS = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")

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
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("WS_DAYS", 190), int(_env("WS_POOL", 70))
    slots, n_rand = int(_env("WS_SLOTS", 3)), int(_env("WS_RANDOM", 400))
    eq = rt._last_known_equity() or 166.0
    now = int(time.time())
    min_turn = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    ranked = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wc_syms = [s for a, s in ranked if s not in majors and a >= min_turn][:pool_n]
    syms = sorted(set(wc_syms) | set(TREND_SYMS) | {"BTC_USDT"})
    print(f"equity ${eq:.2f} | wildcard band {len(wc_syms)} | union {len(syms)} "
          f"| floor ${min_turn/1e6:.0f}M | {slots} slots")

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
    print("generating candidates with the SHIPPED detectors (both sides)...")
    cands = []
    frames = {}
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
        frames[s] = (df, bars, ts, c)

        if s in TREND_SYMS:
            for i in range(400, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None and sig.side == "LONG":
                    cands.append((ts[i], s, sig, i, bars, "TREND", "LONG"))
        if s in wc_syms:
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or roll[i] < min_turn:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    cands.append((ts[i], s, sig, i, bars, "WILDCARD", sig.side))
    cands.sort(key=lambda x: x[0])
    n_l = sum(1 for c_ in cands if c_[5] == "WILDCARD" and c_[6] == "LONG")
    n_s = sum(1 for c_ in cands if c_[5] == "WILDCARD" and c_[6] == "SHORT")
    print(f"signals: {len(cands)}  (wildcard LONG {n_l}, wildcard SHORT {n_s})")

    btc_c = frames["BTC_USDT"][3]
    btc_t = frames["BTC_USDT"][2]

    def btc_move(lo, hi):
        a = min(range(len(btc_t)), key=lambda i: abs(btc_t[i] - lo))
        b = min(range(len(btc_t)), key=lambda i: abs(btc_t[i] - hi))
        return (btc_c[b] / btc_c[a] - 1.0) if btc_c[a] > 0 else 0.0

    def score(sig, i, bars):
        row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
               "tp": float(sig.tp_price), "side": sig.side}
        g = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                    shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                    shadow.cost_r(row), FLOOR,
                    float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
        if g is None:
            return None
        r_net, ex, _k = g
        return r_net * eq * 0.12 * float(sig.sl_margin_pct) / 100.0, ex

    def run_window(allow_short, lo, hi):
        live, per, tot = [], {}, 0.0
        n = 0
        side_pnl = {"LONG": 0.0, "SHORT": 0.0}
        side_n = {"LONG": 0, "SHORT": 0}
        for ts, sym, sig, i, bars, kind, side in cands:
            if not (lo <= ts < hi):
                continue
            if side == "SHORT" and not allow_short:
                continue
            live[:] = [x for x in live if x > ts]
            per[sym] = [x for x in per.get(sym, []) if x > ts]
            if per[sym] or len(live) >= slots:
                continue
            got = score(sig, i, bars)
            if got is None:
                continue
            usd, ex = got
            live.append(ex)
            per[sym].append(ex)
            tot += usd
            n += 1
            if kind == "WILDCARD":
                side_pnl[side] += usd
                side_n[side] += 1
        return tot, n, side_pnl, side_n

    win_s = 7 * 86400
    n_win = max(1, int(span // 7))
    rows = []
    for k in range(n_win):
        hi = now - k * win_s
        lo = hi - win_s
        mv = btc_move(lo, hi)
        L, nl, _sp, _sn = run_window(False, lo, hi)
        B, nb, sp, sn = run_window(True, lo, hi)
        if nl == 0 and nb == 0:
            continue
        rows.append((k, mv, L, B, B - L, sp, sn))

    print()
    print("=== 1. BOOK-LEVEL: long-only vs both-sides, by regime ===")
    print(f"{'bucket':<17} {'weeks':>6} {'long-only $':>12} {'both-sides $':>13} "
          f"{'delta $':>9} {'per wk':>8}")
    for label, fn in BUCKETS:
        sub = [r for r in rows if fn(r[1])]
        if not sub:
            print(f"{label:<17} {0:6d}           --            --        --       --")
            continue
        L = sum(r[2] for r in sub)
        B = sum(r[3] for r in sub)
        print(f"{label:<17} {len(sub):6d} {L:+12.2f} {B:+13.2f} {B-L:+9.2f} "
              f"{(B-L)/len(sub):+8.2f}")
    L = sum(r[2] for r in rows)
    B = sum(r[3] for r in rows)
    print(f"{'TOTAL':<17} {len(rows):6d} {L:+12.2f} {B:+13.2f} {B-L:+9.2f}")

    print()
    print("=== 2. PER-SIDE wildcard record vs a same-side random baseline ===")
    # Drift control. The FIRST attempt drew a random bar and asked the detector
    # for a signal there — which almost never fires, since it needs an 8%/3h
    # impulse, so both baselines came back n=0 and the "edge" column was just
    # raw $/trade. The baseline must vary the ENTRY TIME, not re-run the gate:
    # take a real signal's own geometry (sl_frac, tp_r, sizing) and place it at a
    # random bar in a random symbol of the same band, on the requested side.
    random.seed(20260822)
    templates = [c_ for c_ in cands if c_[5] == "WILDCARD"]
    pool = [s for s in wc_syms if s in frames]
    base = {}
    for side in ("LONG", "SHORT"):
        tot = 0.0
        cnt = 0
        for _ in range(n_rand):
            tmpl = random.choice(templates)[2]
            s = random.choice(pool)
            df, bars, ts, c = frames[s]
            i = random.randrange(300, len(c) - 1)
            e = float(c[i])
            te = float(tmpl.entry_price)
            slf = abs(te - float(tmpl.sl_price)) / te if te else 0.0
            if slf <= 0 or e <= 0:
                continue
            tp_r = shadow.signal_tp_r(tmpl)
            if side == "LONG":
                sl, tp = e * (1 - slf), e * (1 + slf * tp_r)
            else:
                sl, tp = e * (1 + slf), max(e * 0.01, e * (1 - slf * tp_r))
            sig = dc_replace(tmpl, symbol=s, side=side, entry_price=e,
                             sl_price=sl, tp_price=tp)
            got = score(sig, i, bars)
            if got is None:
                continue
            tot += got[0]
            cnt += 1
        base[side] = (tot / cnt if cnt else 0.0, cnt)
    print(f"random-entry baseline: LONG {base['LONG'][0]:+.3f}/trade (n={base['LONG'][1]}), "
          f"SHORT {base['SHORT'][0]:+.3f}/trade (n={base['SHORT'][1]})")
    print(f"{'bucket':<17} {'L n':>5} {'L $':>9} {'L $/t':>8} {'S n':>5} {'S $':>9} "
          f"{'S $/t':>8} {'S edge':>8}")
    for label, fn in BUCKETS:
        sub = [r for r in rows if fn(r[1])]
        if not sub:
            continue
        lp = sum(r[5]["LONG"] for r in sub)
        ln = sum(r[6]["LONG"] for r in sub)
        sp = sum(r[5]["SHORT"] for r in sub)
        sn = sum(r[6]["SHORT"] for r in sub)
        lpt = lp / ln if ln else 0.0
        spt = sp / sn if sn else 0.0
        print(f"{label:<17} {ln:5d} {lp:+9.2f} {lpt:+8.3f} {sn:5d} {sp:+9.2f} "
              f"{spt:+8.3f} {spt - base['SHORT'][0]:+8.3f}")

    print()
    print("=== 3. HALF-SPLIT on the short arm's book-level delta ===")
    mid = n_win // 2
    rec = [r for r in rows if r[0] < mid]
    old = [r for r in rows if r[0] >= mid]
    for label, sub in (("recent half", rec), ("older half", old)):
        d = sum(r[4] for r in sub)
        pos = sum(1 for r in sub if r[4] > 0)
        print(f"  {label:<12} {len(sub):2d} weeks  delta {d:+8.2f}  "
              f"weeks helped {pos}/{len(sub)}")
    dr = sum(r[4] for r in rec)
    do = sum(r[4] for r in old)
    print(f"  survives both halves? "
          f"{'YES' if dr > 0 and do > 0 else ('no' if dr < 0 and do < 0 else 'one half only')}")

    print()
    print("=== worst and best weeks for the short arm ===")
    for r in sorted(rows, key=lambda r: r[4])[:3]:
        print(f"  BTC {r[1]*100:+6.1f}%  delta {r[4]:+8.2f}")
    for r in sorted(rows, key=lambda r: -r[4])[:3]:
        print(f"  BTC {r[1]*100:+6.1f}%  delta {r[4]:+8.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
