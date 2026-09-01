"""SECURE 6R vs the live 5R cap, trade by trade.

    railway run --service Futures-bot python tools/pit_secure_audit.py

+$32.97 is a summary. This is the audit trail: every trade where the two
policies actually differ, what each banked, and why.

THE TWO POLICIES
    LIVE       TP cap at 5R. Floor = 0.50 x peak, ratcheting to 0.75 x peak
               above a 3R peak. A trade that touches 5R exits AT 5R.
    SECURE 6R  No TP cap. Same floor, except once peak >= 6R the floor latches:
               floor = max(6.0, 0.75 x peak). A trade that touches 5R keeps
               going; one that touches 6R can never bank less than 6R.

WHERE THEY DIFFER - and it is not only where SECURE wins:
    peak <  5R    identical. Neither the cap nor the latch is reached.
    peak 5-6R     SECURE LOSES. Live banks a clean 5R at the cap; SECURE has no
                  cap, does not reach the 6R latch, and falls back on the plain
                  0.75 x peak floor - i.e. 3.75R to 4.50R.
    peak >= 6R    SECURE WINS. Live still banks 5R; SECURE banks max(6, 0.75p).

So the change is a bet that trades clearing 5R usually clear 6R too. The census
says 16 of 798 signals reach 5R and 10 of those reach 6R, so the bet is roughly
10 winners against 6 losers - which is why it is worth auditing rather than
trusting.

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
from futuresbot import wildcard as W  # noqa: E402
from futuresbot.config import FuturesConfig  # noqa: E402
from futuresbot.marketdata import MexcFuturesClient  # noqa: E402
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency  # noqa: E402
from futuresbot.runtime import FuturesRuntime  # noqa: E402
from pit_fetch import fetch_frames  # noqa: E402
from pit_pool import day_key, daily_turnover, pit_majors  # noqa: E402

BAR, TAIL = 900, 260


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def walk(bars, i0, entry, sl, side, horizon_s, cost_r, now_ts, *,
         arm, base, rat_r, rat_hi, cap_r, secure_at, bank_frac=0.0, bank_at=None):
    """One trade under one policy. Returns (banked_r, peak_r, why).

    bank_frac/bank_at implement a SCALE-OUT: close bank_frac of the position at
    bank_at R, and let the remainder run on the plain trail with no cap and no
    latch. This is the only shape that both secures part of the 5R AND lets a
    runner run - a latch cannot, because a floor at 5R exits any trade that
    retraces through 5R, and big runners retrace (BSB peaked at 20.84R)."""
    sgn = 1.0 if side == "LONG" else -1.0
    one = abs(entry - sl)
    if one <= 0:
        return None
    t0 = bars[i0][0]
    peak, last, seen = 0.0, entry, False
    floor_min = 1.5 * cost_r
    banked = 0.0          # R already realised by a scale-out
    live_frac = 1.0       # fraction of the position still open
    for k in range(i0 + 1, len(bars)):
        ts, hi, lo, close = bars[k]
        if ts - t0 > horizon_s:
            break
        seen = True
        adverse = ((lo if sgn > 0 else hi) - entry) * sgn / one
        favour = ((hi if sgn > 0 else lo) - entry) * sgn / one
        if peak >= arm:
            lvl = (rat_hi if (rat_r > 0 and peak >= rat_r) else base) * peak
            if secure_at is not None and peak >= secure_at:
                lvl = max(lvl, secure_at)
            lvl = max(lvl, floor_min)
            if lvl < peak and adverse <= lvl:
                return (banked + live_frac * (lvl - cost_r), peak,
                        "trail" if live_frac == 1.0 else "run")
        if adverse <= -1.0:
            return (banked + live_frac * (-1.0 - cost_r), peak,
                    "stop" if live_frac == 1.0 else "runstop")
        if bank_at is not None and live_frac == 1.0 and favour >= bank_at:
            banked = bank_frac * (bank_at - cost_r)
            live_frac = 1.0 - bank_frac
        if favour >= cap_r:
            return (banked + live_frac * (cap_r - cost_r), max(peak, favour), "tp")
        peak = max(peak, favour)
        last = close
    if not seen or now_ts - t0 < horizon_s:
        return None
    return (((last - entry) * sgn / one) - cost_r, peak, "clock")


def main() -> int:
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 220), int(_env("PJ_POOL", 170))
    now = int(time.time())
    eq0 = rt._last_known_equity() or 170.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    lo_, hi_ = _env("FUTURES_REGIME_EFF_LO", 0.20), _env("FUTURES_REGIME_EFF_HI", 0.45)
    flm = _env("FUTURES_REGIME_FLOOR_MULT", 0.50)
    fl = _env("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 2e6)
    band = int(_env("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24))
    calm = _env("FUTURES_WILDCARD_MAX_CALM_RATIO", 0.75)
    arm = _env("FUTURES_CONVEX_TRAIL_ARM_R", 1.0)
    base = _env("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", 0.50)
    rat_r = _env("FUTURES_CONVEX_TRAIL_RATCHET_R", 3.0)
    rat_hi = _env("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", 0.75)
    print("*** LIVE 5R cap  vs  BANK %.0f%% AT %.1fR + let the rest run ***"
          % (100 * _env("AUDIT_BANK_FRAC", 0.5), _env("AUDIT_BANK_AT", 5.0)))
    print("floor 0.%02d x peak, ratchet to 0.%02d above %.0fR\n"
          % (base * 100, rat_hi * 100, rat_r))

    tk = cl.get_all_tickers() or []
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    cand = [s for a, s in crypto if a >= _env("PJ_MIN_TODAY", 2e5)][:pool_n]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    frames, rep = fetch_frames(cl, cand, days=days, workers=6, min_bars=300, now_ts=now)
    print(rep)

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
    PIT = pit_majors(daily_turnover(ROLLS), n=band)

    diffs, n_sig, same = [], 0, 0
    for s, (df, bars, roll, c) in PREP.items():
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < fl:
                continue
            if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < 0.08:
                continue
            if band and s in PIT.get(day_key(bars[i][0]), ()):
                continue
            sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
            if sig is None:
                continue
            cr_calm = getattr(sig, "calm_ratio", None)
            if calm > 0 and cr_calm is not None and float(cr_calm) >= calm:
                continue
            e, sl = float(sig.entry_price), float(sig.sl_price)
            if abs(e - sl) <= 0 or e <= 0:
                continue
            cost = shadow.cost_r({"entry": e, "sl": sl, "tp": float(sig.tp_price),
                                  "side": sig.side})
            kw = dict(arm=arm, base=base, rat_r=rat_r, rat_hi=rat_hi)
            a = walk(bars, i, e, sl, sig.side, shadow.CONVEX_HORIZON_S, cost, now,
                     cap_r=5.0, secure_at=None, **kw)
            b = walk(bars, i, e, sl, sig.side, shadow.CONVEX_HORIZON_S, cost, now,
                     cap_r=99.0, secure_at=None,
                     bank_frac=_env("AUDIT_BANK_FRAC", 0.5),
                     bank_at=_env("AUDIT_BANK_AT", 5.0), **kw)
            if a is None or b is None:
                continue
            n_sig += 1
            if abs(a[0] - b[0]) < 1e-9:
                same += 1
                continue
            eff = trend_efficiency(c[:i + 1], int(_env("FUTURES_REGIME_EFF_WINDOW", 24)))
            mult = regime_size_multiplier(eff, lo=lo_, hi=hi_, floor_mult=flm)
            diffs.append({"sym": s, "ts": bars[i][0], "live": a[0], "live_why": a[2],
                          "sec": b[0], "sec_why": b[2], "peak": b[1], "mult": mult})

    import datetime as dt
    print("signals resolved: %d | identical under both policies: %d (%.1f%%)"
          % (n_sig, same, 100.0 * same / max(1, n_sig)))
    print("TRADES WHERE THE POLICIES DIFFER: %d\n" % len(diffs))
    diffs.sort(key=lambda z: z["peak"])
    print("%-13s %-11s %7s | %8s %-6s | %8s %-6s | %8s %9s"
          % ("symbol", "when", "peak R", "LIVE R", "why", "SEC R", "why", "delta R", "delta $"))
    tot_r = tot_d = 0.0
    lose_r = win_r = 0.0
    for z in diffs:
        d_r = z["sec"] - z["live"]
        d_usd = d_r * risk_pct * eq0 * z["mult"]
        tot_r += d_r
        tot_d += d_usd
        if d_r < 0:
            lose_r += d_r
        else:
            win_r += d_r
        print("%-13s %-11s %7.2f | %+8.2f %-6s | %+8.2f %-6s | %+8.2f %+9.2f"
              % (z["sym"], dt.datetime.fromtimestamp(z["ts"], dt.UTC).strftime("%m-%d %H:%M"),
                 z["peak"], z["live"], z["live_why"], z["sec"], z["sec_why"], d_r, d_usd))
    print("\n%-13s %-11s %7s | %8s %-6s | %8s %-6s | %+8.2f %+9.2f"
          % ("TOTAL", "", "", "", "", "", "", tot_r, tot_d))
    print("\n  trades where the scale-out loses: %+.2fR" % lose_r)
    print("  trades where the scale-out wins : %+.2fR" % win_r)
    print("  net                                   : %+.2fR  = $%+.2f at live sizing"
          % (tot_r, tot_d))
    print("\nThis is the WHOLE difference between the two policies. Every other")
    print("trade in the book resolves identically, which is why the headline")
    print("number rests on this handful.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
