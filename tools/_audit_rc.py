"""White's Reality Check: the correct multiple-comparisons null for
"best cell beats live", using the data's own dependence structure.

  observed  V   = max_k (net_k - net_live)
  bootstrap V_b = max_k [ (net_k^b - net_live^b) - (net_k - net_live) ]   (centred)
  p = P(V_b >= V)      H0: no cell in the family truly beats live.
"""
from __future__ import annotations
import os, sys, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import _audit_surface as A
from _audit_surface import SIGS, stats

TEN=[(3.0,25),(3.0,30),(3.0,40),(4.0,20),(4.0,30),(5.0,20),(5.0,30),(2.0,20),(1.5,20)]
MULTS=[1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0,5.5,6.0]; CAPS=[15,20,25,30,35,40,45,50]
EIGHTY=[(a,c) for a in MULTS for c in CAPS if (a,c)!=(3.0,20)]
FAM=sorted(set(TEN)|set(EIGHTY))
NREP=int(os.environ.get("AUDIT_REP","120"))
BARS0=dict(A.BARS)
BY={}
for j,r in enumerate(SIGS): BY.setdefault(r["sym"],[]).append(j)
SYMS=sorted(BY)

def use(idx):
    sigs=[];bars={}
    for j in idx:
        m=len(sigs);sigs.append(SIGS[j]);bars[m]=BARS0[j]
    A.SIGS=sigs;A.BARS=bars

def nets(cells):
    return {k:(stats(*A.cell(k[0],k[1])) or {"net":0.})["net"] for k in cells}

use(list(range(len(SIGS))))
obs=nets(FAM+[(3.0,20)]); lv=obs[(3.0,20)]
g={k:obs[k]-lv for k in FAM}
V10=max(g[k] for k in TEN); V80=max(g[k] for k in EIGHTY)
print("observed: live %.2f | best-of-10 %+.2f (%s) | best-of-80 %+.2f (%s)"
      % (lv,V10,max(TEN,key=lambda k:g[k]),V80,max(EIGHTY,key=lambda k:g[k])))
sys.stdout.flush()
rng=random.Random(4242); b10=[];b80=[]
for rep in range(NREP):
    pick=[]
    for _ in range(len(SYMS)):
        s=SYMS[rng.randrange(len(SYMS))];pick.extend(BY[s])
    use(sorted(pick,key=lambda j:SIGS[j]["ts"]))
    nb=nets(FAM+[(3.0,20)]); lb=nb[(3.0,20)]
    d={k:(nb[k]-lb)-g[k] for k in FAM}
    b10.append(max(d[k] for k in TEN)); b80.append(max(d[k] for k in EIGHTY))
    if rep%20==0: print("  rc %d/%d"%(rep,NREP)); sys.stdout.flush()
use(list(range(len(SIGS))))
b10=np.array(b10);b80=np.array(b80)
print("\nREALITY CHECK (%d symbol-bootstrap reps)"%NREP)
print("  10-cell family : observed %+.1f   RC p = %.3f   null p50 %+.1f p90 %+.1f p95 %+.1f"
      % (V10,(b10>=V10).mean(),np.median(b10),np.percentile(b10,90),np.percentile(b10,95)))
print("  80-cell family : observed %+.1f   RC p = %.3f   null p50 %+.1f p90 %+.1f p95 %+.1f"
      % (V80,(b80>=V80).mean(),np.median(b80),np.percentile(b80,90),np.percentile(b80,95)))
# the SPECIFIC claimed cell, no selection, plain one-sided bootstrap
print("\n  (for reference) 4.0/30 gap on full sample %+.1f" % g[(4.0,30)])

for tgt in (41.39, 27.4, 61.94):
    print("  P(selection-null best-of-10 gap >= %+.2f) = %.3f   [80-cell: %.3f]"
          % (tgt, (b10 >= tgt).mean(), (b80 >= tgt).mean()))
MU=[1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0,5.5,6.0]; CP=[15,20,25,30,35,40,45,50]
allc=nets([(a,c) for a in MU for c in CP])
def rough(seq):
    d=[abs(seq[i+1]-seq[i]) for i in range(len(seq)-1)]
    return float(np.mean(d)), max(seq)-min(seq)
print("\nSURFACE ROUGHNESS (full sample, net $)")
print("  along ATR-MULT (step 0.5), per cap:")
for c in CP:
    seq=[allc[(a,c)] for a in MU]; m,r=rough(seq)
    print("    cap %2d%%: mean|step| %5.1f range %6.1f   5.0->5.5->6.0 = %.0f -> %.0f -> %.0f"
          % (c,m,r,allc[(5.0,c)],allc[(5.5,c)],allc[(6.0,c)]))
print("  along CAP (step 5pp, caps 25-50 only), per mult:")
for a in MU:
    seq=[allc[(a,c)] for c in CP if c>=25]; m,r=rough(seq)
    print("    mult %.1f: mean|step| %5.1f range %6.1f" % (a,m,r))
