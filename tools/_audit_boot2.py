"""Corrected symbol bootstrap: a symbol drawn k times is re-tagged SYM#k so the
one-position-per-symbol lock does not silently delete the duplicate (which in
the naive version shrank every resampled book by ~27%)."""
import os,sys,random
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np
import _audit_surface as A
from _audit_surface import SIGS,stats
TEN=[(3.0,20),(3.0,25),(3.0,30),(3.0,40),(4.0,20),(4.0,30),(5.0,20),(5.0,30),(2.0,20),(1.5,20)]
NBR=[(3.0,20),(3.5,30),(4.0,25),(4.0,30),(4.0,35),(4.5,30),(4.0,20),(5.0,30)]
CELLS=sorted(set(TEN)|set(NBR))
NREP=int(os.environ.get("AUDIT_REP","300"))
BARS0=dict(A.BARS)
BY={}
for j,r in enumerate(SIGS): BY.setdefault(r["sym"],[]).append(j)
SYMS=sorted(BY)
def build(pick):
    sigs=[];bars={};cnt={}
    for s in pick:
        cnt[s]=cnt.get(s,0)+1;tag="%s#%d"%(s,cnt[s])
        for j in BY[s]:
            m=len(sigs);r=dict(SIGS[j]);r["sym"]=tag;sigs.append(r);bars[m]=BARS0[j]
    order=sorted(range(len(sigs)),key=lambda m:sigs[m]["ts"])
    A.SIGS=[sigs[m] for m in order];A.BARS={i:bars[m] for i,m in enumerate(order)}
def res():
    return {k:(stats(*A.cell(k[0],k[1])) or {"net":0.,"older":0.,"n":0}) for k in CELLS}
A.SIGS=SIGS;A.BARS=BARS0
full=res();flv=full[(3.0,20)]["net"]
rng=random.Random(2024)
G={k:[] for k in CELLS};OP=[];win={};lvn=[];nn=[]
for rep in range(NREP):
    build([SYMS[rng.randrange(len(SYMS))] for _ in range(len(SYMS))])
    R=res();lv=R[(3.0,20)]["net"];lvn.append(lv);nn.append(R[(3.0,20)]["n"])
    for k in CELLS: G[k].append(R[k]["net"]-lv)
    OP.append(1 if R[(4.0,30)]["older"]>0 else 0)
    b=max(TEN,key=lambda k:R[k]["net"]);win[b]=win.get(b,0)+1
    if rep%50==0: print("  boot2 %d/%d"%(rep,NREP));sys.stdout.flush()
A.SIGS=SIGS;A.BARS=BARS0
print("\nCORRECTED SYMBOL BOOTSTRAP (%d reps)"%NREP)
print("  live net: full-sample %+.1f | bootstrap mean %+.1f sd %.1f | n %d vs %.0f"
      %(flv,np.mean(lvn),np.std(lvn),full[(3.0,20)]["n"],np.mean(nn)))
print("  %-10s %8s %9s %9s %18s %8s"%("cell","full$","boot mean","boot sd","95% CI","P(<=0)"))
for k in NBR:
    a=np.array(G[k]);print("  %-10s %+8.1f %+9.1f %9.1f  [%+7.1f,%+7.1f] %7.0f%%"
        %("%.1fx%d%%"%k,full[k]["net"]-flv,a.mean(),a.std(),
          np.percentile(a,2.5),np.percentile(a,97.5),100.0*(a<=0).mean()))
print("  P(4.0/30 older-half > 0) = %.0f%%   [full-sample older = %+.1f, claim says +29]"
      %(100.0*np.mean(OP),full[(4.0,30)]["older"]))
print("  winner of the 10-cell search:")
for k,v in sorted(win.items(),key=lambda kv:-kv[1]):
    print("      %-10s %3.0f%%"%("%.1fx%d%%"%k,100.0*v/NREP))
