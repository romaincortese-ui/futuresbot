from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from futuresbot.config import DEFAULT_FUTURES_SYMBOLS
from futuresbot.prophet_prediction_archive import archive_current_prophet_odds


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive current ProphetMarket crypto odds for the futures prediction overlay.")
    parser.add_argument("--archive-output", default=os.getenv("FUTURES_PROPHET_ARCHIVE_FILE", "data/prophet_prediction_overlay.jsonl"))
    parser.add_argument("--latest-output", default=os.getenv("FUTURES_PROPHET_LATEST_FILE", ""))
    parser.add_argument("--symbols", default=os.getenv("FUTURES_SYMBOLS", ",".join(DEFAULT_FUTURES_SYMBOLS)))
    parser.add_argument("--page-size", type=int, default=int(os.getenv("FUTURES_PROPHET_ARCHIVE_PAGE_SIZE", "50")))
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("FUTURES_PROPHET_ARCHIVE_MAX_PAGES", "2")))
    parser.add_argument("--ttl-seconds", type=int, default=int(os.getenv("FUTURES_PROPHET_ARCHIVE_TTL_SECONDS", "900")))
    parser.add_argument("--timeout-seconds", type=float, default=float(os.getenv("FUTURES_PROPHET_ARCHIVE_TIMEOUT_SECONDS", "10")))
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", ""))
    parser.add_argument("--publish-redis-key", default=os.getenv("FUTURES_PROPHET_ARCHIVE_REDIS_KEY", ""))
    parser.add_argument("--redis-ttl-seconds", type=int, default=int(os.getenv("FUTURES_PROPHET_ARCHIVE_REDIS_TTL_SECONDS", "1800")))
    parser.add_argument("--include-resolved", action="store_true")
    parser.add_argument("--loop", action="store_true", help="Keep archiving on an interval instead of exiting after one snapshot.")
    parser.add_argument("--interval-seconds", type=int, default=int(os.getenv("FUTURES_PROPHET_ARCHIVE_REFRESH_SECONDS", "300")))
    return parser.parse_args()


def _archive_once(args: argparse.Namespace) -> None:
    result = archive_current_prophet_odds(
        archive_path=Path(args.archive_output) if args.archive_output else None,
        latest_path=Path(args.latest_output) if args.latest_output else None,
        symbols=[symbol.strip() for symbol in str(args.symbols or "").split(",") if symbol.strip()],
        page_size=max(1, int(args.page_size)),
        max_pages=max(1, int(args.max_pages)),
        ttl_seconds=max(1, int(args.ttl_seconds)),
        timeout_seconds=max(1.0, float(args.timeout_seconds)),
        include_resolved=bool(args.include_resolved),
        redis_url=str(args.redis_url or ""),
        redis_key=str(args.publish_redis_key or ""),
        redis_ttl_seconds=max(1, int(args.redis_ttl_seconds)),
    )
    print(
        "Archived Prophet odds "
        f"markets={result.raw_market_count} events={result.event_count} "
        f"archive={result.archive_path or 'disabled'} latest={result.latest_path or 'disabled'} "
        f"redis={'published' if result.published_redis else 'disabled'} skipped={result.skipped}",
        flush=True,
    )


def main() -> None:
    args = _parse_args()
    while True:
        _archive_once(args)
        if not args.loop:
            return
        time.sleep(max(1, int(args.interval_seconds)))


if __name__ == "__main__":
    main()