import os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
SYM = "TUT_USDT"
cl = MexcFuturesClient(FuturesConfig.from_env())
ops = [p for p in (cl.get_open_positions() or []) if str(p.get("symbol") or "") == SYM]
if ops:
    p = ops[0]
    op = float(p.get("holdAvgPrice") or p.get("openAvgPrice") or 0)
    im = float(p.get("im") or 0); lev = float(p.get("leverage") or 0)
    try: mk = float(cl.get_fair_price(SYM) or 0)
    except Exception: mk = 0.0
    mv = (mk/op - 1) if op else 0
    print("OPEN mark=%.6g move=%+.2f%% unreal=$%+.2f" % (mk, mv*100, mv*im*lev))
else:
    rows = cl.get_historical_positions(SYM, page_num=1, page_size=5) or []
    if rows:
        r = sorted(rows, key=lambda x: float(x.get("updateTime") or 0))[-1]
        op = float(r.get("openAvgPrice") or 0); cp = float(r.get("closeAvgPrice") or 0)
        print("CLOSED pnl=$%+.2f entry=%.6g exit=%.6g move=%+.2f%% at %s" % (
            float(r.get("realised") or 0), op, cp, (cp/op-1)*100 if op else 0,
            time.strftime("%m-%d %H:%M", time.gmtime(float(r.get("updateTime") or 0)/1000))))
    else:
        print("CLOSED (no history row yet)")
