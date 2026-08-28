"""Offline audit: (b) env re-read, (c) short TP clamp, (e) sizing invariance."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from futuresbot import shadow_ledger as shadow  # noqa: E402
from futuresbot import wildcard as W  # noqa: E402

# relax ONLY the exhaustion gates so a synthetic frame can reach the sizing
# block; nothing under test (stop width / cap / TP geometry) is touched.
os.environ["FUTURES_WILDCARD_RSI_MAX"] = "101"
os.environ["FUTURES_WILDCARD_RSI_MIN"] = "-1"
os.environ["FUTURES_WILDCARD_MAX_WICK"] = "0.99"
os.environ["FUTURES_WILDCARD_VERTICAL_ATR_MULT"] = "99"


def frame(n=300, seed=1, vol=0.004, up=True, atr_mult_of_px=0.995):
    rng = np.random.default_rng(seed)
    px = [100.0]
    for _ in range(n - 1):
        px.append(px[-1] * (1.0 + rng.normal(0, vol)))
    c = np.array(px, dtype=float)
    s = 1.0 if up else -1.0
    pat = [0.030, -0.004, 0.028, -0.004, 0.025, -0.004, 0.022,
           -0.004, 0.010, -0.004, 0.008, -0.012, 0.020]
    for k, p in enumerate(pat):
        c[n - 13 + k] = c[n - 14 + k] * (1.0 + s * p)
    hi = c * (1.0 + (1.0 - atr_mult_of_px))
    lo = c * atr_mult_of_px
    v = np.full(n, 100.0)
    v[-1] = 500.0
    idx = pd.to_datetime(np.arange(n) * 900, unit="s")
    return pd.DataFrame({"open": c, "high": hi, "low": lo, "close": c, "volume": v}, index=idx)


f = frame()
r = []
s0 = W.detect_wildcard_signal(f, "T_USDT", r)
print("=== (b) does the detector re-read env per call? ===")
print("  long gates:", r, "| side", None if s0 is None else s0.side)
rows = []
for mult in (1.5, 2.0, 3.0, 4.0, 5.0):
    os.environ["FUTURES_WILDCARD_SL_ATR_MULT"] = str(mult)
    os.environ["FUTURES_WILDCARD_MAX_SL_MARGIN_PCT"] = "20"
    s = W.detect_wildcard_signal(f, "T_USDT")
    if s is None:
        print("  mult", mult, "none")
        continue
    slf = abs(s.entry_price - s.sl_price) / s.entry_price
    rows.append(round(slf, 9))
    print("  mult %.1f: sl_frac=%.6f lev=%d sl_margin=%.3f%% tp=%.5f"
          % (mult, slf, s.leverage, s.sl_margin_pct, s.tp_price))
print("  distinct sl_frac:", len(set(rows)), "of", len(rows))

print("\n  cap sweep at mult 4.0 (does the cap dial bite, and is the tool's")
print("  'capped' diagnostic right?):")
for cap in (20, 25, 30, 40):
    os.environ["FUTURES_WILDCARD_SL_ATR_MULT"] = "4.0"
    os.environ["FUTURES_WILDCARD_MAX_SL_MARGIN_PCT"] = str(cap)
    s = W.detect_wildcard_signal(f, "T_USDT")
    slf = abs(s.entry_price - s.sl_price) / s.entry_price
    true_bind = slf * 7.0 * 100.0 > cap          # untrimmed lev is 7
    tool_diag = slf * float(s.leverage) * 100.0 >= cap - 0.5
    print("    cap %d: sl_frac=%.6f lev=%d sl_margin=%.3f%% TRUE_bind=%s tool_capped=%s"
          % (cap, slf, s.leverage, s.sl_margin_pct, true_bind, tool_diag))

print("\n=== (c) SHORT TP clamp: reachable R or nominal R? ===")
fs = frame(up=False, atr_mult_of_px=0.995)
r = []
s = W.detect_wildcard_signal(fs, "T_USDT", r)
print("  short gates:", r, "| side", None if s is None else s.side)
if s is not None and s.side == "SHORT":
    for mult in (2.0, 3.0, 4.0, 5.0, 8.0):
        os.environ["FUTURES_WILDCARD_SL_ATR_MULT"] = str(mult)
        os.environ["FUTURES_WILDCARD_MAX_SL_MARGIN_PCT"] = "30"
        rr = []
        s = W.detect_wildcard_signal(fs, "T_USDT", rr)
        e, sl, tp = s.entry_price, s.sl_price, s.tp_price
        one = abs(e - sl)
        print("  mult %.1f: slf=%.5f tp_dist=%.5f clamped=%s tool_tp_r=%.4f shadow_tp_r=%.4f nominal=5.0"
              % (mult, one / e, (e - tp) / e, "short_tp_clamped" in rr,
                 abs(tp - e) / one, shadow.signal_tp_r(s)))

print("\n=== (e) dollar-risk invariance under the LIVE sizing path ===")
print("  runtime._entry_margin: margin = risk_pct*avail*100/sl_margin_pct,")
print("  capped at FUTURES_WILDCARD_MAX_MARGIN_PCT (0.25) of equity.")
eq = 162.0
risk_pct = 0.0187
maxm = 0.25
for cap in (20, 30):
    for mult in (3.0, 4.0):
        os.environ["FUTURES_WILDCARD_SL_ATR_MULT"] = str(mult)
        os.environ["FUTURES_WILDCARD_MAX_SL_MARGIN_PCT"] = str(cap)
        s = W.detect_wildcard_signal(f, "T_USDT")
        smp = float(s.sl_margin_pct)
        want = risk_pct * eq * 100.0 / smp
        used = min(want, maxm * eq)
        risk_usd = used * smp / 100.0
        notional = used * s.leverage
        print("  cap %d mult %.1f: sl_margin=%.2f%% lev=%d margin$=%.2f (want %.2f) "
              "notional$=%.2f -> 1R=$%.4f  bound=%s"
              % (cap, mult, smp, s.leverage, used, want, notional, risk_usd, used < want - 1e-9))
