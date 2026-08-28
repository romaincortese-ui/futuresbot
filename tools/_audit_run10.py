import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _audit_surface import *
print("signals %d  dollar_r %.4f  n_win %d  mid %d  span_d %.1f"
      % (len(SIGS), DOLLAR_R, N_WIN, MID, (HI-LO)/86400))
print("%-14s %5s %9s %6s %5s %6s %7s %6s %8s %8s  %s"
      % ("cell","n","net$","stops","tp","win%","avglev","cap%","top5%","ex-top5","older/recent"))
for a,c in ((3.0,20),(3.0,25),(3.0,30),(3.0,40),(4.0,20),(4.0,30),(5.0,20),(5.0,30),(2.0,20),(1.5,20)):
    t,o,r = cell(a,c); s = stats(t,o,r)
    if not s: continue
    print("%-14s %5d %+9.2f %6d %5d %5.1f%% %6.2f %5.1f%% %7.0f%% %+8.2f  %+7.0f/%+.0f%s"
          % ("%.1fx%d%%"%(a,c), s["n"], s["net"], s["stops"], s["tps"], s["win"], s["lev"],
             s["cap"], s["top5"], s["ex5"], s["older"], s["recent"],
             "  <- LIVE" if (a,c)==(3.0,20) else ""))
