from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pandas as pd

from futuresbot.backtest import FuturesBacktestEngine, build_report
from futuresbot.models import FuturesPosition, FuturesSignal
from futuresbot.opportunity_score import opportunity_balance_fraction, opportunity_nav_risk_pct, opportunity_score_10


@pytest.fixture(autouse=True)
def _clear_pmt_profile_env(monkeypatch):
    for name in (
        "FUTURES_STRATEGY_MODE",
        "FUTURES_PMT_STRATEGY_ENABLED",
        "FUTURES_PMT_SYMBOLS",
        "FUTURES_PMT_MENTAL_THRESHOLD_STEPS",
        "FUTURES_FULL_BALANCE_SIZING_ENABLED",
        "FUTURES_FULL_BALANCE_RISK_PCT",
        "FUTURES_LEVERAGE_MIN",
        "FUTURES_LEVERAGE_MAX",
        "FUTURES_ENTRY_MIN_SCORE",
        "USE_FUTURES_PROFIT_LOCK",
        "FUTURES_PROFIT_LOCK_GIVEBACK_PCT",
        "FUTURES_PROFIT_LOCK_MIN_TP_PROGRESS",
        "FUTURES_MICRO_LOCK_ENABLED",
        "FUTURES_ADVERSE_PEAK_TRAIL_ENABLED",
        "FUTURES_NO_PROGRESS_EXIT_ENABLED",
        "FUTURES_STAGNATION_EXIT_ENABLED",
        "FUTURES_TRAILING_EXIT_DRAWDOWN_PCT",
    ):
        monkeypatch.delenv(name, raising=False)


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


def test_backtest_contract_sizing_full_balance_uses_available_balance(monkeypatch):
    monkeypatch.setenv("FUTURES_FULL_BALANCE_SIZING_ENABLED", "1")
    monkeypatch.setenv("FUTURES_FULL_BALANCE_RISK_PCT", "1.0")
    monkeypatch.setenv("USE_NAV_RISK_SIZING", "1")
    engine = FuturesBacktestEngine.__new__(FuturesBacktestEngine)
    engine.config = SimpleNamespace(margin_budget_usdt=75.0)
    engine.contract_size = 1.0
    engine.min_vol = 1

    contracts, used_margin, leverage = engine._contracts_for_entry(
        entry_price=10.0,
        leverage=2,
        balance=200.0,
        sl_price=9.0,
        margin_multiplier=0.25,
        score=92.0,
    )

    assert leverage == 2
    assert contracts == 40
    assert used_margin == 200.0


def test_backtest_entry_leverage_profile_can_override_symbol_cap(monkeypatch):
    monkeypatch.setenv("FUTURES_ENTRY_MIN_SCORE", "90")
    monkeypatch.setenv("FUTURES_ENTRY_LEVERAGE_MIN", "12")
    monkeypatch.setenv("FUTURES_ENTRY_LEVERAGE_HIGH", "20")
    monkeypatch.setenv("FUTURES_ENTRY_HIGH_SCORE", "95")
    engine = FuturesBacktestEngine.__new__(FuturesBacktestEngine)
    engine.config = SimpleNamespace(
        symbol="ZEC_USDT",
        min_confidence_score=50.0,
        leverage_min=1,
        leverage_max=8,
        long_threshold_offset=0.0,
        short_threshold_offset=0.0,
        crypto_event_stale_seconds=1800,
        crypto_event_min_abs_bias=0.35,
        crypto_event_threshold_relief=4.0,
        crypto_event_score_boost=5.0,
        crypto_event_adverse_score_penalty=4.0,
        crypto_event_overlay_enabled=False,
        prediction_overlay_enabled=False,
        sharp_event_overlay_enabled=False,
        sharp_event_core_symbols=(),
        sharp_event_overlay_risk_multiplier=1.0,
        sharp_event_bypass_symbol_calibration=False,
    )
    engine.calibration = None
    engine._crypto_event_state_for = lambda now: None
    engine._prediction_overlay_state_for = lambda now: None

    raw_signal = FuturesSignal(
        symbol="ZEC_USDT",
        side="LONG",
        score=96.0,
        certainty=0.9,
        entry_price=100.0,
        tp_price=110.0,
        sl_price=95.0,
        leverage=5,
        entry_signal="COIL_BREAKOUT_LONG",
        metadata={},
    )
    monkeypatch.setattr("futuresbot.backtest.score_btc_futures_setup", lambda *args, **kwargs: raw_signal)

    signal = engine._candidate_signal_for_frame(pd.DataFrame(), datetime(2026, 5, 1, tzinfo=timezone.utc), 100)

    assert signal is not None
    assert signal.leverage == 20


def test_backtest_margin_loss_exit_closes_at_entry(monkeypatch):
    monkeypatch.setenv("FUTURES_MARGIN_LOSS_EXIT_ENABLED", "1")
    engine = FuturesBacktestEngine.__new__(FuturesBacktestEngine)
    engine.config = SimpleNamespace(
        trailing_exit_activation_progress=1.5,
        early_exit_min_profit_pct=0.012,
        trailing_exit_drawdown_pct=0.02,
        taker_fee_rate=0.0006,
    )
    position = FuturesPosition(
        symbol="BTC_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=1,
        contract_size=1.0,
        leverage=12,
        margin_usdt=8.33,
        tp_price=110.0,
        sl_price=95.0,
        position_id="BACKTEST",
        order_id="BACKTEST",
        opened_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        score=92.0,
        certainty=0.9,
        entry_signal="COIL_BREAKOUT_LONG",
        metadata={},
    )

    exit_result = engine._bar_exit(position, pd.Series({"high": 101.0, "low": 99.0, "close": 100.0}))

    assert exit_result == (100.0, "MARGIN_LOSS_EXIT")
