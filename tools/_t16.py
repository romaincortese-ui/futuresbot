import json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
S = float(os.environ.get("FUTURES_TRIAL_START_TS") or 1787395448)
cl = MexcFuturesClient(FuturesConfig.from_env())
a = cl.get_account_asset("USDT") or {}
eq = float(a.get("equity") or 0)
rows, page = [], 1
while page <= 4:
    p = cl.private_get("/api/v1/private/position/list/history_positions", {"page_num": page, "page_size": 100})
    d = p.get("data", {}) if isinstance(p, dict) else {}
    b = d if isinstance(d, list) else (d.get("resultList") or [])
    if not b:
        break
    rows.extend(b)
    if min(float(r.get("updateTime") or 0)/1000 for r in b) < S:
        break
    page += 1
sel = sorted((r for r in rows if float(r.get("updateTime") or 0)/1000 >= S), key=lambda r: float(r.get("updateTime") or 0))
tot = sum(float(r.get("realised") or 0) for r in sel)
print("TRIAL 16 | start %s" % time.strftime("%m-%d %H:%M", time.gmtime(S)))
print("equity $%.2f | closes %d | realised $%+.2f" % (eq, len(sel), tot))
for r in sel:
    print("  %s %-14s %-5s lev %2.0fx margin $%5.2f  $%+6.2f" % (
        time.strftime("%m-%d %H:%M", time.gmtime(float(r.get("updateTime") or 0)/1000)),
        r.get("symbol"), "LONG" if int(r.get("positionType") or 1) == 1 else "SHORT",
        float(r.get("leverage") or 0), float(r.get("im") or 0), float(r.get("realised") or 0)))
ops = cl.get_open_positions() or []
print("open %d:" % len(ops))
for p in ops:
    sym = str(p.get("symbol") or "")
    im = float(p.get("im") or 0)
    lev = float(p.get("leverage") or 0)
    op = float(p.get("holdAvgPrice") or p.get("openAvgPrice") or 0)
    try:
        mk = float(cl.get_fair_price(sym) or 0)
    except Exception:
        mk = 0.0
    side = "LONG" if int(p.get("positionType") or 1) == 1 else "SHORT"
    mv = (mk/op - 1) * (1 if side == "LONG" else -1) if op else 0
    age = (time.time() - float(p.get("createTime") or 0)/1000)/3600
    # the trial's own criterion: realised risk per trade should be ~1.87%, not 1.45%
    print("  %-14s %-5s %2.0fx margin $%5.2f  age %4.1fh  move %+6.2f%%  unreal $%+5.2f  margin=%.2f%% of eq" % (
        sym, side, lev, im, age, mv*100, mv*im*lev, im/eq*100 if eq else 0))
