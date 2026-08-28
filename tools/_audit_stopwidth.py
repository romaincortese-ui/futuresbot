"""AUDIT COPY of pit_stop_width.py - same pool/resolver, extra instrumentation.

Answers:
  1. Do (4.0,20) and (4.0,30) actually produce DIFFERENT trade geometry, and on
     how many signals? (the cap can only move sl_price via the x1-leverage
     branch; leverage itself never enters resolve())
  2. Is the tool's `capped` diagnostic measuring "the cap bound" or an integer
     -leverage lattice coincidence?
  3. Trade-level attribution of the (4.0,20) -> (4.0,30) dollar gap.
  4. 1R in dollars under the real runtime sizing path, per cell, on real signals.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

BAR = 900
CHUNK = 1900
TAIL = 260


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 190), int(_env("PJ_POOL", 150))
    now = int(time.time())
    floor = W.wildcard_min_turnover_usdt()
    eq0 = rt._last_known_equity() or 165.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    dollar_r = risk_pct * eq0
    base_lev = int(min(10.0, max(5.0, _env("FUTURES_WILDCARD_LEVERAGE", 7.0))))
    max_margin_pct = _env("FUTURES_WILDCARD_MAX_MARGIN_PCT", 0.25)
    print("equity $%.2f | risk_pct %.4f -> tool 1R = $%.2f | base lev x%d | max_margin %.2f"
          % (eq0, risk_pct, dollar_r, base_lev, max_margin_pct))

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    syms = [s for a, s in crypto if s not in majors and a >= _env("PJ_MIN_TODAY", 3e5)][:pool_n]
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

    print("fetching %d symbols x %.0fd..." % (len(syms), days))
    with ThreadPoolExecutor(max_workers=6) as p:
        frames = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 300}
    print("frames: %d" % len(frames))

    prep = {}
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
        hits = [i for i in range(250, len(c))
                if i > W.ROC_BARS and roll[i] >= floor
                and abs(c[i] / c[i - W.ROC_BARS] - 1.0) >= 0.08]
        prep[s] = (df, bars, hits, sizes.get(s, 0.0))
    print("trigger bars: %d" % sum(len(h) for _d, _b, h, _cs in prep.values()))

    live_floor = ratchet(3.0, 0.75)
    win_s = 7 * 86400
    span = max(b[-1][0] for _d, b, _h, _c in prep.values()) - min(b[0][0] for _d, b, _h, _c in prep.values())
    n_win = max(1, int(span // win_s))
    mid = n_win // 2
    print("span %.0fd -> %d weekly windows, mid=%d" % (span / 86400.0, n_win, mid))

    def signals(atr_mult, cap_pct):
        """All resolvable candidates for a cell, keyed by (sym, bar index)."""
        os.environ["FUTURES_WILDCARD_SL_ATR_MULT"] = str(atr_mult)
        os.environ["FUTURES_WILDCARD_MAX_SL_MARGIN_PCT"] = str(cap_pct)
        out = {}
        for s, (df, bars, hits, cs) in prep.items():
            for i in hits:
                sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                if sig is None:
                    continue
                e, sl, tp = float(sig.entry_price), float(sig.sl_price), float(sig.tp_price)
                one = abs(e - sl)
                if one <= 0 or e <= 0:
                    continue
                slf = one / e
                row = {"entry": e, "sl": sl, "tp": tp, "side": sig.side}
                g = resolve(bars, i, e, sl, tp, abs(tp - e) / one, sig.side,
                            shadow.CONVEX_HORIZON_S, shadow.cost_r(row), live_floor,
                            float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if g is None:
                    continue
                designed = _env("FUTURES_WILDCARD_SL_ATR_MULT", 1.5) * float(sig.atr_pct)
                out[(s, i)] = {
                    "ts": bars[i][0], "sym": s, "net": float(g[0]), "kind": g[2],
                    "exit_ts": float(g[1]), "slf": slf, "lev": float(sig.leverage),
                    "smp": float(sig.sl_margin_pct), "side": sig.side,
                    "e": e, "sl": sl, "tp": tp, "atr": float(sig.atr_pct),
                    "cs": cs,
                    "tool_capped": slf * float(sig.leverage) * 100.0 >= cap_pct - 0.5,
                    "lev_trimmed": designed * base_lev * 100.0 > cap_pct,
                    "stop_tightened": designed > cap_pct / 100.0,
                    "tp_r": abs(tp - e) / one,
                }
        return out

    def book(cands):
        C = sorted(cands.values(), key=lambda x: x["ts"])
        taken, older, recent = [], 0.0, 0.0
        for k in range(n_win):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            slots, per, wk = [], {}, 0.0
            for x in C:
                if not (lo_t <= x["ts"] < hi_t):
                    continue
                slots[:] = [q for q in slots if q > x["ts"]]
                per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
                if per[x["sym"]] or len(slots) >= 3:
                    continue
                slots.append(x["exit_ts"])
                per[x["sym"]].append(x["exit_ts"])
                taken.append(x)
                wk += x["net"] * dollar_r
            if k < mid:
                recent += wk
            else:
                older += wk
        return taken, older, recent

    CELLS = [(3.0, 20), (3.0, 30), (4.0, 20), (4.0, 30), (5.0, 20), (5.0, 30)]
    cell = {}
    for a, c in CELLS:
        cell[(a, c)] = signals(a, c)

    print("\n=== 1. HOW MANY SIGNALS DOES THE CAP DIAL ACTUALLY MOVE? ===")
    print("(leverage never enters resolve(); the cap can only change P&L via")
    print(" sl_price, which moves only when even x1 leverage breaches the cap)")
    for a in (3.0, 4.0, 5.0):
        A, B = cell[(a, 20)], cell[(a, 30)]
        keys = set(A) | set(B)
        same_geo = diff_geo = only_a = only_b = 0
        for k in keys:
            if k not in A:
                only_b += 1
                continue
            if k not in B:
                only_a += 1
                continue
            if abs(A[k]["sl"] - B[k]["sl"]) < 1e-12 and abs(A[k]["tp"] - B[k]["tp"]) < 1e-12:
                same_geo += 1
            else:
                diff_geo += 1
        print("  %.1fxATR  cap20 n=%d cap30 n=%d | IDENTICAL entry/sl/tp: %d | different: %d "
              "| only20 %d only30 %d"
              % (a, len(A), len(B), same_geo, diff_geo, only_a, only_b))
        # and are the resolved outcomes identical on the identical ones?
        d = [k for k in keys if k in A and k in B
             and abs(A[k]["sl"] - B[k]["sl"]) < 1e-12
             and abs(A[k]["net"] - B[k]["net"]) > 1e-9]
        print("       identical geometry but different net R: %d (should be 0)" % len(d))

    print("\n=== 2. THE `capped` DIAGNOSTIC vs REAL BINDING ===")
    for a, c in CELLS:
        S = cell[(a, c)].values()
        n = max(1, len(S))
        tc = sum(1 for x in S if x["tool_capped"])
        lt = sum(1 for x in S if x["lev_trimmed"])
        st = sum(1 for x in S if x["stop_tightened"])
        print("  %.1fx cap%d  n=%4d | tool says capped %5.1f%% | leverage ACTUALLY trimmed "
              "%5.1f%% | stop ACTUALLY tightened %5.1f%%"
              % (a, c, len(S), 100.0 * tc / n, 100.0 * lt / n, 100.0 * st / n))

    print("\n=== 3. BOOKED RESULT PER CELL (audit re-implementation) ===")
    print("%-12s %5s %10s %7s %8s %9s" % ("cell", "n", "net $", "stops", "older", "recent"))
    booked = {}
    for a, c in CELLS:
        taken, older, recent = book(cell[(a, c)])
        booked[(a, c)] = (taken, older, recent)
        net = sum(x["net"] for x in taken) * dollar_r
        stops = sum(1 for x in taken if x["kind"] == "stop")
        print("%-12s %5d %+10.2f %7d %+8.2f %+9.2f"
              % ("%.1f x %d%%" % (a, c), len(taken), net, stops, older, recent))

    print("\n=== 4. ATTRIBUTION: where does (4.0,20) -> (4.0,30) come from? ===")
    tA = {(x["sym"], x["ts"]): x for x in booked[(4.0, 20)][0]}
    tB = {(x["sym"], x["ts"]): x for x in booked[(4.0, 30)][0]}
    shared = set(tA) & set(tB)
    same_pnl = sum(1 for k in shared if abs(tA[k]["net"] - tB[k]["net"]) < 1e-9)
    dA = sum(tA[k]["net"] for k in set(tA) - shared) * dollar_r
    dB = sum(tB[k]["net"] for k in set(tB) - shared) * dollar_r
    shifted = sum(tB[k]["net"] - tA[k]["net"] for k in shared) * dollar_r
    print("  trades in both books: %d (identical P&L on %d of them)" % (len(shared), same_pnl))
    print("  only in cap20 book: %d worth %+.2f" % (len(set(tA) - shared), dA))
    print("  only in cap30 book: %d worth %+.2f" % (len(set(tB) - shared), dB))
    print("  shared-trade P&L shift: %+.2f" % shifted)
    print("  => total gap %+.2f" % (dB - dA + shifted))
    deltas = sorted(((tB[k]["net"] - tA[k]["net"]) * dollar_r, k) for k in shared
                    if abs(tA[k]["net"] - tB[k]["net"]) > 1e-9)
    print("  biggest single-trade shifts among shared:")
    for d, k in (deltas[:3] + deltas[-3:]):
        print("    %-14s %+8.2f  (cap20 %+.2fR %s -> cap30 %+.2fR %s)"
              % (k[0], d, tA[k]["net"], tA[k]["kind"], tB[k]["net"], tB[k]["kind"]))

    print("\n=== 5. HOW CONCENTRATED IS THE (3.0,20) -> (4.0,30) GAIN? ===")
    tL = booked[(3.0, 20)][0]
    tC = booked[(4.0, 30)][0]
    netL = sum(x["net"] for x in tL) * dollar_r
    netC = sum(x["net"] for x in tC) * dollar_r
    vL = sorted((x["net"] * dollar_r for x in tL), reverse=True)
    vC = sorted((x["net"] * dollar_r for x in tC), reverse=True)
    print("  live  net %+.2f  top1 %+.2f top3 %+.2f  ex-top3 %+.2f" % (netL, vL[0], sum(vL[:3]), netL - sum(vL[:3])))
    print("  cand  net %+.2f  top1 %+.2f top3 %+.2f  ex-top3 %+.2f" % (netC, vC[0], sum(vC[:3]), netC - sum(vC[:3])))
    print("  gap %+.2f | gap ex-top3-of-each %+.2f"
          % (netC - netL, (netC - sum(vC[:3])) - (netL - sum(vL[:3]))))

    print("\n=== 6. 1R IN DOLLARS UNDER THE REAL RUNTIME SIZING PATH ===")
    print("  margin = risk_pct*eq*100/sl_margin_pct, capped at max_margin_pct*eq;")
    print("  1R$ = margin*sl_margin_pct/100. Also: contracts = notional/(px*contractSize),")
    print("  ROUNDED DOWN to an integer on a real exchange.")
    for a, c in CELLS:
        S = list(cell[(a, c)].values())
        if not S:
            continue
        rs, bound, zero_ct, quant = [], 0, 0, []
        for x in S:
            smp = x["smp"]
            want = risk_pct * eq0 * 100.0 / smp if smp > 0 else 0.0
            used = min(want, max_margin_pct * eq0)
            rs.append(used * smp / 100.0)
            if used < want - 1e-9:
                bound += 1
            notional = used * x["lev"]
            if x["cs"] > 0 and x["e"] > 0:
                n_ct = notional / (x["e"] * x["cs"])
                if int(n_ct) < 1:
                    zero_ct += 1
                elif n_ct > 0:
                    quant.append(int(n_ct) / n_ct)
        rs.sort()
        print("  %.1fx cap%d n=%4d | 1R$ min %.3f med %.3f max %.3f | margin-cap bound %d "
              "| sub-1-contract %d (%.1f%%) | med size after rounding %.2f%% of target"
              % (a, c, len(S), rs[0], rs[len(rs) // 2], rs[-1], bound, zero_ct,
                 100.0 * zero_ct / len(S),
                 100.0 * (sorted(quant)[len(quant) // 2] if quant else 0.0)))

    print("\n=== 7. SHORT TP CLAMP: is the credited R reachable or nominal? ===")
    for a, c in CELLS:
        S = list(cell[(a, c)].values())
        sh = [x for x in S if x["side"] == "SHORT"]
        if not sh:
            continue
        cl_ = [x for x in sh if abs(x["e"] - x["tp"]) / x["e"] >= 0.4999]
        bad = [x for x in cl_ if abs(x["tp_r"] - 5.0) < 1e-6]
        tps = [x for x in cl_ if x["kind"] == "tp"]
        print("  %.1fx cap%d: shorts %3d, TP-clamped %3d, clamped credited at nominal 5R: %d "
              "(bug marker), clamped tp_r range %s, clamped trades that HIT tp: %d"
              % (a, c, len(sh), len(cl_), len(bad),
                 ("%.2f-%.2f" % (min(x["tp_r"] for x in cl_), max(x["tp_r"] for x in cl_))
                  if cl_ else "-"), len(tps)))

    print("\n=== 8. EXIT MIX + TRAIL-FILL SLACK (does widening shift weight onto")
    print("        the exit type whose fill price the simulator ASSUMES?) ===")
    for a, c in ((3.0, 20), (4.0, 20), (4.0, 30), (5.0, 30)):
        taken = booked[(a, c)][0]
        n = max(1, len(taken))
        mix = {k: sum(1 for x in taken if x["kind"] == k) for k in ("stop", "tp", "trail", "timeout")}
        print("  %.1fx cap%d n=%3d | stop %d tp %d trail %d timeout %d | trail share %.1f%%"
              % (a, c, len(taken), mix["stop"], mix["tp"], mix["trail"], mix["timeout"],
                 100.0 * mix["trail"] / n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
