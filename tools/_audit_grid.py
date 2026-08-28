import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _audit_surface import *
import numpy as np

MULTS = [1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0,5.5,6.0]
CAPS  = [15,20,25,30,35,40,45,50]
# sanity: cached atr_pct must equal the recomputed ATR series at the signal bar
err = max(abs(SIGS[j]["atr_pct"] - SERIES[SIGS[j]["sym"]]["atr"][SIGS[j]["i"]])
          for j in range(0, len(SIGS), max(1,len(SIGS)//200)))
print("ATR-series reconstruction max abs err vs detector: %.3g" % err)
print("signals %d  dollar_r %.4f  n_win %d  span_d %.1f\n" % (len(SIGS), DOLLAR_R, N_WIN, (HI-LO)/86400))

R = {}
for a in MULTS:
    for c in CAPS:
        t,o,r = cell(a,c); s = stats(t,o,r)
        R[(a,c)] = s
live = R[(3.0,20)]["net"]

def grid(key, fmt="%8.1f"):
    print("\n=== %s ===" % key)
    print("mult\cap " + "".join("%8d" % c for c in CAPS))
    for a in MULTS:
        print("%7.1f " % a + "".join(fmt % R[(a,c)][key] for c in CAPS))

grid("net"); grid("older"); grid("recent"); grid("n","%8d"); grid("stops","%8d")
grid("top5","%8.0f"); grid("ex5"); grid("cap","%8.1f"); grid("clamp","%8.1f")
grid("margcap","%8.1f")

print("\n=== net$ minus LIVE(3.0/20=%.2f) ===" % live)
print("mult\cap " + "".join("%8d" % c for c in CAPS))
for a in MULTS:
    print("%7.1f " % a + "".join("%+8.1f" % (R[(a,c)]["net"]-live) for c in CAPS))

print("\n=== older-half SIGN (+ = positive) ===")
print("mult\cap " + "".join("%8d" % c for c in CAPS))
for a in MULTS:
    print("%7.1f " % a + "".join("%8s" % ("POS" if R[(a,c)]["older"]>0 else "neg") for c in CAPS))

best = max(R.items(), key=lambda kv: kv[1]["net"])
print("\nBEST of %d cells: %.1fx%d%% net %+.2f (live %+.2f, gap %+.2f)"
      % (len(R), best[0][0], best[0][1], best[1]["net"], live, best[1]["net"]-live))
nets = sorted((v["net"] for v in R.values()), reverse=True)
print("top-8 nets:", " ".join("%.1f" % x for x in nets[:8]))
print("net spread across surface: min %.1f max %.1f sd %.1f" % (min(nets), max(nets), float(np.std(nets))))
