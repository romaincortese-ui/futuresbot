import os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
S = float(os.environ.get("FUTURES_TRIAL_START_TS") or 1787395448)
cl = MexcFuturesClient(FuturesConfig.from_env())
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
sel = [r for r in rows if float(r.get("updateTime") or 0)/1000 >= S]
print("CLOSES=%d OPEN=%d" % (len(sel), len(cl.get_open_positions() or [])))
