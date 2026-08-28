"""AUDIT COPY of pit_stop_width.py + exchange-contact instrumentation.

Adds, per cell: real contract_size/minVol, real _entry_margin (risk-targeted
+ MAX_MARGIN_PCT cap), live risk_capped_contracts, min_vol skip, concurrent
margin peak, hold-time distribution, timeout share, and a 2-slot book.
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
from futuresbot.risk_controls import risk_capped_contracts  # noqa: E402
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
    eq0 = _env("AUDIT_EQ", 0) or (rt._last_known_equity() or 165.0)
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    dollar_r = risk_pct * eq0
    max_margin_pct = rt._env_float("FUTURES_WILDCARD_MAX_MARGIN_PCT", 0.25)
    base_lev = _env("FUTURES_WILDCARD_LEVERAGE", 7.0)
    rbs = rt._flag("FUTURES_RISK_BASED_SIZING_ENABLED", default=False)
    print("equity $%.2f | risk_pct %.4f -> nominal 1R = $%.2f" % (eq0, risk_pct, dollar_r))
    print("base_lev=%s max_margin_pct=%.3f ($%.2f) risk_based_sizing=%s max_trade_risk=%.1f%% "
          "risk_targeted=%s live_max_concurrent=%s"
          % (base_lev, max_margin_pct, max_margin_pct * eq0, rbs,
             rt._env_float("FUTURES_MAX_TRADE_RISK_PCT", 5.0),
             rt._flag("FUTURES_WILDCARD_RISK_TARGETED", default=True),
             os.environ.get("FUTURES_MAX_CONCURRENT_POSITIONS")))

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    syms = [s for a, s in crypto if s not in majors and a >= _env("PJ_MIN_TODAY", 3e5)][:pool_n]
    details = cl.get_all_contract_details() or []
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0) for d in details}
    minvols = {str(d.get("symbol") or ""): int(float(d.get("minVol") or 1) or 1) for d in details}
    mmr = {}
    for d in details:
        s = str(d.get("symbol") or "")
        for k in ("maintenanceMarginRate", "maintainMarginRate", "maintenanceMargin"):
            if d.get(k) is not None:
                mmr[s] = float(d.get(k) or 0)
                break
    print("contract details: %d | minVol distinct: %s | mmr sample: %s"
          % (len(details), sorted(set(minvols.values()))[:10], list(mmr.items())[:3]))
    nch = int(days * 86400 // (CHUNK * BAR)) + 1

    def fetch(s):
        parts, end = [], now
        for _ in range(nch):
            d = None
            for _try in range(4):          # retry: partial fetches shrank the sample
                try:
                    d = cl.get_klines(s, interval="Min15", start=end - CHUNK * BAR, end=end)
                except Exception:
                    d = None
                if d is not None and len(d):
                    break
                time.sleep(1.0)
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
        prep[s] = (df, bars, hits)
    print("trigger bars: %d" % sum(len(h) for _d, _b, h in prep.values()))

    live_floor = ratchet(3.0, 0.75)
    win_s = 7 * 86400
    span = max(b[-1][0] for _d, b, _h in prep.values()) - min(b[0][0] for _d, b, _h in prep.values())
    n_win = max(1, int(span // win_s))
    mid = n_win // 2

    def run_cell(atr_mult, cap_pct):
        os.environ["FUTURES_WILDCARD_SL_ATR_MULT"] = str(atr_mult)
        os.environ["FUTURES_WILDCARD_MAX_SL_MARGIN_PCT"] = str(cap_pct)
        C = []
        for s, (df, bars, hits) in prep.items():
            cs = sizes.get(s, 0.0)
            mv = minvols.get(s, 1)
            for i in hits:
                sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                if sig is None:
                    continue
                e, sl, tp = float(sig.entry_price), float(sig.sl_price), float(sig.tp_price)
                one = abs(e - sl)
                if one <= 0 or e <= 0:
                    continue
                slf = one / e
                lev = float(sig.leverage)
                was_capped = slf * lev * 100.0 >= cap_pct - 0.5
                slfd = float(getattr(sig, "sl_frac_designed", 0.0) or 0.0)
                tightened = slfd > 0 and slf < slfd - 1e-9
                # ---- REAL SIZING PATH ----
                margin = max(0.0, rt._entry_margin(sig, eq0, kind="WILDCARD", symbol=s))
                sizing = dict(getattr(rt, "_last_entry_sizing", {}) or {})
                mcap_bound = float(sizing.get("risk_cap_bound") or 0.0) > 0.5
                contracts = int((margin * lev / e) / cs) if cs > 0 else 0
                pre_rbs = contracts
                if rbs:
                    contracts = risk_capped_contracts(
                        contracts=contracts, entry_price=e, sl_price=sl,
                        contract_size=cs, equity_usdt=eq0,
                        max_risk_pct=rt._env_float("FUTURES_MAX_TRADE_RISK_PCT", 5.0))
                skipped = contracts < mv
                real_risk = contracts * cs * one
                real_margin = contracts * cs * e / lev if lev > 0 else 0.0
                row = {"entry": e, "sl": sl, "tp": tp, "side": sig.side}
                g = resolve(bars, i, e, sl, tp, abs(tp - e) / one, sig.side,
                            shadow.CONVEX_HORIZON_S, shadow.cost_r(row), live_floor,
                            float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if g is None:
                    continue
                C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                          "kind": g[2], "exit_ts": float(g[1]),
                          "slf": slf, "lev": lev, "capped": was_capped,
                          "tightened": tightened, "margin": margin,
                          "real_margin": real_margin, "contracts": contracts,
                          "pre_rbs": pre_rbs, "minvol": mv, "skip": skipped,
                          "real_risk": real_risk, "mcap": mcap_bound,
                          "notional": margin * lev, "cs": cs, "sl": sl, "entry": e})
        C.sort(key=lambda x: x["ts"])

        def book(nslots, apply_minvol, deplete, reserve=0.0):
            """deplete: size each entry off FREE balance (eq0 - open margin -
            reserve), exactly as runtime does (available_usdt), instead of the
            study's constant equity. _entry_margin is linear in available, so
            margin scales; contracts are re-truncated at the scaled margin."""
            taken, older, recent = [], 0.0, 0.0
            marg_rej = 0
            peak_marg = 0.0
            pnl = []
            for k in range(n_win):
                hi_t = now - k * win_s
                lo_t = hi_t - win_s
                slots, per, wk = [], {}, 0.0
                for x in C:
                    if not (lo_t <= x["ts"] < hi_t):
                        continue
                    slots[:] = [q for q in slots if q[0] > x["ts"]]
                    per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
                    if per[x["sym"]] or len(slots) >= nslots:
                        continue
                    used = sum(q[1] for q in slots)
                    avail = eq0 - used - reserve
                    if deplete:
                        if avail <= 0:
                            marg_rej += 1
                            continue
                        scale = avail / eq0
                        marg = x["margin"] * scale
                        ctr = int((marg * x["lev"] / x["entry"]) / x["cs"]) if x["cs"] > 0 else 0
                        if rbs:
                            ctr = risk_capped_contracts(
                                contracts=ctr, entry_price=x["entry"], sl_price=x["sl"],
                                contract_size=x["cs"], equity_usdt=avail,
                                max_risk_pct=rt._env_float("FUTURES_MAX_TRADE_RISK_PCT", 5.0))
                        if ctr < x["minvol"]:
                            marg_rej += 1
                            continue
                        rrisk = ctr * x["cs"] * abs(x["entry"] - x["sl"])
                        rmarg = ctr * x["cs"] * x["entry"] / x["lev"]
                    else:
                        if apply_minvol and x["skip"]:
                            continue
                        rrisk = x["real_risk"] if apply_minvol else dollar_r
                        rmarg = x["real_margin"]
                        if rmarg > avail:
                            marg_rej += 1
                            continue
                    slots.append((x["exit_ts"], rmarg))
                    peak_marg = max(peak_marg, sum(q[1] for q in slots))
                    per[x["sym"]].append(x["exit_ts"])
                    taken.append(x)
                    d = x["net"] * rrisk
                    pnl.append(d)
                    wk += d
                if k < mid:
                    recent += wk
                else:
                    older += wk
            return taken, older, recent, marg_rej, peak_marg, pnl

        return C, book

    print("\n=== A. NOMINAL (study accounting: 3 slots, no min_vol, flat 1R) ===")
    print("%-14s %5s %9s %7s %7s | %-38s" % ("cell", "n", "net $", "older", "recent", "diag"))
    cells = {}
    for atr_mult, cap_pct in ((3.0, 20), (4.0, 20), (4.0, 30), (5.0, 30)):
        C, book = run_cell(atr_mult, cap_pct)
        taken, older, recent, _mr, _pm, _pl = book(3, False, False)
        cells[(atr_mult, cap_pct)] = (C, book, taken)
        n = len(taken)
        net = sum(x["net"] for x in taken) * dollar_r
        print("%-14s %5d %+9.2f %+7.0f %+7.0f | lev %.2f slf %.2f%% capped %.0f%% tight %.0f%%"
              % ("%.1fx%d%%" % (atr_mult, cap_pct), n, net, older, recent,
                 sum(x["lev"] for x in taken) / max(1, n),
                 100 * sum(x["slf"] for x in taken) / max(1, n),
                 100 * sum(1 for x in taken if x["capped"]) / max(1, n),
                 100 * sum(1 for x in taken if x["tightened"]) / max(1, n)))

    print("\n=== B. EXCHANGE CONTACT (per-signal, before slot selection) ===")
    print("%-14s %6s %8s %8s %8s %8s %8s %8s %8s"
          % ("cell", "sigs", "margin$", "notion$", "contr", "minvolX", "mcapX", "rbsX", "risk$"))
    for key, (C, book, _t) in cells.items():
        n = max(1, len(C))
        print("%-14s %6d %8.2f %8.2f %8.1f %7.1f%% %7.1f%% %7.1f%% %8.3f"
              % ("%.1fx%d%%" % key, len(C),
                 sum(x["margin"] for x in C) / n,
                 sum(x["notional"] for x in C) / n,
                 sum(x["contracts"] for x in C) / n,
                 100 * sum(1 for x in C if x["skip"]) / n,
                 100 * sum(1 for x in C if x["mcap"]) / n,
                 100 * sum(1 for x in C if x["contracts"] < x["pre_rbs"]) / n,
                 sum(x["real_risk"] for x in C) / n))

    print("\n=== C. BOOK UNDER REAL CONSTRAINTS ===")
    print("%-14s %-24s %5s %9s %8s %8s %6s %6s %6s"
          % ("cell", "regime", "n", "net $", "older", "recent", "peakM", "mrej", "avg h"))
    for key, (C, book, _t) in cells.items():
        for label, ns, mv, dp, rsv in (("A study: 3slot flat-R", 3, False, False, 0.0),
                                       ("B +int-truncation", 3, True, False, 0.0),
                                       ("C +free-bal depletion", 3, False, True, 0.0),
                                       ("D +$40 trend/sqz rsv", 3, False, True, 40.0)):
            taken, older, recent, mrej, pm, pl = book(ns, mv, dp, rsv)
            n = len(taken)
            net = sum(pl)
            hrs = sum((x["exit_ts"] - x["ts"]) for x in taken) / max(1, n) / 3600.0
            vals = sorted(pl, reverse=True)
            k5 = max(1, n // 20)
            t5 = sum(vals[:k5])
            print("%-14s %-24s %5d %+9.2f %+8.0f %+8.0f %6.1f %6d %6.1f  top5 %5.0f%% ex5 %+8.2f"
                  % ("%.1fx%d%%" % key, label, n, net, older, recent, pm, mrej, hrs,
                     100.0 * t5 / net if net else 0.0, net - t5))

    print("\n=== D. HOLD TIME / EXIT MIX (3 slots, nominal selection) ===")
    print("%-14s %5s %6s %6s %6s %6s %7s %7s" % ("cell", "n", "stop", "tp", "trail", "t/out", "avgh", "medh"))
    for key, (C, book, taken) in cells.items():
        n = max(1, len(taken))
        hs = sorted((x["exit_ts"] - x["ts"]) / 3600.0 for x in taken)
        print("%-14s %5d %6d %6d %6d %6d %7.2f %7.2f"
              % ("%.1fx%d%%" % key, len(taken),
                 sum(1 for x in taken if x["kind"] == "stop"),
                 sum(1 for x in taken if x["kind"] == "tp"),
                 sum(1 for x in taken if x["kind"] == "trail"),
                 sum(1 for x in taken if x["kind"] == "timeout"),
                 sum(hs) / n, hs[len(hs) // 2] if hs else 0.0))

    print("\n=== E. LIQUIDATION HEADROOM ===")
    for key, (C, book, _t) in cells.items():
        if not C:
            continue
        worst = max(C, key=lambda x: x["slf"] * x["lev"])
        print("%-14s max sl_margin=%.1f%% (slf %.2f%% x lev %.0f) | lev set %s"
              % ("%.1fx%d%%" % key, 100 * worst["slf"] * worst["lev"], 100 * worst["slf"], worst["lev"],
                 sorted({int(x["lev"]) for x in C})))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
