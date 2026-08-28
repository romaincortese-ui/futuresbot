"""TREND take-profit sweep on the corrected point-in-time pool.

WHY THIS IS BEING RE-ASKED. tools/trend_tp_ab.py settled this on 2026-08-22:
"KEEP 3R. The cap binds, and widening it does not survive the half-split."
5R scored +7.35 vs 3R with halves -16.40 / +23.75.

Then on 2026-08-25 the TP/trail sweep threw up an ACCIDENTAL cell -- (5.0, 1.0,
0.30) -- that beat the live baseline by +82.16 with BOTH halves positive. That
cell differed from baseline in exactly one respect: it applied TP 5R to the
TREND sleeve. +82.16/both-halves against +7.35/one-half is too large a gap to
wave away, and the difference between the two runs is the POOL: 70 symbols on
the broken top-N-by-turnover-today pool, versus 152 with point-in-time
eligibility. That is the same correction that reversed three prior acceptances
and one prior rejection, so the re-ask is warranted rather than opportunistic.

WHAT THIS DOES THAT THE ACCIDENTAL CELL DID NOT.
  1. Varies ONLY the trend TP. The wildcard stays at its live 5R.
  2. Sweeps a RANGE (2/3/4/5/6/8R), so a genuine gradient is distinguishable
     from a lucky spike at one value. A single winning point in a sweep is a
     coin flip; a monotone response is a mechanism.
  3. Books the TREND sleeve IN ISOLATION as the primary read. This is valid
     because the sleeves never interact: TREND trades ETH/XRP/ZEC, all of which
     are majors and therefore excluded from the wildcard pool, and the two
     sleeves hold separate slot pools (2 and 3). Isolating removes wildcard
     variance that would otherwise swamp a 3-symbol sleeve.
  4. Reports PER-SYMBOL P&L. The sleeve has THREE symbols. If one of them
     carries the entire result, that is a fact about ETH or ZEC in this window,
     not about the take-profit level, and it must be visible.
  5. Reports ex-best, because a 3-symbol sleeve on ~170 trades is exactly the
     shape where one runner decides the verdict.

READ-ONLY. Never places or modifies an order.

RESULTS 2026-08-25 (208d, 153 symbols, TREND 1009 / WILDCARD 1017 candidates).
Wildcard held fixed at 5R = +220.53 in every row. Sleeve overlap: NONE.

VERDICT: KEEP 3R. The prior 08-22 verdict REPRODUCES on the corrected pool, and
the accidental +82.16 does not.

  trend TP    trend $     vs 3R      n   TP hit    recent     older   both?
      2.0R    +153.78    -37.32    207    28.5%    -17.34    -19.98   no
      3.0R    +191.10     +0.00    177    17.5%     +0.00     +0.00   LIVE
      4.0R    +196.18     +5.08    172     7.0%    -21.09    +26.17   one half
      5.0R    +191.82     +0.72    170     2.9%    -18.33    +19.05   one half
      6.0R    +200.34     +9.23    171     2.3%    -23.27    +32.51   one half
      8.0R    +197.60     +6.49    171     1.2%    -23.27    +29.76   one half

FIVE IS WORTH +0.72, NOT +82.16. Every widening shows the SAME half-split
signature as the 08-22 study -- older half positive, recent half negative -- so
the pattern is stable across two pools and two tools. Nothing here beats 3R in
both halves. Tightening to 2R is clearly worse (-37.32, both halves negative).

WHERE THE PHANTOM CAME FROM. tools/pit_tp_trail_sweep.py handed the NOMINAL
tp_r to the resolver even when the short clamp (MAX_SHORT_TP_DIST=0.50) had cut
the TP price back. Clamped shorts were paid at +5R while their reachable target
was worth far less, so high-TP cells inflated. The baseline used
shadow.signal_tp_r(), which derives R from the signal's own geometry and is
correct. Defect fixed there (tr_eff); the bankable-book conclusion in that file
is unaffected because 1.5R cells cannot clamp.

THE SLEEVE IS MOSTLY ZEC -- read any trend verdict with that in mind.
  trend TP      ETH      XRP      ZEC
      3.0R   +27.70   +33.46  +129.94    <- ZEC is 68% of sleeve P&L
      6.0R   +25.20   +23.36  +151.78
Widening HELPS ZEC and HURTS ETH and XRP at every level above 3R. So even the
apparent 4-8R gradient is one symbol's behaviour in this window, not a property
of the take-profit. A three-symbol sleeve cannot support a general conclusion
about target selection; ex-best sits within ~$25 of total at every level.

METHOD NOTE WORTH KEEPING. Isolating the sleeve was what made this legible.
Booked together, trend moves of $5-9 hide inside wildcard variance of $220+.
The sleeves are provably independent here (majors are excluded from the
wildcard pool, and slot pools are separate), so isolation costs nothing.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from futuresbot import shadow_ledger as shadow
from futuresbot import wildcard as W
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import FuturesRuntime
from futuresbot.trend import detect_trend_signal
from pit_fetch import fetch_frames  # noqa: E402
from pit_ratchet import ratchet
from retention_trail_ab import resolve

CHUNK, BAR = 2000, 900
TREND_SYMS = ("ETH_USDT", "XRP_USDT", "ZEC_USDT")
TAIL = 2000
LIVE_TRAIL = ratchet(3.0, 0.75, base=0.30, arm=1.0)
TPS = (2.0, 3.0, 4.0, 5.0, 6.0, 8.0)
LIVE_TP = 3.0
WILDCARD_TP = 5.0


def _env(n, d):
    try:
        return float(os.environ.get(n) or d)
    except (TypeError, ValueError):
        return float(d)


def main() -> int:
    print("*** SIMULATED REPLAY - model dollars over the window, NOT account P&L.")
    print("    The real account is DOWN lifetime; /report has the true figure. ***")
    os.environ.setdefault("FUTURES_TREND_ENABLED", "1")
    cfg = FuturesConfig.from_env()
    cl = MexcFuturesClient(cfg)
    rt = FuturesRuntime(cfg, cl)
    days, pool_n = _env("PJ_DAYS", 190), int(_env("PJ_POOL", 150))
    min_today = _env("PJ_MIN_TODAY", 3e5)
    eq0 = rt._last_known_equity() or 170.0
    now = int(time.time())
    floor = W.wildcard_min_turnover_usdt()

    tk = cl.get_all_tickers() or []
    majors = rt._major_symbols(tk, int(rt._env_float("FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0)))
    crypto = sorted(((float(t.get("amount24") or 0), str(t.get("symbol") or "")) for t in tk
                     if str(t.get("symbol") or "").endswith("_USDT")
                     and rt._is_tradeable_crypto(str(t.get("symbol") or ""))), reverse=True)
    wide = [(a, s) for a, s in crypto if s not in majors and a >= min_today]
    cand_syms = [s for _a, s in wide[:pool_n]]
    overlap = sorted(set(cand_syms) & set(TREND_SYMS))
    syms = sorted(set(cand_syms) | set(TREND_SYMS))
    print("equity $%.2f | wildcard pool %d | trend/wildcard symbol overlap: %s"
          % (eq0, len(cand_syms), overlap or "NONE (sleeves independent)"))

    sizes = {str(d.get("symbol") or ""): float(d.get("contractSize") or 0.0)
             for d in (cl.get_all_contract_details() or [])}

    frames, _rep = fetch_frames(cl, syms, days=days, workers=6,
                                min_bars=300, now_ts=now)
    print(_rep)
    span = len(next(iter(frames.values()))) * BAR / 86400
    print("frames: %d symbols, %.0fd" % (len(frames), span))

    TR, WC = [], []
    for s, df in frames.items():
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
        if s in TREND_SYMS:
            for i in range(400, len(c)):
                if abs(c[i] / c[i - 96] - 1.0) < 0.04:
                    continue
                sig = detect_trend_signal(df.iloc[:i + 1], s)
                if sig is not None and sig.side == "LONG":
                    TR.append({"ts": ts[i], "sym": s, "sig": sig, "i": i, "bars": bars})
        if s in cand_syms:
            for i in range(250, len(c)):
                if i <= W.ROC_BARS or roll[i] < floor:
                    continue
                if abs(c[i] / c[i - W.ROC_BARS] - 1.0) < 0.08:
                    continue
                sig = W.detect_wildcard_signal(df.iloc[max(0, i - TAIL):i + 1], s)
                if sig is not None:
                    WC.append({"ts": ts[i], "sym": s, "sig": sig, "i": i, "bars": bars})
    TR.sort(key=lambda x: x["ts"])
    WC.sort(key=lambda x: x["ts"])
    print("candidates: TREND %d | WILDCARD %d" % (len(TR), len(WC)))

    win_s = 7 * 86400
    n_win = max(1, int(span // 7))
    mid = n_win // 2

    def resolve_set(cands, tp_r):
        res = {}
        for idx, x in enumerate(cands):
            sig = x["sig"]
            entry = float(sig.entry_price)
            sl = float(sig.sl_price)
            slf = abs(entry - sl) / entry if entry else 0.0
            dist = tp_r * slf
            tp = entry * (1 + dist) if sig.side == "LONG" else entry * (1 - dist)
            row = {"entry": entry, "sl": sl, "tp": tp, "side": sig.side}
            g = resolve(x["bars"], x["i"], entry, sl, tp, tp_r, sig.side,
                        shadow.CONVEX_HORIZON_S, shadow.cost_r(row), LIVE_TRAIL,
                        float(getattr(sig, "atr_pct", 0.0) or 0.0), now)
            if g is not None:
                res[idx] = g
        return res

    def book(cands, res, cap, k_lo=0, k_hi=None):
        tot, n, kinds, per_sym, ds = 0.0, 0, {}, {}, []
        for k in range(k_lo, n_win if k_hi is None else k_hi):
            hi_t = now - k * win_s
            lo_t = hi_t - win_s
            slots, per = [], {}
            for idx, x in enumerate(cands):
                if not (lo_t <= x["ts"] < hi_t) or idx not in res:
                    continue
                slots[:] = [q for q in slots if q > x["ts"]]
                per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
                if per[x["sym"]] or len(slots) >= cap:
                    continue
                g = res[idx]
                slots.append(g[1])
                per[x["sym"]].append(g[1])
                d = g[0] * eq0 * 0.12 * float(x["sig"].sl_margin_pct) / 100.0
                tot += d
                n += 1
                ds.append(d)
                kinds[g[2]] = kinds.get(g[2], 0) + 1
                per_sym[x["sym"]] = per_sym.get(x["sym"], 0.0) + d
        return tot, n, kinds, per_sym, ds

    # wildcard held at live 5R throughout; resolved once
    wres = resolve_set(WC, WILDCARD_TP)
    wtot = book(WC, wres, 3)[0]
    print("wildcard held FIXED at %.0fR: %+.2f (constant across every row)"
          % (WILDCARD_TP, wtot))

    base = {}
    rows = []
    for tp in TPS:
        res = resolve_set(TR, tp)
        tot, n, kinds, per_sym, ds = book(TR, res, 2)
        r = book(TR, res, 2, 0, mid)[0]
        o = book(TR, res, 2, mid, n_win)[0]
        if tp == LIVE_TP:
            base = {"tot": tot, "r": r, "o": o}
        rows.append({"tp": tp, "tot": tot, "n": n, "r": r, "o": o,
                     "kinds": kinds, "per": per_sym, "ds": ds})

    print("")
    print("TREND SLEEVE IN ISOLATION (wildcard excluded -- sleeves are independent)")
    print("%8s %10s %9s %7s %8s %10s %9s %9s  both?"
          % ("trend TP", "trend $", "vs 3R", "n", "TP hit", "ex-best", "recent", "older"))
    for e in rows:
        d = e["tot"] - base["tot"]
        dr = e["r"] - base["r"]
        do = e["o"] - base["o"]
        both = "YES" if dr > 0 and do > 0 else ("no" if dr < 0 and do < 0 else "one half")
        tph = 100.0 * e["kinds"].get("tp", 0) / max(e["n"], 1)
        exb = e["tot"] - (max(e["ds"]) if e["ds"] else 0.0)
        tag = "  <-- LIVE" if e["tp"] == LIVE_TP else ""
        print("%7.1fR %+10.2f %+9.2f %7d %7.1f%% %+10.2f %+9.2f %+9.2f  %s%s"
              % (e["tp"], e["tot"], d, e["n"], tph, exb, dr, do, both, tag))

    print("")
    print("PER-SYMBOL -- the sleeve has THREE symbols; if one carries it, say so")
    allsyms = sorted({s for e in rows for s in e["per"]})
    print("%8s %s" % ("trend TP", " ".join("%12s" % s for s in allsyms)))
    for e in rows:
        print("%7.1fR %s" % (e["tp"], " ".join("%+12.2f" % e["per"].get(s, 0.0) for s in allsyms)))

    print("")
    print("FULL BOOK (trend + wildcard, wildcard fixed at 5R)")
    print("%8s %12s %9s" % ("trend TP", "book $", "vs 3R"))
    for e in rows:
        print("%7.1fR %+12.2f %+9.2f" % (e["tp"], e["tot"] + wtot, e["tot"] - base["tot"]))

    print("")
    print("PRIOR VERDICT (tools/trend_tp_ab.py, 2026-08-22, 70-symbol BROKEN pool):")
    print("  KEEP 3R -- 5R scored +7.35 vs 3R with halves -16.40 / +23.75.")
    print("A sweep that beats 3R at ONE value only is a coin flip. Look for a")
    print("MONOTONE response and both-halves agreement before believing it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
