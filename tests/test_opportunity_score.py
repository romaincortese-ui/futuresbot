from __future__ import annotations

from types import SimpleNamespace

from futuresbot.backtest import FuturesBacktestEngine
from futuresbot.opportunity_score import opportunity_balance_fraction, opportunity_score_10


def test_opportunity_score_bucket_mapping():
    assert opportunity_score_10(49.9) == 5
    assert opportunity_balance_fraction(49.9) == 0.0
    assert opportunity_score_10(56.0) == 6
    assert opportunity_balance_fraction(56.0) == 0.50
    assert opportunity_score_10(74.9) == 7
    assert opportunity_balance_fraction(74.9) == 0.50
    assert opportunity_score_10(85.0) == 9
    assert opportunity_balance_fraction(85.0) == 0.75
    assert opportunity_score_10(95.0) == 10
    assert opportunity_balance_fraction(95.0) == 1.0


def test_backtest_contract_sizing_uses_score_bucket_balance_fraction(monkeypatch):
    monkeypatch.setenv("FUTURES_OPPORTUNITY_BUCKET_SIZING_ENABLED", "1")
    engine = FuturesBacktestEngine.__new__(FuturesBacktestEngine)
    engine.config = SimpleNamespace(margin_budget_usdt=75.0)
    engine.contract_size = 1.0
    engine.min_vol = 1

    contracts, used_margin, leverage = engine._contracts_for_entry(
        entry_price=10.0,
        leverage=2,
        balance=200.0,
        score=85.0,
    )

    assert leverage == 2
    assert contracts == 30
    assert used_margin == 150.0
