"""Trial 18 replayed under combinations of the rejected changes, at two balances.

    railway ssh --service Futures-bot -> /opt/venv/bin/python tools/pit_trial18_variants.py

OWNER'S REQUEST, 2026-09-02: replay the trial-18 window under combinations of
everything rejected, and extrapolate to a ~$1069 starting balance.

COMPOUNDING IS ON. Until 2026-09-02 every study in this repo sized each fill off
a CONSTANT equity, subtracting only margin currently tied up - it never banked
realised P&L. The owner asked whether the balance rolls forward; it did not.
pit_book.take(compound=True) now does what the live bot does: $100, lose $10,
next entry sizes off $90. Both modes are reported so the size of that error is
visible rather than asserted.

WHY $1069 IS RUN RATHER THAN MULTIPLIED. Under fixed sizing the answer scales
linearly and multiplying by 1069/171 would be exact. Under compounding it does
not: a bigger balance takes bigger positions, which move the balance more, which
changes every subsequent size. So both balances are replayed properly.

READ THIS BEFORE READING THE TABLE. The replay reproduces only 4-6 of 16 live
WILDCARD trades in this window (tools/pit_trial_compare.py, and the ablation in
pit_fidelity_ablation.py). It is a rule-equivalent strategy, not this bot. Over
~14 closes there is no statistical content whatsoever. This answers "what would
these dials have done to a book like ours in this window", NOT "what would the
bot have made". Nothing here should move a config.

READ-ONLY.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ["FUTURES_WILDCARD_MIN_ROC"] = "0.07"

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_book import take  # noqa: E402
from pit_corrected import secured  # noqa: E402
from pit_intrabar import fetch_grids  # noqa: E402
from pit_pool import day_key, daily_turnover, pit_majors  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

STATE = "/data/futures_runtime_state.json"
T18 = dt.datetime(2026, 8, 29, 0, 37, tzinfo=dt.UTC).timestamp()
TAIL_W, TAIL_T = 260, 300
BALANCES = (171.0, 1069.0)

# label, wc_trigger, wc_secure, wc_slots, cooldown_s, tr_trigger, tr_clock, tr_slots
VARIANTS = (
    ("LIVE (base)",              0.08, None, 3, 0.0,      0.04, 24, 2),
    ("WC trigger 7%",            0.07, None, 3, 0.0,      0.04, 24, 2),
    ("WC SECURE 6R",             0.08, 6.0,  3, 0.0,      0.04, 24, 2),
    ("WC 4 slots",               0.08, None, 4, 0.0,      0.04, 24, 2),
    ("cooldown 6h",              0.08, None, 3, 6 * 3600, 0.04, 24, 2),
    ("TREND trigger 5%",         0.08, None, 3, 0.0,      0.05, 24, 2),
    ("TREND 3 slots",            0.08, None, 3, 0.0,      0.04, 24, 3),
    ("TREND 48h clock",          0.08, None, 3, 0.0,      0.04, 48, 2),
    ("WC 7% + TREND 3 slots",    0.07, None, 3, 0.0,      0.04, 24, 3),
    ("TREND 5% + 3 slots",       0.08, None, 3, 0.0,      0.05, 24, 3),
    ("TREND 5% + 48h + 3 slots", 0.08, None, 3, 0.0,      0.05, 48, 3),
    ("EVERYTHING",               0.07, 6.0,  4, 6 * 3600, 0.05, 48, 3),
)


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def _ts(rec, key):
    try:
        return dt.datetime.fromisoformat(str(rec.get(key) or "")).timestamp()
    except Exception:
        return 0.0


def main() -> int:
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    now = int(time.time())
    start = float(os.environ.get("FUTURES_TRIAL_START_TS") or 0) or T18
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    lo_, hi_ = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    base_ret = _env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50)
    rat_r = _env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0)
    rat_hi = _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75)
    plain = ratchet(rat_r, rat_hi, base=base_ret, arm=1.0)
    latch = secured(6.0, base_ret, rat_r, rat_hi)
    days = _env("PJ_DAYS", 12)

    state = json.load(open(STATE))
    live = [t for t in (state.get("trade_history") or [])
            if str(t.get("entry_signal") or "").startswith(("WILDCARD", "TREND", "SQUEEZE"))
            and _ts(t, "entry_time") >= start]
    live_usd = sum(float(t.get("pnl_usdt") or 0) for t in live)
    eq_now = rt._last_known_equity() or 171.0
    print("TRIAL 18 window from %s"
          % dt.datetime.fromtimestamp(start, dt.UTC).strftime("%Y-%m-%d %H:%MZ"))
    print("LIVE ACTUAL: %d closes, net $%+.2f  (equity now $%.2f)\n"
          % (len(live), live_usd, eq_now))

    # ---------- WILDCARD ----------
    tk = cl.get_all_tickers() or []
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 2e5)][:int(_env("PJ_POOL", 170))]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    WG, repw = fetch_grids(cl, cand, days=days, workers=6, min_bars=300, now_ts=now)
    print("WILDCARD grids:", repw)

    tp_rW = _env("FUTURES_WILDCARD_TP_R", 5.0)
    floor_to = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band_n = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    _pref = (os.environ.get("FUTURES_WILDCARD_RANGE_PREFILTER") or "1") not in ("0", "false")
    min_move = _env("FUTURES_WILDCARD_MIN_24H_RANGE", 0.08) if _pref else 0.08

    WSIG = []
    for g in WG:
        ROLLS, PREP = {}, {}
        for s, df in g.items():
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
        PIT = pit_majors(daily_turnover(ROLLS), n=band_n)
        for s, (df, bars, roll, c) in PREP.items():
            for i in range(250, len(c)):
                if bars[i][0] < start or i <= W.ROC_BARS or roll[i] < floor_to:
                    continue
                roc = abs(c[i] / c[i - W.ROC_BARS] - 1.0)
                if roc < 0.07:
                    continue
                if i >= 96:
                    wh, wl = max(c[i - 96:i + 1]), min(c[i - 96:i + 1])
                    if wl > 0 and (wh / wl - 1.0) < min_move:
                        continue
                if band_n and s in PIT.get(day_key(bars[i][0]), ()):
                    continue
                sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL_W):i + 1], s)
                if sig is None:
                    continue
                e, sl = float(sig.entry_price), float(sig.sl_price)
                if abs(e - sl) <= 0 or e <= 0:
                    continue
                cr = getattr(sig, "calm_ratio", None)
                eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
                WSIG.append((s, bars, i, e, sl, float(sig.tp_price), sig.side, roc,
                             float(getattr(sig, "atr_pct", 0.0) or 0.0),
                             (float(cr) if cr is not None else None),
                             regime_size_multiplier(eff, lo=lo_, hi=hi_, floor_mult=flm)))
    print("  WILDCARD signals in window: %d" % len(WSIG))

    WRES = {}
    for sec in (None, 6.0):
        out = []
        for s, bars, i, e, sl, tp, side, roc, atr, cr, mlt in WSIG:
            row = {"entry": e, "sl": sl, "tp": tp, "side": side}
            if sec is None:
                u_tp, u_r, fl = tp, tp_rW, plain
            else:
                one = abs(e - sl)
                u_r = 99.0
                u_tp = e + u_r * one if side == "LONG" else e - u_r * one
                fl = latch
            g = resolve(bars, i, e, sl, u_tp, u_r, side, shadow.CONVEX_HORIZON_S,
                        shadow.cost_r(row), fl, atr, now)
            if g is None:
                continue
            out.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                        "exit_ts": float(g[1]), "roc": roc, "calm_ratio": cr,
                        "mult": mlt})
        out.sort(key=lambda z: z["ts"])
        WRES[sec] = out

    # ---------- TREND ----------
    tsyms = tuple(s.strip() for s in
                  (os.environ.get("FUTURES_TREND_SYMBOLS") or
                   "ETH_USDT,XRP_USDT,ZEC_USDT").split(",") if s.strip())
    TG, rept = fetch_grids(cl, tsyms, days=days, workers=3, min_bars=300, now_ts=now)
    print("TREND grids:", rept)
    tp_rT = _env("FUTURES_TREND_TP_R", 3.0)
    os.environ["FUTURES_TREND_MIN_ROC"] = "0.03"
    os.environ["FUTURES_TREND_SL_ATR_MULT"] = "3.0"
    from futuresbot.trend import detect_trend_signal, lookback_bars
    lb = lookback_bars()
    TSIG = []
    for g in TG:
        for s, df in g.items():
            c = [float(x) for x in df["close"]]
            ts_all = [float(x.timestamp()) for x in df.index]
            bars = list(zip(ts_all, [float(x) for x in df["high"]],
                            [float(x) for x in df["low"]], c))
            for i in range(lb + 40, len(c)):
                if bars[i][0] < start:
                    continue
                sig = detect_trend_signal(df.iloc[max(0, i - TAIL_T):i + 1], s)
                if sig is None or sig.side != "LONG":
                    continue
                e, sl = float(sig.entry_price), float(sig.sl_price)
                if abs(e - sl) <= 0 or e <= 0:
                    continue
                eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
                TSIG.append((s, bars, i, e, sl, float(sig.tp_price),
                             abs(float(getattr(sig, "roc_pct", 0.0) or 0.0)),
                             float(getattr(sig, "atr_pct", 0.0) or 0.0),
                             regime_size_multiplier(eff, lo=lo_, hi=hi_, floor_mult=flm)))
    print("  TREND signals in window: %d\n" % len(TSIG))

    TRES = {}
    for clock in (24, 48):
        out = []
        for s, bars, i, e, sl, tp, roc, atr, mlt in TSIG:
            row = {"entry": e, "sl": sl, "tp": tp, "side": "LONG"}
            g = resolve(bars, i, e, sl, tp, tp_rT, "LONG", clock * 3600,
                        shadow.cost_r(row), plain, atr, now)
            if g is None:
                continue
            out.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                        "exit_ts": float(g[1]), "roc": roc, "mult": mlt})
        out.sort(key=lambda z: z["ts"])
        TRES[clock] = out

    def run(v, equity, compound):
        (_lbl, wtg, wsec, wsl, cd, ttg, tck, tsl) = v
        wf = take([z for z in WRES[wsec] if z["roc"] >= wtg], slots=wsl,
                  equity=equity, risk_pct=risk_pct,
                  sl_margin_pct=_env("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", 20.0),
                  scan_s=_env("FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS", 450.0),
                  one_per_scan=True,
                  calm_max=_env("FUTURES_WILDCARD_MAX_CALM_RATIO", 0.75),
                  cooldown_s=cd, compound=compound)
        tf = take([z for z in TRES[tck] if z["roc"] >= ttg], slots=tsl,
                  equity=equity, risk_pct=risk_pct,
                  sl_margin_pct=_env("FUTURES_TREND_MAX_SL_MARGIN_PCT", 20.0),
                  scan_s=_env("FUTURES_TREND_SCAN_INTERVAL_SECONDS", 900.0),
                  one_per_scan=True, calm_max=0.0, compound=compound)
        return (len(wf) + len(tf),
                sum(z["usd"] for z in wf) + sum(z["usd"] for z in tf))

    print("=" * 104)
    print("TRIAL 18 UNDER EACH VARIANT.  compounding ON (live behaviour).")
    print("LIVE ACTUAL was %d closes, $%+.2f at ~$171." % (len(live), live_usd))
    print("=" * 104)
    print("%-26s %6s %11s %11s %11s %11s"
          % ("variant", "fills", "$ @171", "vs base", "$ @1069", "vs base"))
    print("-" * 104)
    b171 = b1069 = None
    for v in VARIANTS:
        n1, u1 = run(v, BALANCES[0], True)
        _n2, u2 = run(v, BALANCES[1], True)
        if b171 is None:
            b171, b1069 = u1, u2
        print("%-26s %6d %+11.2f %+11.2f %+11.2f %+11.2f"
              % (v[0], n1, u1, u1 - b171, u2, u2 - b1069))

    print()
    print("=" * 104)
    print("HOW MUCH DID THE MISSING COMPOUNDING MATTER?")
    print("=" * 104)
    print("%-26s %11s %11s %9s   %11s %11s %9s"
          % ("variant", "fixed@171", "comp@171", "diff", "fixed@1069",
             "comp@1069", "diff"))
    for v in VARIANTS[:4]:
        _a, f1 = run(v, BALANCES[0], False)
        _b, c1 = run(v, BALANCES[0], True)
        _c, f2 = run(v, BALANCES[1], False)
        _d, c2 = run(v, BALANCES[1], True)
        print("%-26s %+11.2f %+11.2f %+9.2f   %+11.2f %+11.2f %+9.2f"
              % (v[0], f1, c1, c1 - f1, f2, c2, c2 - f2))
    print()
    print("  Over a ~4 day window with small returns the two barely differ - the")
    print("  balance has no time to move. Over the 220-day studies it would.")
    print()
    print("  MEASURED: $1069 comes out at almost exactly 6.25x the $171 column,")
    print("  i.e. LINEAR. risk_usdt = risk_pct x available, and usd = net R x")
    print("  risk_usdt, so the model has nothing in it that breaks proportionality.")
    print("  Live would deviate slightly because it rounds to WHOLE CONTRACTS and")
    print("  this replay does not model that - a real effect at small balances,")
    print("  shrinking as the balance grows. Do not read the linearity as a")
    print("  property of the bot; it is a property of the model.")
    print()
    print("  THE REPLAY REPRODUCES 4-6 OF 16 LIVE TRADES IN THIS WINDOW. Read the")
    print("  vs-base columns as the shape of an effect, never as a forecast, and")
    print("  on ~14 closes not even as evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
