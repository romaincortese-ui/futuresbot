"""AUDIT COPY of pit_stop_width.py. Fetch ONCE, cache frames, dump every
candidate for every cell so the taken-book / paired / composition split can be
computed offline on IDENTICAL data (removes pool-draw variance)."""
from __future__ import annotations
import os, sys, time, pickle
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd  # noqa
from futuresbot import shadow_ledger as shadow  # noqa
from futuresbot import wildcard as W  # noqa
from futuresbot.config import FuturesConfig  # noqa
from futuresbot.marketdata import MexcFuturesClient  # noqa
from futuresbot.runtime import FuturesRuntime  # noqa
from pit_ratchet import ratchet  # noqa
from retention_trail_ab import resolve  # noqa

BAR, CHUNK, TAIL = 900, 1900, 260
OUT = os.environ.get("AUD_OUT") or "."

def _env(n, d):
    try: return float(os.environ.get(n) or d)
    except (TypeError, ValueError): return float(d)

def main() -> int:
    cfg = FuturesConfig.from_env(); cl = MexcFuturesClient(cfg); rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 190), int(_env("PJ_POOL", 150))
    now = int(time.time()); floor = W.wildcard_min_turnover_usdt()
    eq0 = rt._last_known_equity() or 165.0
    risk_pct = _env("FUTURES_WILDCARD_RISK_PCT", 0.0241)
    dollar_r = risk_pct * eq0
    print("equity %.2f risk %.4f 1R=$%.4f" % (eq0, risk_pct, dollar_r))
    cache = os.path.join(OUT, "frames.pkl")
    if os.path.exists(cache):
        with open(cache, "rb") as fh:
            frames, sizes, now = pickle.load(fh)
        print("CACHED frames: %d (now=%d)" % (len(frames), now))
    else:
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
                try: d = cl.get_klines(s, interval="Min15", start=end - CHUNK * BAR, end=end)
                except Exception: break
                if d is None or not len(d): break
                parts.append(d); end = int(d.index[0].timestamp()) - BAR
            if not parts: return s, None
            o = pd.concat(parts[::-1])
            return s, o[~o.index.duplicated(keep="first")].sort_index()
        print("fetching %d x %.0fd..." % (len(syms), days))
        with ThreadPoolExecutor(max_workers=6) as p:
            frames = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 300}
        print("frames: %d" % len(frames))
        with open(cache, "wb") as fh:
            pickle.dump((frames, sizes, now), fh)

    prep = {}
    for s, df in frames.items():
        cs = sizes.get(s, 0.0)
        c = [float(x) for x in df["close"]]; v = [float(x) for x in df["volume"]]
        raw = [c[k] * v[k] * cs for k in range(len(c))]
        roll, acc = [0.0] * len(c), 0.0
        for k, x in enumerate(raw):
            acc += x
            if k >= 96: acc -= raw[k - 96]
            roll[k] = acc
        bars = list(zip([float(x.timestamp()) for x in df.index], [float(x) for x in df["high"]],
                        [float(x) for x in df["low"]], c))
        hits = [i for i in range(250, len(c)) if i > W.ROC_BARS and roll[i] >= floor
                and abs(c[i] / c[i - W.ROC_BARS] - 1.0) >= 0.08]
        prep[s] = (df, bars, hits)
    print("trigger bars: %d" % sum(len(h) for _d, _b, h in prep.values()))
    live_floor = ratchet(3.0, 0.75)
    span = max(b[-1][0] for _d, b, _h in prep.values()) - min(b[0][0] for _d, b, _h in prep.values())
    print("span_days %.1f" % (span / 86400.0))

    CELLS = [(3.0,20),(3.0,25),(3.0,30),(4.0,20),(4.0,25),(4.0,30),(4.0,35),
             (3.5,30),(4.5,30),(5.0,20),(5.0,30),(2.0,20),(1.5,20),(6.0,30)]
    rows = []
    for atr_mult, cap_pct in CELLS:
        os.environ["FUTURES_WILDCARD_SL_ATR_MULT"] = str(atr_mult)
        os.environ["FUTURES_WILDCARD_MAX_SL_MARGIN_PCT"] = str(cap_pct)
        n = 0
        for s, (df, bars, hits) in prep.items():
            for i in hits:
                sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                if sig is None: continue
                e, sl, tp = float(sig.entry_price), float(sig.sl_price), float(sig.tp_price)
                one = abs(e - sl)
                if one <= 0 or e <= 0: continue
                slf = one / e
                row = {"entry": e, "sl": sl, "tp": tp, "side": sig.side}
                g = resolve(bars, i, e, sl, tp, abs(tp - e) / one, sig.side,
                            shadow.CONVEX_HORIZON_S, shadow.cost_r(row), live_floor,
                            float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
                if g is None: continue
                rows.append({"cell": "%.1fx%d" % (atr_mult, cap_pct), "ts": bars[i][0], "sym": s,
                             "bar": i, "net": float(g[0]), "kind": g[2], "exit_ts": float(g[1]),
                             "slf": slf, "lev": float(sig.leverage), "entry": e, "sl": sl, "tp": tp,
                             "side": sig.side, "atr_pct": float(getattr(sig, "atr_pct", 0.0) or 0.0),
                             "cs": sizes.get(s, 0.0)})
                n += 1
        print("cell %.1fx%-3d candidates %d" % (atr_mult, cap_pct, n), flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "cand.csv"), index=False)
    with open(os.path.join(OUT, "meta.txt"), "w") as fh:
        fh.write("now=%d\neq=%f\nrisk=%f\ndollar_r=%f\nframes=%d\n" % (now, eq0, risk_pct, dollar_r, len(frames)))
    print("dumped %d rows" % len(rows))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
