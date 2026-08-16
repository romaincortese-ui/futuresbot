"""A/B the pullback-resume gate on the LIVE exit stack.

    railway run --service Futures-bot python tools/pullback_ab.py
    AB_OFFSET_D=7 railway run --service Futures-bot python tools/pullback_ab.py

Run it across several AB_OFFSET_D values. On 2026-08-16 four disjoint weeks
disagreed in SIGN (-34.60, +23.70, -8.64, +3.17), so a single window will report
whatever that week happened to do and read like a verdict.

FUTURES_WILDCARD_REQUIRE_PULLBACK is the single largest filter in the detector
(~76% of trigger bars) and wildcard.py says outright it "has never been measured
for value". This measures it the only way that means anything: the shipped
detector, the live convex exits (-1R stop / own target / 0.30xpeak retention /
24h clock), live sizing, funding included -- AND the real slot cap, because
turning the filter off multiplies signals and a study that lets the OFF arm hold
unlimited concurrent positions is measuring a bot that does not exist.

Read-only. Places nothing.
"""
import os, sys, time, json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime
from futuresbot import shadow_ledger as shadow
from futuresbot import wildcard as W

cfg = FuturesConfig.from_env()
client = MexcFuturesClient(cfg)
rt = FuturesRuntime(cfg, client)

SPAN_BARS = int(os.environ.get("AB_BARS", "672"))        # 7d of Min15
MAX_SYMS = int(os.environ.get("AB_SYMS", "40"))
SLOTS = int(os.environ.get("AB_SLOTS", "2"))
EQUITY = rt._last_known_equity() or 140.0
now_t = time.time()

# --- universe: the wildcard's own band -------------------------------------
tickers = client.get_all_tickers() or []
majors = rt._major_symbols(tickers, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
floor = W.wildcard_min_turnover_usdt()
band = []
for t in tickers:
    s = str(t.get("symbol") or "")
    if not s.endswith("_USDT") or not rt._is_tradeable_crypto(s) or s in majors:
        continue
    if float(t.get("amount24") or 0.0) < floor:
        continue
    band.append((rt._range_24h(t), s))
band.sort(reverse=True)
syms = [s for _r, s in band[:MAX_SYMS]]
print(f"equity ${EQUITY:.2f} | band {len(band)} -> studying {len(syms)} | "
      f"{SPAN_BARS} Min15 bars | {SLOTS} slots | offset {os.environ.get('AB_OFFSET_D','0')}d")

OFFSET_D = float(os.environ.get("AB_OFFSET_D", "0"))
end = int(now_t - OFFSET_D * 86400)
now_t = end   # resolve as of the window end, not wall clock
def _fetch(s):
    try:
        return s, client.get_klines(s, interval="Min15", start=end - SPAN_BARS * 900, end=end)
    except Exception:
        return s, None
with ThreadPoolExecutor(max_workers=8) as pool:
    frames = {s: f for s, f in pool.map(_fetch, syms)}
frames = {s: f for s, f in frames.items() if f is not None and len(f) >= 250}
print(f"frames ok: {len(frames)}")

funding = {s: rt._funding_settlements(s) for s in frames}

def bars_of(df):
    idx = df.index
    def ts(i):
        try:
            return float(idx[i].timestamp())
        except Exception:
            return now_t - (len(df) - 1 - i) * 900.0
    h = [float(x) for x in df["high"]]; l = [float(x) for x in df["low"]]
    c = [float(x) for x in df["close"]]
    return [(ts(i), h[i], l[i], c[i]) for i in range(len(df))], c

CACHE = {s: bars_of(f) for s, f in frames.items()}
MIN_ROC = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))

def candidates(require_pullback: bool):
    """Every signal the detector emits in the window, chronologically."""
    os.environ["FUTURES_WILDCARD_REQUIRE_PULLBACK"] = "1" if require_pullback else "0"
    out = []
    for s, df in frames.items():
        bars, closes = CACHE[s]
        n = len(closes)
        for i in range(250, n + 1):
            if i <= W.ROC_BARS:
                continue
            if abs(closes[i - 1] / closes[i - 1 - W.ROC_BARS] - 1.0) < MIN_ROC:
                continue
            sig = W.detect_wildcard_signal(df.iloc[:i], s)
            if sig is not None:
                out.append((bars[i - 1][0], s, sig))
    out.sort(key=lambda x: x[0])
    return out

def run_arm(require_pullback: bool):
    cands = candidates(require_pullback)
    open_until = {}          # symbol -> resolved_ts
    slots = []               # list of free-at timestamps
    taken, net, wins = 0, 0.0, 0
    skipped_slot = skipped_sym = 0
    for ts, s, sig in cands:
        slots[:] = [x for x in slots if x > ts]
        if open_until.get(s, 0) > ts:
            skipped_sym += 1
            continue
        if len(slots) >= SLOTS:
            skipped_slot += 1
            continue
        row = shadow.candidate_row(sig, sleeve="WILDCARD", reject_reason="ab")
        row["ts"] = ts
        done = shadow.resolve_outcome(row, CACHE[s][0], now_t,
                                      horizon_s=shadow.CONVEX_HORIZON_S, convex=True)
        if done is None:
            continue
        f_r = shadow.funding_cost_r(done, funding.get(s) or [])
        usd = shadow.net_usd(done, EQUITY, funding_r=f_r)
        if usd is None:
            continue
        taken += 1; net += usd; wins += 1 if usd > 0 else 0
        exit_ts = float(done.get("resolved_ts") or ts)
        open_until[s] = exit_ts
        slots.append(exit_ts)
    return {"signals": len(cands), "taken": taken, "net_usd": round(net, 2),
            "win_pct": round(100 * wins / taken, 1) if taken else 0.0,
            "blocked_slot": skipped_slot, "blocked_same_sym": skipped_sym}

res = {}
for label, flag in (("pullback ON (live)", True), ("pullback OFF", False)):
    res[label] = run_arm(flag)
    print(f"\n{label}: {json.dumps(res[label])}")

on, off = res["pullback ON (live)"], res["pullback OFF"]
print("\n" + "=" * 62)
print(f"signals   {on['signals']:5d} -> {off['signals']:5d}  "
      f"(x{off['signals']/max(1,on['signals']):.1f})")
print(f"taken     {on['taken']:5d} -> {off['taken']:5d}   (slot cap {SLOTS})")
print(f"net $   {on['net_usd']:+8.2f} -> {off['net_usd']:+8.2f}   "
      f"delta {off['net_usd']-on['net_usd']:+.2f}")
print(f"win%      {on['win_pct']:5.1f} -> {off['win_pct']:5.1f}")
os.environ["FUTURES_WILDCARD_REQUIRE_PULLBACK"] = "1"
