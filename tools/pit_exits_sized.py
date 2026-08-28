"""The exit stack, re-priced under the LIVE sizing model.

    railway run --service Futures-bot python tools/pit_exits_sized.py

WHY. Every gate and tilt study priced trades at a flat 1R; tools/pit_size.py
closed that. Exit studies were flagged as only PARTIALLY exposed and were not
re-checked. This checks them.

The argument for why exits are less exposed: an exit change keeps the SAME
entries, so each trade carries the SAME regime multiplier in both arms. The
dollar comparison is then a scaler-WEIGHTED version of the flat one:

    flat    sum_i (R_A,i - R_B,i)
    live    sum_i mult_i * (R_A,i - R_B,i)

Those agree unless the exit's benefit CORRELATES with the multiplier. And
there is a specific reason to think it might: the regime scaler is high on
clean trends and floored in chop, while trail and ratchet changes do most of
their work on RUNNERS - which happen in trends. If so, exit improvements are
worth MORE live than flat, and the flat studies understated them.

THE CELL THAT MATTERS MOST is the owner's withdrawal question.
tools/pit_tp_trail_sweep.py found TP 1.5R / arm 1.0 / retain 0.30 was the only
one of sixteen cells with a positive ex-top-5% (+2.61 vs baseline -87.37) -
the only book that survives having its five biggest trades withdrawn - at a
cost of 39% of the edge. That was flat-sized. If runner-heavy exits gain under
live sizing, the cost of going bankable is HIGHER than 39%, not lower.

REPORTED PER CELL: net $ under flat / live scaler / compounding, max drawdown
(compounding only - it is the number that decides whether a book is holdable),
win rate, and ex-top-5% net, which is what "can I withdraw the winners and
still have a business" actually means.

Entries are held at the live trigger throughout; only the exit varies.
Point-in-time majors band (tools/pit_pool.py). READ-ONLY.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_pool import day_key, daily_turnover, pit_majors  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from pit_size import price  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

BAR, CHUNK, TAIL = 900, 1900, 260
MAX_SHORT_TP_DIST = 0.50


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars, NOT account P&L. ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 220), int(_env("PJ_POOL", 140))
    now = int(time.time())
    floor = W.wildcard_min_turnover_usdt()
    eq0 = rt._last_known_equity() or 158.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    N_BAND = int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0))
    lo = _env("FUTURES_REGIME_EFF_LO", 0.20)
    hi = _env("FUTURES_REGIME_EFF_HI", 0.45)
    fl = _env("FUTURES_REGIME_FLOOR_MULT", 0.25)
    print("equity $%.2f | risk %.4f | scaler %.2f/%.2f floor %.2f" % (eq0, risk_pct, lo, hi, fl))

    tk = cl.get_all_tickers() or []
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 3e5)][:pool_n]
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

    print("fetching %d symbols..." % len(cand))
    with ThreadPoolExecutor(max_workers=6) as p:
        frames = {s: f for s, f in p.map(fetch, cand) if f is not None and len(f) >= 300}
    print("frames: %d" % len(frames))

    ROLLS, PREP = {}, {}
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
        ts_all = [float(x.timestamp()) for x in df.index]
        ROLLS[s] = [(ts_all[k], roll[k]) for k in range(96, len(c))]
        PREP[s] = (df, list(zip(ts_all, [float(x) for x in df["high"]],
                                [float(x) for x in df["low"]], c)), roll, c)
    PIT = pit_majors(daily_turnover(ROLLS), n=N_BAND)

    # entries fixed once; only exits vary below
    SIG = []
    for s, (df, bars, roll, c) in PREP.items():
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < floor:
                continue
            if s in PIT.get(day_key(bars[i][0]), ()):
                continue
            if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < 0.08:
                continue
            sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
            if sig is None:
                continue
            e, sl = float(sig.entry_price), float(sig.sl_price)
            one = abs(e - sl)
            if one <= 0 or e <= 0:
                continue
            eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
            SIG.append({"ts": bars[i][0], "sym": s, "bars": bars, "i": i,
                        "e": e, "sl": sl, "side": sig.side, "slf": one / e,
                        "atr": float(getattr(sig, "atr_pct", 0.0) or 0.0),
                        "mult": regime_size_multiplier(eff, lo=lo, hi=hi, floor_mult=fl)})
    SIG.sort(key=lambda x: x["ts"])
    print("entries: %d\n" % len(SIG))

    def run(tp_r, retain, arm, rat_trig, rat_hi):
        fl_fn = (ratchet(rat_trig, rat_hi, base=retain, arm=arm) if rat_trig
                 else ratchet(99.0, retain, base=retain, arm=arm))
        out = []
        for x in SIG:
            dist = tp_r * x["slf"]
            if x["side"] == "SHORT" and dist >= MAX_SHORT_TP_DIST:
                dist = MAX_SHORT_TP_DIST
            tp = x["e"] * (1 + dist) if x["side"] == "LONG" else x["e"] * (1 - dist)
            tr_eff = (dist / x["slf"]) if x["slf"] > 0 else tp_r
            row = {"entry": x["e"], "sl": x["sl"], "tp": tp, "side": x["side"]}
            g = resolve(x["bars"], x["i"], x["e"], x["sl"], tp, tr_eff, x["side"],
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), fl_fn,
                        x["atr"], now)
            if g is None:
                continue
            out.append({"ts": x["ts"], "sym": x["sym"], "net": float(g[0]),
                        "exit_ts": float(g[1]), "mult": x["mult"]})
        out.sort(key=lambda z: z["ts"])
        slots, per, taken = [], {}, []
        for z in out:
            slots[:] = [q for q in slots if q > z["ts"]]
            per[z["sym"]] = [q for q in per.get(z["sym"], []) if q > z["ts"]]
            if per[z["sym"]] or len(slots) >= 3:
                continue
            slots.append(z["exit_ts"])
            per[z["sym"]].append(z["exit_ts"])
            taken.append(z)
        return taken

    print("%-30s %9s %9s %9s %7s %6s %9s"
          % ("exit config", "FLAT $", "LIVE $", "compound", "maxDD", "win%", "ex-top5"))
    base_live = None
    for lbl, tp_r, retain, arm, rt_, rh in (
            ("LIVE 5R / 0.30 / ratchet 3.0", 5.0, 0.30, 1.0, 3.0, 0.75),
            ("5R / 0.30 / no ratchet", 5.0, 0.30, 1.0, None, None),
            ("5R / 0.50 / ratchet 3.0", 5.0, 0.50, 1.0, 3.0, 0.75),
            ("5R / 0.70 / ratchet 3.0", 5.0, 0.70, 1.0, 3.0, 0.75),
            ("3R / 0.30 / ratchet 3.0", 3.0, 0.30, 1.0, 3.0, 0.75),
            ("2R / 0.30 / ratchet 3.0", 2.0, 0.30, 1.0, 3.0, 0.75),
            ("BANKABLE 1.5R / 0.30", 1.5, 0.30, 1.0, None, None),
            ("7R / 0.30 / ratchet 3.0", 7.0, 0.30, 1.0, 3.0, 0.75),
            ("5R / 0.30 / ratchet 2.0", 5.0, 0.30, 1.0, 2.0, 0.60),
    ):
        taken = run(tp_r, retain, arm, rt_, rh)
        f = price(taken, risk_pct=risk_pct, equity0=eq0, model="flat")
        s = price(taken, risk_pct=risk_pct, equity0=eq0, model="scaler")
        c2 = price(taken, risk_pct=risk_pct, equity0=eq0, model="compound")
        vals = sorted((t["net"] * risk_pct * eq0 * t["mult"] for t in taken), reverse=True)
        k5 = max(1, len(vals) // 20)
        ex5 = sum(vals[k5:])
        if base_live is None:
            base_live = s["net"]
        print("%-30s %+9.2f %+9.2f %+9.2f %6.1f%% %5.0f%% %+9.2f%s"
              % (lbl, f["net"], s["net"], c2["net"], 100 * c2["max_dd"],
                 s["win_pct"], ex5,
                 "" if base_live == s["net"] else "  (%+.2f vs live)" % (s["net"] - base_live)))
    print("\nex-top5 = net $ with the best 5%% of trades REMOVED - the book that")
    print("survives withdrawing the winners. Positive = bankable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
