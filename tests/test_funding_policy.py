from __future__ import annotations

from datetime import datetime, timezone

import pytest

from futuresbot.funding_policy import (
    evaluate_entry,
    seconds_to_next_settlement,
    stop_multiplier_for_funding,
)


def _utc(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 1, 1, hour, minute, second, tzinfo=timezone.utc)


def test_seconds_to_next_settlement_before_midnight():
    # 23:59:00 -> next boundary 00:00 in 60s.
    assert seconds_to_next_settlement(_utc(23, 59, 0)) == 60


def test_seconds_to_next_settlement_right_after_boundary():
    # 08:00:01 -> next boundary 16:00 in ~8h - 1s.
    secs = seconds_to_next_settlement(_utc(8, 0, 1))
    assert 28_700 < secs < 28_800


def test_evaluate_entry_blocks_long_2min_before_settlement_when_funding_positive():
    # 07:59:00 UTC, funding +0.01% (longs pay). Long is sub-2min -> block.
    decision = evaluate_entry(
        side="LONG",
        funding_rate_8h=0.0001,
        now=_utc(7, 59, 0),
    )
    assert decision.allowed is False
    assert "pre-funding" in decision.reason


def test_evaluate_entry_permits_short_2min_before_settlement_when_funding_positive():
    # Short receives positive funding -> permitted even in the block window.
    decision = evaluate_entry(
        side="SHORT",
        funding_rate_8h=0.0001,
        now=_utc(7, 59, 0),
    )
    assert decision.allowed is True
    assert decision.receives_funding is True


def test_evaluate_entry_permits_outside_block_window():
    decision = evaluate_entry(
        side="LONG",
        funding_rate_8h=0.0001,
        now=_utc(4, 0, 0),
    )
    assert decision.allowed is True


def test_stop_multiplier_normal_when_funding_below_threshold():
    policy = stop_multiplier_for_funding(side="LONG", funding_rate_8h=0.00001)
    assert policy.stop_multiplier == 1.0
    assert policy.label == "NORMAL"


def test_stop_multiplier_tightens_crowded_long_when_funding_very_positive():
    # funding 0.08%/8h > 0.06% threshold, long pays -> crowded -> tighten.
    policy = stop_multiplier_for_funding(side="LONG", funding_rate_8h=0.0008)
    assert policy.label == "CROWDED"
    assert policy.stop_multiplier == pytest.approx(0.7)


def test_stop_multiplier_widens_counter_short_when_funding_very_positive():
    # funding 0.08%/8h, short receives -> counter-crowd -> widen.
    policy = stop_multiplier_for_funding(side="SHORT", funding_rate_8h=0.0008)
    assert policy.label == "COUNTER_CROWD"
    assert policy.stop_multiplier == pytest.approx(1.2)
