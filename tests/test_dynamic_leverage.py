from __future__ import annotations

from futuresbot.dynamic_leverage import resolve_dynamic_leverage


def test_high_score_tight_btc_setup_can_reach_x20(monkeypatch):
    monkeypatch.setenv("FUTURES_DYNAMIC_LEVERAGE_ENABLED", "1")
    monkeypatch.setenv("FUTURES_DYNAMIC_LEVERAGE_MIN", "5")
    monkeypatch.setenv("FUTURES_DYNAMIC_LEVERAGE_MAX", "20")
    monkeypatch.setenv("FUTURES_DYNAMIC_LEVERAGE_MAX_MARGIN_LOSS_PCT", "0.25")

    decision = resolve_dynamic_leverage(
        certainty=0.99,
        sl_distance_pct=0.010,
        hard_loss_cap_pct=0.25,
        leverage_min=5,
        leverage_max=20,
        raw_score=96.0,
        symbol="BTC_USDT",
        entry_signal="COIL_BREAKOUT_LONG",
    )

    assert decision.leverage == 20
    assert decision.stop_margin_loss_pct == 0.20


def test_wide_stop_dash_sharp_event_cannot_use_high_leverage(monkeypatch):
    monkeypatch.setenv("FUTURES_DYNAMIC_LEVERAGE_ENABLED", "1")
    monkeypatch.setenv("FUTURES_DYNAMIC_LEVERAGE_MIN", "5")
    monkeypatch.setenv("FUTURES_DYNAMIC_LEVERAGE_MAX", "20")
    monkeypatch.setenv("FUTURES_DYNAMIC_LEVERAGE_MAX_MARGIN_LOSS_PCT", "0.25")

    decision = resolve_dynamic_leverage(
        certainty=0.99,
        sl_distance_pct=0.0367,
        hard_loss_cap_pct=0.25,
        leverage_min=5,
        leverage_max=20,
        raw_score=104.0,
        symbol="DASH_USDT",
        entry_signal="SHARP_EVENT_BREAKOUT_LONG",
    )

    assert decision.leverage == 6
    assert decision.leverage < 12
    assert decision.stop_margin_loss_pct <= 0.25


def test_low_score_is_capped_even_with_tight_stop(monkeypatch):
    monkeypatch.setenv("FUTURES_DYNAMIC_LEVERAGE_ENABLED", "1")
    monkeypatch.setenv("FUTURES_DYNAMIC_LEVERAGE_MIN", "5")
    monkeypatch.setenv("FUTURES_DYNAMIC_LEVERAGE_MAX", "20")

    decision = resolve_dynamic_leverage(
        certainty=0.50,
        sl_distance_pct=0.006,
        hard_loss_cap_pct=0.25,
        leverage_min=5,
        leverage_max=20,
        raw_score=63.0,
        symbol="BTC_USDT",
        entry_signal="COIL_BREAKOUT_LONG",
    )

    assert decision.score_cap == 5
    assert decision.leverage == 5


def test_static_mode_preserves_legacy_certainty_curve(monkeypatch):
    monkeypatch.setenv("FUTURES_DYNAMIC_LEVERAGE_ENABLED", "0")

    decision = resolve_dynamic_leverage(
        certainty=0.50,
        sl_distance_pct=0.01,
        hard_loss_cap_pct=0.25,
        leverage_min=5,
        leverage_max=20,
    )

    assert not decision.enabled
    assert decision.leverage == 12