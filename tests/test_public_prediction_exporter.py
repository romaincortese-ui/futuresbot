from __future__ import annotations

from datetime import datetime, timezone

import pytest

from futuresbot.prediction_overlay import select_point_in_time_prediction_state
from tools.export_public_prediction_history import PublicPredictionMarket, build_timeline_payload, classify_prediction_market


def test_classifies_clear_directional_crypto_markets():
    assert classify_prediction_market("Will Bitcoin be above $100,000 on Friday?", ["BTC_USDT"]) == ("BTC_USDT", "bullish")
    assert classify_prediction_market("Will Ethereum fall below $2,000 this month?", ["ETH_USDT"]) == ("ETH_USDT", "bearish")


def test_skips_ambiguous_range_and_non_price_markets():
    assert classify_prediction_market("BTC price range on Jun 1?", ["BTC_USDT"]) is None
    assert classify_prediction_market("Will Pump.fun perform an airdrop?", ["SOL_USDT"]) is None
    assert classify_prediction_market("Will Bitcoin ETF approval happen?", ["BTC_USDT"]) is None


def test_build_timeline_forward_fills_past_observations_only():
    start = datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 30, 10, 30, tzinfo=timezone.utc)
    market = PublicPredictionMarket(
        provider="polymarket",
        event_id="polymarket:btc-above",
        title="Will Bitcoin be above $100,000?",
        symbol="BTC_USDT",
        direction="bullish",
        token_or_ticker="token",
        history=((start, 0.61), (datetime(2026, 5, 30, 10, 22, tzinfo=timezone.utc), 0.66)),
    )

    payload = build_timeline_payload(
        [market],
        start=start,
        end=end,
        grid_minutes=15,
        max_observation_age_minutes=60,
        skipped={},
    )

    assert payload["metadata"]["snapshot_count"] == 3
    state_1015 = select_point_in_time_prediction_state(payload, datetime(2026, 5, 30, 10, 15, tzinfo=timezone.utc))
    state_1030 = select_point_in_time_prediction_state(payload, datetime(2026, 5, 30, 10, 30, tzinfo=timezone.utc))

    assert state_1015 is not None
    assert state_1015["events"][0]["probability"] == 0.61
    assert state_1030 is not None
    assert state_1030["events"][0]["probability"] == 0.66


def test_build_timeline_requires_market_history():
    with pytest.raises(ValueError, match="No public prediction histories"):
        build_timeline_payload(
            [],
            start=datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 5, 30, 10, 30, tzinfo=timezone.utc),
            grid_minutes=15,
            max_observation_age_minutes=60,
        )
