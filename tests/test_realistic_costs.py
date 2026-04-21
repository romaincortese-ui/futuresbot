from __future__ import annotations

from datetime import datetime, timezone

import pytest

from futuresbot.realistic_costs import (
    apply_entry_slippage,
    apply_exit_slippage,
    check_liquidation_breach,
    compute_funding_accrual,
    compute_liq_price,
    simulate_position_close,
)


def _utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, day, hour, minute, tzinfo=timezone.utc)


def test_liq_price_long_at_10x_is_entry_minus_9p5pct():
    liq = compute_liq_price(entry_price=100.0, leverage=10, side="LONG")
    assert liq is not None
    # buffer = 1/10 - 0.005 = 0.095
    assert liq.price == pytest.approx(100.0 * (1.0 - 0.095))


def test_liq_price_short_at_20x_is_entry_plus_4p5pct():
    liq = compute_liq_price(entry_price=100.0, leverage=20, side="SHORT")
    assert liq is not None
    # buffer = 1/20 - 0.005 = 0.045
    assert liq.price == pytest.approx(100.0 * (1.0 + 0.045))


def test_liq_price_invalid_inputs():
    assert compute_liq_price(entry_price=0.0, leverage=10, side="LONG") is None
    assert compute_liq_price(entry_price=100.0, leverage=0, side="LONG") is None
    assert compute_liq_price(entry_price=100.0, leverage=10, side="XXX") is None


def test_entry_slippage_long_moves_price_up():
    filled = apply_entry_slippage(mid_price=100.0, side="LONG", leverage=10, slip_bps_per_lev=0.5)
    # 5 bps on leverage 10 -> +0.05%.
    assert filled == pytest.approx(100.05)


def test_exit_slippage_long_moves_stop_fill_down():
    filled = apply_exit_slippage(
        quoted_price=100.0,
        side="LONG",
        leverage=10,
        slip_bps_per_lev=0.5,
        exit_mult=1.5,
    )
    # 0.5 bps/lev * 10 * 1.5 = 7.5 bps -> -0.075%.
    assert filled == pytest.approx(99.925)


def test_funding_accrual_counts_settlements_crossed():
    # Open Jan 1 07:55 UTC, close Jan 1 16:05 UTC -> crosses 08:00 and 16:00.
    open_at = _utc(1, 7, 55)
    close_at = _utc(1, 16, 5)
    accrual = compute_funding_accrual(
        open_at=open_at,
        close_at=close_at,
        side="LONG",
        notional_usdt=1_000.0,
        funding_rate_8h=0.0001,
    )
    assert accrual.settlements_crossed == 2
    # +0.0001 * 2 * 1000 = 0.20 USDT paid by long.
    assert accrual.funding_usdt == pytest.approx(0.20)


def test_funding_accrual_short_receives_when_rate_positive():
    open_at = _utc(1, 7, 55)
    close_at = _utc(1, 8, 5)
    accrual = compute_funding_accrual(
        open_at=open_at,
        close_at=close_at,
        side="SHORT",
        notional_usdt=1_000.0,
        funding_rate_8h=0.0001,
    )
    assert accrual.settlements_crossed == 1
    assert accrual.funding_usdt == pytest.approx(-0.10)  # short receives


def test_check_liquidation_breach_long_touches_liq():
    assert check_liquidation_breach(liq_price=95.0, side="LONG", bar_high=101.0, bar_low=94.5) is True
    assert check_liquidation_breach(liq_price=95.0, side="LONG", bar_high=101.0, bar_low=96.0) is False


def test_check_liquidation_breach_short_touches_liq():
    assert check_liquidation_breach(liq_price=105.0, side="SHORT", bar_high=106.0, bar_low=100.0) is True
    assert check_liquidation_breach(liq_price=105.0, side="SHORT", bar_high=104.0, bar_low=100.0) is False


def test_simulate_position_close_normal_long_win():
    result = simulate_position_close(
        side="LONG",
        entry_price=100.0,
        exit_price=102.0,
        base_qty=1.0,
        leverage=10,
        open_at=_utc(1, 1, 0),
        close_at=_utc(1, 3, 0),
        funding_rate_8h=0.0,
    )
    # Exit slippage applied downward: 102 * (1 - 7.5bps) = 101.9235.
    assert result.effective_exit_price == pytest.approx(102.0 * (1 - 0.00075))
    assert result.funding_usdt == 0.0
    assert result.gross_pnl > 0
    assert result.net_pnl < result.gross_pnl  # fees eat into it


def test_simulate_position_close_liquidation_overrides_exit_price():
    result = simulate_position_close(
        side="LONG",
        entry_price=100.0,
        exit_price=95.0,  # ignored when liquidated
        base_qty=1.0,
        leverage=10,
        open_at=_utc(1, 0, 0),
        close_at=_utc(1, 1, 0),
        liquidated=True,
        liq_price=90.5,
    )
    # Effective exit = 90.5 * (1 - 0.005) = 90.0475.
    assert result.effective_exit_price == pytest.approx(90.5 * (1 - 0.005))
    assert result.liquidated is True
    assert result.net_pnl < 0
