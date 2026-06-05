from __future__ import annotations

import json
import logging
import os

from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.pmt_core_weight import (
    DEFAULT_REDIS_KEY,
    DEFAULT_TTL_SECONDS,
    build_core_weight_payload,
    collect_live_market_inputs,
    load_payload_via_url,
    publish_payload_via_url,
)
from futuresbot.pmt_strategy import ELIGIBLE_PMT_SYMBOLS


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _symbols() -> tuple[str, ...]:
    raw = os.environ.get("FUTURES_PMT_SYMBOLS", "")
    if not raw.strip():
        return ELIGIBLE_PMT_SYMBOLS
    requested = [part.strip().upper() for part in raw.replace(",", " ").split() if part.strip()]
    allowed = [symbol for symbol in requested if symbol in ELIGIBLE_PMT_SYMBOLS]
    return tuple(allowed) or ELIGIBLE_PMT_SYMBOLS


def main() -> int:
    os.environ.setdefault("FUTURES_PMT_SYMBOLS", ",".join(ELIGIBLE_PMT_SYMBOLS))
    os.environ.setdefault("FUTURES_PMT_SIMPLE_CORE_WEIGHT_REDIS_KEY", DEFAULT_REDIS_KEY)
    os.environ.setdefault("FUTURES_PMT_SIMPLE_CORE_WEIGHT_TTL_SECONDS", str(DEFAULT_TTL_SECONDS))
    config = FuturesConfig.from_env()
    redis_key = os.environ.get("FUTURES_PMT_SIMPLE_CORE_WEIGHT_REDIS_KEY", DEFAULT_REDIS_KEY).strip() or DEFAULT_REDIS_KEY
    ttl_seconds = int(float(os.environ.get("FUTURES_PMT_SIMPLE_CORE_WEIGHT_TTL_SECONDS", DEFAULT_TTL_SECONDS) or DEFAULT_TTL_SECONDS))
    previous = load_payload_via_url(config.redis_url, key=redis_key)
    inputs = collect_live_market_inputs(MexcFuturesClient(config), _symbols())
    payload = build_core_weight_payload(inputs, previous_payload=previous)
    published = publish_payload_via_url(config.redis_url, payload, key=redis_key, ttl_seconds=ttl_seconds)
    summary = {
        "published": published,
        "redis_key": redis_key,
        "recommended_core_weight": payload.get("recommended_core_weight"),
        "calculated_core_weight": payload.get("calculated_core_weight"),
        "portfolio": payload.get("portfolio"),
        "symbols": payload.get("symbols"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0 if published or not config.redis_url else 1


if __name__ == "__main__":
    raise SystemExit(main())
