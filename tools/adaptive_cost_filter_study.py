"""Fixed margin-% floor vs ADAPTIVE cost-drag filter for the squeeze.

Algebra: fee(margin) = 2*fee_rate*lev*100 and 1R(margin) = sl_frac*lev*100, so
    cost_drag = (2*fee_rate + slippage) / sl_frac
LEVERAGE CANCELS. Thresholding "1R >= 8% of margin" therefore permits ~5.5%
drag at x2 but ~27% at x10 — it is a leverage-contaminated proxy for the real
quantity. The adaptive rule thresholds cost_drag directly, and uses the
SYMBOL's own taker fee, so each opportunity is judged on its true cost burden.

Compares, on the same fire set: no filter / fixed margin floors / adaptive
cost-drag caps. Reports what each design keeps, kills, and earns.
"""
import json
import os
import time
import urllib.request

import pandas as pd

from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.squeeze import detect_squeeze_signal, _ema, _atr_series, BB_PERIOD, KC_PERIOD

c = MexcFuturesClient(FuturesConfig.from_env())
now = int(time.time()) - int(float(os.environ.get("BT_END_OFFSET_D", "0")) * 86400)
SPAN_D = int(os.environ.get("BT_SPAN_D", "60"))
UNIV = int(os.environ.get("BT_UNIV", "30"))
SKIP = int(os.environ.get("BT_UNIV_SKIP", "0"))
HAIR = 0.001; DEFAULT_FEE = 0.000594; TP_R = 5.0
MAXBARS = int(float(os.environ.get("BT_HORIZON_D", "7")) * 96)
STBL = ("USDC", "USDE", "USD1", "DAI", "FDUSD", "TUSD", "BUSD")

tk = c.public_get("/api/v1/contract/ticker", {}); td = tk.get("data") if isinstance(tk, dict) else tk
uni = sorted([(t["symbol"], float(t.get("amount24") or 0)) for t in (td or [])
              if t.get("symbol", "").endswith("_USDT") and float(t.get("amount24") or 0) >= 3e6
              and not any(k in t["symbol"] for k in STBL)], key=lambda x: -x[1])[SKIP:SKIP + UNIV]

fee_cache = {}
def taker_fee(sym):
    if sym not in fee_cache:
        try:
            d = c.get_contract_detail(sym) or {}
            f = float(d.get("takerFeeRate") or 0) or DEFAULT_FEE
        except Exception:
            f = DEFAULT_FEE
        fee_cache[sym] = f
    return fee_cache[sym]

listed = {}
def blisted(s):
    if s not in listed:
        try:
            req = urllib.request.Request(
                f"https://api.bybit.com/v5/market/kline?category=linear&symbol={s.replace('_','')}&interval=60&limit=2",
                headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                listed[s] = bool(((json.loads(r.read().decode()).get("result") or {}).get("list")) or [])
        except Exception:
            listed[s] = None
    return listed[s]


def fetch(s):
    step = 900; span = step * 1999; cur = now - (SPAN_D + 3) * 86400; fr = []
    while cur < now:
        df = c.get_klines(s, interval="Min15", start=cur, end=min(now, cur + span))
        if df is None or df.empty:
            break
        fr.append(df); nxt = int(df.index[-1].timestamp()) + step
        if nxt <= cur:
            break
        cur = nxt
    if not fr:
        return None
    df = pd.concat(fr)
    return df[~df.index.duplicated(keep="first")].reset_index(drop=True)


def sim(entry, sl_frac, lev, fee_rate, H, L, C, i0):
    one_r = sl_frac * lev * 100.0
    o = entry * (1 + HAIR)
    cost = (2 * fee_rate * lev * 100.0) + (HAIR * lev * 100.0)
    end = min(len(H), i0 + 1 + MAXBARS); realized = None
    for k in range(i0 + 1, end):
        if (L[k] - o) / o * lev * 100.0 <= -one_r:
            realized = -one_r; break
        if (H[k] - o) / o * lev * 100.0 >= TP_R * one_r:
            realized = TP_R * one_r; break
    if realized is None:
        realized = (C[end - 1] - o) / o * lev * 100.0
    return (realized - cost) / one_r


fires = []
for s, _ in uni:
    df = fetch(s)
    if df is None or len(df) < 120:
        continue
    cl = df["close"].astype(float)
    mid = cl.rolling(BB_PERIOD).mean(); sd = cl.rolling(BB_PERIOD).std()
    ema = _ema(cl, KC_PERIOD); atr = _atr_series(df, KC_PERIOD)
    on = [bool(x) for x in ((mid + 2.0 * sd) < (ema + 1.5 * atr)) & ((mid - 2.0 * sd) > (ema - 1.5 * atr))]
    C = [float(x) for x in df["close"]]; H = [float(x) for x in df["high"]]; L = [float(x) for x in df["low"]]
    for i in range(100, len(C) - 1):
        if not on[i - 1]:          # lossless prefilter: detector requires coil on prior bar
            continue
        sig = detect_squeeze_signal(df.iloc[i - 90:i + 1], s)
        if sig is None or blisted(s) is False:
            continue
        sl_frac = sig.sl_margin_pct / (sig.leverage * 100.0)
        fr_ = taker_fee(s)
        drag = (2 * fr_ + HAIR) / sl_frac if sl_frac > 0 else 9.99
        fires.append({"sym": s, "R": sim(sig.entry_price, sl_frac, sig.leverage, fr_, H, L, C, i),
                      "m": sig.sl_margin_pct, "lev": sig.leverage, "drag": drag, "sl_frac": sl_frac})

if not fires:
    print("no fires"); raise SystemExit
print(f"squeeze fires={len(fires)} | band skip={SKIP} univ={UNIV} | {SPAN_D}d | horizon {MAXBARS//96}d\n")


def rep(label, kept):
    if not kept:
        print(f"{label:34} n=  0  (filters everything)"); return
    R = [f["R"] for f in kept]; net = sum(R)
    killed = len(fires) - len(kept)
    kr = sum(f["R"] for f in fires if f not in kept)
    print(f"{label:34} keep={len(kept):3d} kill={killed:3d} | netR={net:+7.2f} avgR={net/len(kept):+.2f} "
          f"win%={100*sum(1 for r in R if r>0)/len(R):3.0f} exBest={net-max(R):+7.2f} | killedR={kr:+7.2f}")

print("BASELINE")
rep("no filter (pre-2026-07-25)", fires)
print("\nFIXED margin-% floor (what is LIVE now = 8)")
for m in (5, 8, 10, 12):
    rep(f"  1R >= {m}% of margin", [f for f in fires if f["m"] >= m])
print("\nADAPTIVE cost-drag cap (leverage-invariant, symbol-fee aware)")
for d in (0.20, 0.15, 0.12, 0.10, 0.08):
    rep(f"  cost drag <= {d*100:.0f}% of 1R", [f for f in fires if f["drag"] <= d])
print("\nDISAGREEMENTS (where the two designs differ), live-relevant:")
LIVE_M, BEST_D = 8.0, 0.12
only_fixed = [f for f in fires if f["m"] >= LIVE_M and f["drag"] > BEST_D]
only_adapt = [f for f in fires if f["m"] < LIVE_M and f["drag"] <= BEST_D]
print(f"  kept by fixed-8 but KILLED by drag-12%: n={len(only_fixed):3d} netR={sum(f['R'] for f in only_fixed):+7.2f}")
print(f"  killed by fixed-8 but KEPT by drag-12%: n={len(only_adapt):3d} netR={sum(f['R'] for f in only_adapt):+7.2f}")
lv = sorted({f["lev"] for f in fires})
print(f"\n  leverage values in sample: {lv} (if all equal, the two rules are equivalent by construction)")
