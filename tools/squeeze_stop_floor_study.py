"""Squeeze stop-FLOOR study (motivated by XRP 2026-07-24: 1R = 2.31% margin,
closed -1.43R with 32% fee drag).

The squeeze's stop floor is ATR-relative (0.8 x ATR); on a low-ATR major that
produces a razor-thin stop in MARGIN terms, so noise stops it out and fees eat
the edge. The -20% cap only trims stops that are too WIDE — nothing enforces a
minimum. This measures:
  1. How often historical squeeze fires produce a thin 1R (< X% margin)?
  2. How do thin-stop fires perform vs normal ones (R and fee drag)?
  3. Would a MARGIN FLOOR (raise sl_frac so 1R >= floor%) improve the sleeve?

Floor is applied like the cap's sibling: widen sl_frac to the floor, keep
leverage, so the TP (+5R) scales with it. Fees modelled per-leg on notional so
the fee-drag effect of thin stops is captured in R.
"""
import json
import os
import time
import urllib.request

import pandas as pd

from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.squeeze import detect_squeeze_signal

c = MexcFuturesClient(FuturesConfig.from_env())
now = int(time.time())
SPAN_D = int(os.environ.get("BT_SPAN_D", "60"))
UNIV = int(os.environ.get("BT_UNIV", "30"))
SKIP = int(os.environ.get("BT_UNIV_SKIP", "0"))  # squeeze turf = liquid band
HAIR = 0.001; FEE = 0.000594; TP_R = 5.0
MAXBARS = int(float(os.environ.get("BT_HORIZON_D", "7")) * 96)
FLOORS = [float(x) for x in os.environ.get("FLOORS", "0,5,8,10,12").split(",")]
STBL = ("USDC", "USDE", "USD1", "DAI", "FDUSD", "TUSD", "BUSD")

tk = c.public_get("/api/v1/contract/ticker", {}); td = tk.get("data") if isinstance(tk, dict) else tk
uni = sorted([(t["symbol"], float(t.get("amount24") or 0)) for t in (td or [])
              if t.get("symbol", "").endswith("_USDT") and float(t.get("amount24") or 0) >= 3e6
              and not any(k in t["symbol"] for k in STBL)], key=lambda x: -x[1])[SKIP:SKIP + UNIV]


def blisted(s):
    try:
        req = urllib.request.Request(
            f"https://api.bybit.com/v5/market/kline?category=linear&symbol={s.replace('_','')}&interval=60&limit=2",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return bool(((json.loads(r.read().decode()).get("result") or {}).get("list")) or [])
    except Exception:
        return None


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


def sim(entry, sl_frac, lev, H, L, C, i0):
    """Convex sim in R. Fees are per-leg on NOTIONAL (=lev x margin), so a thin
    stop (small 1R) correctly shows a large fee drag in R terms."""
    one_r_margin = sl_frac * lev * 100.0
    o = entry * (1 + HAIR)
    fee_margin = 2 * FEE * lev * 100.0          # round-trip fees, % of margin
    slip_margin = HAIR * lev * 100.0
    end = min(len(H), i0 + 1 + MAXBARS); realized = None
    for k in range(i0 + 1, end):
        fl = (L[k] - o) / o * lev * 100.0
        fh = (H[k] - o) / o * lev * 100.0
        if fl <= -one_r_margin:
            realized = -one_r_margin; break
        if fh >= TP_R * one_r_margin:
            realized = TP_R * one_r_margin; break
    if realized is None:
        realized = (C[end - 1] - o) / o * lev * 100.0
    net = realized - fee_margin - slip_margin
    return net / one_r_margin, fee_margin / one_r_margin  # R, fee-as-fraction-of-1R


PD = {}; listed = {}
for s, _ in uni:
    df = fetch(s)
    if df is None or len(df) < 120:
        continue
    PD[s] = df

print(f"squeeze stop-floor study | band skip={SKIP} univ={UNIV} | {SPAN_D}d | horizon {MAXBARS//96}d | long-only, gate on")
base_fires = []
for s, df in PD.items():
    C = [float(x) for x in df["close"]]; H = [float(x) for x in df["high"]]; L = [float(x) for x in df["low"]]
    for i in range(100, len(C) - 1):
        sig = detect_squeeze_signal(df.iloc[i - 90:i + 1], s)
        if sig is None:
            continue
        if s not in listed:
            listed[s] = blisted(s)
        if listed[s] is False:
            continue
        base_fires.append({"sym": s, "i": i, "entry": sig.entry_price, "sl_frac": sig.sl_margin_pct / (sig.leverage * 100.0),
                           "lev": sig.leverage, "sl_margin": sig.sl_margin_pct, "H": H, "L": L, "C": C})

if not base_fires:
    print("no fires"); raise SystemExit
thin5 = sum(1 for f in base_fires if f["sl_margin"] < 5)
thin8 = sum(1 for f in base_fires if f["sl_margin"] < 8)
sl_vals = sorted(f["sl_margin"] for f in base_fires)
print(f"\nfires={len(base_fires)} | 1R margin%: min={sl_vals[0]:.2f} p25={sl_vals[len(sl_vals)//4]:.2f} "
      f"median={sl_vals[len(sl_vals)//2]:.2f} max={sl_vals[-1]:.2f}")
print(f"THIN stops: {thin5} fires (<5% margin, {100*thin5/len(base_fires):.0f}%) | {thin8} (<8%, {100*thin8/len(base_fires):.0f}%)  [XRP live was 2.31%]")

# 1) thin vs normal at CURRENT settings
print(f"\n--- current settings: thin (<8% 1R) vs normal ---")
for label, grp in (("thin(<8%)", [f for f in base_fires if f["sl_margin"] < 8]),
                   ("normal(>=8%)", [f for f in base_fires if f["sl_margin"] >= 8])):
    if not grp:
        print(f"  {label:14} n=0"); continue
    res = [sim(f["entry"], f["sl_frac"], f["lev"], f["H"], f["L"], f["C"], f["i"]) for f in grp]
    R = [r for r, _ in res]; fee = [x for _, x in res]
    print(f"  {label:14} n={len(R):3d} netR={sum(R):+7.2f} avgR={sum(R)/len(R):+.2f} "
          f"win%={100*sum(1 for r in R if r>0)/len(R):3.0f} avg fee={sum(fee)/len(fee)*100:5.1f}% of 1R")

# 2) sweep the margin floor
print(f"\n--- margin-floor sweep (widen sl_frac so 1R >= floor% of margin) ---")
print(f"{'floor%':>8}{'n':>5}{'netR':>9}{'avgR':>7}{'win%':>6}{'exBest':>9}{'avgFee%1R':>11}{'early':>7}{'late':>7}")
for floor in FLOORS:
    res = []
    for f in base_fires:
        sl_frac = f["sl_frac"]
        if floor > 0 and sl_frac * f["lev"] * 100.0 < floor:
            sl_frac = floor / 100.0 / f["lev"]
        r, fee = sim(f["entry"], sl_frac, f["lev"], f["H"], f["L"], f["C"], f["i"])
        res.append((f["i"], r, fee))
    R = [r for _, r, _ in res]; fees = [x for _, _, x in res]
    half = len(res) // 2
    e = [r for _, r, _ in res[:half]]; l = [r for _, r, _ in res[half:]]
    net = sum(R)
    print(f"{floor:>8.0f}{len(R):>5}{net:>+9.2f}{net/len(R):>+7.2f}{100*sum(1 for r in R if r>0)/len(R):>6.0f}"
          f"{net-max(R):>+9.2f}{sum(fees)/len(fees)*100:>11.1f}{sum(e)/len(e) if e else float('nan'):>+7.2f}{sum(l)/len(l) if l else float('nan'):>+7.2f}")
print("\nfloor=0 is the CURRENT live behaviour (no minimum). exBest = netR minus best single trade.")
