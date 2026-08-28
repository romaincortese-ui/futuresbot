"""AUDIT COPY of pit_stop_width.py -- dumps per-trade rows for two cells."""
from __future__ import annotations

import csv
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
OUT = os.environ.get("PJ_OUT", "C:/Users/Rocot/AppData/Local/Temp/claude/C--Users-Rocot-Claude-session/8c93b1ba-3446-4dcb-9618-2245bc04ca42/scratchpad")


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
    print("equity %.4f risk %.6f dollar_r %.6f now %d" % (eq0, risk_pct, dollar_r, now))

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
        prep[s] = (df, bars, hits)
    print("trigger bars: %d" % sum(len(h) for _d, _b, h in prep.values()))

    live_floor = ratchet(3.0, 0.75)
    win_s = 7 * 86400
    span = max(b[-1][0] for _d, b, _h in prep.values()) - min(b[0][0] for _d, b, _h in prep.values())
    n_win = max(1, int(span // win_s))
    mid = n_win // 2
    print("span_days %.2f n_win %d mid %d" % (span / 86400.0, n_win, mid))

    FIELDS = ["cell", "week_k", "ts", "exit_ts", "sym", "side", "netR", "net_usd",
              "kind", "slf", "lev", "sl_margin", "capped", "taken", "entry", "sl", "tp", "cost_r"]

    def run_cell(atr_mult, cap_pct, wr):
        os.environ["FUTURES_WILDCARD_SL_ATR_MULT"] = str(atr_mult)
        os.environ["FUTURES_WILDCARD_MAX_SL_MARGIN_PCT"] = str(cap_pct)
        cell = "%.1fx%d" % (atr_mult, cap_pct)
        C = []
        for s, (df, bars, hits) in prep.items():
            for i in hits:
                sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                if sig is None:
                    continue
                e, sl, tp = float(sig.entry_price), float(sig.sl_price), float(sig.tp_price)
                one = abs(e - sl)
                if one <= 0 or e <= 0:
                    continue
                slf = one / e
                was_capped = slf * float(sig.leverage) * 100.0 >= cap_pct - 0.5
                row = {"entry": e, "sl": sl, "tp": tp, "side": sig.side}
                cr = shadow.cost_r(row)
                g = resolve(bars, i, e, sl, tp, abs(tp - e) / one, sig.side,
                            shadow.CONVEX_HORIZON_S, cr, live_floor,
                            float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if g is None:
                    continue
                C.append({"cell": cell, "ts": bars[i][0], "sym": s, "side": sig.side,
                          "netR": float(g[0]), "net_usd": float(g[0]) * dollar_r,
                          "kind": g[2], "exit_ts": float(g[1]),
                          "slf": slf, "lev": float(sig.leverage),
                          "sl_margin": slf * float(sig.leverage) * 100.0,
                          "capped": int(was_capped), "taken": 0,
                          "entry": e, "sl": sl, "tp": tp, "cost_r": cr, "week_k": -1})
        C.sort(key=lambda x: x["ts"])
        for k in range(n_win):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            slots, per = [], {}
            for x in C:
                if not (lo_t <= x["ts"] < hi_t):
                    continue
                x["week_k"] = k
                slots[:] = [q for q in slots if q > x["ts"]]
                per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
                if per[x["sym"]] or len(slots) >= 3:
                    continue
                slots.append(x["exit_ts"])
                per[x["sym"]].append(x["exit_ts"])
                x["taken"] = 1
        for x in C:
            wr.writerow(x)
        n = sum(x["taken"] for x in C)
        net = sum(x["net_usd"] for x in C if x["taken"])
        print("cell %s cand %d taken %d net %+.2f" % (cell, len(C), n, net))

    path = os.path.join(OUT, "audit_trades.csv")
    with open(path, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=FIELDS)
        wr.writeheader()
        for a, c in ((3.0, 20), (4.0, 30), (4.0, 20)):
            run_cell(a, c, wr)
    print("wrote %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
