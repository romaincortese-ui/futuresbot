from __future__ import annotations

import pytest

from futuresbot.nav_risk_sizing import compute_nav_risk_sizing


def test_nav_risk_sizing_basic_long():
    # NAV 10k, 1% risk -> $100 risk. Entry 100, SL 98 -> $2/contract (size 1).
    # -> 50 contracts. Notional 50*100 = 5000, affordable at min leverage 1.
    result = compute_nav_risk_sizing(
        nav_usdt=10_000.0,
        entry_price=100.0,
        sl_price=98.0,
        contract_size=1.0,
    )
    assert result is not None
    assert result.qty_contracts == 50
    assert result.risk_usdt == pytest.approx(100.0)
    assert result.notional_usdt == pytest.approx(5_000.0)
    assert 5 <= result.applied_leverage <= 10


def test_nav_risk_sizing_respects_budget_and_picks_min_affordable_leverage():
    # Notional 5000 with budget 600 -> needs leverage ceil(5000/600) = 9.
    result = compute_nav_risk_sizing(
        nav_usdt=10_000.0,
        entry_price=100.0,
        sl_price=98.0,
        contract_size=1.0,
        available_margin_usdt=600.0,
    )
    assert result is not None
    assert result.applied_leverage == 9


def test_nav_risk_sizing_returns_none_when_unaffordable_even_at_max_lev():
    # Notional 5000, max leverage 10 -> required margin 500. Budget 100 -> None.
    result = compute_nav_risk_sizing(
        nav_usdt=10_000.0,
        entry_price=100.0,
        sl_price=98.0,
        contract_size=1.0,
        available_margin_usdt=100.0,
    )
    assert result is None


def test_nav_risk_sizing_invalid_inputs_return_none():
    assert compute_nav_risk_sizing(nav_usdt=0.0, entry_price=100.0, sl_price=99.0, contract_size=1.0) is None
    assert compute_nav_risk_sizing(nav_usdt=10.0, entry_price=0.0, sl_price=99.0, contract_size=1.0) is None
    assert compute_nav_risk_sizing(nav_usdt=10.0, entry_price=100.0, sl_price=100.0, contract_size=1.0) is None
    assert compute_nav_risk_sizing(nav_usdt=10.0, entry_price=100.0, sl_price=99.0, contract_size=0.0) is None


def test_nav_risk_sizing_leverage_bounds_are_respected():
    result = compute_nav_risk_sizing(
        nav_usdt=10_000.0,
        entry_price=100.0,
        sl_price=98.0,
        contract_size=1.0,
        leverage_min=3,
        leverage_max=7,
    )
    assert result is not None
    assert 3 <= result.applied_leverage <= 7
