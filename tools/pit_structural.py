"""Slots, trend universe and renormalised sizing — all on the corrected pool.

    railway run --service Futures-bot python tools/pit_structural.py

Three live settings that were decided on the "top-N by turnover today" pool,
which tools/replay_vs_live.py showed covers 30% of the symbols the bot actually
trades. Rerun here on the point-in-time construction: a wide candidate set, each
symbol's rolling 24h turnover computed bar by bar from its contractSize, and
eligibility judged AT THE BAR so names enter and leave the band as they did live.

  A. SLOT COUNTS (live 3 wildcard / 2 trend). Slot contention is directly a
     function of how many candidates exist, and the corrected pool produces far
     more of them, so this is the most mechanically exposed of the three.
  B. TREND UNIVERSE (live ETH/XRP/ZEC). Dropping SOL was worth +$134 on the old
     book. Majors churn less in turnover than alts, so the symbol screen itself
     is fairly robust — but the joint validation against the shared wildcard book
     is fully exposed.
  C. RENORMALISED SIZING (live risk_pct 0.0241). This is what trial 16 is
     measuring RIGHT NOW. If it does not survive the corrected pool the live
     trial is testing something unsupported, which is worth knowing before it
     finishes rather than after. Scored on a COMPOUNDED equity path, because a
     sizing question cannot be answered by summing dollars at a fixed 1R.

All arms share candidates, funding, costs and the live ratchet trail. Every
section carries a half-split, and the ~$10 run-to-run noise band applies.

RESULT, 2026-08-24 -- 154 symbols, 208 days, 2075 candidates, point-in-time.
TWO OF THE THREE SURVIVE. THE ONE THAT DOES NOT IS TRIAL 16's SUBJECT.

A. SLOTS: 3 wildcard / 2 trend CONFIRMED. Nothing beats it on both halves.

    wc / tr         net $   vs live   pos wk    recent     older  halves
    3 / 2         +389.62     +0.00   19/29      +0.00     +0.00  (null, live)
    2 / 2         +393.20     +3.58   19/29     +11.08     -7.50  one half
    2 / 3         +381.60     -8.02   19/29     +10.74    -18.76  one half
    3 / 1         +344.08    -45.54   21/29     -48.62     +3.08  one half
    3 / 3         +378.02    -11.60   19/29      -0.34    -11.26  no
    4 / 2         +352.87    -36.74   18/29     -18.54    -18.21  no
    5 / 2         +344.05    -45.56   17/29     -23.30    -22.26  no

   The only arm that even edges it is 2/2 at +$3.58, one half only. Adding
   wildcard slots is monotonically WORSE (4/2 -$36.74, 5/2 -$45.56) and cutting
   the trend book to one slot costs -$45.54. Both live values are right.

B. TREND UNIVERSE: ETH/XRP/ZEC CONFIRMED, and by a wide margin.

    universe                      net $   vs live   halves
    ETH+XRP+ZEC (live)          +389.62     +0.00   (null)
    ETH+SOL                     +257.25   -132.37   no
    ETH+SOL+XRP+ZEC             +331.57    -58.05   no
    ETH+XRP                     +283.48   -106.14   no
    ETH+ZEC                     +342.96    -46.65   no
    XRP+ZEC                     +349.67    -39.95   no

   EVERY alternative is worse in BOTH halves. Dropping SOL was worth +$134 on the
   broken pool and is worth +$132 here; adding it back still costs -$58.05. This
   is the one big change from this week that the corrected pool strengthens
   rather than undermines.

C. RENORMALISED SIZING: FAILS. It does not beat turning the scaler OFF.

    arm                                 risk/trade   final eq    growth    maxDD  halves
    no scaler, flat 1.87%                    1.87%    1274.83   +640.6%    25.4%  (null)
    scaler, NOT renormalised (old)           1.87%     831.31   +382.9%    26.0%  no
    scaler, RENORMALISED (live)              2.44%    1263.81   +634.2%    32.7%  one half

   All three arms deploy the SAME mean risk, so this compares the shape of the
   tilt, not the size of the book. On the broken pool the same test read
   +659.1% growth and maxDD FALLING 24.2% -> 20.2%, passing both halves, and it
   was called the strongest result of the session. On the corrected pool it is
   slightly WORSE on growth and carries SEVEN POINTS more drawdown.

   The un-renormalised scaler remains catastrophic (+382.9%), so renormalising
   was the right fix RELATIVE TO THE SCALER. Relative to having no scaler at all
   it is a wash on growth and materially worse on drawdown: the efficiency tilt
   widens position-size variance (0.61%-2.44%) without paying for it.

   TRIAL 16 IS MEASURING THIS SETTING RIGHT NOW. The best available evidence now
   says it does not beat doing nothing.

CAVEAT WORTH KEEPING IN FRONT: this is the third replay-based reversal in a row,
and the replay is the instrument that has been wrong repeatedly. Live evidence is
the thing that is scarce, which is an argument for letting trial 16 run to its 30
closes rather than acting on yet another simulation.

Read-only. Places nothing.

Env: PS_DAYS (190) PS_POOL (150) PS_MIN_TODAY (300000)
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
from pit_ratchet import ratchet
from retention_trail_ab import resolve

CHUNK, BAR = 2000, 900
ALL_TREND = ("ETH_USDT", "SOL_USDT", "XRP_USDT", "ZEC_USDT")
LIVE_TREND = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
LIVE_TRAIL = ratchet(3.0, 0.75)          # what is live while trial 16 runs
BASE_RISK = 0.0187                        # pre-renormalisation


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars over the window, NOT account P&L.")
    print("    The real account is DOWN lifetime; /report has the true figure. ***")
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PS_DAYS", 190), int(_env("PS_POOL", 150))
    min_today = _env("PS_MIN_TODAY", 3e5)
    eq0 = rt._last_known_equity() or 172.0
    now = int(time.time())
    live_floor = W.wildcard_min_turnover_usdt()
    eff_win = max(4, int(rt._env_float("FUTURES_REGIME_EFF_WINDOW", 24.0)))

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    wide = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                   if str(t.get("symbol") or "").endswith("_USDT")
                   and rt._is_tradeable_crypto(str(t.get("symbol") or ""))
                   and str(t.get("symbol") or "") not in majors
                   and float(t.get("amount24") or 0) >= min_today), reverse=True)
    cand_syms = [s for _a, s in wide[:pool_n]]
    syms = sorted(set(cand_syms) | set(ALL_TREND))
    print(f"equity ${eq0:.2f} | wide set {len(cand_syms)} | floor "
          f"${live_floor/1e6:.0f}M judged per bar")

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

    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))
    print("generating candidates...")
    cands = []          # (ts, sym, sig, i, bars, kind, eff)
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
        if s in ALL_TREND:
            for i in range(400, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None and sig.side == "LONG":
                    cands.append((ts[i], s, sig, i, bars, "TREND",
                                  trend_efficiency(c[:i + 1], eff_win)))
        if s in cand_syms:
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or roll[i] < live_floor:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    cands.append((ts[i], s, sig, i, bars, "WILDCARD",
                                  trend_efficiency(c[:i + 1], eff_win)))
    cands.sort(key=lambda x: x[0])
    print(f"candidates: {len(cands)} "
          f"(wildcard {sum(1 for x in cands if x[5]=='WILDCARD')}, "
          f"trend {sum(1 for x in cands if x[5]=='TREND')})")
    if not cands:
        return 0

    def outcome(c_):
        _ts, _s, sig, i, bars, _k, _e = c_
        row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
               "tp": float(sig.tp_price), "side": sig.side}
        return resolve(bars, i, row["entry"], row["sl"], row["tp"],
                       shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                       shadow.cost_r(row), LIVE_TRAIL,
                       float(getattr(sig, "atr_pct", 0.0) or 0.0), now)

    resolved = {}
    for idx, c_ in enumerate(cands):
        g = outcome(c_)
        if g is not None:
            resolved[idx] = g
    print(f"resolved: {len(resolved)}")

    win_s = 7 * 86400
    n_win = max(1, int(span // 7))
    mid = n_win // 2

    def book(wc_slots, tr_slots, universe, k_lo=0, k_hi=None):
        tot = 0.0
        pos = 0
        n = 0
        for k in range(k_lo, n_win if k_hi is None else k_hi):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            wcl, trl, per, wt = [], [], {}, 0.0
            for idx, c_ in enumerate(cands):
                ts0, sym, sig, i, bars, kind, eff = c_
                if not (lo_t <= ts0 < hi_t) or idx not in resolved:
                    continue
                if kind == "TREND" and sym not in universe:
                    continue
                wcl[:] = [x for x in wcl if x > ts0]
                trl[:] = [x for x in trl if x > ts0]
                per[sym] = [x for x in per.get(sym, []) if x > ts0]
                bk = trl if kind == "TREND" else wcl
                cap = tr_slots if kind == "TREND" else wc_slots
                if per[sym] or len(bk) >= cap:
                    continue
                g = resolved[idx]
                bk.append(g[1])
                per[sym].append(g[1])
                wt += g[0] * eq0 * 0.12 * float(sig.sl_margin_pct) / 100.0
                n += 1
            tot += wt
            pos += 1 if wt > 0 else 0
        return tot, pos, n

    def halves(fn):
        return fn(0, mid)[0], fn(mid, n_win)[0]

    # ---- A. SLOTS -------------------------------------------------------
    print()
    print("=== A. SLOT COUNTS (trend universe = live ETH/XRP/ZEC) ===")
    print(f"{'wc / tr':<10} {'net $':>10} {'vs live':>9} {'trades':>7} {'pos wk':>8} "
          f"{'recent':>9} {'older':>9}  both halves?")
    base_a, base_pos, base_n = book(3, 2, LIVE_TREND)
    ar, ao = halves(lambda a, b: book(3, 2, LIVE_TREND, a, b))
    print(f"{'3 / 2':<10} {base_a:+10.2f} {0.0:+9.2f} {base_n:7d} {base_pos:4d}/{n_win:<3d} "
          f"{0.0:+9.2f} {0.0:+9.2f}  (null)  <-live cfg")
    for wc_s in (2, 3, 4, 5):
        for tr_s in (1, 2, 3):
            if (wc_s, tr_s) == (3, 2):
                continue
            tot, pos, n = book(wc_s, tr_s, LIVE_TREND)
            r, o = halves(lambda a, b: book(wc_s, tr_s, LIVE_TREND, a, b))
            dr, do = r - ar, o - ao
            ok = "YES" if dr > 0 and do > 0 else ("no" if dr < 0 and do < 0 else "one half only")
            print(f"{str(wc_s) + ' / ' + str(tr_s):<10} {tot:+10.2f} {tot-base_a:+9.2f} "
                  f"{n:7d} {pos:4d}/{n_win:<3d} {dr:+9.2f} {do:+9.2f}  {ok}")

    # ---- B. TREND UNIVERSE ----------------------------------------------
    print()
    print("=== B. TREND UNIVERSE (slots 3 / 2) ===")
    print(f"{'universe':<24} {'net $':>10} {'vs live':>9} {'pos wk':>8} "
          f"{'recent':>9} {'older':>9}  both halves?")
    universes = [("ETH+XRP+ZEC (live)", LIVE_TREND),
                 ("ETH+SOL", ("ETH_USDT", "SOL_USDT")),
                 ("ETH+SOL+XRP+ZEC", ALL_TREND),
                 ("ETH+XRP", ("ETH_USDT", "XRP_USDT")),
                 ("ETH+ZEC", ("ETH_USDT", "ZEC_USDT")),
                 ("XRP+ZEC", ("XRP_USDT", "ZEC_USDT"))]
    for label, uni in universes:
        tot, pos, n = book(3, 2, uni)
        r, o = halves(lambda a, b: book(3, 2, uni, a, b))
        dr, do = r - ar, o - ao
        ok = "(null)" if uni == LIVE_TREND else (
            "YES" if dr > 0 and do > 0 else ("no" if dr < 0 and do < 0 else "one half only"))
        print(f"{label:<24} {tot:+10.2f} {tot-base_a:+9.2f} {pos:4d}/{n_win:<3d} "
              f"{dr:+9.2f} {do:+9.2f}  {ok}")

    # ---- C. SIZING, COMPOUNDED ------------------------------------------
    print()
    print("=== C. RENORMALISED SIZING (compounded, what trial 16 is testing) ===")

    def mult_of(eff, scaler):
        if not scaler:
            return 1.0
        return regime_size_multiplier(eff, lo=0.20, hi=0.45, floor_mult=0.25)

    def path(scaler, renorm, k_lo=0, k_hi=None):
        pool = [(i, c) for i, c in enumerate(cands) if i in resolved]
        mm = 1.0
        if scaler and renorm:
            ms = [mult_of(c[6], True) for _i, c in pool]
            mm = (sum(ms) / len(ms)) if ms else 1.0
        risk_eff = BASE_RISK / mm
        equity, peak, maxdd = eq0, eq0, 0.0
        openp = []
        lo_t = now - (n_win if k_hi is None else k_hi) * win_s
        hi_t = now - (k_lo * win_s)
        for idx, c_ in pool:
            ts0, sym, sig, i, bars, kind, eff = c_
            if not (lo_t <= ts0 < hi_t):
                continue
            for p_ in [x for x in openp if x[0] <= ts0]:
                equity += p_[1] * p_[2]
                openp.remove(p_)
                peak = max(peak, equity)
                maxdd = max(maxdd, (peak - equity) / peak if peak > 0 else 0.0)
            if equity <= 0:
                break
            bk = [x for x in openp if x[3] == kind]
            cap = 2 if kind == "TREND" else 3
            if any(x[4] == sym for x in openp) or len(bk) >= cap:
                continue
            if kind == "TREND" and sym not in LIVE_TREND:
                continue
            g = resolved[idx]
            openp.append((g[1], equity * risk_eff * mult_of(eff, scaler), g[0], kind, sym))
        for p_ in openp:
            equity += p_[1] * p_[2]
        peak = max(peak, equity)
        maxdd = max(maxdd, (peak - equity) / peak if peak > 0 else 0.0)
        return equity, maxdd * 100, risk_eff * 100

    print(f"{'arm':<34} {'risk/trade':>11} {'final eq':>10} {'growth':>9} {'maxDD':>8}  both halves?")
    arms = [("no scaler, flat 1.87%", False, False),
            ("scaler, NOT renormalised (old)", True, False),
            ("scaler, RENORMALISED (live)", True, True)]
    nulls = None
    for label, sc, rn in arms:
        e, dd, rp = path(sc, rn)
        gr = (e / eq0 - 1) * 100
        er = path(sc, rn, 0, mid)[0]
        eo = path(sc, rn, mid, n_win)[0]
        if nulls is None:
            nulls = (er, eo)
            ok = "(null)"
        else:
            ok = "YES" if er > nulls[0] and eo > nulls[1] else (
                "no" if er < nulls[0] and eo < nulls[1] else "one half only")
        star = "  <-live cfg" if rn else ""
        print(f"{label:<34} {rp:10.2f}% {e:10.2f} {gr:+8.1f}% {dd:7.1f}%  {ok}{star}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
