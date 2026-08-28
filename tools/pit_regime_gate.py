"""Market-regime entry gates: should the wildcard trade at all right now?

WHY THIS IS NEW GROUND. detect_wildcard_signal takes ONE symbol's price frame.
No BTC, no ETH, no breadth, nothing market-wide anywhere in the entry path. The
regime scaler is per-symbol and only sets SIZE. So unlike the target sweeps --
which retuned things already at their optimum -- this tests a dimension the bot
has never had. A null result here is informative; a positive one is a new lever.

THE OPERATOR'S RULE: only enter when BTC or ETH or SOL has moved >=5% over 24h.
Tested at a range of thresholds, plus six alternative formulations, because the
interesting question is not the number but the SHAPE of the rule:

  A ANY-MAJOR    max(|BTC|,|ETH|,|SOL|) >= X over 24h   -- the operator's rule
  B BTC-ONLY     |BTC| >= X                             -- does the leader suffice?
  C ALL-THREE    min(|BTC|,|ETH|,|SOL|) >= X            -- demand agreement
  D CALM         max(...) < X  -- THE INVERSE. Alt impulses may work BETTER when
                 majors are quiet, because the move is then idiosyncratic rather
                 than everything-moves-together beta. Testing the operator's
                 hypothesis without its negation would be assuming the answer.
  E ALIGNED      LONG only when mean major 24h >= +X, SHORT only when <= -X.
                 Not "is there movement" but "is my side the market's side".
  F BREADTH      fraction of the POOL up over 24h >= X for longs, <= 1-X for
                 shorts. Market-wide participation rather than three tickers.
  G LOOKBACK     the operator's rule at 6h / 12h / 48h instead of 24h.

MULTIPLICITY IS SEVERE: ~24 cells. Best-of-24 finds winners by chance and the
half-split is a weak guard at this width. Nothing here is actionable on one run;
a survivor is a PRE-REGISTRATION CANDIDATE, nothing more. Ranked output shows
every cell, not just winners, so the shape of the response is visible -- a lone
spike surrounded by failures is noise, a smooth gradient is a mechanism.

SCOPE. Gate applied to the WILDCARD sleeve only, booked in isolation. TREND is
held out deliberately: it is long-only on three majors AND already requires a
24h ROC >= 4% on the symbol itself, so gating it on major moves would partly
re-apply its own entry condition and confound the read.

FAIL-OPEN ON MISSING DATA. A candidate whose major/breadth series is unavailable
is ADMITTED, not dropped, and the count is printed. Silently dropping them would
let a gate look selective when it was merely blind.

READ-ONLY. Never places or modifies an order.

RESULTS 2026-08-25 (208d, 153 symbols, 1024 candidates).
NO GATE (live): +237.07 over 663 trades, win 54.4%.

THE OPERATOR'S RULE IS DECISIVELY REFUTED, AND SO IS ITS WHOLE FAMILY.
  A any-major >= 5%   -246.19   (keeps 16% of trades)
  A any-major >= 3%   -234.73   (39%)
  A any-major >= 2%   -134.11   (59%)
  B btc >= 3%         -270.40   E aligned >= 2%   -294.11
  C all-three >= 3%   -267.79   G any-major 6h    -322.74
Every "demand that the majors are moving" formulation loses, at every threshold,
at every lookback, on one ticker or three. E aligned >= 0% -- simply trade the
market's own direction -- costs -139.81. There is no version of this that works.

THE ONLY SURVIVOR IS THE INVERSE, AND IT IS TOO WEAK TO ACT ON.
  D calm: majors < 5%   +11.06   both halves (+1.89 / +9.17), keeps 88%
It clears the $10 noise floor by $1.06 and it is a SPIKE, not a gradient:
<3% is +3.41 (one half), <5% is +11.06, <7% is -9.87. By the criterion stated at
the top of this file -- a lone spike surrounded by failures is noise -- it does
not qualify. Recorded, NOT actionable.

READ THE TABLE AGAINST A PROPORTIONAL BENCHMARK, NOT AGAINST ZERO.
Baseline is $0.3576/trade. A gate that carried NO information would earn exactly
that on whatever trades it kept. Measuring each cell against its own trade count
separates SELECTION from THROTTLING:

  rule                 trades   expected   actual   surplus
  A any-major >= 3%       258     +92.26    +2.33    -89.93
  A any-major >= 5%       107     +38.26    -9.12    -47.38
  D calm < 5%             584    +208.84  +248.12    +39.28
  F breadth >= 50%        410    +146.62  +208.76    +62.14

So the majors-volatility gates are WORSE THAN RANDOMLY DROPPING THE SAME NUMBER
OF TRADES -- they actively select bad ones. And BREADTH is the opposite: it has
the largest positive surplus in the run (+62) and lifts win rate 54.4% -> 57.8%,
yet still LOSES 28.30 outright because it throttles away 38% of the book. The
selection is real; the veto wastes it.

THAT POINTS SOMEWHERE, BUT NOT YET. Breadth looks like a CLASSIFIER wired as a
VETO -- the mirror of the regime scaler, which [[futures-bot-trial8-state]]
records as a good classifier wired as a SIZE DIAL. The natural follow-up is
breadth as a size TILT rather than a gate. Flagged as untested: the per-trade
surplus benchmark above was introduced POST HOC on a 24-cell run, so it is a
hypothesis-generator, not evidence.

THE RECURRING HALF-SPLIT SIGNATURE. Nearly every cell is heavily negative in the
RECENT half and mildly positive in the OLDER one -- the same pattern the TP
sweeps showed. Whatever else is true, the recent ~3.5 months rewarded taking MORE
trades and the older period rewarded selectivity. Any filter tested on this
window inherits that, and it is the single most likely source of false negatives
across every study in this family.
"""
from __future__ import annotations

import os
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from futuresbot import shadow_ledger as shadow
from futuresbot import wildcard as W
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet
from retention_trail_ab import resolve

CHUNK, BAR = 2000, 900
TAIL = 2000
MAJORS = ("BTC_USDT", "ETH_USDT", "SOL_USDT")
LIVE_TRAIL = ratchet(3.0, 0.75, base=0.30, arm=1.0)
WILDCARD_TP = 5.0
NOISE = 10.0


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars over the window, NOT account P&L.")
    print("    The real account is DOWN lifetime; /report has the true figure. ***")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 190), int(_env("PJ_POOL", 150))
    min_today = _env("PJ_MIN_TODAY", 3e5)
    eq0 = rt._last_known_equity() or 170.0
    now = int(time.time())
    floor = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors_ex = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wide = [(a, s) for a, s in crypto if s not in majors_ex and a >= min_today]
    cand_syms = [s for _a, s in wide[:pool_n]]
    syms = sorted(set(cand_syms) | set(MAJORS))
    print("equity $%.2f | wildcard pool %d | majors %s" % (eq0, len(cand_syms), ",".join(MAJORS)))

    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}

    frames, _rep = fetch_frames(cl, syms, days=days, workers=6,
                                min_bars=300, now_ts=now)
    print(_rep)
    span = len(next(iter(frames.values()))) * BAR / 86400
    print("frames: %d symbols, %.0fd" % (len(frames), span))

    # ---- major returns at several lookbacks, keyed by bar timestamp ----
    LOOKBACKS = (24, 48, 96, 192)          # 6h, 12h, 24h, 48h in 15m bars
    MRET = {lb: {} for lb in LOOKBACKS}    # lb -> ts -> {sym: ret}
    for m in MAJORS:
        df = frames.get(m)
        if df is None:
            print("WARNING: no frame for %s -- gates using it will fail open" % m)
            continue
        c = [float(x) for x in df["close"]]
        ts = [float(x.timestamp()) for x in df.index]
        for lb in LOOKBACKS:
            d = MRET[lb]
            for i in range(lb, len(c)):
                if c[i - lb] > 0:
                    d.setdefault(ts[i], {})[m] = c[i] / c[i - lb] - 1.0

    # ---- breadth: fraction of the POOL up over 24h, keyed by bar timestamp ----
    up = defaultdict(int)
    tot = defaultdict(int)
    for s in cand_syms:
        df = frames.get(s)
        if df is None:
            continue
        c = [float(x) for x in df["close"]]
        ts = [float(x.timestamp()) for x in df.index]
        for i in range(96, len(c)):
            if c[i - 96] <= 0:
                continue
            tot[ts[i]] += 1
            if c[i] > c[i - 96]:
                up[ts[i]] += 1
    BREADTH = {t: up[t] / tot[t] for t in tot if tot[t] >= 20}
    print("breadth series: %d bars with >=20 symbols" % len(BREADTH))

    # ---- candidates ----
    C = []
    for s in cand_syms:
        df = frames.get(s)
        if df is None:
            continue
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
        ts = [b[0] for b in bars]
        for i in range(250, len(c)):
            if i <= W.ROC_BARS or roll[i] < floor:
                continue
            if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < 0.08:
                continue
            sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
            if sig is not None:
                C.append({"ts": ts[i], "sym": s, "sig": sig, "i": i, "bars": bars})
    C.sort(key=lambda x: x["ts"])
    print("candidates: %d" % len(C))

    # ---- resolve once: exits never change, only admission ----
    res = {}
    for idx, x in enumerate(C):
        sig = x["sig"]
        entry = float(sig.entry_price)
        sl = float(sig.sl_price)
        slf = abs(entry - sl) / entry if entry else 0.0
        dist = WILDCARD_TP * slf
        if sig.side == "SHORT" and dist >= 0.50:
            dist = 0.50
        tr_eff = (dist / slf) if slf > 0 else WILDCARD_TP
        tp = entry * (1 + dist) if sig.side == "LONG" else entry * (1 - dist)
        row = {"entry": entry, "sl": sl, "tp": tp, "side": sig.side}
        g = resolve(x["bars"], x["i"], entry, sl, tp, tr_eff, sig.side,
                    shadow.CONVEX_HORIZON_S, shadow.cost_r(row), LIVE_TRAIL,
                    float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
        if g is not None:
            res[idx] = g
    print("resolved: %d" % len(res))

    win_s = 7 * 86400
    n_win = max(1, int(span // 7))
    mid = n_win // 2
    misses = defaultdict(int)

    def mr(x, lb):
        return MRET[lb].get(x["ts"])

    def gate_any(x, thr, lb=96):
        d = mr(x, lb)
        if not d:
            misses["major"] += 1
            return True
        return max(abs(v) for v in d.values()) >= thr

    def gate_btc(x, thr):
        d = mr(x, 96)
        if not d or "BTC_USDT" not in d:
            misses["btc"] += 1
            return True
        return abs(d["BTC_USDT"]) >= thr

    def gate_all(x, thr):
        d = mr(x, 96)
        if not d or len(d) < 3:
            misses["all"] += 1
            return True
        return min(abs(v) for v in d.values()) >= thr

    def gate_calm(x, thr):
        d = mr(x, 96)
        if not d:
            misses["calm"] += 1
            return True
        return max(abs(v) for v in d.values()) < thr

    def gate_aligned(x, thr):
        d = mr(x, 96)
        if not d:
            misses["align"] += 1
            return True
        m = sum(d.values()) / len(d)
        return m >= thr if x["sig"].side == "LONG" else m <= -thr

    def gate_breadth(x, thr):
        b = BREADTH.get(x["ts"])
        if b is None:
            misses["breadth"] += 1
            return True
        return b >= thr if x["sig"].side == "LONG" else b <= (1.0 - thr)

    def book(keep, k_lo=0, k_hi=None):
        total, n, wins = 0.0, 0, 0
        for k in range(k_lo, n_win if k_hi is None else k_hi):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            slots, per = [], {}
            for idx, x in enumerate(C):
                if not (lo_t <= x["ts"] < hi_t) or idx not in res or not keep(x):
                    continue
                slots[:] = [q for q in slots if q > x["ts"]]
                per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
                if per[x["sym"]] or len(slots) >= 3:
                    continue
                g = res[idx]
                slots.append(g[1])
                per[x["sym"]].append(g[1])
                total += g[0] * eq0 * 0.12 * float(x["sig"].sl_margin_pct) / 100.0
                n += 1
                wins += 1 if g[0] > 0 else 0
        return total, n, wins

    b, bn, bw = book(lambda x: True)
    br = book(lambda x: True, 0, mid)[0]
    bo = book(lambda x: True, mid, n_win)[0]
    print("")
    print("NO GATE (live): %+.2f over %d trades, win %.1f%%" % (b, bn, 100.0 * bw / max(bn, 1)))
    print("")
    print("*** MULTIPLICITY: ~24 cells. A lone spike is noise; look for gradients. ***")
    print("")
    print("%-26s %10s %9s %7s %7s %7s %9s %9s  both?"
          % ("rule", "net $", "vs live", "trades", "kept%", "win%", "recent", "older"))

    rows = []

    def run(label, keep):
        tot, n, w = book(keep)
        r = book(keep, 0, mid)[0] - br
        o = book(keep, mid, n_win)[0] - bo
        both = "YES" if r > 0 and o > 0 else ("no" if r < 0 and o < 0 else "one half")
        print("%-26s %+10.2f %+9.2f %7d %6.0f%% %6.1f%% %+9.2f %+9.2f  %s"
              % (label, tot, tot - b, n, 100.0 * n / max(bn, 1),
                 100.0 * w / max(n, 1), r, o, both))
        rows.append({"label": label, "tot": tot, "d": tot - b, "n": n,
                     "r": r, "o": o, "both": both})

    print("--- A: ANY MAJOR moved >= X over 24h (the operator's rule) ---")
    for t in (0.02, 0.03, 0.04, 0.05, 0.07, 0.10):
        run("A any-major >= %.0f%%" % (t * 100), lambda x, t=t: gate_any(x, t))
    print("--- B: BTC alone ---")
    for t in (0.03, 0.05, 0.07):
        run("B btc >= %.0f%%" % (t * 100), lambda x, t=t: gate_btc(x, t))
    print("--- C: ALL THREE majors moved (agreement) ---")
    for t in (0.02, 0.03, 0.05):
        run("C all-three >= %.0f%%" % (t * 100), lambda x, t=t: gate_all(x, t))
    print("--- D: CALM -- the INVERSE hypothesis ---")
    for t in (0.03, 0.05, 0.07):
        run("D calm: majors < %.0f%%" % (t * 100), lambda x, t=t: gate_calm(x, t))
    print("--- E: ALIGNED -- trade only with the market's direction ---")
    for t in (0.0, 0.02, 0.05):
        run("E aligned >= %.0f%%" % (t * 100), lambda x, t=t: gate_aligned(x, t))
    print("--- F: BREADTH of the pool, not three tickers ---")
    for t in (0.50, 0.60, 0.70):
        run("F breadth >= %.0f%%" % (t * 100), lambda x, t=t: gate_breadth(x, t))
    print("--- G: the operator's rule at other lookbacks ---")
    for lb, lab, t in ((24, "6h", 0.03), (48, "12h", 0.04), (192, "48h", 0.07)):
        run("G any-major %s >= %.0f%%" % (lab, t * 100),
            lambda x, t=t, lb=lb: gate_any(x, t, lb))

    print("")
    if misses:
        print("fail-open admissions (missing data): %s" % dict(misses))
    surv = [e for e in rows if e["both"] == "YES" and e["d"] > NOISE]
    print("")
    if surv:
        print("SURVIVORS (both halves AND > $%.0f):" % NOISE)
        for e in sorted(surv, key=lambda e: -e["d"]):
            print("  %-26s %+9.2f  (%d trades, %.0f%% kept)"
                  % (e["label"], e["d"], e["n"], 100.0 * e["n"] / max(bn, 1)))
        print("  PRE-REGISTER AND RETEST. One run of 24 cells proves nothing.")
    else:
        print("NO REGIME GATE SURVIVES. The bot's lack of market-wide awareness")
        print("is not, on this evidence, costing it money.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
