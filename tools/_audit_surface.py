"""AUDIT stage 2: sweep the FULL (atr_mult x cap) surface off the stage-1 cache.

Book construction is copied verbatim from tools/pit_stop_width.py: 3 slots, one
position per symbol, weekly windows walked backwards from `now`, half-split at
mid = n_win//2.  Geometry is the verbatim transcription verified in stage 1.
"""
from __future__ import annotations
import os, sys, pickle, math, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from futuresbot import shadow_ledger as shadow
from pit_ratchet import ratchet
from retention_trail_ab import resolve

CACHE = os.environ["AUDIT_CACHE"]
D = pickle.load(open(CACHE, "rb"))
SIGS, SERIES, NOW = D["sigs"], D["series"], D["now"]
DOLLAR_R = D["risk_pct"] * D["eq0"]
LEV0 = float(os.environ.get("FUTURES_WILDCARD_LEVERAGE") or 7.0)
TP_R = float(os.environ.get("FUTURES_WILDCARD_TP_R") or 5.0)
MAXSHORT = float(os.environ.get("FUTURES_WILDCARD_MAX_SHORT_TP_DIST") or 0.50)
COST_PCT = float(os.environ.get("FUTURES_CONVEX_COST_PCT") or shadow.COST_PCT)
RISK_PCT = D["risk_pct"]
MAXMARG = float(os.environ.get("FUTURES_WILDCARD_MAX_MARGIN_PCT") or 0.25)
FLOOR = ratchet(3.0, 0.75)
WIN_S = 7 * 86400
LO = min(float(v["ts"][0]) for v in SERIES.values())
HI = max(float(v["ts"][-1]) for v in SERIES.values())
N_WIN = max(1, int((HI - LO) // WIN_S))
MID = N_WIN // 2
BARS = {}
for j, r in enumerate(SIGS):
    BARS[j] = [tuple(x) for x in r["bars"]]

def geom(side, entry, atr_pct, atr_mult, cap_pct):
    s = 1 if side == "LONG" else -1
    lev = int(min(10.0, max(5.0, LEV0)))
    slf = atr_mult * atr_pct
    if cap_pct > 0 and slf > 0:
        if slf * lev * 100.0 > cap_pct:
            lev = max(1, int(cap_pct / (slf * 100.0)))
        if slf * lev * 100.0 > cap_pct:
            slf = cap_pct / 100.0 / lev
    slm = slf * lev * 100.0
    sl = entry * (1 - slf) if s > 0 else entry * (1 + slf)
    td = slf * TP_R
    clamp = False
    if s < 0 and td >= MAXSHORT:
        td = MAXSHORT; clamp = True
    tp = entry * (1 + td) if s > 0 else entry * (1 - td)
    return slf, lev, slm, sl, tp, clamp

def cell(atr_mult, cap_pct, sub=None, jitter=None):
    """sub = list of signal indices (bootstrap); jitter = dict j->shifted entry."""
    C = []
    src = range(len(SIGS)) if sub is None else sub
    for j in src:
        r = SIGS[j]
        entry, atr, side = r["entry"], r["atr_pct"], r["side"]
        if jitter is not None:
            e2 = jitter.get(j)
            if e2 is None: continue
            entry, side = e2
        slf, lev, slm, sl, tp, clamp = geom(side, entry, atr, atr_mult, cap_pct)
        if slf <= 0 or entry <= 0: continue
        one = abs(entry - sl)
        cr = (COST_PCT / 100.0) / slf
        g = resolve(BARS[j], 0, entry, sl, tp, abs(tp - entry) / one, side,
                    shadow.CONVEX_HORIZON_S, cr, FLOOR, atr, NOW)
        if g is None: continue
        C.append({"ts": r["ts"], "sym": r["sym"], "net": float(g[0]), "kind": g[2],
                  "exit_ts": float(g[1]), "lev": float(lev), "slm": slm,
                  "capped": slm >= cap_pct - 0.5, "clamp": clamp,
                  "margcap": slm < RISK_PCT * 100.0 / MAXMARG})
    C.sort(key=lambda x: x["ts"])
    taken, older, recent = [], 0.0, 0.0
    for k in range(N_WIN):
        hi_t = NOW - k * WIN_S; lo_t = hi_t - WIN_S
        slots, per, wk = [], {}, 0.0
        for x in C:
            if not (lo_t <= x["ts"] < hi_t): continue
            slots[:] = [q for q in slots if q > x["ts"]]
            per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > x["ts"]]
            if per[x["sym"]] or len(slots) >= 3: continue
            slots.append(x["exit_ts"]); per[x["sym"]].append(x["exit_ts"])
            taken.append(x); wk += x["net"] * DOLLAR_R
        if k < MID: recent += wk
        else: older += wk
    return taken, older, recent

def stats(taken, older, recent):
    n = len(taken)
    if n == 0: return None
    net = sum(x["net"] for x in taken) * DOLLAR_R
    vals = sorted((x["net"] * DOLLAR_R for x in taken), reverse=True)
    k5 = max(1, n // 20); top5 = sum(vals[:k5])
    return dict(n=n, net=net, stops=sum(1 for x in taken if x["kind"] == "stop"),
                tps=sum(1 for x in taken if x["kind"] == "tp"),
                win=100.0*sum(1 for x in taken if x["net"] > 0)/n,
                lev=sum(x["lev"] for x in taken)/n,
                cap=100.0*sum(1 for x in taken if x["capped"])/n,
                clamp=100.0*sum(1 for x in taken if x["clamp"])/n,
                margcap=100.0*sum(1 for x in taken if x["margcap"])/n,
                top5=100.0*top5/net if net else 0.0, ex5=net-top5,
                older=older, recent=recent)
