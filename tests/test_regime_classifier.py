from __future__ import annotations

from futuresbot.regime_classifier import classify_regime, signal_allowed


def test_vol_shock_disables_everything():
    r = classify_regime(slope_20d=0.01, adx_1h=15.0, realised_vol_pct=95.0)
    assert r.label == "VOL_SHOCK"
    assert not r.allow_coil_breakout
    assert not r.allow_mean_reversion
    assert not r.allow_long and not r.allow_short


def test_chop_enables_mean_reversion_only():
    r = classify_regime(slope_20d=0.005, adx_1h=14.0, realised_vol_pct=20.0)
    assert r.label == "CHOP"
    assert r.allow_mean_reversion
    assert not r.allow_coil_breakout
    assert r.allow_long and r.allow_short


def test_trend_up_enables_longs_only():
    r = classify_regime(slope_20d=0.08, adx_1h=32.0, realised_vol_pct=50.0)
    assert r.label == "TREND_UP"
    assert r.allow_coil_breakout
    assert not r.allow_mean_reversion
    assert r.allow_long and not r.allow_short


def test_trend_down_enables_shorts_only():
    r = classify_regime(slope_20d=-0.06, adx_1h=28.0, realised_vol_pct=55.0)
    assert r.label == "TREND_DOWN"
    assert r.allow_coil_breakout
    assert not r.allow_mean_reversion
    assert r.allow_short and not r.allow_long


def test_signal_allowed_filters_sides_and_strategies():
    r_trend = classify_regime(slope_20d=0.08, adx_1h=32.0, realised_vol_pct=50.0)
    assert signal_allowed(r_trend, side="LONG", strategy="coil_breakout")
    assert not signal_allowed(r_trend, side="SHORT", strategy="coil_breakout")
    assert not signal_allowed(r_trend, side="LONG", strategy="mean_reversion")

    r_chop = classify_regime(slope_20d=0.0, adx_1h=10.0, realised_vol_pct=15.0)
    assert signal_allowed(r_chop, side="LONG", strategy="mean_reversion")
    assert not signal_allowed(r_chop, side="LONG", strategy="coil_breakout")
