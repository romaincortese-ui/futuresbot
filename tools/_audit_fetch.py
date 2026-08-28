"""AUDIT stage 1: fetch once, run the REAL detector once per trigger bar, cache.

Also VERIFIES (not assumes) that the detector's ENTRY decision is invariant to
FUTURES_WILDCARD_SL_ATR_MULT / MAX_SL_MARGIN_PCT, and that an analytic rebuild
of (sl_frac, leverage, tp_price) reproduces the real detector exactly.
"""
from __future__ import annotations
import os, sys, time, pickle, random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
from futuresbot import wildcard as W
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime

BAR, CHUNK, TAIL = 900, 1900, 260
OUT = os.environ["AUDIT_CACHE"]

def _env(n, d):
    try: return float(os.environ.get(n) or d)
    except (TypeError, ValueError): return float(d)

def geom(side, entry, atr_pct, atr_mult, cap_pct, tp_r=5.0, lev0=7,
         max_short_tp=0.50):
    """Verbatim transcription of futuresbot/wildcard.py lines 272-305."""
    s = 1 if side == "LONG" else -1
    leverage = int(min(10.0, max(5.0, float(lev0))))
    sl_frac = atr_mult * atr_pct
    if cap_pct > 0 and sl_frac > 0:
        if sl_frac * leverage * 100.0 > cap_pct:
            leverage = max(1, int(cap_pct / (sl_frac * 100.0)))
        if sl_frac * leverage * 100.0 > cap_pct:
            sl_frac = cap_pct / 100.0 / leverage
    sl_margin = sl_frac * leverage * 100.0
    sl_price = entry * (1 - sl_frac) if s > 0 else entry * (1 + sl_frac)
    tp_dist = sl_frac * tp_r
    clamped = False
    if s < 0 and tp_dist >= max_short_tp:
        tp_dist = max_short_tp; clamped = True
    tp_price = entry * (1 + tp_dist) if s > 0 else entry * (1 - tp_dist)
    return sl_frac, leverage, sl_margin, sl_price, tp_price, clamped

def main():
    cfg = FuturesConfig.from_env(); cl = MexcFuturesClient(cfg); rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 190), int(_env("PJ_POOL", 150))
    now = int(time.time()); floor = W.wildcard_min_turnover_usdt()
    eq0 = rt._last_known_equity() or 165.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    print("equity %.4f risk %.6f dollar_r %.6f" % (eq0, risk_pct, risk_pct*eq0))
    print("LONG_ONLY=%s  TP_R=%s  LEVERAGE=%s  COST_PCT=%s" % (
        W.wildcard_long_only(), os.environ.get("FUTURES_WILDCARD_TP_R"),
        os.environ.get("FUTURES_WILDCARD_LEVERAGE"),
        os.environ.get("FUTURES_CONVEX_COST_PCT")))
    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    syms = [s for a, s in crypto if s not in majors and a >= _env("PJ_MIN_TODAY", 3e5)][:pool_n]
    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}
    nch = int(days*86400 // (CHUNK*BAR)) + 1
    def fetch(s):
        parts, end = [], now
        for _ in range(nch):
            try: d = cl.get_klines(s, interval="Min15", start=end-CHUNK*BAR, end=end)
            except Exception: break
            if d is None or not len(d): break
            parts.append(d); end = int(d.index[0].timestamp()) - BAR
        if not parts: return s, None
        o = pd.concat(parts[::-1])
        return s, o[~o.index.duplicated(keep="first")].sort_index()
    print("fetching %d symbols x %.0fd..." % (len(syms), days)); sys.stdout.flush()
    with ThreadPoolExecutor(max_workers=6) as p:
        frames = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 300}
    print("frames: %d" % len(frames)); sys.stdout.flush()

    sigs, series, nhit = [], {}, 0
    for s, df in frames.items():
        cs = sizes.get(s, 0.0)
        c = [float(x) for x in df["close"]]; v = [float(x) for x in df["volume"]]
        raw = [c[k]*v[k]*cs for k in range(len(c))]
        roll, acc = [0.0]*len(c), 0.0
        for k, x in enumerate(raw):
            acc += x
            if k >= 96: acc -= raw[k-96]
            roll[k] = acc
        ts = np.array([float(x.timestamp()) for x in df.index])
        hi = df["high"].astype(float).to_numpy(); lo = df["low"].astype(float).to_numpy()
        cl_ = np.array(c)
        hits = [i for i in range(250, len(c))
                if i > W.ROC_BARS and roll[i] >= floor
                and abs(c[i]/c[i-W.ROC_BARS] - 1.0) >= 0.08]
        nhit += len(hits)
        for i in hits:
            sig = W.detect_wildcard_signal(df.iloc[max(0, i-TAIL):i+1], s)
            if sig is None: continue
            fwd = min(len(ts), i+130)
            sigs.append({"sym": s, "i": i, "ts": float(ts[i]), "side": sig.side,
                         "entry": float(sig.entry_price), "atr_pct": float(sig.atr_pct),
                         "bars": np.stack([ts[i:fwd], hi[i:fwd], lo[i:fwd], cl_[i:fwd]], 1)})
        # ATR% series, same definition as W._atr_pct (14-bar mean TR / close)
        pc = np.concatenate([[np.nan], cl_[:-1]])
        tr = np.nanmax(np.stack([hi-lo, np.abs(hi-pc), np.abs(lo-pc)],1),1)
        atrs = np.full(len(cl_), np.nan)
        for k in range(14, len(cl_)):
            atrs[k] = tr[k-13:k+1].mean() / cl_[k] if cl_[k] > 0 else np.nan
        series[s] = {"ts": ts, "hi": hi, "lo": lo, "close": cl_, "atr": atrs}
    print("trigger bars: %d  signals: %d" % (nhit, len(sigs))); sys.stdout.flush()

    # ---------- VERIFICATION ----------
    random.seed(0)
    idx = {}
    for j, r in enumerate(sigs): idx.setdefault(r["sym"], []).append(j)
    sample = random.sample(range(len(sigs)), min(300, len(sigs)))
    base_env = (os.environ.get("FUTURES_WILDCARD_SL_ATR_MULT"),
                os.environ.get("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT"))
    bad_inv = bad_geo = 0; worst = 0.0
    for cell in (("3.0", "20"), ("4.0", "30"), ("6.0", "50"), ("1.5", "15"), ("4.0", "20")):
        os.environ["FUTURES_WILDCARD_SL_ATR_MULT"], os.environ["FUTURES_WILDCARD_MAX_SL_MARGIN_PCT"] = cell
        for j in sample:
            r = sigs[j]; i = r["i"]
            df = frames[r["sym"]]
            sig = W.detect_wildcard_signal(df.iloc[max(0, i-TAIL):i+1], r["sym"])
            if sig is None:
                bad_inv += 1; continue
            if sig.side != r["side"] or abs(sig.entry_price-r["entry"]) > 1e-12 \
               or abs(float(sig.atr_pct)-r["atr_pct"]) > 1e-12:
                bad_inv += 1; continue
            g = geom(r["side"], r["entry"], r["atr_pct"], float(cell[0]), float(cell[1]))
            d = max(abs(g[3]-float(sig.sl_price))/r["entry"],
                    abs(g[4]-float(sig.tp_price))/r["entry"],
                    abs(g[1]-float(sig.leverage)))
            worst = max(worst, d)
            if d > 1e-9: bad_geo += 1
    os.environ["FUTURES_WILDCARD_SL_ATR_MULT"] = base_env[0] or "3.0"
    os.environ["FUTURES_WILDCARD_MAX_SL_MARGIN_PCT"] = base_env[1] or "20"
    print("VERIFY entry-set invariance across 5 cells: %d/%d mismatches" % (bad_inv, 5*len(sample)))
    print("VERIFY analytic geometry vs real detector: %d/%d mismatches, worst rel-err %.3g"
          % (bad_geo, 5*len(sample), worst))

    with open(OUT, "wb") as f:
        pickle.dump({"sigs": sigs, "series": series, "now": now, "eq0": eq0,
                     "risk_pct": risk_pct, "days": days,
                     "long_only": W.wildcard_long_only()}, f, protocol=4)
    print("cached -> %s (%.1f MB)" % (OUT, os.path.getsize(OUT)/1e6))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
