"""Is the placebo book on a comparable SCALE to the real one? If it were much
noisier its null would be unfairly wide, so check it before trusting it."""
import os,sys,random
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np
import _audit_surface as A
from _audit_surface import SIGS,SERIES,stats
TEN=[(3.0,20),(3.0,25),(3.0,30),(3.0,40),(4.0,20),(4.0,30),(5.0,20),(5.0,30),(2.0,20),(1.5,20)]
BARS0=dict(A.BARS)
CAND={}
for j,r in enumerate(SIGS):
    S=SERIES[r["sym"]];c=S["close"];n=len(c);i=r["i"]
    ok=[k for k in range(max(250,i-192),min(n-3,i+192)+1)
        if abs(k-i)>8 and k>12 and abs(c[k]/c[k-12]-1.0)>=0.08
        and np.isfinite(S["atr"][k]) and S["atr"][k]>0]
    CAND[j]=ok
def build(rng):
    sigs=[];bars={}
    for j,r in enumerate(SIGS):
        ok=CAND[j]
        if not ok: continue
        k=ok[rng.randrange(len(ok))];S=SERIES[r["sym"]];c=S["close"];n=len(c)
        m=len(sigs)
        sigs.append({"sym":r["sym"],"i":k,"ts":float(S["ts"][k]),
                     "side":"LONG" if c[k]/c[k-12]-1.0>0 else "SHORT",
                     "entry":float(c[k]),"atr_pct":float(S["atr"][k])})
        bars[m]=[(float(S["ts"][x]),float(S["hi"][x]),float(S["lo"][x]),float(c[x]))
                 for x in range(k,min(n,k+130))]
    A.SIGS=sigs;A.BARS=bars
def nets():
    return {k:(stats(*A.cell(k[0],k[1])) or {"net":0.,"n":0})for k in TEN}
A.SIGS=SIGS;A.BARS=BARS0
R=nets()
print("REAL   live %+7.1f  n %d  cross-cell sd %.1f  mean|net| %.1f"
      %(R[(3.0,20)]["net"],R[(3.0,20)]["n"],np.std([v["net"] for v in R.values()]),
        np.mean([abs(v["net"]) for v in R.values()])))
rng=random.Random(7);lv=[];sd=[];mn=[]
for _ in range(40):
    build(rng);P=nets()
    lv.append(P[(3.0,20)]["net"]);sd.append(np.std([v["net"] for v in P.values()]))
    mn.append(np.mean([abs(v["net"]) for v in P.values()]))
A.SIGS=SIGS;A.BARS=BARS0
print("PLACEBO live %+7.1f +- %.1f | cross-cell sd %.1f +- %.1f | mean|net| %.1f"
      %(np.mean(lv),np.std(lv),np.mean(sd),np.std(sd),np.mean(mn)))
