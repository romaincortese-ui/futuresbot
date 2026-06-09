"""Export full MEXC futures position history to JSONL for replay analysis.

Run with Railway env injection (read-only private GET endpoints only):

    railway run --service Futures-bot python tools/export_position_history.py

Writes ``_position_history_full.jsonl`` (one position dict per line) plus a
stdout summary. Never prints credentials.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient

SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT", "SEI_USDT", "ZEC_USDT"]
PAGE_SIZE = 100
MAX_PAGES = 50
OUT_PATH = Path(__file__).resolve().parents[1] / "_position_history_full.jsonl"


def main() -> int:
    config = FuturesConfig.from_env()
    if not config.api_key or not config.api_secret:
        print("ERROR: MEXC_API_KEY/MEXC_API_SECRET not present in environment")
        return 1
    client = MexcFuturesClient(config)
    seen: set[int] = set()
    rows: list[dict] = []
    for symbol in SYMBOLS:
        page = 1
        while page <= MAX_PAGES:
            batch = client.get_historical_positions(symbol, page_num=page, page_size=PAGE_SIZE)
            if not batch:
                break
            new = 0
            for row in batch:
                pid = int(row.get("positionId") or 0)
                if pid and pid in seen:
                    continue
                seen.add(pid)
                rows.append(row)
                new += 1
            print(f"{symbol} page {page}: {len(batch)} rows ({new} new)")
            if len(batch) < PAGE_SIZE:
                break
            page += 1
            time.sleep(0.25)
    rows.sort(key=lambda r: int(r.get("createTime") or 0))
    with OUT_PATH.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    closed = [r for r in rows if str(r.get("positionShowStatus") or "") == "CLOSED" or int(r.get("state") or 0) == 3]
    print(f"TOTAL positions: {len(rows)} (closed: {len(closed)}) -> {OUT_PATH.name}")
    if rows:
        first = int(rows[0].get("createTime") or 0) / 1000.0
        last = int(rows[-1].get("createTime") or 0) / 1000.0
        print(f"window: {time.strftime('%Y-%m-%d %H:%M', time.gmtime(first))} .. {time.strftime('%Y-%m-%d %H:%M', time.gmtime(last))} UTC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
