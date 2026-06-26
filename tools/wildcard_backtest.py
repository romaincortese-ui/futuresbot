"""Wildcard-specific backtest (the shared 15m engine gets no vote here).
Realism upgrades vs the prototype: (1) Min5 execution fidelity for the
forward exit leg (15m smears stop/bank/breakeven on fast movers); (2) slippage
haircut on entry + every exit fill; (3) per-week breakdown across the span
(robustness, not one lucky window). Detection uses the SHIPPED
detect_wildcard_signal on rolling 15m slices."""
import math, time, statistics as st
from datetime import datetime, timezone
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.wildcard import detect_wildcard_signal
import pandas as pd
c=MexcFuturesClient(FuturesConfig.from_env())
now=int(time.time()); SPAN_D=14; HAIRCUT=float(__import__("os").environ.get("WC_HAIRCUT_BPS","10"))/10000.0
FEE=0.000594; BAL=100.0
tk=c.public_get("/api/v1/contract/ticker",{}); data=tk.get("data") if isinstance(tk,dict) else tk
STBL=("USDC","USDE","USD1","DAI","FDUSD","TUSD","BUSD")
uni=sorted([(t["symbol"],float(t.get("amount24") or 0)) for t in (data or []) if t.get("symbol","").endswith("_USDT") and float(t.get("amount24") or 0)>=3e6 and not any(k in t["symbol"] for k in STBL)],key=lambda x:-x[1])[:100]
PD={}
for s,amt in uni:
    df=c.get_klines(s,interval="Min15",start=now-(SPAN_D+1)*86400,end=now)
    if df is None or len(df)<60: continue
    PD[s]={"df":df.reset_index(drop=True),"C":[float(x) for x in df["close"]],"T":[int(t.timestamp()) for t in df.index]}
print(f"universe: {len(PD)} pairs | haircut {HAIRCUT*1e4:.0f}bps/leg | Min5 execution")
def fwd_min5(sym,sig,t0):
    df=c.get_klines(sym,interval="Min5",start=t0,end=t0+5*3600)
    used="Min5"
    if df is None or len(df)<6:
        df=PD[sym]["df"]; used="Min15-fallback"  # rare: Min5 unavailable
        rows=[(float(h),float(l)) for h,l,tt in zip(df["high"],df["low"],[int(x) for x in PD[sym]["T"]]) if tt>=t0][:48]
    else:
        rows=[(float(h),float(l)) for h,l in zip(df["high"],df["low"])][:60]
    if not rows: return 0.0,used
    o=sig.entry_price*(1+HAIRCUT if sig.side=="LONG" else 1-HAIRCUT)  # entry slippage
    fav=1.0 if sig.side=="LONG" else -1.0; lev=sig.leverage; one_r=sig.sl_margin_pct; fee=2*FEE*lev*100
    peak=-9.0;banked=False;rz=0.0;rem=1.0;mgn=sig.balance_fraction*BAL
    def exitpx(p): return p*(1-HAIRCUT if fav>0 else 1+HAIRCUT)  # exit slippage (worse)
    for h,l in rows:
        fh=((h-o)/o if fav>0 else (o-l)/o)*lev*100; fl=((l-o)/o if fav>0 else (o-h)/o)*lev*100
        peak=max(peak,fh); stop=-one_r
        if banked: stop=max(stop,0.0)
        if fl<=stop: rz+=rem*stop;rem=0;break
        if not banked and fh>=one_r: banked=True;rz+=0.5*one_r;rem=0.5
        if banked and fh>=5*one_r: rz+=rem*5*one_r;rem=0;break
    if rem>0: rz+=rem*(((rows[-1][0]+rows[-1][1])/2-o)/o*fav*lev*100)
    # haircut already in entry; apply exit-leg haircut as extra cost approx
    return mgn*(rz-fee-2*HAIRCUT*lev*100)/100, used
anchor=next(iter(PD.values()))["T"]; nb=len(anchor)
picks=[]
for j in range(40,nb-1,16):
    tj=anchor[j]; best=None
    for s,d in PD.items():
        if j>=len(d["C"]) or d["C"][j-12]<=0: continue
        if abs(d["C"][j]/d["C"][j-12]-1)<0.08: continue  # cheap pre-filter
        sig=detect_wildcard_signal(d["df"].iloc[max(0,j-60):j+1], s)
        if sig and (best is None or abs(sig.roc_pct)>abs(best[1].roc_pct)): best=(s,sig,tj)
    if best:
        s,sig,tj=best; pnl,used=fwd_min5(s,sig,tj); picks.append((tj,s,pnl,used))
# per-week + total
wk={}
for tj,s,pnl,used in picks:
    w=(now-tj)//(7*86400); wk.setdefault(w,[]).append(pnl)
tot=sum(p[2] for p in picks); m5=sum(1 for p in picks if p[3]=="Min5")
print(f"\ntotal picks {len(picks)} ({m5} Min5, {len(picks)-m5} fallback) | TOTAL ${tot:+.1f}")
for w in sorted(wk):
    v=wk[w]; print(f"  week -{w}: {len(v)} picks ${sum(v):+.1f}  (win {sum(1 for x in v if x>0)/len(v)*100:.0f}%)")
print("  last 24h: " + (f"${sum(p[2] for p in picks if p[0]>=now-86400):+.1f}"))
print("  last 10h: " + (f"${sum(p[2] for p in picks if p[0]>=now-10*3600):+.1f}"))
