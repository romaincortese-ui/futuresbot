"""Coiled-Spring (squeeze) vs Wildcard, APPLES-TO-APPLES: same universe, same
window, and the SAME convex exit that is now live (no bank, -1R hard stop / +5R
TP, ride). 15m detection (live cadence) + 15m forward execution, adverse-first
intrabar, entry+exit slippage, single-slot (1 position at a time, like live).
Reports 60d + last-30d, win%, avg R, and OUTLIER-ROBUSTNESS (net excl. best trade).
"""
import os, time
from datetime import datetime, timezone
import pandas as pd
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.wildcard import detect_wildcard_signal
from futuresbot.squeeze import detect_squeeze_signal, _ema, _atr_series, BB_PERIOD, KC_PERIOD

c = MexcFuturesClient(FuturesConfig.from_env())
now = int(time.time())
SPAN_D = int(os.environ.get("BT_SPAN_D", "60"))
UNIV = int(os.environ.get("BT_UNIV", "45"))
HAIR = float(os.environ.get("BT_HAIRCUT_BPS", "10")) / 10000.0
FEE = 0.000594; BAL = 62.0; TP_R = 5.0; MAXBARS = 192  # 48h forward at 15m
STBL = ("USDC", "USDE", "USD1", "DAI", "FDUSD", "TUSD", "BUSD")

tk = c.public_get("/api/v1/contract/ticker", {}); td = tk.get("data") if isinstance(tk, dict) else tk
uni = sorted([(t["symbol"], float(t.get("amount24") or 0)) for t in (td or [])
              if t.get("symbol", "").endswith("_USDT") and float(t.get("amount24") or 0) >= 3e6
              and not any(k in t["symbol"] for k in STBL)], key=lambda x: -x[1])[:UNIV]

def fetch_min15(sym):
    step = 900; span = step * 1999; cur = now - (SPAN_D + 2) * 86400; frames = []
    while cur < now:
        end = min(now, cur + span)
        df = c.get_klines(sym, interval="Min15", start=cur, end=end)
        if df is None or df.empty: break
        frames.append(df); nxt = int(df.index[-1].timestamp()) + step
        if nxt <= cur: break
        cur = nxt
    if not frames: return None
    df = pd.concat(frames); df = df[~df.index.duplicated(keep="first")]
    return df

PD = {}
for s, _ in uni:
    df = fetch_min15(s)
    if df is None or len(df) < 120: continue
    df = df.reset_index(drop=False).rename(columns={"index": "time"}) if "time" not in df.columns else df.reset_index(drop=True)
    cl = df["close"].astype(float)
    mid = cl.rolling(BB_PERIOD).mean(); sd = cl.rolling(BB_PERIOD).std()
    ema = _ema(cl, KC_PERIOD); atr = _atr_series(df, KC_PERIOD)
    sq = ((mid + 2.0 * sd) < (ema + 1.5 * atr)) & ((mid - 2.0 * sd) > (ema - 1.5 * atr))
    PD[s] = {"df": df.reset_index(drop=True),
             "H": [float(x) for x in df["high"]], "L": [float(x) for x in df["low"]],
             "C": [float(x) for x in df["close"]],
             "T": [int(t.timestamp()) for t in pd.to_datetime(df["time"])] if "time" in df.columns else [int(t) for t in df.index],
             "SQ": [bool(x) for x in sq]}
print(f"universe {len(PD)} pairs | span {SPAN_D}d | convex exit (-1R/+{TP_R:.0f}R) | 15m exec | {HAIR*1e4:.0f}bps/leg")

def sim_convex(sig, d, i0):
    H, L, C, T = d["H"], d["L"], d["C"], d["T"]
    fav = 1.0 if sig.side == "LONG" else -1.0
    lev = sig.leverage; one_r = sig.sl_margin_pct
    o = sig.entry_price * (1 + HAIR if fav > 0 else 1 - HAIR)
    fee = 2 * FEE * lev * 100
    end = min(len(H), i0 + 1 + MAXBARS); realized = None; k = i0 + 1
    for k in range(i0 + 1, end):
        fl = ((L[k] - o) / o if fav > 0 else (o - H[k]) / o) * lev * 100  # fav-excursion at adverse tip
        fh = ((H[k] - o) / o if fav > 0 else (o - L[k]) / o) * lev * 100  # fav-excursion at favorable tip
        if fl <= -one_r: realized = -one_r; break          # adverse-first: -1R stop
        if fh >= TP_R * one_r: realized = TP_R * one_r; break  # +5R TP
    if realized is None:
        k = end - 1; realized = ((C[k] - o) / o if fav > 0 else (o - C[k]) / o) * lev * 100
    net = realized - fee - HAIR * lev * 100
    return net / one_r, sig.balance_fraction * BAL * net / 100.0, T[k]

def scan(kind):
    fires = []
    for s, d in PD.items():
        df = d["df"]; C, H, L, SQ, T = d["C"], d["H"], d["L"], d["SQ"], d["T"]
        n = len(C)
        for i in range(60, n - 1):
            sig = None
            if kind == "wildcard":
                if C[i - 12] > 0 and abs(C[i] / C[i - 12] - 1) >= 0.08:
                    sig = detect_wildcard_signal(df.iloc[i - 60:i + 1], s)
            else:  # squeeze — cheap prefilter on precomputed coil + range break
                if SQ[i - 1] and (C[i] > max(H[i - 6:i]) or C[i] < min(L[i - 6:i])):
                    sig = detect_squeeze_signal(df.iloc[i - 55:i + 1], s)
            if sig is not None:
                fires.append((T[i], s, i, sig))
    return fires

def serialize(fires):  # single-slot, best-score-first at ties
    fires = sorted(fires, key=lambda x: (x[0], -abs(x[3].roc_pct)))
    busy = 0; out = []
    for t, s, i, sig in fires:
        if t < busy: continue
        R, usd, xt = sim_convex(sig, PD[s], i)
        out.append({"t": t, "s": s, "R": R, "usd": usd}); busy = xt
    return out

def stats(trades, since=None):
    tr = [x for x in trades if since is None or x["t"] >= since]
    if not tr: return "n=0"
    R = sorted(x["R"] for x in tr); usd = sum(x["usd"] for x in tr)
    netR = sum(R); wins = sum(1 for r in R if r > 0)
    best = max(R); netR_xbest = netR - best
    avg = netR / len(R)
    return (f"n={len(R):3d} netR={netR:+6.2f} net$={usd:+6.2f} win%={100*wins/len(R):3.0f} "
            f"avgR={avg:+.2f} best={best:+.2f} netR_exBest={netR_xbest:+6.2f}")

t30 = now - 30 * 86400
wc = serialize(scan("wildcard"))
os.environ["FUTURES_SQUEEZE_LONG_ONLY"] = "0"; sqLS = serialize(scan("squeeze"))
os.environ["FUTURES_SQUEEZE_LONG_ONLY"] = "1"; sqLO = serialize(scan("squeeze"))
print("\n=== 60d ===")
print(f"WILDCARD (baseline) : {stats(wc)}")
print(f"SQUEEZE  long+short : {stats(sqLS)}")
print(f"SQUEEZE  long-only  : {stats(sqLO)}")
print("=== last 30d ===")
print(f"WILDCARD (baseline) : {stats(wc, t30)}")
print(f"SQUEEZE  long+short : {stats(sqLS, t30)}")
print(f"SQUEEZE  long-only  : {stats(sqLO, t30)}")
