from __future__ import annotations

from types import SimpleNamespace

import pytest

from futuresbot.backtest import FuturesBacktestEngine, build_report
from futuresbot.opportunity_score import opportunity_balance_fraction, opportunity_nav_risk_pct, opportunity_score_10


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


def test_opportunity_nav_risk_pct_default_buckets(monkeypatch):
    for name in (
        "FUTURES_SCORE_BUCKET_NAV_RISK_ENABLED",
        "FUTURES_OPPORTUNITY_NAV_RISK_PCT",
        "FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE6",
        "FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE6_7",
        "FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE7",
        "FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE8",
        "FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE9",
        "FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE10",
    ):
        monkeypatch.delenv(name, raising=False)
    assert opportunity_nav_risk_pct(49.9) == 0.0
    assert opportunity_nav_risk_pct(56.0) == pytest.approx(0.015)
    assert opportunity_nav_risk_pct(74.9) == pytest.approx(0.04)
    assert opportunity_nav_risk_pct(80.0) == pytest.approx(0.04)
    assert opportunity_nav_risk_pct(85.0) == pytest.approx(0.04)
    assert opportunity_nav_risk_pct(95.0) == pytest.approx(0.045)


def test_opportunity_nav_risk_pct_env_overrides(monkeypatch):
    monkeypatch.setenv("FUTURES_OPPORTUNITY_NAV_RISK_PCT", "0.08")
    monkeypatch.setenv("FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE7", "0.04")
    monkeypatch.setenv("FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE9", "0.05")
    assert opportunity_nav_risk_pct(74.9) == pytest.approx(0.04)
    assert opportunity_nav_risk_pct(85.0) == pytest.approx(0.05)
    assert opportunity_nav_risk_pct(95.0) == pytest.approx(0.09)
    monkeypatch.setenv("FUTURES_SCORE_BUCKET_NAV_RISK_ENABLED", "0")
    assert opportunity_nav_risk_pct(85.0) == pytest.approx(0.08)


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


def test_build_report_groups_by_opportunity_score():
    report = build_report(
        [{"timestamp": "2026-05-01T00:00:00+00:00", "equity": 1005.0}],
        [
            {
                "strategy": "BTC_FUTURES",
                "symbol": "ZEC_USDT",
                "entry_signal": "IMPULSE_EVENT_CONTINUATION_LONG",
                "opportunity_score_10": 9,
                "pnl_usdt": 5.0,
            }
        ],
        1000.0,
    )

    assert report["by_opportunity_score"]["9"]["trades"] == 1
    assert report["by_opportunity_score_signal"]["9"]["IMPULSE_EVENT_CONTINUATION_LONG"]["total_pnl"] == 5.0
