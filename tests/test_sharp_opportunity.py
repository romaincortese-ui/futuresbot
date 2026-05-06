from __future__ import annotations

import math
from dataclasses import replace

import pandas as pd

from futuresbot.config import FuturesBacktestConfig
from futuresbot.models import FuturesSignal
from futuresbot.sharp_opportunity import (
    annotate_sharp_event_signal,
    build_sharp_event_signal,
    evaluate_sharp_opportunity_overlay,
    sharp_event_margin_multiplier,
    sharp_event_signal_allowed,
)
from futuresbot.strategy import score_btc_futures_setup


def _event_frame(*, bars: int = 260, direction: str = "LONG") -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=bars, freq="15min", tz="UTC")
    base = [100.0 + math.sin(idx / 9.0) * 0.4 for idx in range(bars)]
    if direction == "LONG":
        for idx in range(24):
            base[-24 + idx] = 101.0 + idx * 0.08
        base[-2:] = [104.0, 104.8]
    else:
        for idx in range(24):
            base[-24 + idx] = 99.0 - idx * 0.08
        base[-2:] = [96.0, 95.2]
    volume = [1000.0 for _ in range(bars)]
    for idx in range(8):
        volume[-8 + idx] = 2300.0
    high = [price * 1.002 for price in base]
    low = [price * 0.998 for price in base]
    return pd.DataFrame({"open": base, "high": high, "low": low, "close": base, "volume": volume}, index=index)


def _frame_from_prices(prices: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(prices), freq="15min", tz="UTC")
    volume = [1000.0 + idx * 3 for idx in range(len(prices))]
    volume[-1] = volume[-2] * 2.4
    return pd.DataFrame(
        {
            "open": prices,
            "high": [price * 1.0015 for price in prices],
            "low": [price * 0.9985 for price in prices],
            "close": prices,
            "volume": volume,
        },
        index=index,
    )


def test_sharp_opportunity_permits_non_core_breakout(monkeypatch):
    monkeypatch.setenv("FUTURES_SHARP_EVENT_MIN_SCORE", "60")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_MAX_EMA_EXTENSION_ATR", "8.0")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_MAX_MOVE_ATR", "20.0")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_CLOSE_BUFFER_ATR", "2.0")
    decision = evaluate_sharp_opportunity_overlay(
        _event_frame(direction="LONG"),
        symbol="BCH_USDT",
        core_symbols=("BTC_USDT",),
        risk_multiplier=0.25,
    )

    assert decision.allowed is True
    assert decision.side == "LONG"
    assert decision.risk_multiplier == 0.25
    assert decision.metadata["sharp_event_move_atr"] > 1.0


def test_sharp_opportunity_blocks_corelessly_quiet_symbol():
    frame = _event_frame(direction="LONG")
    frame["close"] = 100.0
    frame["high"] = 100.1
    frame["low"] = 99.9

    decision = evaluate_sharp_opportunity_overlay(frame, symbol="BCH_USDT", core_symbols=("BTC_USDT",))

    assert decision.allowed is False


def test_sharp_event_signal_alignment_and_margin_multiplier(monkeypatch):
    monkeypatch.setenv("FUTURES_SHARP_EVENT_MAX_EMA_EXTENSION_ATR", "8.0")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_MAX_MOVE_ATR", "20.0")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_CLOSE_BUFFER_ATR", "2.0")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_SIGNAL_MIN_SCORE", "60")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_SIGNAL_MIN_MOVE_ATR", "1")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_SIGNAL_MIN_EMA_EXTENSION_ATR", "0")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_SIGNAL_MIN_24H_MOVE_PCT", "0")
    decision = evaluate_sharp_opportunity_overlay(
        _event_frame(direction="LONG"),
        symbol="BCH_USDT",
        core_symbols=("BTC_USDT",),
        risk_multiplier=0.35,
    )
    signal = FuturesSignal(
        symbol="BCH_USDT",
        side="LONG",
        score=82.0,
        certainty=0.7,
        entry_price=105.0,
        tp_price=110.0,
        sl_price=102.0,
        leverage=8,
        entry_signal="IMPULSE_EVENT_CONTINUATION_LONG",
    )

    assert sharp_event_signal_allowed(signal, decision)
    annotated = annotate_sharp_event_signal(signal, decision, bypass_symbol_calibration=True)

    assert sharp_event_margin_multiplier(annotated.metadata) == 0.35
    assert annotated.metadata["sharp_event_bypass_symbol_calibration"] == 1.0


def test_build_sharp_event_signal_uses_wider_trailing_profile(monkeypatch):
    monkeypatch.setenv("FUTURES_SHARP_EVENT_MAX_EMA_EXTENSION_ATR", "8.0")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_MAX_MOVE_ATR", "20.0")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_CLOSE_BUFFER_ATR", "2.0")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_SIGNAL_MIN_SCORE", "60")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_SIGNAL_MIN_MOVE_ATR", "1")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_SIGNAL_MIN_EMA_EXTENSION_ATR", "0")
    monkeypatch.setenv("FUTURES_SHARP_EVENT_SIGNAL_MIN_24H_MOVE_PCT", "0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    frame = _event_frame(direction="LONG")
    decision = evaluate_sharp_opportunity_overlay(frame, symbol="BCH_USDT", core_symbols=("BTC_USDT",), risk_multiplier=0.35)
    cfg = replace(
        FuturesBacktestConfig.from_env(),
        symbol="BCH_USDT",
        leverage_min=1,
        leverage_max=12,
        min_reward_risk=1.0,
    )

    signal = build_sharp_event_signal(frame, cfg, decision, bypass_symbol_calibration=True)

    assert signal is not None
    assert signal.entry_signal == "SHARP_EVENT_BREAKOUT_LONG"
    assert signal.metadata["sharp_event_synthetic_signal"] == 1.0
    assert signal.metadata["trailing_exit_activation_progress"] < 1.0
    assert signal.sl_price < signal.entry_price
    assert signal.tp_price > signal.entry_price


def test_strategy_allows_level_break_path_for_sharp_overlay_symbol(monkeypatch):
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_ENABLED", "1")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_SYMBOLS", "BTC_USDT")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_VOLUME_FLOOR", "0.20")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_MIN_BREAK_PCT", "0.002")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_MIN_BREAK_ATR", "0.20")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_RSI_15_LONG_MAX", "100")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_MAX_EMA_EXTENSION_ATR", "8.0")
    monkeypatch.setenv("FUTURES_IMPULSE_CONTINUATION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BREAKAWAY_ENABLED", "0")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_EVENT_CATALYST_ENABLED", "0")
    monkeypatch.setenv("FUTURES_CONTINUATION_ENABLED", "0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    cfg = replace(
        FuturesBacktestConfig.from_env(),
        symbol="XRP_USDT",
        min_confidence_score=50.0,
        min_reward_risk=0.8,
        leverage_min=1,
        leverage_max=8,
        trend_24h_floor=0.50,
        trend_6h_floor=0.50,
    )

    base = [2500 + idx * 0.65 + math.sin(idx / 7.0) * 8 for idx in range(520)]
    prior_level = 2925.0
    for offset in range(100):
        base[-104 + offset] = prior_level - 45.0 + math.sin(offset / 4.0) * 10.0
    base[-4:] = [2934.0, 2941.0, 2948.0, 2955.0]
    frame = _frame_from_prices(base)

    assert score_btc_futures_setup(frame, cfg) is None
    signal = score_btc_futures_setup(frame, cfg, sharp_event_overlay_active=True)

    assert signal is not None
    assert signal.entry_signal == "LEVEL_BREAK_LONG"
