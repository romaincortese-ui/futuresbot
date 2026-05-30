from __future__ import annotations

from datetime import datetime, timezone

from futuresbot.models import FuturesSignal
from futuresbot.prediction_overlay import apply_prediction_overlay, evaluate_prediction_overlay, select_point_in_time_prediction_state


def _signal(side: str = "LONG") -> FuturesSignal:
    return FuturesSignal(
        symbol="BTC_USDT",
        side=side,
        score=80.0,
        certainty=0.62,
        entry_price=100.0,
        tp_price=104.0,
        sl_price=98.0,
        leverage=8,
        entry_signal="BREAKOUT_HOLD_LONG" if side == "LONG" else "BREAKDOWN_SHORT",
        metadata={},
    )


def test_prediction_overlay_neutral_fallback_leaves_signal_unchanged():
    signal = _signal()
    adjusted = apply_prediction_overlay(
        signal,
        None,
        datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc),
        enabled=True,
        fallback_mode="neutral",
    )

    assert adjusted is signal


def test_prediction_overlay_blocks_oracle_divergence():
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    state = {
        "generated_at": now.isoformat(),
        "ttl_seconds": 120,
        "events": [
            {
                "event_id": "btc-etf-flow",
                "source": "prophet",
                "symbols": ["BTC_USDT"],
                "direction": "bullish",
                "probability": 0.82,
            },
            {
                "event_id": "btc-etf-flow",
                "source": "polymarket",
                "symbols": ["BTC_USDT"],
                "direction": "bullish",
                "probability": 0.55,
            },
        ],
    }

    decision = evaluate_prediction_overlay(
        _signal(),
        state,
        now,
        enabled=True,
        divergence_threshold=0.15,
    )

    assert decision.allowed is False
    assert decision.reason == "prediction_oracle_divergence"
    assert round(decision.divergence or 0.0, 2) == 0.27


def test_prediction_overlay_updates_score_and_size_for_favourable_event():
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    state = {
        "generated_at": now.isoformat(),
        "ttl_seconds": 120,
        "events": [
            {
                "event_id": "btc-risk-on",
                "source": "prophet",
                "symbols": ["BTC_USDT"],
                "direction": "bullish",
                "probability": 0.70,
                "secondary_probability": 0.68,
                "event_given_success": 0.75,
            }
        ],
    }

    adjusted = apply_prediction_overlay(
        _signal(),
        state,
        now,
        enabled=True,
        min_favourable_probability=0.55,
        min_posterior=0.55,
        event_given_success=0.70,
        kelly_base_fraction=0.10,
        max_size_multiplier=1.0,
        score_scale=20.0,
    )

    assert adjusted is not None
    assert adjusted.score > 80.0
    assert adjusted.metadata["prediction_overlay"] == 1.0
    assert adjusted.metadata["prediction_event_id"] == "btc-risk-on"
    assert 0 < adjusted.metadata["prediction_size_multiplier"] <= 1.0
    assert adjusted.metadata["prediction_bayesian_success_probability"] > adjusted.metadata["prediction_base_success_probability"]


def test_prediction_overlay_point_in_time_selection_uses_latest_past_state():
    payload = {
        "timeline": [
            {
                "timestamp": "2026-05-30T10:00:00Z",
                "state": {"events": [{"event_id": "old", "probability": 0.40, "direction": "bearish"}]},
            },
            {
                "timestamp": "2026-05-30T11:00:00Z",
                "state": {"events": [{"event_id": "selected", "probability": 0.70, "direction": "bullish"}]},
            },
            {
                "timestamp": "2026-05-30T13:00:00Z",
                "state": {"events": [{"event_id": "future", "probability": 0.95, "direction": "bullish"}]},
            },
        ]
    }

    state = select_point_in_time_prediction_state(payload, datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc))

    assert state is not None
    assert state["events"][0]["event_id"] == "selected"
    assert state["generated_at"] == "2026-05-30T11:00:00+00:00"
