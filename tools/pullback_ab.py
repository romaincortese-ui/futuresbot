"""A/B the pullback-resume gate on the LIVE exit stack, over many weeks.

    railway run --service Futures-bot python tools/pullback_ab.py

`wildcard.py` says of FUTURES_WILDCARD_REQUIRE_PULLBACK: "the single largest
filter in the detector, rejecting ~76% of all trigger bars... It has never been
measured for value." This measures it, against the bot that actually exists:

  - the SHIPPED detector, toggled only by its own flag;
  - the LIVE convex exits (-1R stop / own target / 0.30xpeak retention / 24h
    clock), via shadow_ledger.resolve_outcome(convex=True);
  - live sizing, and funding charged on the settlements each hold crossed;
  - the REAL slot cap. Turning the filter off multiplies signals 3-5x, and an
    arm allowed unlimited concurrent positions is measuring a bot that does not
    exist. With 2 slots most of those extra signals are never taken.

POINT-IN-TIME UNIVERSE. The first version of this study picked its symbols from
TODAY's ticker and then replayed weeks backwards, which selects on liquidity the
bot could not have known and quietly drops every symbol that was liquid then and
is not now. Here the $3M turnover floor is re-tested at every bar from the
symbol's own rolling 24h volume, so a name enters and leaves the band exactly as
it did live. Majors are still today's set: reconstructing that ranking
historically needs the deflator across the whole book per day, which this does
not do — the one look-ahead left, and it is stated rather than hidden.

RESULT, 2026-08-16/17 — 97 symbols, 62.5d of Min15, 8 disjoint 7d windows,
point-in-time floor. delta = OFF - ON, so NEGATIVE means the gate earned its keep.

    slots=1   OFF-ON  +8.45   mean +1.06/wk  t +0.17   OFF better 3/8
    slots=2   OFF-ON -69.42   mean -8.68/wk  t -1.33   OFF better 3/8   <- live
    slots=3   OFF-ON -16.95   mean -2.12/wk  t -0.42   OFF better 5/8

At the live slot count the gate looks worth ~$8.68/wk, and win rate favours ON
in 7 of 8 windows. That lean does NOT survive changing an unrelated parameter by
one: the sign flips at 1 slot and the magnitude collapses at 3, with no monotonic
story. An effect that only appears at one slot count is an unstable estimate, not
a property of the filter. VERDICT: still unproven. Do not tune it on this.

Read-only. Places nothing.

Env: AB_SPAN_D (56) AB_WINDOW_D (7) AB_SLOTS (2) AB_MIN_TURNOVER (3e6)
     AB_POOL_TURNOVER (1e6) AB_MAX_SYMS (120)
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

    def run_arm(require_pullback: bool, lo_ts: float, hi_ts: float, cands):
        open_until, live = {}, []
        taken = wins = blocked_slot = blocked_sym = 0
        net = 0.0
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
            taken += 1
            net += usd
            wins += 1 if usd > 0 else 0
            exit_ts = float(done.get("resolved_ts") or ts)
            open_until[s] = exit_ts
            live.append(exit_ts)
        return {"taken": taken, "net": round(net, 2),
                "win": round(100 * wins / taken, 1) if taken else 0.0,
                "blocked_slot": blocked_slot, "blocked_sym": blocked_sym}

    print("\ngenerating candidates (both arms, whole span)...")
    cand_on = candidates(True)
    cand_off = candidates(False)
    print(f"signals over {span_d:.0f}d: ON {len(cand_on)} | OFF {len(cand_off)} "
          f"(x{len(cand_off)/max(1,len(cand_on)):.1f})")

    n_win = int(span_d // window_d)
    print(f"\n{'window':>14} {'ON $':>9} {'OFF $':>9} {'delta':>9}  "
          f"{'ON n':>5} {'OFF n':>6} {'ON w%':>6} {'OFF w%':>7}")
    deltas, tot_on, tot_off = [], 0.0, 0.0
    for k in range(n_win):
        hi = now_t - k * window_d * 86400
        lo = hi - window_d * 86400
        a = run_arm(True, lo, hi, cand_on)
        b = run_arm(False, lo, hi, cand_off)
        d = b["net"] - a["net"]
        deltas.append(d)
        tot_on += a["net"]
        tot_off += b["net"]
        print(f"{'-' + str(int(k*window_d)) + 'd..-' + str(int((k+1)*window_d)) + 'd':>14} "
              f"{a['net']:+9.2f} {b['net']:+9.2f} {d:+9.2f}  "
              f"{a['taken']:5d} {b['taken']:6d} {a['win']:6.1f} {b['win']:7.1f}")

    n = len(deltas)
    mean = sum(deltas) / n if n else 0.0
    var = sum((x - mean) ** 2 for x in deltas) / (n - 1) if n > 1 else 0.0
    sd = var ** 0.5
    se = sd / (n ** 0.5) if n else 0.0
    pos = sum(1 for x in deltas if x > 0)
    print("\n" + "=" * 74)
    print(f"windows {n} | ON total {tot_on:+.2f} | OFF total {tot_off:+.2f} | "
          f"OFF-ON {tot_off-tot_on:+.2f}")
    print(f"delta per window: mean {mean:+.2f} sd {sd:.2f} se {se:.2f} "
          f"t {(mean/se if se else 0):+.2f} | OFF better in {pos}/{n}")
    os.environ["FUTURES_WILDCARD_REQUIRE_PULLBACK"] = "1"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
