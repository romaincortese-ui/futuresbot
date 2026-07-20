"""Entry-lateness vs convex outcome for the wildcard, on the LIVE config
(small-cap band, Bybit gate). ALL detector fires (not slot-serialized) — this
studies the conditional relationship, not portfolio P&L. Buckets must be
time-split consistent before any gate is proposed (the 3 live losers at
lateness 0.7-1.0 are n=3; this gives hundreds of observations)."""
import json
import os
import time
import urllib.request

import pandas as pd

from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.wildcard import ROC_BARS, detect_wildcard_signal

c = MexcFuturesClient(FuturesConfig.from_env())
now = int(time.time())
SPAN_D = int(os.environ.get("BT_SPAN_D", "60"))
HAIR = 0.001; FEE = 0.000594; TP_R = 5.0; MAXBARS = 192
STBL = ("USDC", "USDE", "USD1", "DAI", "FDUSD", "TUSD", "BUSD")

tk = c.public_get("/api/v1/contract/ticker", {}); td = tk.get("data") if isinstance(tk, dict) else tk
ranked = sorted([(t["symbol"], float(t.get("amount24") or 0)) for t in (td or [])
                 if t.get("symbol", "").endswith("_USDT") and float(t.get("amount24") or 0) >= 3e6
                 and not any(k in t["symbol"] for k in STBL)], key=lambda x: -x[1])
uni = ranked[30:90]  # live band: skip top-30 majors


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
    step = 900; span = step * 1999; cur = now - (SPAN_D + 2) * 86400; frames = []
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
    return df[~df.index.duplicated(keep="first")].reset_index(drop=True)


def sim_convex(sig, H, L, C, i0):
    fav = 1.0 if sig.side == "LONG" else -1.0
    lev = sig.leverage; one_r = sig.sl_margin_pct
    o = sig.entry_price * (1 + HAIR if fav > 0 else 1 - HAIR)
    fee = 2 * FEE * lev * 100
    end = min(len(H), i0 + 1 + MAXBARS); realized = None
    for k in range(i0 + 1, end):
        fl = ((L[k] - o) / o if fav > 0 else (o - H[k]) / o) * lev * 100
        fh = ((H[k] - o) / o if fav > 0 else (o - L[k]) / o) * lev * 100
        if fl <= -one_r:
            realized = -one_r; break
        if fh >= TP_R * one_r:
            realized = TP_R * one_r; break
    if realized is None:
        k = end - 1
        realized = ((C[k] - o) / o if fav > 0 else (o - C[k]) / o) * lev * 100
    return (realized - fee - HAIR * lev * 100) / one_r


fires = []
listed_cache = {}
for sym, _turn in uni:
    df = fetch_min15(sym)
    if df is None or len(df) < 80:
        continue
    C = [float(x) for x in df["close"]]; H = [float(x) for x in df["high"]]; L = [float(x) for x in df["low"]]
    T = [int(t.timestamp()) for t in pd.to_datetime(df["time"])] if "time" in df.columns else list(range(len(C)))
    for i in range(60, len(C) - 1):
        if C[i - 12] <= 0 or abs(C[i] / C[i - 12] - 1) < 0.08:
            continue
        sig = detect_wildcard_signal(df.iloc[i - 60:i + 1], sym)
        if sig is None:
            continue
        if sym not in listed_cache:
            listed_cache[sym] = bybit_listed(sym)
        if listed_cache[sym] is False:
            continue  # live gate vetoes MEXC-only
        w = C[max(0, i - ROC_BARS):i + 1]
        lo, hi = min(w), max(w)
        lat = None if hi <= lo else ((C[i] - lo) / (hi - lo) if sig.side == "LONG" else (hi - C[i]) / (hi - lo))
        if lat is None:
            continue
        fires.append({"t": T[i], "sym": sym, "lat": lat, "R": sim_convex(sig, H, L, C, i)})

fires.sort(key=lambda x: x["t"])
half_t = fires[len(fires) // 2]["t"] if fires else 0
BUCKETS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 0.95), (0.95, 0.99), (0.99, 1.01)]
print(f"fires={len(fires)} | band=rank30-90 | gate=on | span={SPAN_D}d | ALL fires (not slot-serialized)")
print(f"{'lateness':12}{'n':>5}{'netR':>8}{'avgR':>7}{'win%':>6}{'exBestR':>9}{'earlyHalf':>10}{'lateHalf':>9}")
for a, b in BUCKETS:
    xs = [f for f in fires if a <= f["lat"] < b]
    if not xs:
        print(f"[{a:.2f},{b:.2f})    n=0"); continue
    rs = sorted(x["R"] for x in xs)
    net = sum(rs); wins = sum(1 for r in rs if r > 0)
    e = [x["R"] for x in xs if x["t"] < half_t]; l = [x["R"] for x in xs if x["t"] >= half_t]
    print(f"[{a:.2f},{b:.2f}) {len(xs):>5}{net:>+8.1f}{net/len(xs):>+7.2f}{100*wins/len(xs):>6.0f}{net-max(rs):>+9.1f}"
          f"{(sum(e)/len(e)) if e else float('nan'):>+10.2f}{(sum(l)/len(l)) if l else float('nan'):>+9.2f}")
