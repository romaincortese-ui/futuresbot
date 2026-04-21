"""Tests for Quarter 2 §4.1 basis-trade detector."""

from __future__ import annotations

import pytest

from futuresbot.basis_trade import (
    BasisTradeConfig,
    compute_annualised_basis,
    evaluate_basis,
)


def test_compute_annualised_basis_contango() -> None:
    # 1% raw basis over 30 days → ~12.17% annualised.
    ann = compute_annualised_basis(spot_price=100.0, future_price=101.0, days_to_expiry=30.0)
    assert ann == pytest.approx(0.12166, rel=1e-3)


def test_compute_annualised_basis_backwardation() -> None:
    ann = compute_annualised_basis(spot_price=100.0, future_price=99.0, days_to_expiry=30.0)
    assert ann == pytest.approx(-0.12166, rel=1e-3)


def test_compute_annualised_basis_handles_zero_inputs() -> None:
    assert compute_annualised_basis(spot_price=0, future_price=100, days_to_expiry=30) == 0.0
    assert compute_annualised_basis(spot_price=100, future_price=100, days_to_expiry=0) == 0.0


def test_evaluate_basis_fires_long_on_contango() -> None:
    op = evaluate_basis(spot_price=30_000.0, future_price=30_750.0, days_to_expiry=45.0)
    assert op.action == "LONG_BASIS"
    assert op.annualised_basis > 0.08


def test_evaluate_basis_fires_short_on_backwardation() -> None:
    op = evaluate_basis(spot_price=30_000.0, future_price=29_250.0, days_to_expiry=45.0)
    assert op.action == "SHORT_BASIS"
    assert op.annualised_basis < -0.08


def test_evaluate_basis_holds_when_within_band() -> None:
    op = evaluate_basis(spot_price=30_000.0, future_price=30_050.0, days_to_expiry=45.0)
    assert op.action == "HOLD"


def test_evaluate_basis_rejects_near_expiry() -> None:
    op = evaluate_basis(spot_price=30_000.0, future_price=31_000.0, days_to_expiry=5.0)
    assert op.action == "HOLD"
    assert "dte" in op.reason


def test_evaluate_basis_rejects_far_expiry() -> None:
    op = evaluate_basis(spot_price=30_000.0, future_price=40_000.0, days_to_expiry=200.0)
    assert op.action == "HOLD"
    assert "dte" in op.reason


def test_evaluate_basis_custom_threshold() -> None:
    cfg = BasisTradeConfig(entry_annualised_premium=0.20)
    # 12% ann carry: under 20% custom threshold → HOLD.
    op = evaluate_basis(spot_price=100.0, future_price=101.0, days_to_expiry=30.0, config=cfg)
    assert op.action == "HOLD"
