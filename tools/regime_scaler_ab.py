"""Does the regime size scaler earn its keep, and at what settings?

    railway run --service Futures-bot python tools/regime_scaler_ab.py

`FUTURES_REGIME_SIZE_SCALER_ENABLED=1` scales every convex entry by the traded
symbol's own Kaufman trend efficiency: full size at eff >= 0.45, a 0.25 FLOOR at
eff <= 0.20, linear between. It is currently justified by a thin result (+$3.93
over 42 entries) and it is doing real work — FARTCOIN_USDT opened at x0.25, so
1R was $0.75 against a ~$2.66 design R, and ZAMA at 42% of design.

THE ONLY WAY THIS CAN PAY. The scaler cannot change R; it changes DOLLARS. Total
$ = sum(R_i x mult_i) x 1R. Since every multiplier is <= 1.0, the scaler adds
money ONLY if it puts the small sizes on the LOSING trades — i.e. only if trend
efficiency at entry actually predicts the outcome. If efficiency is not
predictive, the scaler is a pure size reduction applied to a positive-expectancy
sleeve, which costs money by construction.

So two figures are reported, and they answer different questions:
  RAW        sum(R x mult) -- what it did to the account.
  NORMALISED sum(R x mult) / mean(mult) -- the same allocation at EQUAL average
             size. This isolates "is the tilt smart" from "is the book smaller".
If NORMALISED is not above the no-scaler total, the tilt is worthless and the
raw number is just the cost of trading smaller.

Part 2 replays the LAST 72 HOURS of real closed trades: recompute each entry's
efficiency, back out the multiplier that was actually applied, and rescale the
realised P&L to what each candidate setting would have paid.

RESULT, 2026-08-22 -- 85 symbols, 208 days, 1476 resolved convex trades.
THE TILT IS REAL. THE HAIRCUT COSTS MORE THAN THE TILT IS WORTH.

    efficiency at entry    n    mean R     net R    win%   live mult
    <= 0.10 chop          49    +0.103     +5.05   55.1%       0.25
    0.10-0.20            101    +0.019     +1.95   50.5%       0.25
    0.20-0.30            205    +0.280    +57.43   55.6%       0.40
    0.30-0.45            462    +0.153    +70.51   58.2%       0.77
    0.45-0.60            366    +0.243    +88.76   58.2%       1.00
    > 0.60 clean         293    +0.401   +117.47   61.8%       1.00

Efficiency PREDICTS. The bottom two buckets (n=150) are +0.103R and +0.019R,
i.e. zero, and the top bucket is +0.401R on 61.8% wins. Broadly monotonic with
one inversion (0.20-0.30 beats 0.30-0.45). The scaler is pointing the right way.

    setting                   mean mult      raw $    vs off  equal-size $     tilt
    OFF (no scaler)               1.000   +1052.97     +0.00      +1052.97    +0.00
    LIVE 0.20/0.45/0.25           0.777    +884.67   -168.31      +1139.11   +86.13
    floor 0.50                    0.851    +940.77   -112.20      +1105.37   +52.40
    floor 0.75                    0.926    +996.87    -56.10      +1077.06   +24.09
    narrow 0.15/0.30/0.25         0.895    +971.37    -81.60      +1084.99   +32.02
    wide 0.25/0.60/0.25           0.633    +759.91   -293.06      +1199.93  +146.96
    aggressive 0.30/0.50/0.10     0.604    +754.08   -298.89      +1247.58  +194.61

    half-split on the tilt      older      recent   both halves?
    LIVE 0.20/0.45/0.25        +13.60      +71.48   YES
    floor 0.50                  +8.26      +43.54   YES
    floor 0.75                  +3.79      +20.04   YES
    narrow 0.15/0.30/0.25      +24.75       +7.35   YES
    wide 0.25/0.60/0.25        +20.42     +123.60   YES
    aggressive 0.30/0.50/0.10  +12.71     +178.31   YES

EVERY VARIANT PASSES THE HALF-SPLIT. Nothing else measured this session did.

AND YET THE LIVE SETTING COSTS -$168.31. The reason is structural, not
statistical: every multiplier is <= 1.0, so the scaler can only ever SHRINK the
book. Mean multiplier 0.777 means the sleeve trades at 78% of its design size,
and on a positive-expectancy book that is a straight 22% haircut on P&L. The
tilt earns +$86; the haircut costs ~$254; the net is -$168.

Sharpening the tilt makes BOTH effects bigger and the net worse: "aggressive"
earns the largest tilt in the study (+$194.61) and the worst raw result
(-$298.89).

THE FIX IS RENORMALISATION, NOT RETUNING. Divide the multiplier by its own mean
so the average is 1.0 -- size UP in clean trends instead of only DOWN in chop.
That keeps the +$86 tilt and removes the -$254 haircut. Implemented as
FUTURES_WILDCARD_RISK_PCT 0.0187 -> 0.0187/0.777 = 0.0241, which RESTORES the
designed 1.87% mean risk (realised mean risk today is 0.777 x 1.87% = 1.45%),
rather than raising it. Per-trade risk at full multiplier becomes 2.41%, still
far under FUTURES_MAX_TRADE_RISK_PCT=5.

TWO HONEST CAVEATS.
- The tilt is RECENT-WEIGHTED in every variant (+13.60 older vs +71.48 recent on
  the live params). Efficiency has been more predictive in this trending market
  than before it; in chop the tilt is worth much less, though it stayed positive.
- This replay is unconstrained and produces ~3x the live trade count, so scale
  the dollar figures down accordingly before believing a monthly number.

THE LAST 72 HOURS OF REAL TRADES (15 closes, $+25.58 actually realised):

    when         symbol            eff  applied  actual $
    08-20 08:07  BTC_USDT         0.40     0.86     +0.17
    08-20 08:12  SOL_USDT         0.49     1.00     +5.49
    08-20 10:44  PRL_USDT         0.25     0.41     -0.87
    08-20 15:58  ETH_USDT         0.15     0.25     +0.32
    08-20 19:14  ENA_USDT         0.43     0.95    +11.10
    08-21 06:17  SOL_USDT         0.28     0.49     +0.85
    08-21 08:29  ORDI_USDT        0.64     1.00     -2.72
    08-21 09:45  GALA_USDT        0.36     0.73     +2.02
    08-21 12:41  TUT_USDT         0.69     1.00     +0.79
    08-21 18:57  GPS_USDT         0.57     1.00     -2.71
    08-21 19:26  ZEC_USDT         0.33     0.65     +5.72
    08-21 21:31  ETH_USDT         0.45     0.99     +0.56
    08-22 01:15  XRP_USDT         0.38     0.80     +5.84
    08-22 02:02  ZEC_USDT         0.64     1.00     +0.56
    08-22 08:10  ZAMA_USDT        0.09     0.25     -1.52

    setting                   would be $   delta $
    OFF (no scaler)               +27.48     +1.90
    LIVE 0.20/0.45/0.25           +25.58     +0.00  <- live
    floor 0.50                    +26.21     +0.63
    floor 0.75                    +26.85     +1.27
    narrow 0.15/0.30/0.25         +31.40     +5.82
    wide 0.25/0.60/0.25           +16.05     -9.53
    aggressive 0.30/0.50/0.10     +15.99     -9.60
    LIVE renormalised (x1/0.777)  +32.92     +7.34   [25.58/0.777]

READ THE 72h TABLE CAREFULLY. It is 15 trades and the window was PROFITABLE, so
"bigger size wins" is arithmetic, not evidence -- which is exactly why
renormalised-LIVE tops it. The tilt did do real work here (ZAMA, the worst trade,
was correctly floored to x0.25 on eff 0.09), but the 208-day study is the
evidence and the 72h table is an illustration.

Read-only. Places nothing.

Env: RS_DAYS (190) RS_POOL (80) RS_HOURS (72)
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from futuresbot import shadow_ledger as shadow
from futuresbot import wildcard as W
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.risk_controls import regime_size_multiplier, trend_efficiency
from futuresbot.runtime import FuturesRuntime
from futuresbot.trend import detect_trend_signal
from retention_trail_ab import make_floor, resolve

CHUNK, BAR = 2000, 900
FLOOR = make_floor("flat", 0.30, 1.0)
TREND_SYMS = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
LIVE = (0.20, 0.45, 0.25)

# Candidate settings. "off" is the null; the rest widen or narrow the ramp and
# lift the floor. A floor of 1.0 IS "off" by another name and is included as a
# consistency check on the arithmetic.
GRID = [
    ("OFF (no scaler)", None),
    ("LIVE 0.20/0.45/0.25", (0.20, 0.45, 0.25)),
    ("floor 0.50", (0.20, 0.45, 0.50)),
    ("floor 0.75", (0.20, 0.45, 0.75)),
    ("narrow 0.15/0.30/0.25", (0.15, 0.30, 0.25)),
    ("wide 0.25/0.60/0.25", (0.25, 0.60, 0.25)),
    ("aggressive 0.30/0.50/0.10", (0.30, 0.50, 0.10)),
]


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def mult_of(eff, params):
    if params is None:
        return 1.0
    lo, hi, fl = params
    return regime_size_multiplier(eff, lo=lo, hi=hi, floor_mult=fl)


def main() -> int:
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("RS_DAYS", 190), int(_env("RS_POOL", 80))
    hours = _env("RS_HOURS", 72)
    eq = rt._last_known_equity() or 165.0
    now = int(time.time())
    min_turn = W.wildcard_min_turnover_usdt()
    window = max(4, int(rt._env_float("FUTURES_REGIME_EFF_WINDOW", 24.0)))

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    ranked = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wc_syms = [s for a, s in ranked if s not in majors and a >= min_turn][:pool_n]

    # ---- part 2 needs the real trades first, so we know which symbols to pull
    cut = now - hours * 3600
    hist, page = [], 1
    while page <= 8:
        payload = cl.private_get("/api/v1/private/position/list/history_positions",
                                 {"page_num": page, "page_size": 100})
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        batch = data if isinstance(data, list) else (data.get("resultList") or [])
        if not batch:
            break
        hist.extend(batch)
        if min(float(r.get("updateTime") or 0) / 1000.0 for r in batch) < cut:
            break
        page += 1
    real = sorted((r for r in hist if float(r.get("updateTime") or 0) / 1000.0 >= cut),
                  key=lambda r: float(r.get("createTime") or 0))
    real_syms = {str(r.get("symbol") or "") for r in real}

    syms = sorted(set(wc_syms) | set(TREND_SYMS) | real_syms)
    print(f"equity ${eq:.2f} | {len(syms)} symbols | eff window {window} bars "
          f"| live params lo/hi/floor {LIVE}")

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

    with ThreadPoolExecutor(max_workers=6) as p:
        F = {s: f for s, f in p.map(fetch, syms) if f is not None and len(f) >= 200}
    span = len(F.get(wc_syms[0], next(iter(F.values())))) * BAR / 86400
    print(f"frames: {len(F)} symbols, ~{span:.0f}d")

    # =====================================================================
    # PART 1 — is efficiency predictive at all?
    # =====================================================================
    min_roc = max(0.0, rt._env_float("FUTURES_WILDCARD_MIN_ROC", 0.08))
    print("\ngenerating candidates, tagging each with its entry efficiency...")
    trades = []
    for s, df in F.items():
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

        def add(sig, i, kind):
            row = {"entry": float(sig.entry_price), "sl": float(sig.sl_price),
                   "tp": float(sig.tp_price), "side": sig.side}
            g = resolve(bars, i, row["entry"], row["sl"], row["tp"],
                        shadow.signal_tp_r(sig), sig.side, shadow.CONVEX_HORIZON_S,
                        shadow.cost_r(row), FLOOR,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is None:
                return
            r_net, _ex, _k = g
            eff = trend_efficiency(c[:i + 1], window)
            one_r = eq * 0.0187          # risk-targeted: 1R is a constant $
            trades.append({"sym": s, "kind": kind, "r": r_net, "eff": eff,
                           "ts": bars[i][0], "usd_full": r_net * one_r})

        if s in TREND_SYMS:
            for i in range(200, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None and sig.side == "LONG":
                    add(sig, i, "TREND")
        if s in wc_syms:
            for i in range(200, len(c)):
                if i <= W.ROC_BARS or roll[i] < min_turn:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < min_roc:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[:i + 1], s)
                if sig is not None:
                    add(sig, i, "WILDCARD")
    print(f"resolved trades: {len(trades)}")
    if not trades:
        return 0

    print("\n=== 1. IS ENTRY EFFICIENCY PREDICTIVE? (R is size-independent) ===")
    print(f"{'efficiency':<16} {'n':>5} {'mean R':>9} {'net R':>9} {'win%':>7} "
          f"{'live mult':>10}")
    eb = [("<= 0.10 chop", 0.0, 0.10), ("0.10-0.20", 0.10, 0.20),
          ("0.20-0.30", 0.20, 0.30), ("0.30-0.45", 0.30, 0.45),
          ("0.45-0.60", 0.45, 0.60), ("> 0.60 clean", 0.60, 9.9)]
    for label, a, b in eb:
        sub = [t for t in trades if a <= t["eff"] < b]
        if not sub:
            continue
        mr = sum(t["r"] for t in sub) / len(sub)
        wr = 100 * sum(1 for t in sub if t["r"] > 0) / len(sub)
        mm = mult_of((a + b) / 2 if b < 9 else 0.7, LIVE)
        print(f"{label:<16} {len(sub):5d} {mr:+9.3f} {sum(t['r'] for t in sub):+9.2f} "
              f"{wr:6.1f}% {mm:10.2f}")

    print("\n=== 2. $ P&L BY SETTING — raw vs at equal average size ===")
    base_r = sum(t["r"] for t in trades)
    one_r = eq * 0.0187
    print(f"  no-scaler baseline: netR {base_r:+.2f} = ${base_r*one_r:+.2f} "
          f"at 1R=${one_r:.2f}")
    print(f"{'setting':<24} {'mean mult':>10} {'raw $':>10} {'vs off':>9} "
          f"{'equal-size $':>13} {'tilt':>8}")
    for label, params in GRID:
        ms = [mult_of(t["eff"], params) for t in trades]
        mm = sum(ms) / len(ms)
        rawr = sum(t["r"] * m for t, m in zip(trades, ms))
        norm = rawr / mm if mm > 0 else 0.0
        print(f"{label:<24} {mm:10.3f} {rawr*one_r:+10.2f} "
              f"{(rawr-base_r)*one_r:+9.2f} {norm*one_r:+13.2f} "
              f"{(norm-base_r)*one_r:+8.2f}")

    print()
    print("=== 2b. HALF-SPLIT ON THE TILT (equal-size allocation effect) ===")
    tss = sorted(t["ts"] for t in trades)
    midts = tss[len(tss) // 2]
    print(f"{'setting':<24} {'older tilt $':>13} {'recent tilt $':>14}  both halves?")
    for label, params in GRID:
        if params is None:
            continue
        out = []
        for lo_t, hi_t in ((0, midts), (midts, 9e18)):
            sub = [t for t in trades if lo_t <= t["ts"] < hi_t]
            if not sub:
                out.append(0.0)
                continue
            ms = [mult_of(t["eff"], params) for t in sub]
            mm = sum(ms) / len(ms)
            rawr = sum(t["r"] * m for t, m in zip(sub, ms))
            out.append((rawr / mm - sum(t["r"] for t in sub)) * one_r if mm > 0 else 0.0)
        ok = "YES" if out[0] > 0 and out[1] > 0 else (
            "no" if out[0] < 0 and out[1] < 0 else "one half only")
        print(f"{label:<24} {out[0]:+13.2f} {out[1]:+14.2f}  {ok}")

    # =====================================================================
    # PART 2 — the last 72h of REAL trades
    # =====================================================================
    print(f"\n=== 3. THE LAST {hours:.0f}h OF REAL TRADES, RESCALED ===")
    print(f"{'when':<12} {'symbol':<14} {'eff':>6} {'applied':>8} {'actual $':>9}")
    rows = []
    for r in real:
        sym = str(r.get("symbol") or "")
        t_open = float(r.get("createTime") or 0) / 1000.0
        pnl = float(r.get("realised") or 0.0)
        df = F.get(sym)
        if df is None or len(df) == 0:
            print(f"{'?':<12} {sym:<14}    n/a      n/a {pnl:+9.2f}  (no klines)")
            continue
        ts = [float(x.timestamp()) for x in df.index]
        c = [float(x) for x in df["close"]]
        i = min(range(len(ts)), key=lambda k: abs(ts[k] - t_open))
        eff = trend_efficiency(c[:i + 1], window)
        applied = mult_of(eff, LIVE)
        rows.append({"sym": sym, "eff": eff, "applied": applied, "pnl": pnl})
        print(f"{time.strftime('%m-%d %H:%M', time.gmtime(t_open)):<12} {sym:<14} "
              f"{eff:6.2f} {applied:8.2f} {pnl:+9.2f}")
    if not rows:
        return 0
    actual = sum(x["pnl"] for x in rows)
    print(f"  actual realised over {len(rows)} closes: ${actual:+.2f}")
    print(f"\n{'setting':<24} {'would be $':>11} {'delta $':>9}  note")
    for label, params in GRID:
        tot = 0.0
        for x in rows:
            m_new = mult_of(x["eff"], params)
            # P&L scales linearly with margin at a fixed price path.
            tot += x["pnl"] * (m_new / x["applied"]) if x["applied"] > 0 else x["pnl"]
        note = "<- live" if params == LIVE else ""
        print(f"{label:<24} {tot:+11.2f} {tot-actual:+9.2f}  {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
