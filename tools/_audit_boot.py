"""(b)(d) SYMBOL BOOTSTRAP on the REAL data + placebo scale diagnostics."""
from __future__ import annotations
import os, sys, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import _audit_surface as A
from _audit_surface import SIGS, SERIES, NOW, DOLLAR_R, stats

TEN=[(3.0,20),(3.0,25),(3.0,30),(3.0,40),(4.0,20),(4.0,30),(5.0,20),(5.0,30),(2.0,20),(1.5,20)]
NBR=[(3.5,30),(4.5,30),(4.0,25),(4.0,35),(4.0,30),(3.0,20)]
NREP=int(os.environ.get("AUDIT_REP","300"))
BARS0=dict(A.BARS)
BY={}
for j,r in enumerate(SIGS): BY.setdefault(r["sym"],[]).append(j)
SYMS=sorted(BY)
print("symbols with signals: %d ; signals %d" % (len(SYMS),len(SIGS)))

def use(idxlist):
    sigs=[]; bars={}
    for j in idxlist:
        m=len(sigs); sigs.append(SIGS[j]); bars[m]=BARS0[j]
    A.SIGS=sigs; A.BARS=bars

def search(cells):
    return {k:(stats(*A.cell(k[0],k[1])) or {"net":0.,"older":0.,"recent":0.}) for k in cells}

rng=random.Random(999)
gap=[]; olderpos=[]; winner={}; nbr={k:[] for k in NBR}; liven=[]
for rep in range(NREP):
    pick=[]
    for _ in range(len(SYMS)):
        s=SYMS[rng.randrange(len(SYMS))]; pick.extend(BY[s])
    use(sorted(pick,key=lambda j:SIGS[j]["ts"]))
    R=search(sorted(set(TEN)|set(NBR)))
    lv=R[(3.0,20)]["net"]; liven.append(lv)
    gap.append(R[(4.0,30)]["net"]-lv)
    olderpos.append(1 if R[(4.0,30)]["older"]>0 else 0)
    b=max(TEN,key=lambda k:R[k]["net"]); winner[b]=winner.get(b,0)+1
    for k in NBR: nbr[k].append(R[k]["net"]-lv)
    if rep%50==0: print("  boot %d/%d" % (rep,NREP)); sys.stdout.flush()
use(list(range(len(SIGS))))
gap=np.array(gap)
print("\nSYMBOL BOOTSTRAP (%d reps, real data)" % NREP)
print("  live net           : mean %+.1f  sd %.1f" % (np.mean(liven),np.std(liven)))
print("  4.0/30 - live gap  : mean %+.1f  sd %.1f  95%%CI [%+.1f, %+.1f]  P(gap<=0) %.0f%%"
      % (gap.mean(),gap.std(),np.percentile(gap,2.5),np.percentile(gap,97.5),100.0*(gap<=0).mean()))
print("  P(4.0/30 older-half > 0) = %.0f%%  <-- the claim asserts this is TRUE" % (100.0*np.mean(olderpos)))
print("  winner of the 10-cell search, share of resamples:")
for k,v in sorted(winner.items(),key=lambda kv:-kv[1]):
    print("      %-10s %4.0f%%" % ("%.1fx%d%%"%k, 100.0*v/NREP))
print("  NEIGHBOUR gaps vs live (mean +- sd over resamples):")
for k in NBR:
    a=np.array(nbr[k]); print("      %-10s %+7.1f +- %5.1f   P(<0) %3.0f%%" % ("%.1fx%d%%"%k,a.mean(),a.std(),100.0*(a<0).mean()))
