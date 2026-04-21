"""Integration smoke test for Sprint 3 flags and modules."""

from __future__ import annotations

import pytest


SPRINT3_FLAGS = (
    "USE_REGIME_CLASSIFIER",
    "USE_MEAN_REVERSION",
    "USE_MAKER_LADDER",
    "USE_PORTFOLIO_VAR",
    "USE_SLIPPAGE_ATTRIBUTION",
    "USE_WALK_FORWARD_GATE",
)


@pytest.fixture(autouse=True)
def _clear_flags(monkeypatch):
    for flag in SPRINT3_FLAGS:
        monkeypatch.delenv(flag, raising=False)
    for name in (
        "REGIME_VOL_SHOCK_PCT",
        "REGIME_CHOP_ADX_MAX",
        "REGIME_CHOP_VOL_PCT_MAX",
        "REGIME_TREND_SLOPE_ABS",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


def test_regime_classifier_module_is_importable():
    from futuresbot import regime_classifier

    r = regime_classifier.classify_regime(
        slope_20d=0.05,
        adx_1h=25.0,
        realised_vol_pct=50.0,
    )
    assert r.label == "TREND_UP"


def test_mean_reversion_module_is_importable():
    from futuresbot import mean_reversion

    assert hasattr(mean_reversion, "score_mean_reversion_setup")


def test_walk_forward_module_is_importable():
    from futuresbot.walk_forward import (
        WalkForwardMetrics,
        evaluate_walk_forward,
    )

    gate = evaluate_walk_forward(
        is_metrics=WalkForwardMetrics(trades=50, profit_factor=1.5, win_rate=0.5, expectancy=1.0),
        oos_metrics=WalkForwardMetrics(trades=25, profit_factor=1.3, win_rate=0.5, expectancy=1.0),
    )
    assert gate.accepted is True


def test_maker_ladder_module_is_importable():
    from futuresbot.maker_ladder import decide_next_action

    d = decide_next_action(
        side="LONG",
        seconds_since_signal=0.0,
        best_bid=100.0,
        best_ask=100.02,
        tick_size=0.01,
        seconds_to_funding=3600.0,
        filled=False,
    )
    assert d.action == "POST_MAKER"


def test_portfolio_var_module_is_importable():
    from futuresbot.portfolio_var import PositionWeight, check_new_position

    res = check_new_position(
        existing=[],
        candidate=PositionWeight("BTC_USDT", 100.0),
        nav_usdt=1000.0,
        annualised_vol={"BTC_USDT": 0.6},
        correlation={},
        cap_vol=0.08,
    )
    assert res.accepted is True


def test_slippage_attribution_module_is_importable():
    from futuresbot.slippage_attribution import SlippageAttribution

    s = SlippageAttribution()
    summary = s.summarise()
    assert summary["fills"] == 0
