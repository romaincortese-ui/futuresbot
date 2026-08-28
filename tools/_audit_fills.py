"""Is the stop-width result an artifact of the resolver's MODELLED exit fills?

Same pool/detector/slots as pit_stop_width.py. Only the resolver changes:

  A  live      trail books at the modelled level (what pit_stop_width uses)
  B  gapfill   trail books at the bar's own adverse extreme when the bar traded
               through the level (a stop order that gaps does not fill at the
               level); stop and tp unchanged
  C  stopfirst the hard stop is checked BEFORE the trail, so a bar that traded
               through both books -1R instead of the trail level
  D  notrail   no trail at all: -1R stop / tp / 24h clock only

If the ranking of (4.0, 30) vs (3.0, 20) only holds under A, the finding is a
fill assumption, not a stop-width effect.
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

BAR, CHUNK, TAIL = 900, 1900, 260


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def resolve_v(bars, i0, entry, sl, tp, tp_r, side, horizon_s, cost_r, floor_fn,
              atr_frac, now_ts, mode="live"):
    """retention_trail_ab.resolve with the fill/ordering assumption swapped."""
    sgn = 1.0 if side == 'LONG' else -1.0
    one_r = abs(entry - sl)
    if one_r <= 0:
        return None
    t0 = bars[i0][0]
    floor_min = 1.5 * cost_r
    peak_r, last, seen = 0.0, entry, False
    for k in range(i0 + 1, len(bars)):
        ts, hi, lo, close = bars[k]
        if ts - t0 > horizon_s:
            break
        seen = True
        adverse_r = ((lo if sgn > 0 else hi) - entry) * sgn / one_r
        if mode == "stopfirst" and ((lo <= sl) if sgn > 0 else (hi >= sl)):
            return (-1.0 - cost_r, ts, 'stop')
        if mode != "notrail":
            level = floor_fn(peak_r, atr_frac, one_r / entry)
            if level is not None:
                level = max(level, floor_min)
                if level < peak_r and adverse_r <= level:
                    booked = level if mode != "gapfill" else max(adverse_r, -1.0)
                    return (booked - cost_r, ts, 'trail')
        if (lo <= sl) if sgn > 0 else (hi >= sl):
            return (-1.0 - cost_r, ts, 'stop')
        if (hi >= tp) if sgn > 0 else (lo <= tp):
            return (tp_r - cost_r, ts, 'tp')
        peak_r = max(peak_r, ((hi if sgn > 0 else lo) - entry) * sgn / one_r)
        last = close
    if not seen:
        return None
    if now_ts - t0 < horizon_s:
        return None
    return (((last - entry) * sgn / one_r) - cost_r, t0 + horizon_s, 'timeout')


def main() -> int:
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 190), int(_env("PJ_POOL", 150))
    now = int(time.time())
    floor = W.wildcard_min_turnover_usdt()
    eq0 = rt._last_known_equity() or 165.0
    dollar_r = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241) * eq0
    print("1R = $%.2f" % dollar_r)

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

    with ThreadPoolExecutor(max_workers=6) as p:
        frames = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 300}
    print("frames: %d" % len(frames))

    prep = {}
    atrs = []
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

    live_floor = ratchet(3.0, 0.75)
    win_s = 7 * 86400
    span = max(b[-1][0] for _d, b, _h in prep.values()) - min(b[0][0] for _d, b, _h in prep.values())
    n_win = max(1, int(span // win_s))
    mid = n_win // 2

    SIGCACHE = {}

    def sigs_for(atr_mult, cap_pct):
        key = (atr_mult, cap_pct)
        if key in SIGCACHE:
            return SIGCACHE[key]
        os.environ["FUTURES_WILDCARD_SL_ATR_MULT"] = str(atr_mult)
        os.environ["FUTURES_WILDCARD_MAX_SL_MARGIN_PCT"] = str(cap_pct)
        out = []
        for s, (df, bars, hits) in prep.items():
            for i in hits:
                sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                if sig is None:
                    continue
                e, sl, tp = float(sig.entry_price), float(sig.sl_price), float(sig.tp_price)
                one = abs(e - sl)
                if one <= 0 or e <= 0:
                    continue
                row = {"entry": e, "sl": sl, "tp": tp, "side": sig.side}
                out.append((s, bars, i, e, sl, tp, abs(tp - e) / one, sig.side,
                            shadow.cost_r(row), float(getattr(sig, "atr_pct", 0.0) or 0.0)))
                if atr_mult == 3.0 and cap_pct == 20:
                    atrs.append(float(sig.atr_pct))
        SIGCACHE[key] = out
        return out

    def run(atr_mult, cap_pct, mode):
        C = []
        for s, bars, i, e, sl, tp, tpr, side, cr, atr in sigs_for(atr_mult, cap_pct):
            g = resolve_v(bars, i, e, sl, tp, tpr, side, shadow.CONVEX_HORIZON_S,
                          cr, live_floor, atr, now, mode)
            if g is None:
                continue
            C.append({"ts": bars[i][0], "sym": s, "net": float(g[0]),
                      "kind": g[2], "exit_ts": float(g[1])})
        C.sort(key=lambda x: x["ts"])
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
        net = sum(x["net"] for x in taken) * dollar_r
        vals = sorted((x["net"] * dollar_r for x in taken), reverse=True)
        k5 = max(1, len(taken) // 20)
        return net, len(taken), older, recent, net - sum(vals[:k5])

    CELLS = ((3.0, 20), (3.0, 30), (4.0, 20), (4.0, 30), (5.0, 30))
    print("\n%-12s %-10s %5s %10s %9s %9s %9s" %
          ("resolver", "cell", "n", "net $", "older", "recent", "ex-top5"))
    res = {}
    for mode in ("live", "gapfill", "stopfirst", "notrail"):
        for a, c in CELLS:
            net, n, old, rec, ex5 = run(a, c, mode)
            res[(mode, a, c)] = net
            print("%-12s %-10s %5d %+10.2f %+9.2f %+9.2f %+9.2f" %
                  (mode, "%.1fx%d%%" % (a, c), n, net, old, rec, ex5))
        print()
    print("=== candidate MINUS live, per resolver ===")
    for mode in ("live", "gapfill", "stopfirst", "notrail"):
        print("  %-10s (4.0,30)-(3.0,20) = %+8.2f   (4.0,30)-(4.0,20) = %+8.2f" %
              (mode, res[(mode, 4.0, 30)] - res[(mode, 3.0, 20)],
               res[(mode, 4.0, 30)] - res[(mode, 4.0, 20)]))
    if atrs:
        atrs.sort()
        print("\n15m atr_pct at live cell: p50 %.3f%% p90 %.3f%% p99 %.3f%% max %.3f%% | "
              "share > 5%% %.1f%% | share > 6.67%% %.1f%%" %
              (100 * atrs[len(atrs) // 2], 100 * atrs[int(.9 * len(atrs))],
               100 * atrs[int(.99 * len(atrs))], 100 * atrs[-1],
               100.0 * sum(1 for a in atrs if a > 0.05) / len(atrs),
               100.0 * sum(1 for a in atrs if a > 0.0667) / len(atrs)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
