"""H4-coil + 15m-trigger squeeze variant ("slow spring, fast trigger").

Thesis (timeframe audit): the live squeeze's 5h window catches micro-coils; the
AKE-class monsters compress for DAYS — a daily/H4-chart pattern (TTM literature:
daily squeezes = the 3-7 high-quality signals/year). Detect the coil on H4 bars
(BB20-in-KC20, >=6 H4 bars = 24h+), enter on a 15m range-break with volume,
ride the live convex exit (-1R/+5R), 7d horizon. Long-only, Bybit-gate.

Run with BT_UNIV_SKIP=0 (liquid band / live squeeze turf) and =30 (small-cap
band) to answer placement. Single-slot serialized, fees+slippage as the main
harness. Judged by the standard bar: net>0, ex-best>0, halves consistent.
"""
import json
import os
import time
import urllib.request

import pandas as pd

from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient

c = MexcFuturesClient(FuturesConfig.from_env())
now = int(time.time())
SPAN_D = int(os.environ.get("BT_SPAN_D", "60"))
UNIV = int(os.environ.get("BT_UNIV", "45"))
SKIP = int(os.environ.get("BT_UNIV_SKIP", "0"))
HAIR = 0.001; FEE = 0.000594; BAL = 62.0; TP_R = 5.0
MAXBARS = int(float(os.environ.get("BT_HORIZON_D", "7")) * 96)
MIN_COIL_H4 = int(os.environ.get("H4_MIN_COIL", "6"))       # >=24h compression
BREAK_LB = int(os.environ.get("H4_BREAK_LB", "24"))          # 15m range-break lookback (6h)
STBL = ("USDC", "USDE", "USD1", "DAI", "FDUSD", "TUSD", "BUSD")

tk = c.public_get("/api/v1/contract/ticker", {}); td = tk.get("data") if isinstance(tk, dict) else tk
uni = sorted([(t["symbol"], float(t.get("amount24") or 0)) for t in (td or [])
              if t.get("symbol", "").endswith("_USDT") and float(t.get("amount24") or 0) >= 3e6
              and not any(k in t["symbol"] for k in STBL)], key=lambda x: -x[1])[SKIP:SKIP + UNIV]


def bybit_listed(sym):
    try:
        req = urllib.request.Request(
            f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym.replace('_','')}&interval=60&limit=2",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return bool(((json.loads(r.read().decode()).get("result") or {}).get("list")) or [])
    except Exception:
        return None


def fetch_min15(sym):
    step = 900; span = step * 1999; cur = now - (SPAN_D + 8) * 86400; frames = []
    while cur < now:
        df = c.get_klines(sym, interval="Min15", start=cur, end=min(now, cur + span))
        if df is None or df.empty:
            break
        frames.append(df); nxt = int(df.index[-1].timestamp()) + step
        if nxt <= cur:
            break
        cur = nxt
    if not frames:
        return None
    df = pd.concat(frames)
    return df[~df.index.duplicated(keep="first")]


def h4_squeeze_flags(df15):
    """Aggregate 15m -> H4; return per-H4-bar squeeze-on flags + coil length."""
    h4 = pd.DataFrame({
        "high": df15["high"].resample("4h").max(),
        "low": df15["low"].resample("4h").min(),
        "close": df15["close"].resample("4h").last(),
    }).dropna()
    cl = h4["close"].astype(float)
    mid = cl.rolling(20).mean(); sd = cl.rolling(20).std()
    ema = cl.ewm(span=20, adjust=False).mean()
    pc = cl.shift(1)
    tr = pd.concat([(h4["high"] - h4["low"]), (h4["high"] - pc).abs(), (h4["low"] - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(20).mean()
    on = ((mid + 2.0 * sd) < (ema + 1.5 * atr)) & ((mid - 2.0 * sd) > (ema - 1.5 * atr))
    coil = []
    run = 0
    for v in on:
        run = run + 1 if bool(v) else 0
        coil.append(run)
    return pd.Series(coil, index=h4.index), h4


def sim_convex(entry, sl_frac, lev, H, L, C, i0):
    one_r = sl_frac * lev * 100
    o = entry * (1 + HAIR)
    fee = 2 * FEE * lev * 100
    end = min(len(H), i0 + 1 + MAXBARS); realized = None
    for k in range(i0 + 1, end):
        fl = (L[k] - o) / o * lev * 100
        fh = (H[k] - o) / o * lev * 100
        if fl <= -one_r:
            realized = -one_r; break
        if fh >= TP_R * one_r:
            realized = TP_R * one_r; break
    if realized is None:
        k = end - 1
        realized = (C[k] - o) / o * lev * 100
    return (realized - fee - HAIR * lev * 100) / one_r


fires = []
listed_cache = {}
for sym, _turn in uni:
    df15 = fetch_min15(sym)
    if df15 is None or len(df15) < 800:
        continue
    coil, h4 = h4_squeeze_flags(df15)
    d = df15.reset_index()
    tcol = d.columns[0]
    T = [int(x.timestamp()) for x in d[tcol]]
    C = [float(x) for x in d["close"]]; H = [float(x) for x in d["high"]]; L = [float(x) for x in d["low"]]
    V = [float(x) for x in d["volume"]]
    coil_at = {int(ts.timestamp()): int(cv) for ts, cv in coil.items()}
    coil_keys = sorted(coil_at)
    ck_i = 0
    for i in range(100, len(C) - 1):
        t = T[i]
        # prior COMPLETED H4 bar's coil state
        while ck_i + 1 < len(coil_keys) and coil_keys[ck_i + 1] + 14400 <= t:
            ck_i += 1
        prior_coil = coil_at.get(coil_keys[ck_i], 0) if coil_keys and coil_keys[ck_i] + 14400 <= t else 0
        if prior_coil < MIN_COIL_H4:
            continue
        rng_hi = max(H[i - BREAK_LB:i])
        if C[i] <= rng_hi:
            continue  # long-only break of the recent range
        if C[i - 1] > 0 and abs(C[i] / C[i - 1] - 1) > 0.06:
            continue  # vertical blow-off bar guard
        vb = V[i - 21:i - 1]
        mu = sum(vb) / len(vb); sdv = (sum((x - mu) ** 2 for x in vb) / len(vb)) ** 0.5
        if sdv > 0 and (V[i] - mu) / sdv < 1.0:
            continue
        if sym not in listed_cache:
            listed_cache[sym] = bybit_listed(sym)
        if listed_cache[sym] is False:
            continue
        # stop: recent-range low distance, ATR15 floored/capped (as live squeeze)
        atr15 = sum(abs(H[j] - L[j]) for j in range(i - 14, i)) / 14 / max(C[i], 1e-9)
        rng_lo = min(L[i - 6:i])
        sl_frac = min(max((C[i] - rng_lo) / C[i], 0.8 * atr15), 2.5 * atr15)
        lev = 5
        if sl_frac * lev * 100 > 20.0:
            lev = max(1, int(20.0 / (sl_frac * 100)))
        if sl_frac * lev * 100 > 20.0:
            sl_frac = 20.0 / 100.0 / lev
        fires.append({"t": t, "sym": sym, "i": i, "entry": C[i], "sl": sl_frac, "lev": lev,
                      "H": None})  # H filled below via closure-free sim
        fires[-1]["R"] = sim_convex(C[i], sl_frac, lev, H, L, C, i)

fires.sort(key=lambda x: x["t"])
# single-slot serialization: skip fires while a prior trade is "open" (approx by horizon exit bar)
serial = []
busy_until = 0
for f in fires:
    if f["t"] < busy_until:
        continue
    serial.append(f)
    busy_until = f["t"] + MAXBARS * 900  # conservative: full horizon occupancy upper bound
# report both: ALL fires (signal quality) and serialized (portfolio-ish)
def stats(xs, label):
    if not xs:
        print(f"{label:22} n=0"); return
    rs = sorted(x["R"] for x in xs)
    net = sum(rs); wins = sum(1 for r in rs if r > 0)
    half_t = xs[len(xs) // 2]["t"]
    e = [x["R"] for x in xs if x["t"] < half_t]; l = [x["R"] for x in xs if x["t"] >= half_t]
    print(f"{label:22} n={len(xs):3d} netR={net:+7.2f} avgR={net/len(xs):+.2f} win%={100*wins/len(xs):3.0f} "
          f"exBest={net-max(rs):+7.2f} early={sum(e)/len(e) if e else float('nan'):+.2f} late={sum(l)/len(l) if l else float('nan'):+.2f}")
print(f"H4-coil(>= {MIN_COIL_H4} bars) + 15m break | band skip={SKIP} univ={UNIV} | span {SPAN_D}d | horizon {MAXBARS//96}d | gate on | long-only")
stats(fires, "ALL fires")
stats(serial, "serialized (1 slot)")
