"""When, if ever, should the bot switch from CONVEX to SQUEEZE?

    railway ssh -> setsid nohup /opt/venv/bin/python tools/pit_squeeze_switch.py

THE OWNER'S PROPOSAL (2026-09-02): when the majors are down, stop trading the
convex sleeve and run PMT / Squeeze / Sniper instead.

WHAT THE LIVE RECORD ALREADY SETTLED. PMT is disqualified on its own evidence -
55 closes, -$101.23, and -$1.182/trade in exactly the DOWN regime the rule would
deploy it in, against convex's -$0.130. Sniper has ZERO down-market closes.
Squeeze is the only live thread: +$0.454/trade over FOUR down-market trades,
the single positive down-market cell anywhere in the history.

WHY THIS IS A REPLAY AND NOT A SWEEP. Squeeze has 13 lifetime closes. Running
"more combinations" over 13 trades manufactures winners - it is the exact failure
mode that produced and then destroyed half of this week's findings. So the sample
is rebuilt by replaying the real detector over 220 days, the same way WILDCARD
and TREND were.

COMPLETED BARS, deliberately. Intra-bar phase grids matter when reproducing the
bot's FILL timing, and they overturned several WILDCARD results. Here the
question is RELATIVE - squeeze against convex on one harness - so the fidelity
error is largely common-mode, and completed bars cost a third of the compute.
Absolute dollars here are not live-comparable; only the comparison is.

THE PLACEBO CONTROL APPLIES. A switch rule is keyed on TIME, so it faces
tools/pit_placebo.py like every other regime study. Seventeen have failed.

READ-ONLY.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from futuresbot.squeeze import detect_squeeze_signal  # noqa: E402
from pit_book import take  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_placebo import placebo_test  # noqa: E402
from pit_pool import day_key, daily_turnover, pit_majors  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

TAIL = 260


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - relative comparison only, not account P&L ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    now = int(time.time())
    days, pool_n = _env("PJ_DAYS", 220), int(_env("PJ_POOL", 170))
    eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    lo_, hi_ = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    floor_to = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band_n = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    calm_max = _env("FUTURES_WILDCARD_MAX_CALM_RATIO", 0.75)
    fn = ratchet(_env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0),
                 _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75),
                 base=_env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50), arm=1.0)
    sq_slots = int(_env("FUTURES_SQUEEZE_MAX_POSITIONS", 1))
    sq_tp = _env("FUTURES_SQUEEZE_TP_R", 5.0)
    wc_slots = int(_env("FUTURES_WILDCARD_MAX_POSITIONS", 3))
    wc_tp = _env("FUTURES_WILDCARD_TP_R", 5.0)
    print("squeeze: %d slot(s) TP %.1fR | wildcard: %d slots TP %.1fR | equity $%.2f"
          % (sq_slots, sq_tp, wc_slots, wc_tp, eq0))

    tk = cl.get_all_tickers() or []
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 2e5)][:pool_n]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    frames, rep = fetch_frames(cl, tuple(cand) + ("BTC_USDT",), days=days,
                               workers=6, min_bars=300, now_ts=now, strict=False)
    print(rep)

    BT = [float(x.timestamp()) for x in frames["BTC_USDT"].index]
    BC = [float(x) for x in frames["BTC_USDT"]["close"]]

    def btc24(t):
        i = None
        for k in range(len(BT) - 1, -1, -1):
            if BT[k] <= t:
                i = k
                break
        if i is None or i < 96 or not BC[i - 96]:
            return None
        return (BC[i] / BC[i - 96] - 1.0) * 100.0

    ROLLS, PREP = {}, {}
    for s, df in frames.items():
        if s == "BTC_USDT":
            continue
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

    # Vectorised coil map: 2*std(20) < 1.5*ATR(20) is the squeeze condition
    # (squeeze.py BB_PERIOD/KC_PERIOD 20, BB_K 2.0, KC_MULT 1.5). A release can
    # only follow a coil, so a bar with no coil in the trailing MIN_LEN window
    # cannot emit. Deliberately LOOSE - it never drops a bar the detector would
    # have accepted, it only skips bars it certainly would not.
    import numpy as np
    coil_lb = int(_env("FUTURES_SQUEEZE_MIN_LEN", 6)) + 2
    bb_k = _env("FUTURES_SQUEEZE_BB_K", 2.0)
    kc_m = _env("FUTURES_SQUEEZE_KC_MULT", 1.5)
    COIL = {}
    for s, (df, bars, roll, c) in PREP.items():
        cl_s = df["close"].astype(float)
        std = cl_s.rolling(20).std()
        hi_s = df["high"].astype(float)
        lo_s = df["low"].astype(float)
        pc = cl_s.shift(1)
        tr = np.maximum(hi_s - lo_s,
                        np.maximum((hi_s - pc).abs(), (lo_s - pc).abs()))
        atr = tr.rolling(20).mean()
        squeezed = (bb_k * std) < (kc_m * atr)
        # allow a release up to coil_lb bars after the coil
        rel = squeezed.rolling(coil_lb, min_periods=1).max().fillna(0).to_numpy()
        COIL[s] = [bool(x) for x in rel]
    kept = sum(sum(1 for x in v if x) for v in COIL.values())
    tot = sum(len(v) for v in COIL.values())
    print("coil pre-gate keeps %d of %d bars (%.0f%%)" % (kept, tot, 100.0*kept/max(1, tot)))

    def build(kind):
        out = []
        for s, (df, bars, roll, c) in PREP.items():
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or roll[i] < floor_to:
                    continue
                if kind == "WILDCARD":
                    if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < 0.08:
                        continue
                    if band_n and s in PIT.get(day_key(bars[i][0]), ()):
                        continue
                    sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                    tp_r = wc_tp
                else:
                    # CHEAP PRE-GATE. The squeeze detector has no equivalent of
                    # wildcard's ROC check, so calling it on every bar means ~1M
                    # pandas slices and the run never finishes. Its own first
                    # gate is a Bollinger-inside-Keltner coil, which is computed
                    # vectorised once per symbol below; only bars where a coil
                    # was present in the preceding window can produce a release,
                    # so skipping the rest cannot drop a signal.
                    if not COIL[s][i]:
                        continue
                    sig = detect_squeeze_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                    tp_r = sq_tp
                if sig is None:
                    continue
                e, sl = float(sig.entry_price), float(sig.sl_price)
                if abs(e - sl) <= 0 or e <= 0:
                    continue
                row = {"entry": e, "sl": sl, "tp": float(sig.tp_price), "side": sig.side}
                g = resolve(bars, i, e, sl, float(sig.tp_price), tp_r, sig.side,
                            shadow.CONVEX_HORIZON_S, shadow.cost_r(row), fn,
                            float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if g is None:
                    continue
                cr = getattr(sig, "calm_ratio", None)
                eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
                out.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                            "exit_ts": float(g[1]),
                            "calm_ratio": (float(cr) if cr is not None else None),
                            "btc": btc24(bars[i][0]),
                            "mult": regime_size_multiplier(eff, lo=lo_, hi=hi_,
                                                           floor_mult=flm)})
        out.sort(key=lambda z: z["ts"])
        return out

    WC = build("WILDCARD")
    SQ = build("SQUEEZE")
    print("signals: WILDCARD %d, SQUEEZE %d (live squeeze history is 13 closes)\n"
          % (len(WC), len(SQ)))
    if len(SQ) < 50:
        print("too few squeeze signals to analyse")
        return 1

    def book(pool, slots, cd=0.0):
        return take(pool, slots=slots, equity=eq0, risk_pct=risk_pct,
                    sl_margin_pct=_env("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", 20.0),
                    scan_s=_env("FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS", 450.0),
                    one_per_scan=True, calm_max=calm_max, compound=True)

    base = book(WC, wc_slots)
    base_usd = sum(z["usd"] for z in base)
    sq_all = book(SQ, sq_slots)
    print("=" * 96)
    print("A. EACH SLEEVE ALONE, BY BTC 24h REGIME")
    print("=" * 96)
    print("  %-10s %-14s %6s %10s %10s" % ("sleeve", "band", "fills", "net $", "$/fill"))
    for nm, f in (("CONVEX", base), ("SQUEEZE", sq_all)):
        for bn, lo2, hi2 in (("DOWN < -1%", -99, -1.0), ("FLAT -1..+1", -1.0, 1.0),
                             ("UP > +1%", 1.0, 99)):
            g = [z for z in f if z["btc"] is not None and lo2 <= z["btc"] < hi2]
            if len(g) < 5:
                continue
            u = sum(z["usd"] for z in g)
            print("  %-10s %-14s %6d %+10.2f %+10.3f" % (nm, bn, len(g), u, u / len(g)))
        u = sum(z["usd"] for z in f)
        print("  %-10s %-14s %6d %+10.2f %+10.3f" % (nm, "ALL", len(f), u, u / len(f)))
        print("  " + "-" * 60)

    print()
    print("=" * 96)
    print("B. THE SWITCH: convex above the threshold, squeeze below it")
    print("=" * 96)
    print("  %-28s %6s %10s %10s  %s"
          % ("rule", "fills", "net $", "vs convex", "placebo verdict"))
    for thr in (-2.0, -1.0, 0.0, 1.0):
        wc_on = [z for z in WC if z["btc"] is not None and z["btc"] >= thr]
        sq_on = [z for z in SQ if z["btc"] is not None and z["btc"] < thr]
        f = book(wc_on, wc_slots) + book(sq_on, sq_slots)
        u = sum(z["usd"] for z in f)
        merged = sorted(f, key=lambda z: z["ts"])
        gate_thr = thr

        def gate(t, _thr=gate_thr):
            b = btc24(t)
            return b is not None
        res = placebo_test(merged, lambda t: True, time_of=lambda x: x["ts"],
                           value_of=lambda x: x["usd"], min_n=5)
        # the switch itself is the object under test: shift the BTC signal
        def switched(shift_s):
            a = [z for z in WC if (btc24(z["ts"] + shift_s) or -99) >= thr]
            b = [z for z in SQ if (btc24(z["ts"] + shift_s) or 99) < thr]
            return sum(x["usd"] for x in book(a, wc_slots)) + \
                sum(x["usd"] for x in book(b, sq_slots))
        shifts = [d * 86400.0 for d in (-21, -14, -10, -7, -5, 5, 7, 10, 14, 21)]
        pl = [switched(s) for s in shifts]
        beaten = sum(1 for v in pl if v >= u)
        verdict = ("SURVIVES" if beaten == 0 else
                   "WEAK" if beaten <= 1 else "REFUTED (%d/%d placebos matched)"
                   % (beaten, len(pl)))
        print("  %-28s %6d %+10.2f %+10.2f  %s"
              % ("squeeze when BTC24 < %+.0f%%" % thr, len(f), u, u - base_usd, verdict))

    print()
    print("  Placebos shift the BTC signal by +-5 to +-21 days: same switching")
    print("  behaviour, no information about the market each trade traded in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
