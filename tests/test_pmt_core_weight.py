from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from futuresbot.pmt_core_weight import DEFAULT_REDIS_KEY, SymbolMarketInput, build_core_weight_payload, core_weight_from_payload


def _frame(start: float, step: float, *, bars: int = 140, volume_start: float = 1000.0, volume_step: float = 0.0) -> pd.DataFrame:
    prices = [start + step * idx for idx in range(bars)]
    index = pd.date_range(datetime(2026, 6, 1, tzinfo=timezone.utc), periods=bars, freq="15min")
    volumes = [volume_start + volume_step * idx for idx in range(bars)]
    return pd.DataFrame(
        {
            "open": prices,
            "high": [price * 1.001 for price in prices],
            "low": [price * 0.999 for price in prices],
            "close": prices,
            "volume": volumes,
        },
        index=index,
    )


def test_live_core_weight_drops_when_market_support_is_broad_and_clean():
    inputs = [
        SymbolMarketInput(
            symbol="BTC_USDT",
            frame=_frame(70000.0, 75.0, volume_step=12.0),
            ticker={"bid1": 80495.0, "ask1": 80505.0, "amount24": 5_000_000_000, "holdVol": 1_100_000},
            funding_rate=0.00008,
        ),
        SymbolMarketInput(
            symbol="ETH_USDT",
            frame=_frame(1900.0, 2.5, volume_step=8.0),
            ticker={"bid1": 2249.5, "ask1": 2250.5, "amount24": 2_000_000_000, "holdVol": 900_000},
            funding_rate=0.00006,
        ),
        SymbolMarketInput(
            symbol="SOL_USDT",
            frame=_frame(80.0, 0.12, volume_step=4.0),
            ticker={"bid1": 96.7, "ask1": 96.8, "amount24": 700_000_000, "holdVol": 500_000},
            funding_rate=0.00005,
        ),
    ]

    state = build_core_weight_payload(inputs, now_unix=1_800_000_000.0)

    assert state["recommended_core_weight"] <= 0.90
    assert state["portfolio"]["market_breadth"] >= 0.70
    assert state["symbols"] == ["BTC_USDT", "ETH_USDT", "SOL_USDT"]


def test_live_core_weight_stays_defensive_when_market_is_mixed_and_crowded():
    inputs = [
        SymbolMarketInput(
            symbol="BTC_USDT",
            frame=_frame(80000.0, -20.0),
            ticker={"bid1": 77200.0, "ask1": 77350.0, "amount24": 30_000_000, "holdVol": 1_000_000},
            funding_rate=0.0012,
        ),
        SymbolMarketInput(
            symbol="ETH_USDT",
            frame=_frame(2200.0, 0.10),
            ticker={"bid1": 2210.0, "ask1": 2218.0, "amount24": 20_000_000, "holdVol": 900_000},
            funding_rate=-0.0010,
        ),
    ]

    state = build_core_weight_payload(inputs, now_unix=1_800_000_000.0)

    assert state["recommended_core_weight"] >= 0.90
    assert state["portfolio"]["market_risk"] >= 0.35


def test_core_weight_payload_rejects_stale_or_unknown_symbol():
    stale_payload = {
        "schema_version": 1,
        "produced_at_unix": 100.0,
        "recommended_core_weight": 0.85,
        "symbols": ["BTC_USDT"],
    }
    result = core_weight_from_payload(stale_payload, now_unix=10_000.0, stale_seconds=60)
    assert result.applied is False
    assert result.reason == "stale_payload"

    bad_symbols = {
        "schema_version": 1,
        "produced_at_unix": 10_000.0,
        "recommended_core_weight": 0.85,
        "symbols": ["DOGE_USDT"],
    }
    result = core_weight_from_payload(bad_symbols, now_unix=10_000.0, stale_seconds=60)
    assert result.applied is False
    assert result.reason == "unknown_symbols"

    fresh_payload = {
        "schema_version": 1,
        "produced_at_unix": 10_000.0,
        "recommended_core_weight": 0.85,
        "symbols": ["BTC_USDT"],
    }
    result = core_weight_from_payload(fresh_payload, now_unix=10_000.0, stale_seconds=60)
    assert result.applied is True
    assert result.weight == pytest.approx(0.85)
    assert DEFAULT_REDIS_KEY == "mexc:pmt_simple_core_weight"