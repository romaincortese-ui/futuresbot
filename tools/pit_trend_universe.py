"""Should the TREND sleeve trade more than three symbols?

    railway ssh -> setsid nohup /opt/venv/bin/python tools/pit_trend_universe.py

THE CASE FOR ASKING. FUTURES_TREND_SYMBOLS is ETH, XRP, ZEC - three symbols, and
nothing in the record says three is right; it is simply what was configured.
TREND books 17 lifetime closes against WILDCARD's 84, at a comparable per-trade
rate (+$0.28 vs +$0.22). So its universe, not its edge, is what limits it.

WHY THIS MATTERS MORE THAN IT LOOKS. The drought work established that this
bot's P&L variance is mostly its own SAMPLE SIZE: a 28-trade convex book turns a
1.1-standard-error wobble in universe follow-through into a $40 swing
(tools/pit_drought_persistence.py). Seventeen regime formulations failed to
predict that wobble. More trades per unit time is the only lever that shrinks
the amplification without touching expectancy, and expanding a three-symbol
universe is its most concrete form.

A CORRECTION CARRIED FORWARD. On 2026-09-03 I described TREND as "the profitable
sleeve" from trial 18, where it ran +$2.64/trade against WILDCARD's -$0.47. Over
ALL history the two are near-identical. Trial 18 is 6 TREND closes. The case
here rests on trade COUNT, not on TREND being better.

WHAT IS HELD FIXED. Slots stay at the live 2, so this measures the universe and
not capacity - adding both at once would confound them, and the slot question
was answered separately (3 slots, +$9.15, the only cell to clear the screen).
Trigger 4%, clock 24h, stop 3.0x, long-only: all live values.

READ DOLLARS AND $/FILL. More symbols always take more fills, so net $ rises
almost mechanically. The question is whether the MARGINAL fill pays.

READ-ONLY.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_book import take  # noqa: E402
from pit_intrabar import fetch_grids  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

TAIL = 300
LIVE_SET = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
# candidate additions, in descending order of 24h turnover among majors
EXTRA = ("SOL_USDT", "BNB_USDT", "DOGE_USDT", "ADA_USDT", "LINK_USDT",
         "AVAX_USDT", "LTC_USDT", "DOT_USDT")


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** INTRA-BAR REPLAY on the CORRECTED book - model dollars ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    now = int(time.time())
    days = _env("PJ_DAYS", 220)
    # PINNED, not live equity. Reading _last_known_equity() made two runs an hour
    # apart disagree by $8.66 on the SAME config, because sizing scales with
    # equity and the boundary resolution moves with `now`. A harness whose own
    # calibration drifts cannot bound anything. Override with PJ_EQUITY.
    eq0 = _env("PJ_EQUITY", 170.0)
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    slots = int(_env("FUTURES_TREND_MAX_POSITIONS", 2))
    tp_r = _env("FUTURES_TREND_TP_R", 3.0)
    scan_s = _env("FUTURES_TREND_SCAN_INTERVAL_SECONDS", 900.0)
    slmp = _env("FUTURES_TREND_MAX_SL_MARGIN_PCT", 20.0)
    lo_, hi_ = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    trig = _env("FUTURES_TREND_MIN_ROC", 0.04)
    horizon = shadow.CONVEX_HORIZON_S
    fn = ratchet(_env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0),
                 _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75),
                 base=_env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50), arm=1.0)
    os.environ["FUTURES_TREND_SL_ATR_MULT"] = "3.0"
    os.environ["FUTURES_TREND_MIN_ROC"] = str(trig)

    universe = LIVE_SET + EXTRA
    GRIDS, rep = fetch_grids(cl, universe, days=days, workers=4, min_bars=2000,
                             now_ts=now)
    print(rep)
    have = sorted({s for g in GRIDS for s in g})
    print("symbols with data: %d of %d -> %s"
          % (len(have), len(universe), ", ".join(s.replace("_USDT", "") for s in have)))
    missing = [s for s in universe if s not in have]
    if missing:
        print("  MISSING (excluded from every cell): %s"
              % ", ".join(s.replace("_USDT", "") for s in missing))

    from futuresbot.trend import detect_trend_signal, lookback_bars
    lb = lookback_bars()
    SIG = {}
    for g in GRIDS:
        for s, df in g.items():
            c = [float(x) for x in df["close"]]
            ts_all = [float(x.timestamp()) for x in df.index]
            bars = list(zip(ts_all, [float(x) for x in df["high"]],
                            [float(x) for x in df["low"]], c))
            out = SIG.setdefault(s, [])
            for i in range(lb + 40, len(c)):
                sig = detect_trend_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                if sig is None or sig.side != "LONG":
                    continue
                e, sl = float(sig.entry_price), float(sig.sl_price)
                if abs(e - sl) <= 0 or e <= 0:
                    continue
                row = {"entry": e, "sl": sl, "tp": float(sig.tp_price), "side": "LONG"}
                res = resolve(bars, i, e, sl, float(sig.tp_price), tp_r, "LONG",
                              horizon, shadow.cost_r(row), fn,
                              float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if res is None:
                    continue
                eff = trend_efficiency(c[:i + 1],
                                       int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
                out.append({"ts": bars[i][0], "sym": s, "net": float(res[0]),
                            "exit_ts": float(res[1]), "kind": str(res[2]),
                            "mult": regime_size_multiplier(eff, lo=lo_, hi=hi_,
                                                           floor_mult=flm)})
    for s in SIG:
        SIG[s].sort(key=lambda z: z["ts"])
    print("signals per symbol: %s\n"
          % {s.replace("_USDT", ""): len(SIG.get(s, [])) for s in have})

    def book(syms, n_slots=None):
        pool = []
        for s in syms:
            pool += SIG.get(s, [])
        pool.sort(key=lambda z: z["ts"])
        return take(pool, slots=(slots if n_slots is None else n_slots),
                    equity=eq0, risk_pct=risk_pct,
                    sl_margin_pct=slmp, scan_s=scan_s, one_per_scan=True,
                    calm_max=0.0, compound=True)

    live_syms = [s for s in LIVE_SET if s in have]
    BASE = book(live_syms)
    if not BASE:
        print("no fills on the live set")
        return 1
    t0, t1 = BASE[0]["ts"], BASE[-1]["ts"]
    base_usd = sum(z["usd"] for z in BASE)

    def halves(f, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(z["usd"] for z in f if z["ts"] < cut),
                sum(z["usd"] for z in f if z["ts"] >= cut))

    # ---- CALIBRATION, demanded before any delta is read ----
    # The owner asked (2026-09-03) whether the replay reproduces the live bot.
    # It does not, and this prints by how much on THIS harness rather than
    # relying on the figures measured elsewhere. Deltas below are only worth
    # reading if they are large against this error.
    import datetime as _dt
    import json as _json
    _lu, _start = 0.0, 0.0
    try:
        _st = _json.load(open("/data/futures_runtime_state.json"))
        _start = float(os.environ.get("FUTURES_TRIAL_START_TS") or 0)
        def _ts(t, k):
            try:
                return _dt.datetime.fromisoformat(str(t.get(k) or "")).timestamp()
            except Exception:
                return 0.0
        _live = [t for t in (_st.get("trade_history") or [])
                 if str(t.get("entry_signal") or "").startswith("TREND")
                 and _ts(t, "entry_time") >= _start]
        _lu = sum(float(t.get("pnl_usdt") or 0) for t in _live)
        _w = [z for z in BASE if z["ts"] >= _start]
        _wu = sum(z["usd"] for z in _w)
        print("=" * 104)
        print("CALIBRATION: does this harness reproduce the live bot on TREND?")
        print("=" * 104)
        print("  trial 18 window, TREND sleeve only")
        print("    LIVE   %2d closes  $%+8.2f" % (len(_live), _lu))
        print("    REPLAY %2d fills   $%+8.2f" % (len(_w), _wu))
        print("    HARNESS ERROR              $%+8.2f" % (_wu - _lu))
        print("  -> any delta below smaller than this error is not readable.")
        print()
    except Exception as _exc:
        print("  (calibration failed: %s)" % _exc)

    print("=" * 104)
    print("ADDING SYMBOLS, one at a time, SLOTS HELD AT %d" % slots)
    print("=" * 104)
    print("%-34s %6s %10s %10s %8s %9s %6s   %s"
          % ("universe", "fills", "net $", "vs live", "$/fill", "marginal",
             "both?", "thirds"))
    prev_u, prev_n = None, None
    cur = list(live_syms)
    rows = [("LIVE: " + ",".join(s.replace("_USDT", "") for s in cur), list(cur))]
    for x in EXTRA:
        if x not in have:
            continue
        cur = cur + [x]
        rows.append(("+ " + x.replace("_USDT", ""), list(cur)))
    for label, syms in rows:
        f = book(syms)
        if not f:
            continue
        u = sum(z["usd"] for z in f)
        vals = sorted((z["usd"] for z in f), reverse=True)
        ex5 = sum(vals[max(1, len(vals) // 20):])
        ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                    *halves(f, fr), *halves(BASE, fr))
                 for fr in (0.35, 0.425, 0.5, 0.575, 0.65))
        th = []
        for k in range(3):
            a = t0 + k * (t1 - t0) / 3.0
            b = t0 + (k + 1) * (t1 - t0) / 3.0 + (1 if k == 2 else 0)
            th.append(sum(z["usd"] for z in f if a <= z["ts"] < b))
        marg = ("%+9.3f" % ((u - prev_u) / (len(f) - prev_n))
                if prev_u is not None and len(f) > prev_n else "        -")
        print("%-34s %6d %+10.2f %+10.2f %8.3f %s %6s   %+6.1f %+6.1f %+6.1f"
              % (label[:34], len(f), u, u - base_usd, u / len(f), marg,
                 "base" if label.startswith("LIVE") else ("YES" if ok else "no"),
                 *th))
        prev_u, prev_n = u, len(f)

    print()
    print("Read $/fill and 'marginal', not net $. More symbols always take more")
    print("fills. The question is whether the MARGINAL fill pays - and whether")
    print("the extra trade count actually arrives, since 2 slots still bind.")

    print()
    print("=" * 104)
    print("SLOT SWEEP at the LIVE universe (%s), symbols held fixed"
          % ",".join(x.replace("_USDT", "") for x in live_syms))
    print("=" * 104)
    print("  The universe sweep above showed adding SYMBOLS dilutes because the")
    print("  2-slot cap binds. So the capacity question is asked directly here,")
    print("  with the same calibration and the same screen.")
    print()
    print("  %-8s %6s %10s %10s %8s %9s %6s   %s"
          % ("slots", "fills", "net $", "vs live", "$/fill", "marginal",
             "both?", "thirds"))
    prev_u2, prev_n2 = None, None
    for n in (1, 2, 3, 4):
        f = book(live_syms, n_slots=n)
        if not f:
            continue
        u = sum(z["usd"] for z in f)
        vals = sorted((z["usd"] for z in f), reverse=True)
        ex5 = sum(vals[max(1, len(vals) // 20):])
        ok = all((lambda bo, br, zo, zr: bo - zo > 0 and br - zr > 0)(
                    *halves(f, fr), *halves(BASE, fr))
                 for fr in (0.35, 0.425, 0.5, 0.575, 0.65))
        th = []
        for k in range(3):
            a = t0 + k * (t1 - t0) / 3.0
            b = t0 + (k + 1) * (t1 - t0) / 3.0 + (1 if k == 2 else 0)
            th.append(sum(z["usd"] for z in f if a <= z["ts"] < b))
        marg = ("%+9.3f" % ((u - prev_u2) / (len(f) - prev_n2))
                if prev_u2 is not None and len(f) > prev_n2 else "        -")
        # calibration for THIS cell over the trial-18 window
        try:
            w = [z for z in f if z["ts"] >= _start]
            cal = " | t18 replay $%+.2f vs live $%+.2f" % (
                sum(z["usd"] for z in w), _lu)
        except Exception:
            cal = ""
        print("  %-8s %6d %+10.2f %+10.2f %8.3f %s %6s   %+6.1f %+6.1f %+6.1f%s"
              % ("%d%s" % (n, "  LIVE" if n == slots else ""), len(f), u,
                 u - base_usd, u / len(f), marg,
                 "base" if n == slots else ("YES" if ok else "no"), *th,
                 cal if n == slots else ""))
        prev_u2, prev_n2 = u, len(f)
    print()
    print("  4 slots should equal 3: the universe is 3 symbols and take() already")
    print("  enforces one position per symbol, so 3 is the structural ceiling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
