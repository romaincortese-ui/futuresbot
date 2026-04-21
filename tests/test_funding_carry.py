"""Tests for Quarter 2 §3.8 funding-delta-neutral carry detector."""

from __future__ import annotations

import pytest

from futuresbot.funding_carry import (
    FundingCarryConfig,
    annualised_from_8h_funding,
    evaluate_carry,
)


def test_annualised_from_8h_funding_positive() -> None:
    # 0.01% per 8h → 0.0001 * 1095 = 10.95% annualised.
    assert annualised_from_8h_funding(0.0001) == pytest.approx(0.1095, rel=1e-4)


def test_annualised_from_8h_funding_negative() -> None:
    assert annualised_from_8h_funding(-0.0003) == pytest.approx(-0.3285, rel=1e-4)


def test_evaluate_carry_fires_long_spot_short_perp_on_positive_funding() -> None:
    # 0.02%/8h → ~21.9% ann gross. Default fee_drag at 30d ~ 1%. Net ~20.9%.
    op = evaluate_carry(funding_8h=0.0002)
    assert op.action == "LONG_SPOT_SHORT_PERP"
    assert op.net_annualised_carry > 0.08


def test_evaluate_carry_fires_short_spot_long_perp_on_negative_funding() -> None:
    op = evaluate_carry(funding_8h=-0.0003)
    assert op.action == "SHORT_SPOT_LONG_PERP"
    assert op.net_annualised_carry > 0.08


def test_evaluate_carry_holds_when_below_threshold() -> None:
    # 0.003%/8h → ~3.3% ann gross - ~1% fee drag = ~2.3% net < 8% threshold.
    op = evaluate_carry(funding_8h=0.00003)
    assert op.action == "HOLD"


def test_evaluate_carry_respects_custom_threshold() -> None:
    cfg = FundingCarryConfig(entry_annualised_carry=0.30)
    op = evaluate_carry(funding_8h=0.0002, config=cfg)
    assert op.action == "HOLD"  # ~21% ann net below 30% custom threshold


def test_evaluate_carry_fee_drag_varies_with_hold_window() -> None:
    long_hold = evaluate_carry(
        funding_8h=0.0001,
        config=FundingCarryConfig(assumed_hold_days=180.0),
    )
    short_hold = evaluate_carry(
        funding_8h=0.0001,
        config=FundingCarryConfig(assumed_hold_days=7.0),
    )
    # Longer hold amortises fees more → higher net carry.
    assert long_hold.net_annualised_carry > short_hold.net_annualised_carry


def test_evaluate_carry_borrow_drag_reduces_net() -> None:
    no_borrow = evaluate_carry(funding_8h=0.0002)
    with_borrow = evaluate_carry(
        funding_8h=0.0002,
        config=FundingCarryConfig(spot_borrow_apr=0.05),
    )
    assert with_borrow.net_annualised_carry < no_borrow.net_annualised_carry
