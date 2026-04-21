"""Tests for Quarter 2 §3.7 liquidation-cascade fade detector."""

from __future__ import annotations

import pytest

from futuresbot.liquidation_cascade import (
    LiquidationBar,
    LiquidationCascadeConfig,
    detect_cascade_fade,
)


def _make_history(count: int, base: float = 500_000.0) -> list[LiquidationBar]:
    return [
        LiquidationBar(
            timestamp_ms=i * 15 * 60_000,
            long_liq_usdt=base + (i % 10) * 1000,
            short_liq_usdt=base + (i % 7) * 800,
        )
        for i in range(count)
    ]


def test_detect_cascade_fade_returns_none_on_thin_history() -> None:
    history = _make_history(50)
    latest = LiquidationBar(timestamp_ms=99, long_liq_usdt=50_000_000, short_liq_usdt=0)
    assert detect_cascade_fade(history, latest) is None


def test_detect_cascade_fade_long_side_fires_when_outlier() -> None:
    history = _make_history(500)
    latest = LiquidationBar(
        timestamp_ms=10**12,
        long_liq_usdt=50_000_000.0,  # 100x baseline
        short_liq_usdt=100_000.0,
    )
    signal = detect_cascade_fade(history, latest)
    assert signal is not None
    assert signal.side == "LONG"
    assert signal.size_multiplier == pytest.approx(0.6)
    assert signal.tp_atr_mult == pytest.approx(1.5)
    assert signal.sl_atr_mult == pytest.approx(2.0)


def test_detect_cascade_fade_short_side_fires_when_outlier() -> None:
    history = _make_history(500)
    latest = LiquidationBar(
        timestamp_ms=10**12,
        long_liq_usdt=100_000.0,
        short_liq_usdt=50_000_000.0,
    )
    signal = detect_cascade_fade(history, latest)
    assert signal is not None
    assert signal.side == "SHORT"


def test_detect_cascade_fade_ignores_sub_minimum_cascade() -> None:
    history = _make_history(500, base=5_000.0)
    latest = LiquidationBar(
        timestamp_ms=10**12,
        long_liq_usdt=800_000.0,  # big vs history, but under min_cascade_usdt default 2M
        short_liq_usdt=50.0,
    )
    assert detect_cascade_fade(history, latest) is None


def test_detect_cascade_fade_does_not_fire_on_normal_bar() -> None:
    history = _make_history(500)
    latest = LiquidationBar(
        timestamp_ms=10**12,
        long_liq_usdt=500_000.0,
        short_liq_usdt=500_000.0,
    )
    assert detect_cascade_fade(history, latest) is None


def test_detect_cascade_fade_respects_custom_config() -> None:
    history = _make_history(500)
    latest = LiquidationBar(
        timestamp_ms=10**12,
        long_liq_usdt=3_000_000.0,
        short_liq_usdt=100.0,
    )
    # Default min_cascade=2M → fires. Raise it to 5M → must not fire.
    cfg = LiquidationCascadeConfig(min_cascade_usdt=5_000_000.0)
    assert detect_cascade_fade(history, latest, cfg) is None
