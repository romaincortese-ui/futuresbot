"""A/B the COLD-STREAK SIZE THROTTLE on the live exit stack.

    railway run --service Futures-bot python tools/streak_throttle_ab.py

FUTURES_CONVEX_STREAK_THROTTLE_ENABLED halves size per loss past
FUTURES_CONVEX_STREAK_N (2), floored at FUTURES_CONVEX_STREAK_FLOOR (0.25),
restoring fully on a win. Live it has fired on only 3 of the 13 trades that
carry the column, so the live ledger cannot answer whether it pays.

A size throttle is easier to measure than an entry gate: it never changes
WHICH trades are taken, so both arms replay an identical sequence and the only
difference is the dollar weight on each. It pays if and only if losses CLUSTER.
If they do not it is a pure EV reducer, shrinking winners in proportion to how
often it fires.

Everything else matches the live sleeve: shipped detector, convex exits, the
2-slot cap, funding, and the point-in-time turnover floor.

Read-only. Places nothing.

RESULT, 2026-08-22 -- run at two window lengths, both on the live exit stack.
DIRECTIONALLY "REMOVE IT", BUT NOT AT A SIGNIFICANCE WORTH ACTING ON MID-TRIAL.

    span    windows   THROTTLED      FLAT   FLAT-THROTTLED   t    FLAT better in
     56d          8     +101.60   +113.25          +11.65  0.58        5/8  (63%)
    190d         27     +205.74   +223.67          +17.93  0.92      17/27  (63%)

Removing the throttle is worth about +$2.8/month on the longer window, the sign
is the same at both lengths, and the proportion of windows favouring FLAT is
identical (63%). But t=0.92 is not significance, and this repo has been burned
repeatedly by acting on results of exactly this size.

THE STRUCTURAL ARGUMENT IS STRONGER THAN THE STATISTICAL ONE, and it is the same
one that condemned the regime scaler's haircut: every throttle multiplier is
<= 1.0, so it can only ever SHRINK a positive-expectancy book. It pays if and
only if losses CLUSTER — that is its entire premise — and the measurement finds
no clustering to exploit. Unlike the regime scaler, which at least carries a real
predictive tilt (efficiency buckets +0.019R at the bottom against +0.401R at the
top), the throttle has no measured signal underneath it at all.

NOT CHANGED, for a reason that is about method rather than the number: trial 16
is testing renormalised sizing. Changing a second size rule inside it would
confound exactly the thing the trial exists to measure. This is a candidate for
the START of trial 17, where it can be the change under test rather than noise
in someone else's.

Read-only. Places nothing.

Env: AB_SPAN_D (56) AB_WINDOW_D (7) AB_SLOTS (2) AB_MAX_SYMS (120)
     AB_STREAK_N (2) AB_STREAK_FLOOR (0.25)
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from futuresbot import shadow_ledger as shadow
from futuresbot import wildcard as W
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime

CHUNK_BARS = 2000            # MEXC's hard cap on a Min15 request (~20.8d)
BAR_S = 900


def _env(name, default):
    try:
        return float(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return float(default)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars over the window, NOT account P&L.")
    print("    Arms marked 'live cfg' are the live SETTINGS, not live results.")
    print("    The real account is DOWN lifetime; /report has the true figure. ***")
    cfg = FuturesConfig.from_env()
    client = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, client)

    span_d = _env("AB_SPAN_D", 56)
    window_d = _env("AB_WINDOW_D", 7)
    slots = int(_env("AB_SLOTS", 2))
    min_turn = _env("AB_MIN_TURNOVER", W.wildcard_min_turnover_usdt())
    pool_turn = _env("AB_POOL_TURNOVER", 1e6)
    max_syms = int(_env("AB_MAX_SYMS", 120))
    equity = rt._last_known_equity() or 140.0
    now_t = int(time.time())
    start_t = now_t - int(span_d * 86400)

    tickers = client.get_all_tickers() or []
    majors = rt._major_symbols(
        tickers, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    pool = []
    for t in tickers:
        s = str(t.get("symbol") or "")
        if not s.endswith("_USDT") or not rt._is_tradeable_crypto(s) or s in majors:
            continue
        amt = float(t.get("amount24") or 0.0)
        if amt >= pool_turn:
            pool.append((amt, s))
    pool.sort(reverse=True)
    syms = [s for _a, s in pool[:max_syms]]
    amt_today = {s: a for a, s in pool}
    print(f"equity ${equity:.2f} | pool {len(pool)} (>= ${pool_turn/1e6:.1f}M today, "
          f"non-major) -> studying {len(syms)} | span {span_d:.0f}d | "
          f"window {window_d:.0f}d | {slots} slots | live floor ${min_turn/1e6:.1f}M "
          f"applied POINT-IN-TIME")

    n_chunks = int((now_t - start_t) // (CHUNK_BARS * BAR_S)) + 1

    def fetch(sym):
        parts = []
        end = now_t
        for _ in range(n_chunks):
            try:
                df = client.get_klines(sym, interval="Min15",
                                       start=end - CHUNK_BARS * BAR_S, end=end)
            except Exception:
                break
            if df is None or not len(df):
                break
            parts.append(df)
            end = int(df.index[0].timestamp()) - BAR_S
            if end <= start_t:
                break
        if not parts:
            return sym, None
        out = pd.concat(parts[::-1])
        out = out[~out.index.duplicated(keep="first")].sort_index()
        return sym, out

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as pool_ex:
        frames = dict(pool_ex.map(fetch, syms))
    frames = {s: f for s, f in frames.items() if f is not None and len(f) >= 300}
    got = [len(f) for f in frames.values()]
    print(f"frames: {len(frames)} symbols, median {sorted(got)[len(got)//2] if got else 0} bars "
          f"({(sorted(got)[len(got)//2] if got else 0)*BAR_S/86400:.1f}d), "
          f"fetched in {time.time()-t0:.0f}s")

    funding = {s: rt._funding_settlements(s) for s in frames}

    # --- per-symbol precompute: bars, closes, and POINT-IN-TIME turnover -----
    cache = {}
    for s, df in frames.items():
        h = [float(x) for x in df["high"]]
        lo = [float(x) for x in df["low"]]
        c = [float(x) for x in df["close"]]
        v = [float(x) for x in df["volume"]]
        ts = [float(x.timestamp()) for x in df.index]
        # Kline volume is in contracts; amount24 is USDT. Calibrate the scale on
        # the trailing 24h so the historical floor is in the same units as the
        # live one, without a contract-detail call per symbol.
        raw = [c[i] * v[i] for i in range(len(c))]
        tail = sum(raw[-96:])
        scale = (amt_today.get(s, 0.0) / tail) if tail > 0 else 0.0
        roll, acc = [0.0] * len(c), 0.0
        for i, x in enumerate(raw):
            acc += x
            if i >= 96:
                acc -= raw[i - 96]
            roll[i] = acc * scale
        cache[s] = {"bars": [(ts[i], h[i], lo[i], c[i]) for i in range(len(c))],
                    "closes": c, "turn": roll, "df": df}

    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))

    def candidates(require_pullback: bool):
        os.environ["FUTURES_WILDCARD_REQUIRE_PULLBACK"] = "1" if require_pullback else "0"
        out = []
        for s, d in cache.items():
            closes, turn, bars, df = d["closes"], d["turn"], d["bars"], d["df"]
            for i in range(250, len(closes) + 1):
                j = i - 1
                if j <= W.ROC_BARS or turn[j] < min_turn:   # the floor, as of THAT bar
                    continue
                if abs(closes[j] / closes[j - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i], s)
                if sig is not None:
                    out.append((bars[j][0], s, sig))
        out.sort(key=lambda x: x[0])
        return out

    streak_n = int(_env('AB_STREAK_N', 2))
    streak_floor = _env('AB_STREAK_FLOOR', 0.25)

    def run_arm(throttle: bool, lo_ts: float, hi_ts: float, cands):
        open_until, live = {}, []
        taken = wins = blocked_slot = blocked_sym = throttled = 0
        net = 0.0
        loss_streak = 0
        for ts, s, sig in cands:
            if not (lo_ts <= ts < hi_ts):
                continue
            live[:] = [x for x in live if x > ts]
            if open_until.get(s, 0.0) > ts:
                blocked_sym += 1
                continue
            if len(live) >= slots:
                blocked_slot += 1
                continue
            row = shadow.candidate_row(sig, sleeve="WILDCARD", reject_reason="ab")
            row["ts"] = ts
            done = shadow.resolve_outcome(row, cache[s]["bars"], hi_ts,
                                          horizon_s=shadow.CONVEX_HORIZON_S, convex=True)
            if done is None:
                continue
            usd = shadow.net_usd(done, equity,
                                 funding_r=shadow.funding_cost_r(done, funding.get(s) or []))
            if usd is None:
                continue
            # Weight from the streak SO FAR: chosen before the outcome is
            # known, exactly as the live sizing path does it.
            mult = 1.0
            if throttle and loss_streak >= streak_n:
                mult = max(streak_floor, 0.5 ** (loss_streak - streak_n + 1))
                throttled += 1
            taken += 1
            net += usd * mult
            wins += 1 if usd > 0 else 0
            loss_streak = 0 if usd > 0 else loss_streak + 1
            exit_ts = float(done.get("resolved_ts") or ts)
            open_until[s] = exit_ts
            live.append(exit_ts)
        return {"taken": taken, "net": round(net, 2), "throttled": throttled,
                "win": round(100 * wins / taken, 1) if taken else 0.0,
                "blocked_slot": blocked_slot, "blocked_sym": blocked_sym}

    print("")
    print("generating candidates (live detector settings)...")
    cands = candidates(True)
    print("signals over %.0fd: %d | throttle N=%d floor=%.2f" % (
        span_d, len(cands), streak_n, streak_floor))

    n_win = int(span_d // window_d)
    print("")
    print("%14s %9s %9s %9s  %5s %4s %6s" % (
        "window", "THROT $", "FLAT $", "delta", "n", "thr", "win%"))
    deltas, tot_on, tot_off = [], 0.0, 0.0
    for k in range(n_win):
        hi = now_t - k * window_d * 86400
        lo = hi - window_d * 86400
        a = run_arm(True, lo, hi, cands)     # throttle ON (live)
        b = run_arm(False, lo, hi, cands)    # flat sizing
        d = b["net"] - a["net"]
        deltas.append(d)
        tot_on += a["net"]
        tot_off += b["net"]
        print("%14s %+9.2f %+9.2f %+9.2f  %5d %4d %6.1f" % (
            "-%dd..-%dd" % (int(k * window_d), int((k + 1) * window_d)),
            a['net'], b['net'], d, a['taken'], a['throttled'], a['win']))

    n = len(deltas)
    mean = sum(deltas) / n if n else 0.0
    var = sum((x - mean) ** 2 for x in deltas) / (n - 1) if n > 1 else 0.0
    sd = var ** 0.5
    se = sd / (n ** 0.5) if n else 0.0
    pos = sum(1 for x in deltas if x > 0)
    print("\n" + "=" * 74)
    print(f"windows {n} | THROTTLED {tot_on:+.2f} | FLAT {tot_off:+.2f} | "
          f"FLAT-THROTTLED {tot_off-tot_on:+.2f}")
    print(f"delta per window: mean {mean:+.2f} sd {sd:.2f} se {se:.2f} "
          f"t {(mean/se if se else 0):+.2f} | FLAT better in {pos}/{n}")
    os.environ["FUTURES_WILDCARD_REQUIRE_PULLBACK"] = "1"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
