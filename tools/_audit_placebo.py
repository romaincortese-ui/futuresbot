"""(c) PLACEBO + (b/d) STABILITY.

PLACEBO: keep the symbol, the calendar week, and the trigger regime, but move
the entry bar.  For each real signal at bar i, pick at random another bar i' in
[i-192, i+192] (+-2 days), excluding [i-8, i+8], that also satisfies the raw
trigger |3h ROC| >= 8%.  Entry price, side, ATR and the forward path are all
re-read at i'.  Everything else -- geometry, cost, slots, weekly windows, the
same 10-cell search -- is unchanged.  This destroys the detector's bar-level
timing edge while preserving volatility, symbol mix and sampling density.
Under the null "stop width does nothing", best-of-10 minus live should still be
positive by construction (max of 10 noisy draws); the question is HOW positive.

BOOTSTRAP: resample SYMBOLS with replacement (signals cluster by symbol) and
re-run the search on the real data, to see how stable the winner and the
older-half sign are to a different draw of the same market.
"""
from __future__ import annotations
import os, sys, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import _audit_surface as A
from _audit_surface import SIGS, SERIES, NOW, DOLLAR_R, stats

TEN = [(3.0,20),(3.0,25),(3.0,30),(3.0,40),(4.0,20),(4.0,30),(5.0,20),(5.0,30),(2.0,20),(1.5,20)]
MULTS=[1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0,5.5,6.0]; CAPS=[15,20,25,30,35,40,45,50]
EIGHTY=[(a,c) for a in MULTS for c in CAPS]
NREP=int(os.environ.get("AUDIT_REP","200"))

# candidate shifted bars per signal
CAND={}
for j,r in enumerate(SIGS):
    S=SERIES[r["sym"]]; c=S["close"]; n=len(c); i=r["i"]
    lo=max(250,i-192); hi=min(n-3,i+192)
    ok=[]
    for k in range(lo,hi+1):
        if abs(k-i)<=8: continue
        if k<=12: continue
        if abs(c[k]/c[k-12]-1.0)>=0.08 and np.isfinite(S["atr"][k]) and S["atr"][k]>0:
            ok.append(k)
    CAND[j]=ok
print("signals %d ; median #placebo candidates %.0f ; signals with none %d"
      % (len(SIGS), float(np.median([len(v) for v in CAND.values()])),
         sum(1 for v in CAND.values() if not v)))

BARS_ORIG=dict(A.BARS)
def build_placebo(rng):
    """Rewrite A.SIGS / A.BARS in place with time-shifted entries."""
    sigs=[]; bars={}
    for j,r in enumerate(SIGS):
        ok=CAND[j]
        if not ok: continue
        k=ok[rng.randrange(len(ok))]
        S=SERIES[r["sym"]]; c=S["close"]; n=len(c)
        side="LONG" if c[k]/c[k-12]-1.0>0 else "SHORT"
        fwd=min(n,k+130)
        m=len(sigs)
        sigs.append({"sym":r["sym"],"i":k,"ts":float(S["ts"][k]),"side":side,
                     "entry":float(c[k]),"atr_pct":float(S["atr"][k])})
        bars[m]=[(float(S["ts"][x]),float(S["hi"][x]),float(S["lo"][x]),float(c[x]))
                 for x in range(k,fwd)]
    A.SIGS=sigs; A.BARS=bars
    return len(sigs)

def search(cells):
    out={}
    for a,cp in cells:
        t,o,r=A.cell(a,cp); s=stats(t,o,r)
        out[(a,cp)]=s if s else {"net":0.0,"older":0.0,"recent":0.0}
    return out

# ---------- real-data reference ----------
A.SIGS=SIGS; A.BARS=BARS_ORIG
ref=search(EIGHTY); live=ref[(3.0,20)]["net"]
print("REAL: live %.2f | 4.0/30 %.2f (gap %+.2f) | best-of-10 %s %+.2f (gap %+.2f) | best-of-80 %s %+.2f (gap %+.2f)"
      % (live, ref[(4.0,30)]["net"], ref[(4.0,30)]["net"]-live,
         max(TEN,key=lambda k:ref[k]["net"]), max(ref[k]["net"] for k in TEN),
         max(ref[k]["net"] for k in TEN)-live,
         max(EIGHTY,key=lambda k:ref[k]["net"]), max(ref[k]["net"] for k in EIGHTY),
         max(ref[k]["net"] for k in EIGHTY)-live))
sys.stdout.flush()

# ---------- PLACEBO ----------
rng=random.Random(12345)
g10=[]; g80=[]; g4030=[]; wins={}; ns=[]
for rep in range(NREP):
    ns.append(build_placebo(rng))
    R=search(EIGHTY)
    lv=R[(3.0,20)]["net"]
    b10=max(TEN,key=lambda k:R[k]["net"]); b80=max(EIGHTY,key=lambda k:R[k]["net"])
    g10.append(R[b10]["net"]-lv); g80.append(R[b80]["net"]-lv); g4030.append(R[(4.0,30)]["net"]-lv)
    wins[b10]=wins.get(b10,0)+1
    if rep%25==0: print("  placebo rep %d/%d n=%d gap10=%+.1f" % (rep,NREP,ns[-1],g10[-1])); sys.stdout.flush()
A.SIGS=SIGS; A.BARS=BARS_ORIG
g10=np.array(g10); g80=np.array(g80); g4030=np.array(g4030)
TARGET=ref[(4.0,30)]["net"]-live
print("\nPLACEBO (%d reps, mean n=%.0f vs real %d)" % (NREP,np.mean(ns),len(SIGS)))
print("  best-of-10 minus live : mean %+.1f  median %+.1f  p90 %+.1f  p95 %+.1f  max %+.1f"
      % (g10.mean(),np.median(g10),np.percentile(g10,90),np.percentile(g10,95),g10.max()))
print("  best-of-80 minus live : mean %+.1f  median %+.1f  p95 %+.1f  max %+.1f"
      % (g80.mean(),np.median(g80),np.percentile(g80,95),g80.max()))
print("  4.0/30 minus live     : mean %+.1f  median %+.1f  sd %.1f  P(>0) %.0f%%"
      % (g4030.mean(),np.median(g4030),g4030.std(),100.0*(g4030>0).mean()))
print("  P(best-of-10 gap >= +41.4 [claimed]) = %.1f%%" % (100.0*(g10>=41.39).mean()))
print("  P(best-of-10 gap >= %.1f [this pool]) = %.1f%%" % (TARGET,100.0*(g10>=TARGET).mean()))
print("  placebo argmax-of-10 distribution:", sorted(((v,k) for k,v in wins.items()),reverse=True)[:6])
