"""Trials 17+18 only: convex vs squeeze, split by the top-5 majors' 24h move.

    railway ssh -> /opt/venv/bin/python tools/pit_t1718_switch.py

THE OWNER'S RULE (2026-09-03): take the five biggest symbols by volume - BTC,
ETH, SOL and the next two - and check their 24h return. If negative, run SQUEEZE
instead of CONVEX.

WHY THIS VERSION IS TRACTABLE AND THE LAST ONE WAS NOT. A full 220-day squeeze
replay needs ~885k detector calls, because squeeze has no cheap pre-filter the
way wildcard's 3h-ROC check is: a Bollinger-inside-Keltner coil is present 42%
of the time. Restricting to the ~7-day trial window cuts that by ~30x.

SQUEEZE HAS NOT TRADED SINCE 2026-07-31, so there are ZERO live squeeze trades
in this window. Both sleeves are therefore REPLAYED on one harness so the
comparison is like-for-like, and convex's LIVE result is printed beside its
replay so the harness error is visible rather than assumed.

THE SAMPLE IS ~7 DAYS. Nothing here can be significant. It answers "what would
this rule have done in the window the owner asked about", not "does this rule
work". The placebo control needs far more data than a week provides.

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

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from futuresbot.squeeze import detect_squeeze_signal  # noqa: E402
from pit_book import take  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_pool import day_key, daily_turnover, pit_majors  # noqa: E402
from pit_ratchet import ratchet  # noqa: E402
from retention_trail_ab import resolve  # noqa: E402

WIN_START = dt.datetime(2026, 8, 27, tzinfo=dt.UTC).timestamp()
STATE = "/data/futures_runtime_state.json"
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
    now = int(time.time())
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

    tk = cl.get_all_tickers() or []
    ranked = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or ""))
                     for t in tk if str(t.get("symbol") or "").endswith("_USDT")),
                    reverse=True)
    # CRYPTO majors only. Raw top-5-by-volume returns BTC, ETH, SOL, XAU, XAUT -
    # the last two are TOKENISED GOLD, so requiring them to be down makes the
    # rule partly a bet on bullion. The owner asked for "BTC, SOL, ETH and the
    # next 2 biggest", meaning the next two biggest CRYPTO.
    TOP5 = [s for _, s in ranked if rt._is_tradeable_crypto(s)][:5]
    excluded = [s for _, s in ranked[:8] if s not in TOP5][:4]
    print("TOP 5 CRYPTO BY 24h VOLUME: %s"
          % ", ".join(s.replace("_USDT", "") for s in TOP5))
    if excluded:
        print("  excluded as non-crypto: %s"
              % ", ".join(s.replace("_USDT", "") for s in excluded))

    crypto = [s for a, s in ranked if rt._is_tradeable_crypto(s)
              and a >= _env("PJ_MIN_TODAY", 2e5)][:int(_env("PJ_POOL", 170))]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    universe = tuple(dict.fromkeys(list(crypto) + TOP5))
    frames, rep = fetch_frames(cl, universe, days=_env("PJ_DAYS", 14), workers=6,
                               min_bars=300, now_ts=now, strict=False)
    print(rep)

    MAJ = {}
    for s in TOP5:
        if s in frames:
            MAJ[s] = ([float(x.timestamp()) for x in frames[s].index],
                      [float(x) for x in frames[s]["close"]])
    print("majors with data: %d of 5" % len(MAJ))

    def top5_rets(t):
        vals = []
        for s, (ts_, c) in MAJ.items():
            i = None
            for k in range(len(ts_) - 1, -1, -1):
                if ts_[k] <= t:
                    i = k
                    break
            if i is None or i < 96 or not c[i - 96]:
                continue
            vals.append(c[i] / c[i - 96] - 1.0)
        return vals

    def top5_down(t):
        """(all_down, counts_at_each_threshold)."""
        vals = top5_rets(t)
        if not vals:
            return None
        counts = {thr: sum(1 for v in vals if v * 100.0 < thr)
                  for thr in (0.0, -0.25, -0.5, -0.75, -1.0)}
        return max(vals) < 0.0, counts

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

    def build(kind):
        out = []
        for s, (df, bars, roll, c) in PREP.items():
            for i in range(250, len(c)):
                if bars[i][0] < WIN_START or i <= W.ROC_BARS or roll[i] < floor_to:
                    continue
                if kind == "WILDCARD":
                    if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < 0.08:
                        continue
                    if band_n and s in PIT.get(day_key(bars[i][0]), ()):
                        continue
                    sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                    tp_r = wc_tp
                else:
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
                d5 = top5_down(bars[i][0])
                n_down = d5[1] if d5 else None
                out.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                            "exit_ts": float(g[1]),
                            "calm_ratio": (float(cr) if cr is not None else None),
                            "down": (d5[0] if d5 else None),
                            "n_down": n_down,
                            "mult": regime_size_multiplier(eff, lo=lo_, hi=hi_,
                                                           floor_mult=flm)})
        out.sort(key=lambda z: z["ts"])
        return out

    WC, SQ = build("WILDCARD"), build("SQUEEZE")
    print("replayed in-window: WILDCARD %d signals, SQUEEZE %d signals\n"
          % (len(WC), len(SQ)))

    def book(pool, slots):
        return take(pool, slots=slots, equity=eq0, risk_pct=risk_pct,
                    sl_margin_pct=_env("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", 20.0),
                    scan_s=_env("FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS", 450.0),
                    one_per_scan=True, calm_max=calm_max, compound=True)

    st = json.load(open(STATE))

    def _ts(t, k):
        try:
            return dt.datetime.fromisoformat(str(t.get(k) or "")).timestamp()
        except Exception:
            return 0.0
    live = [t for t in (st.get("trade_history") or [])
            if str(t.get("entry_signal") or "").startswith(("WILDCARD", "TREND"))
            and _ts(t, "entry_time") >= WIN_START]
    live_usd = sum(float(t.get("pnl_usdt") or 0) for t in live)

    wc_all, sq_all = book(WC, wc_slots), book(SQ, sq_slots)
    print("=" * 88)
    print("WHAT ACTUALLY HAPPENED vs THE HARNESS")
    print("=" * 88)
    print("  live convex (real fills)   %3d closes  $%+8.2f" % (len(live), live_usd))
    print("  replayed convex           %3d fills   $%+8.2f" % (len(wc_all), sum(z["usd"] for z in wc_all)))
    print("  replayed squeeze          %3d fills   $%+8.2f" % (len(sq_all), sum(z["usd"] for z in sq_all)))
    print("  -> the gap on the convex row is HARNESS ERROR; read deltas, not levels")

    print()
    print("=" * 88)
    print("SPLIT BY THE RULE: are ALL top-5 negative over 24h?")
    print("=" * 88)
    print("  %-10s %-22s %6s %10s %10s" % ("sleeve", "top-5 state", "fills", "net $", "$/fill"))
    for nm, f in (("CONVEX", wc_all), ("SQUEEZE", sq_all)):
        for lbl, want in (("ALL DOWN (rule fires)", True), ("not all down", False)):
            g = [z for z in f if z["down"] is want]
            if not g:
                print("  %-10s %-22s %6d %10s %10s" % (nm, lbl, 0, "-", "-"))
                continue
            u = sum(z["usd"] for z in g)
            print("  %-10s %-22s %6d %+10.2f %+10.3f" % (nm, lbl, len(g), u, u / len(g)))
    print()
    print("=" * 88)
    print("DOES SQUEEZE ADD ANYTHING? skip-only vs switch")
    print("=" * 88)
    conv = sum(z["usd"] for z in wc_all)
    skip_only = book([z for z in WC if z["down"] is False], wc_slots)
    u_skip = sum(z["usd"] for z in skip_only)
    sq_leg = book([z for z in SQ if z["down"] is True], sq_slots)
    sw = skip_only + sq_leg
    u_sw = sum(z["usd"] for z in sw)
    print("  %-46s %5s %10s %10s" % ("rule", "fills", "net $", "vs convex"))
    print("  %-46s %5d %+10.2f %10s"
          % ("convex always (baseline)", len(wc_all), conv, "-"))
    print("  %-46s %5d %+10.2f %+10.2f"
          % ("SKIP when all-5 down, NO squeeze", len(skip_only), u_skip,
             u_skip - conv))
    print("  %-46s %5d %+10.2f %+10.2f"
          % ("SWITCH to squeeze when all-5 down", len(sw), u_sw, u_sw - conv))
    print()
    print("  squeeze leg alone: %d fills, $%+.2f" % (len(sq_leg),
          sum(z["usd"] for z in sq_leg)))
    print("  squeeze MARGINAL contribution: %+.2f" % (u_sw - u_skip))
    print("  -> if that is <= 0 the rule earns by AVOIDING CONVEX, and squeeze is")
    print("     dead weight. The simpler rule would then be: do not trade.")

    print()
    print("=" * 88)
    print("HOW MANY MAJORS MUST BE DOWN? skip-only, no squeeze")
    print("=" * 88)
    print("  %-44s %5s %10s %10s %8s"
          % ("do not trade when >= N of 5 are down", "fills", "net $",
             "vs convex", "blocked"))
    print("  rows = how many of the 5 must be below the threshold to BLOCK")
    print("  %-6s" % "" + "".join("  %13s" % ("< %+.2f%%" % t)
                                  for t in (0.0, -0.25, -0.5, -0.75, -1.0)))
    best = []
    for n in (1, 2, 3, 4, 5):
        row = "  N>=%d " % n
        for thr in (0.0, -0.25, -0.5, -0.75, -1.0):
            keep = [z for z in WC
                    if z["n_down"] is not None and z["n_down"].get(thr, 0) < n]
            blocked = 100.0 * (1 - len(keep) / max(1, len(WC)))
            f = book(keep, wc_slots) if keep else []
            if not f:
                row += "  %13s" % "none"
                continue
            u = sum(z["usd"] for z in f)
            best.append((u - conv, n, thr, len(f), blocked))
            row += "  %+7.2f/%3.0f%%" % (u - conv, blocked)
        print(row)
    print()
    print("  cell = $ vs convex-always / %% of signals blocked")
    best.sort(reverse=True)
    print("  best: N>=%d at <%+.2f%%  ->  %+.2f  (%d fills, %.0f%% blocked)"
          % (best[0][1], best[0][2], best[0][0], best[0][3], best[0][4]))
    print("  worst: N>=%d at <%+.2f%% -> %+.2f"
          % (best[-1][1], best[-1][2], best[-1][0]))
    print()
    print("  25 CELLS on 67 signals over 7 days. A no-edge cell beats the")
    print("  baseline about half the time, so ~12 winners are EXPECTED. The")
    print("  spread from best to worst is the honest measure of the noise.")
    n_down = sum(1 for z in WC if z["down"] is True)
    print()
    print("  convex signals the all-5 rule would have SKIPPED: %d of %d"
          % (n_down, len(WC)))
    print("  ~7 days. Nothing here is significant; it is what the rule would have")
    print("  done in the window asked about, not evidence that it works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
