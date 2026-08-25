"""Everything this session REJECTED, rerun on the corrected pool.

    railway run --service Futures-bot python tools/pit_rejections.py

Three settings that were ACCEPTED on the 30%-coverage pool have now reversed on
the point-in-time rebuild: the turnover floor, the retention ratchet and
renormalised sizing. A broken instrument does not only manufacture false
positives — it manufactures false negatives too, and those are invisible because
nothing prompts you to look at them again.

So this reruns the five rejections, on the same point-in-time construction:

  6.  ENTRY LATENESS as a gate       (rejected at -$260)
  7.  PRE-IMPULSE TURNOVER as a gate (rejected: no monotonic signal)
  8.  THE SQUEEZE SLEEVE             (rejected: +$2.58/mo, failed half-split)
  9.  SHARPER REGIME-SCALER TILTS    (rejected: all failed compounded halves)
  10. TREND SHORTS                   (rejected: -$61.51 unconditional)

A rejection that flips is money currently being left on the table. A rejection
that holds is one fewer thing to relitigate. Either answer is worth the compute.

All arms share candidates, slots, funding, costs and the live trail; only the
rule under test differs. Every section carries a half-split.

Read-only. Places nothing.

Env: PJ_DAYS (190) PJ_POOL (150) PJ_MIN_TODAY (300000)

RESULTS 2026-08-25 (190d req -> 208d, 171 symbols, pool 150, $2M/bar floor).
LIVE BASELINE +425.94 over 743 trades, 19/29 positive weeks. 2961 candidates.

ONE of five flips. That is the healthy outcome: had four or five reversed, the
corrected pool would be doing something systematically different rather than
removing a bias, and none of it would be trustworthy.

  6. LATENESS GATE       HOLDS, hard. All three thresholds cost $195-218 and
                         lose in BOTH halves. The original -$260 reproduces in
                         sign and rough size. Stop proposing this.
  7. PRE-IMPULSE FLOOR   HOLDS. $2M lands +0.38 -- indistinguishable from zero
                         against a ~$10 noise floor. $3M costs $77.82.
  8. SQUEEZE SLEEVE      HOLDS. -$30.22, positive recent half only (+4.35 /
                         -34.57). The clean rejection I hoped for: the squeeze
                         universe is the top-30 by turnover, the part of the
                         market the pool bug touched LEAST, so it had the least
                         room to move -- and it didn't.
  9. SHARPER TILTS       HOLD. Every tilt is inside noise of no-scaler
                         (1457.08) and none beats it in both halves. Note the
                         drawdown column: no-scaler 25.4% vs live 32.9%. That
                         is independent support for the queued trial-17 item
                         "scaler off", which was justified on the same grounds.
 10. TREND SHORTS        **FLIPS, gated at BTC 7d <= -12%.**
                         unconditional      -59.00  (fails both halves)
                         gated at -5%       -65.40  (fails both halves)
                         gated at -12%     **+50.79, +26.63 / +24.17, 20/29 wk**
                         Both halves positive, best positive-week count in the
                         whole run.

WHY THE -12% ROW IS STRONGER THAN A BEST-OF-THREE PICK: this exact rule --
trend shorts behind a BTC trailing-7d <= -12% gate -- was PRE-REGISTERED in
docs/DECISION_RULE.md on 2026-08-22, before this pool existed and before this
tool was written. Selecting the best of three thresholds carries multiplicity;
confirming a threshold written down three days earlier does not.

CAVEATS, stated so nobody quotes the $50.79 as income:
  - Replay dollars. Levels are inflated by shared bias (baseline reads
    $62/mo against an account that has never done that); only the RELATIVE
    +11.9% vs baseline is meaningful.
  - The event count behind the -12% trigger is NOT in this output. A rule that
    fires in a handful of clustered days can post a clean half-split on very
    few independent events. COUNT THE TRIGGERS before sizing anything.
  - It adds ~26 net trades over baseline (769 vs 743) -- this is tail
    insurance, not a growth engine.

WHAT IT IS ACTUALLY FOR: the bot has ZERO live closes in DOWN or CRASH regimes,
ever. Its whole record is FLAT and SURGE. This gate only acts in the regime
with no live record at all, which is the argument for it and equally the reason
its backtest cannot be trusted as a forecast.

DO NOT DEPLOY MID-TRIAL. Trial 16 is open. Queue for trial 17.

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
from futuresbot.squeeze import detect_squeeze_signal
from futuresbot.trend import detect_trend_signal
from pit_ratchet import ratchet
from retention_trail_ab import resolve

CHUNK, BAR = 2000, 900
TREND_SYMS = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
LIVE_TRAIL = ratchet(3.0, 0.75)
BASE_RISK = 0.0187


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def lateness(closes, i, side):
    c = closes[max(0, i - W.ROC_BARS):i + 1]
    if len(c) < 2:
        return None
    lo, hi = min(c), max(c)
    if hi <= lo:
        return None
    return (c[-1] - lo) / (hi - lo) if side == "LONG" else (hi - c[-1]) / (hi - lo)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars over the window, NOT account P&L.")
    print("    The real account is DOWN lifetime; /report has the true figure. ***")
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 190), int(_env("PJ_POOL", 150))
    min_today = _env("PJ_MIN_TODAY", 3e5)
    eq0 = rt._last_known_equity() or 172.0
    now = int(time.time())
    floor = W.wildcard_min_turnover_usdt()
    eff_win = max(4, int(rt._env_float("FUTURES_REGIME_EFF_WINDOW", 24.0)))
    LAG = 24                                   # 6h in 15m bars, pre-impulse

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wide = [(a, s) for a, s in crypto if s not in majors and a >= min_today]
    cand_syms = [s for _a, s in wide[:pool_n]]
    sq_syms = [s for _a, s in crypto[:int(rt._env_float("FUTURES_SQUEEZE_MAX_SCAN", 30.0))]]
    syms = sorted(set(cand_syms) | set(TREND_SYMS) | set(sq_syms) | {"BTC_USDT"})
    print(f"equity ${eq0:.2f} | wildcard {len(cand_syms)} | squeeze {len(sq_syms)} "
          f"| floor ${floor/1e6:.0f}M per bar")

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

    print("fetching...")
    with ThreadPoolExecutor(max_workers=6) as p:
        frames = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 300}
    span = len(next(iter(frames.values()))) * BAR / 86400
    print(f"frames: {len(frames)} symbols, {span:.0f}d")

    btc = frames.get("BTC_USDT")
    btc_t = [float(x.timestamp()) for x in btc.index]
    btc_c = [float(x) for x in btc["close"]]

    def btc_trail(ts):
        k = min(range(len(btc_t)), key=lambda i: abs(btc_t[i] - ts))
        j = max(0, k - 672)
        return (btc_c[k] / btc_c[j] - 1.0) if btc_c[j] > 0 else 0.0

    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))
    print("generating candidates...")
    C = []          # dicts, so sections can filter on whatever they need
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
        ts = [b[0] for b in bars]

        def add(sig, i, kind):
            C.append({"ts": ts[i], "sym": s, "sig": sig, "i": i, "bars": bars,
                      "kind": kind, "eff": trend_efficiency(c[:i + 1], eff_win),
                      "late": lateness(c, i, sig.side),
                      "base_turn": roll[max(0, i - LAG)], "turn": roll[i]})

        if s in TREND_SYMS:
            for i in range(400, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    add(sig, i, "TREND")               # BOTH sides, for #10
        if s in cand_syms:
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or roll[i] < floor:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    add(sig, i, "WILDCARD")
        if s in sq_syms:
            for i in range(250, len(c)):
                if roll[i] < floor:
                    continue
                sig = detect_squeeze_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    add(sig, i, "SQUEEZE")
    C.sort(key=lambda x: x["ts"])
    kinds = {}
    for x in C:
        kinds[x["kind"]] = kinds.get(x["kind"], 0) + 1
    print(f"candidates: {len(C)}  {kinds}")

    res = {}
    for idx, x in enumerate(C):
        sig = x["sig"]
        row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
               "tp": float(sig.tp_price), "side": sig.side}
        g = resolve(x["bars"], x["i"], row["entry"], row["sl"], row["tp"],
                    shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                    shadow.cost_r(row), LIVE_TRAIL,
                    float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
        if g is not None:
            res[idx] = g
    print(f"resolved: {len(res)}")

    win_s = 7 * 86400
    n_win = max(1, int(span // 7))
    mid = n_win // 2

    def book(keep, k_lo=0, k_hi=None, wc=3, tr=2):
        tot = 0.0
        n = 0
        pos = 0
        for k in range(k_lo, n_win if k_hi is None else k_hi):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            wcl, trl, per, wt = [], [], {}, 0.0
            for idx, x in enumerate(C):
                if not (lo_t <= x["ts"] < hi_t) or idx not in res or not keep(x):
                    continue
                wcl[:] = [q for q in wcl if q > x["ts"]]
                trl[:] = [q for q in trl if q > x["ts"]]
                per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
                bk = trl if x["kind"] == "TREND" else wcl
                cap = tr if x["kind"] == "TREND" else wc
                if per[x["sym"]] or len(bk) >= cap:
                    continue
                g = res[idx]
                bk.append(g[1])
                per[x["sym"]].append(g[1])
                wt += g[0] * eq0 * 0.12 * float(x["sig"].sl_margin_pct) / 100.0
                n += 1
            tot += wt
            pos += 1 if wt > 0 else 0
        return tot, n, pos

    # LIVE baseline: no squeeze, trend long-only, no lateness/baseline gates.
    def LIVE(x):
        if x["kind"] == "SQUEEZE":
            return False
        if x["kind"] == "TREND" and x["sig"].side == "SHORT":
            return False
        return True

    b, bn, bp = book(LIVE)
    br = book(LIVE, 0, mid)[0]
    bo = book(LIVE, mid, n_win)[0]
    print()
    print(f"LIVE BASELINE: {b:+.2f} over {bn} trades, {bp}/{n_win} positive weeks")

    def row(label, keep, note=""):
        tot, n, pos = book(keep)
        r = book(keep, 0, mid)[0] - br
        o = book(keep, mid, n_win)[0] - bo
        ok = "YES" if r > 0 and o > 0 else ("no" if r < 0 and o < 0 else "one half only")
        print(f"{label:<30} {tot:+10.2f} {tot-b:+9.2f} {n:7d} {pos:4d}/{n_win:<3d} "
              f"{r:+9.2f} {o:+9.2f}  {ok}{note}")
        return ok == "YES"

    hdr = (f"{'rule':<30} {'net $':>10} {'vs live':>9} {'trades':>7} {'pos wk':>8} "
           f"{'recent':>9} {'older':>9}  flips?")
    flips = []

    print()
    print("=== 6. ENTRY LATENESS AS A GATE (was -$260) ===")
    print(hdr)
    for g in (0.99, 0.95, 0.85):
        if row(f"skip late > {g:.2f}",
               lambda x, gg=g: LIVE(x) and (x["kind"] != "WILDCARD"
                                            or x["late"] is None or x["late"] <= gg)):
            flips.append(f"lateness <= {g}")

    print()
    print("=== 7. PRE-IMPULSE TURNOVER AS A GATE (was no signal) ===")
    print(hdr)
    for f_usd in (1e6, 2e6, 3e6):
        if row(f"pre-impulse >= ${f_usd/1e6:.0f}M",
               lambda x, ff=f_usd: LIVE(x) and (x["kind"] != "WILDCARD"
                                                or x["base_turn"] >= ff)):
            flips.append(f"baseline turnover >= {f_usd/1e6:.0f}M")

    print()
    print("=== 8. THE SQUEEZE SLEEVE (was +$2.58/mo, failed halves) ===")
    print(hdr)
    if row("squeeze ON",
           lambda x: (x["kind"] != "TREND" or x["sig"].side == "LONG")):
        flips.append("squeeze on")

    print()
    print("=== 10. TREND SHORTS (was -$61.51 unconditional) ===")
    print(hdr)
    if row("trend shorts, unconditional", lambda x: x["kind"] != "SQUEEZE"):
        flips.append("trend shorts unconditional")
    for gate in (-0.05, -0.12):
        if row(f"trend shorts if BTC7d <= {gate*100:.0f}%",
               lambda x, gg=gate: x["kind"] != "SQUEEZE" and (
                   x["kind"] != "TREND" or x["sig"].side == "LONG"
                   or btc_trail(x["ts"]) <= gg)):
            flips.append(f"trend shorts gated at {gate*100:.0f}%")

    print()
    print("=== 9. SHARPER REGIME TILTS, COMPOUNDED (was all failed) ===")

    def path(params, k_lo=0, k_hi=None):
        pool = [(i, x) for i, x in enumerate(C) if i in res and LIVE(x)]
        ms = [regime_size_multiplier(x["eff"], lo=params[0], hi=params[1],
                                     floor_mult=params[2]) if params else 1.0
              for _i, x in pool]
        mm = (sum(ms) / len(ms)) if ms else 1.0
        risk = BASE_RISK / mm
        equity, peak, dd = eq0, eq0, 0.0
        openp = []
        lo_t = now - (n_win if k_hi is None else k_hi) * win_s
        hi_t = now - k_lo * win_s
        for idx, x in pool:
            if not (lo_t <= x["ts"] < hi_t):
                continue
            for p_ in [q for q in openp if q[0] <= x["ts"]]:
                equity += p_[1] * p_[2]
                openp.remove(p_)
                peak = max(peak, equity)
                dd = max(dd, (peak - equity) / peak if peak > 0 else 0.0)
            if equity <= 0:
                break
            bk = [q for q in openp if q[3] == x["kind"]]
            cap = 2 if x["kind"] == "TREND" else 3
            if any(q[4] == x["sym"] for q in openp) or len(bk) >= cap:
                continue
            m = regime_size_multiplier(x["eff"], lo=params[0], hi=params[1],
                                       floor_mult=params[2]) if params else 1.0
            openp.append((res[idx][1], equity * risk * m, res[idx][0], x["kind"], x["sym"]))
        for p_ in openp:
            equity += p_[1] * p_[2]
        peak = max(peak, equity)
        dd = max(dd, (peak - equity) / peak if peak > 0 else 0.0)
        return equity, dd * 100

    print(f"{'tilt':<30} {'final eq':>10} {'growth':>9} {'maxDD':>8}  beats no-scaler twice?")
    n_e, n_dd = path(None)
    nr = path(None, 0, mid)[0]
    no_ = path(None, mid, n_win)[0]
    print(f"{'no scaler (null)':<30} {n_e:10.2f} {(n_e/eq0-1)*100:+8.1f}% {n_dd:7.1f}%  (null)")
    for lab, pr in (("live 0.20/0.45/0.25", (0.20, 0.45, 0.25)),
                    ("0.20/0.60/0.10", (0.20, 0.60, 0.10)),
                    ("0.30/0.50/0.10", (0.30, 0.50, 0.10)),
                    ("floor 0.50", (0.20, 0.45, 0.50))):
        e, d = path(pr)
        r = path(pr, 0, mid)[0]
        o = path(pr, mid, n_win)[0]
        ok = "YES" if r > nr and o > no_ else ("no" if r < nr and o < no_ else "one half only")
        if ok == "YES":
            flips.append(f"tilt {lab}")
        print(f"{lab:<30} {e:10.2f} {(e/eq0-1)*100:+8.1f}% {d:7.1f}%  {ok}")

    print()
    if flips:
        print("REJECTIONS THAT FLIP ON THE CORRECTED POOL:")
        for f in flips:
            print(f"  - {f}")
    else:
        print("NO REJECTION FLIPS. All five stay rejected on the corrected pool.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
