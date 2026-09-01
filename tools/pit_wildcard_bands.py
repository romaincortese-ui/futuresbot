"""Does proximity to a GATE THRESHOLD predict quality on WILDCARD?

    railway ssh --service Futures-bot -> /opt/venv/bin/python tools/pit_wildcard_bands.py

THE TREND RESULT THIS TESTS FOR TRANSFER. On TREND, entries firing just above
the 4% trigger were the only negative band of six (85 fills, -$0.311/fill over
231 days) - the first entry-quality signal in this project to survive from a
live observation into a corrected full-coverage replay. If the effect is general
- "a signal that barely clears its gate is a weak signal" - it should appear on
WILDCARD too, where the sleeve books ~2.5x the volume and therefore where it
could actually clear the $10/month bar. If it is specific to TREND's 3-symbol
universe, it should not.

WILDCARD has THREE gated thresholds, so this asks the question three times:
    3h ROC        >= 8%      the trigger itself
    24h turnover  >= $2m     the liquidity floor
    calm_ratio    <  0.75    the shock filter, gated from ABOVE

The live 28-day read (pit_loss_context.py) showed NO near-trigger penalty on 3h
ROC - the 8-10% band ran +$0.602/trade against +$1.153 for 10-16% - but that is
n=44 on a sleeve whose per-band counts are single digits. This is the same
question at ~500 fills.

WHAT THE TREND WORK ALREADY SETTLED, so it is not re-derived here:
  a threshold RAISE does not excise a band, it RESHUFFLES THE SCHEDULE. Dropping
  trades frees slots that different trades then occupy, and the displaced set can
  dwarf the excised one (+$61.27 displaced against -$26.40 excised on TREND). So
  section B reports the reshuffle decomposition for whichever band looks worst,
  rather than assuming the band's own P&L is what a trigger change would capture.

READ-ONLY.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# The detector carries its OWN roc gate (wildcard.py:234). Lowering the loop's
# pre-check alone would not widen the pool, so this must be set before import.
ROC_FLOOR = float(os.environ.get("WCB_ROC_FLOOR") or 0.08)
os.environ["FUTURES_WILDCARD_MIN_ROC"] = str(ROC_FLOOR)

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_book import take  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_intrabar import fetch_grids  # noqa: E402
from pit_pool import day_key, daily_turnover, pit_majors  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

BAR, TAIL = 900, 260
NL = chr(10)

ROC_BANDS = ((0.03, 0.04), (0.04, 0.05), (0.05, 0.06), (0.06, 0.07),
             (0.07, 0.08), (0.08, 0.10), (0.10, 0.12), (0.12, 0.16),
             (0.16, 0.24), (0.24, 0.40), (0.40, 99.0))
TO_BANDS = ((2e6, 4e6), (4e6, 8e6), (8e6, 2e7), (2e7, 6e7), (6e7, 1e12))
CALM_BANDS = ((0.0, 0.15), (0.15, 0.30), (0.30, 0.45), (0.45, 0.60), (0.60, 0.75))
ROC_SWEEP = (0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10, 0.12)


def KEY_ROC(z):
    return z["roc"]


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY on the CORRECTED book - model dollars, not P&L ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    now = int(time.time())
    days, pool_n = _env("PJ_DAYS", 220), int(_env("PJ_POOL", 170))
    eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    slots = int(_env("FUTURES_WILDCARD_MAX_POSITIONS", 3))
    tp_r = _env("FUTURES_WILDCARD_TP_R", 5.0)
    scan_s = _env("FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS", 900.0)
    slmp = _env("FUTURES_MAX_SL_MARGIN_PCT", 20.0)
    lo_, hi_ = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    floor_to = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band_n = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    calm_max = _env("FUTURES_WILDCARD_MAX_CALM_RATIO", 0.75)
    # DEFECT FIXED 2026-09-01. Live resolves this gate through the RANGE branch,
    # not the MOVE branch: FUTURES_WILDCARD_RANGE_PREFILTER defaults TRUE, so
    # min_move = FUTURES_WILDCARD_MIN_24H_RANGE, which is unset and therefore
    # DEFAULTS TO min_roc = 0.08 (runtime.py:5765-5769). Reading
    # FUTURES_WILDCARD_MIN_24H_MOVE=0.03 instead applied a 3% gate where the bot
    # applies 8%, admitting a far wider universe - the live scan reports
    # movers=39-42 while this replay was scanning ~170.
    _pref = (os.environ.get("FUTURES_WILDCARD_RANGE_PREFILTER") or "1") not in ("0", "false", "False")
    _roc_live = _env("FUTURES_WILDCARD_MIN_ROC_LIVE", 0.08)
    min_move = (_env("FUTURES_WILDCARD_MIN_24H_RANGE", _roc_live) if _pref
                else _env("FUTURES_WILDCARD_MIN_24H_MOVE", 0.08))
    fn = ratchet(_env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0),
                 _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75),
                 base=_env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50), arm=1.0)

    print("ROC floor for this run: %.1f%% (live trigger is 8.0%%)" % (ROC_FLOOR * 100))
    print("%d slots | TP %.1fR | trigger 3h ROC >= 8%% | turnover >= $%.1fm | "
          "calm < %.2f" % (slots, tp_r, floor_to / 1e6, calm_max))
    print("equity $%.2f | risk %.3f%% of AVAILABLE | sl margin %.0f%%\n"
          % (eq0, risk_pct * 100, slmp))

    tk = cl.get_all_tickers() or []
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 2e5)][:pool_n]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    # INTRA-BAR (2026-09-01, default ON). Live evaluates a PARTIALLY FORMED
    # 15m candle every 450s, so completed-bar replays cannot fire where live
    # fires. The ablation attributed 63% of the dollar error against the live
    # book to this. PIT_INTRABAR=0 reproduces the old completed-bar numbers.
    intrabar = (os.environ.get("PIT_INTRABAR") or "1") not in ("0", "false", "False")
    if intrabar:
        GRIDS, rep = fetch_grids(cl, cand, days=days, workers=6, min_bars=300,
                                 now_ts=now)
        print("INTRA-BAR: 3 phase grids,", [len(g) for g in GRIDS], "symbols each")
    else:
        _f, rep = fetch_frames(cl, cand, days=days, workers=6, min_bars=300,
                               now_ts=now)
        GRIDS = [_f]
        print("COMPLETED-BAR (legacy path)")
    print(rep)

    C = []
    for _frames in GRIDS:
        frames = _frames
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
        PIT = pit_majors(daily_turnover(ROLLS), n=band_n)

        for s, (df, bars, roll, c) in PREP.items():
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or roll[i] < floor_to:
                    continue
                roc = abs(c[i] / c[i - W.ROC_BARS] - 1.0)
                if roc < ROC_FLOOR:
                    continue
                # live prefilter that the band tool originally omitted:
                # FUTURES_WILDCARD_MIN_24H_MOVE, immaterial at a 8% trigger but
                # binding once the trigger drops toward it
                if i >= 96:
                    w_hi, w_lo = max(c[i - 96:i + 1]), min(c[i - 96:i + 1])
                    if w_lo > 0 and (w_hi / w_lo - 1.0) < min_move:
                        continue
                if band_n and s in PIT.get(day_key(bars[i][0]), ()):
                    continue
                sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
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
                eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
                cr = getattr(sig, "calm_ratio", None)
                C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                          "exit_ts": float(g[1]), "roc": roc, "turn": roll[i],
                          "calm_ratio": (float(cr) if cr is not None else None),
                          "side": sig.side,
                          "mult": regime_size_multiplier(eff, lo=lo_, hi=hi_, floor_mult=flm)})
    C.sort(key=lambda z: z["ts"])
    print("candidates past every gate except calm: %d\n" % len(C))

    def book(pool=None, calm=None):
        return take(C if pool is None else pool, slots=slots, equity=eq0,
                    risk_pct=risk_pct, sl_margin_pct=slmp, scan_s=scan_s,
                    one_per_scan=True,
                    calm_max=(calm_max if calm is None else calm))

    BASE = book(pool=[z for z in C if z["roc"] >= 0.08])
    if not BASE:
        print("no fills")
        return 1
    t0, t1 = BASE[0]["ts"], BASE[-1]["ts"]
    base_usd = sum(z["usd"] for z in BASE)
    print("LIVE book: %d fills over %.0f days, net $%+.2f, $%.3f/fill\n"
          % (len(BASE), (t1 - t0) / 86400.0, base_usd, base_usd / len(BASE)))

    def bandtable(title, key, bands, fmt):
        print("=" * 88)
        print(title)
        print("=" * 88)
        print("  %-18s %6s %6s %10s %10s %10s"
              % ("band", "fills", "wins", "net $", "$/fill", "mean R"))
        worst, worst_pf = None, None
        for a, b in bands:
            src = (POOL_ALL if key is KEY_ROC else BASE)
            g = [z for z in src if key(z) is not None and a <= key(z) < b]
            if len(g) < 5:
                continue
            u = sum(z["usd"] for z in g)
            pf = u / len(g)
            if worst_pf is None or pf < worst_pf:
                worst, worst_pf = (a, b), pf
            print("  %-18s %6d %6d %+10.2f %+10.3f %+10.3f"
                  % (fmt(a, b), len(g), sum(1 for z in g if z["net"] > 0), u, pf,
                     sum(z["net"] for z in g) / len(g)))
        print("  %-18s %6d %6d %+10.2f %+10.3f %+10.3f"
              % ("ALL", len(BASE), sum(1 for z in BASE if z["net"] > 0), base_usd,
                 base_usd / len(BASE), sum(z["net"] for z in BASE) / len(BASE)))
        print()
        return worst, worst_pf

    POOL_ALL = book(pool=C)
    print("BELOW-TRIGGER POOL: %d fills if the trigger were %.0f%% instead of "
          "8%%, net $%+.2f" % (len(POOL_ALL), ROC_FLOOR * 100,
                              sum(z["usd"] for z in POOL_ALL)))
    print()
    w_roc, pf_roc = bandtable(
        "A1. by 3h ROC - bands BELOW 8% are booked from the WIDENED pool," + NL
        + "    i.e. they are exactly what live never takes", KEY_ROC,
        ROC_BANDS, lambda a, b: ("%.0f - %.0f%%" % (a * 100, b * 100) if b < 90
                                 else ">= %.0f%%" % (a * 100)))
    w_to, pf_to = bandtable(
        "A2. by 24h turnover at entry - the floor is $2m", lambda z: z["turn"],
        TO_BANDS, lambda a, b: ("$%.0fm - $%.0fm" % (a / 1e6, b / 1e6) if b < 1e11
                                else ">= $%.0fm" % (a / 1e6)))
    w_cr, pf_cr = bandtable(
        "A3. by calm_ratio at entry - the filter refuses at 0.75",
        lambda z: z["calm_ratio"], CALM_BANDS,
        lambda a, b: "%.2f - %.2f" % (a, b))

    print("=" * 88)
    print("B. THE TRIGGER SWEEP - does raising 8%% pay, after the reshuffle?")
    print("=" * 88)
    print("%-9s %6s %10s %10s %10s %8s %6s   %s"
          % ("trigger", "fills", "net $", "vs live", "ex-top5", "$/fill", "both?", "thirds"))

    def halves(f, frac):
        cut = t0 + (t1 - t0) * frac
        return (sum(z["usd"] for z in f if z["ts"] < cut),
                sum(z["usd"] for z in f if z["ts"] >= cut))

    for thr in ROC_SWEEP:
        f = book(pool=[z for z in C if z["roc"] >= thr])
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
        print("%-9s %6d %+10.2f %+10.2f %+10.2f %8.3f %6s   %+6.1f %+6.1f %+6.1f"
              % ("%.0f%%" % (thr * 100), len(f), u, u - base_usd, ex5, u / len(f),
                 "base" if abs(thr - 0.08) < 1e-9 else ("YES" if ok else "no"), *th))

    print()
    print("=" * 88)
    print("C. VERDICT")
    print("=" * 88)
    print("  worst 3h-ROC band     : %s at $%+.3f/fill"
          % ("%.0f-%.0f%%" % (w_roc[0] * 100, w_roc[1] * 100) if w_roc else "-",
             pf_roc if pf_roc is not None else 0.0))
    print("  worst turnover band   : %s at $%+.3f/fill"
          % ("$%.0fm-$%.0fm" % (w_to[0] / 1e6, w_to[1] / 1e6) if w_to else "-",
             pf_to if pf_to is not None else 0.0))
    print("  worst calm_ratio band : %s at $%+.3f/fill"
          % ("%.2f-%.2f" % w_cr if w_cr else "-",
             pf_cr if pf_cr is not None else 0.0))
    print()
    print("  TREND comparison: its near-trigger band ran $-0.311/fill against a")
    print("  sleeve mean of $+0.575. The question is whether ANY WILDCARD band is")
    print("  negative, and whether the near-trigger one in particular is.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
