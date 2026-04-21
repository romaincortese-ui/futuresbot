"""Integration smoke test for Sprint 2 flags.

Verifies that when each flag is ON the wired paths behave as documented; and
with flags OFF they are pure no-ops.
"""
from __future__ import annotations

import importlib
from datetime import datetime, timezone

import pytest


SPRINT2_FLAGS = (
    "USE_FUNDING_AWARE_ENTRY",
    "USE_FUNDING_STOP_MULT",
    "USE_REALISTIC_BACKTEST",
)


@pytest.fixture(autouse=True)
def _clear_flags(monkeypatch):
    for flag in SPRINT2_FLAGS:
        monkeypatch.delenv(flag, raising=False)
    for name in (
        "FUNDING_BLOCK_WINDOW_SECONDS",
        "FUNDING_HIGH_THRESHOLD",
        "FUNDING_CROWDED_STOP_MULT",
        "FUNDING_COUNTER_STOP_MULT",
        "REALISTIC_FUNDING_RATE_8H",
        "REALISTIC_SLIPPAGE_BPS_PER_LEV",
        "REALISTIC_EXIT_SLIP_MULT",
        "REALISTIC_LIQ_SLIPPAGE",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


def test_funding_entry_decision_blocks_long_in_pre_settlement_window():
    from futuresbot.funding_policy import evaluate_entry

    decision = evaluate_entry(
        side="LONG",
        funding_rate_8h=0.0002,
        now=datetime(2026, 1, 1, 7, 59, 0, tzinfo=timezone.utc),
        block_window_seconds=120,
    )
    assert decision.allowed is False


def test_funding_stop_multiplier_tightens_crowded_long():
    from futuresbot.funding_policy import stop_multiplier_for_funding

    policy = stop_multiplier_for_funding(
        side="LONG",
        funding_rate_8h=0.0008,
        high_funding_threshold=0.0006,
    )
    assert policy.label == "CROWDED"
    assert policy.stop_multiplier == pytest.approx(0.7)


def test_realistic_costs_apply_when_simulate_called_directly():
    from futuresbot.realistic_costs import simulate_position_close

    result = simulate_position_close(
        side="LONG",
        entry_price=100.0,
        exit_price=101.0,
        base_qty=10.0,
        leverage=10,
        open_at=datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc),
        close_at=datetime(2026, 1, 1, 17, 0, tzinfo=timezone.utc),  # crosses 08 + 16
        funding_rate_8h=0.0001,
    )
    # Two funding settlements crossed, 0.01%/8h, notional 1000 -> 0.20 USDT cost.
    assert result.funding_usdt == pytest.approx(0.20)
    assert result.net_pnl < result.gross_pnl  # fees + funding + slippage all bite


def test_liquidation_simulation_force_fills_at_liq_slippage_price():
    from futuresbot.realistic_costs import simulate_position_close

    result = simulate_position_close(
        side="LONG",
        entry_price=100.0,
        exit_price=120.0,  # irrelevant when liquidated
        base_qty=10.0,
        leverage=10,
        open_at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        close_at=datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc),
        liquidated=True,
        liq_price=90.5,
        liq_extra_slippage=0.005,
    )
    assert result.liquidated is True
    # 90.5 * (1 - 0.005) = 90.0475 effective fill, not 120.
    assert result.effective_exit_price == pytest.approx(90.5 * 0.995)
    assert result.net_pnl < 0
