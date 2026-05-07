from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timezone

import pandas as pd

from futuresbot.config import FuturesBacktestConfig
from futuresbot.strategy import _entry_signal_disabled, diagnose_impulse_rejection, score_btc_futures_setup


def _config() -> FuturesBacktestConfig:
    now = datetime(2026, 4, 18, tzinfo=timezone.utc)
    return replace(
        FuturesBacktestConfig.from_env(now=now),
        min_confidence_score=56.0,
        long_threshold_offset=0.0,
        short_threshold_offset=0.0,
        min_reward_risk=1.0,
        hard_loss_cap_pct=0.8,
        trend_24h_floor=0.01,
        trend_6h_floor=0.0025,
    )


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


def _disable_competing_entry_paths(monkeypatch):
    monkeypatch.setenv("FUTURES_BTC_ROUND_LEVEL_LONG_ENABLED", "0")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_ENABLED", "0")
    monkeypatch.setenv("FUTURES_IMPULSE_CONTINUATION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_CONTINUATION_ENABLED", "false")
    monkeypatch.setenv("FUTURES_BREAKAWAY_ENABLED", "0")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_EVENT_CATALYST_ENABLED", "0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")


def test_strategy_produces_long_signal_on_uptrend_breakout():
    base = [90000 + idx * 12 + math.sin(idx / 5.0) * 38 + math.cos(idx / 11.0) * 22 + ((idx % 5) - 2) * 14 for idx in range(520)]
    base[-20:-1] = [base[-21] + ((idx % 4) - 1) * 15 for idx in range(19)]
    base[-1] = max(base[-20:-1]) + 220
    frame = _frame_from_prices(base)

    signal = score_btc_futures_setup(frame, _config())

    assert signal is not None
    assert signal.side == "LONG"
    assert 20 <= signal.leverage <= 50


def test_symbol_entry_signal_denylist_has_overridable_defaults(monkeypatch):
    cfg = replace(_config(), symbol="BTC_USDT")

    assert not _entry_signal_disabled(cfg, "COIL_BREAKOUT_LONG")
    assert _entry_signal_disabled(cfg, "MOMENTUM_BREAKAWAY_SHORT")
    assert not _entry_signal_disabled(cfg, "MOMENTUM_BREAKAWAY_LONG")

    monkeypatch.setenv("FUTURES_BTCUSDT_DISABLED_ENTRY_SIGNALS", "COIL_BREAKOUT_LONG")
    assert _entry_signal_disabled(cfg, "COIL_BREAKOUT_LONG")

    monkeypatch.setenv("FUTURES_BTCUSDT_DISABLED_ENTRY_SIGNALS", "none")
    assert not _entry_signal_disabled(cfg, "COIL_BREAKOUT_LONG")

    assert _entry_signal_disabled(replace(_config(), symbol="SOL_USDT"), "TREND_CONTINUATION_SHORT")
    assert _entry_signal_disabled(replace(_config(), symbol="BNB_USDT"), "LEVEL_BREAK_LONG")
    assert _entry_signal_disabled(replace(_config(), symbol="BNB_USDT"), "IMPULSE_EVENT_CONTINUATION_SHORT")
    assert _entry_signal_disabled(replace(_config(), symbol="ZEC_USDT"), "IMPULSE_EVENT_CONTINUATION_SHORT")


def test_major_threshold_long_covers_btc_sol_eth(monkeypatch):
    _disable_competing_entry_paths(monkeypatch)
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ENABLED", "1")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_SYMBOLS", "BTC_USDT SOL_USDT ETH_USDT")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_VOLUME_FLOOR", "0.10")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_TREND_24H_MIN", "0")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_TREND_6H_MIN", "0")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_RSI_1H_LONG_MAX", "100")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_RSI_15_LONG_MAX", "100")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_MAX_EMA_EXTENSION_ATR", "12.0")

    cases = [
        ("BTC_USDT", 79000.0, 76000.0, 140.0, 120.0, 240.0),
        ("ETH_USDT", 2500.0, 2320.0, 5.0, 7.0, 12.0),
        ("SOL_USDT", 150.0, 139.0, 0.35, 0.55, 0.85),
    ]
    for symbol, level, start, prior_gap, first_break, second_break in cases:
        step = (level - prior_gap - start) / 517.0
        prices = [start + idx * step + math.sin(idx / 9.0) * prior_gap * 0.05 for idx in range(518)]
        prices[-1] = level - prior_gap
        prices.extend([level + first_break, level + second_break])
        signal = score_btc_futures_setup(
            _frame_from_prices(prices),
            replace(_config(), symbol=symbol, min_confidence_score=58.0, min_reward_risk=0.8),
        )

        assert signal is not None, symbol
        assert signal.side == "LONG"
        assert signal.entry_signal == "MAJOR_THRESHOLD_LONG"
        assert signal.metadata["major_threshold"] == 1.0
        assert signal.metadata["major_threshold_level"] == level
        assert signal.sl_price < level < signal.entry_price


def test_major_threshold_short_covers_btc_sol_eth(monkeypatch):
    _disable_competing_entry_paths(monkeypatch)
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ENABLED", "1")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_VOLUME_FLOOR", "0.10")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_TREND_24H_MIN", "0")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_TREND_6H_MIN", "0")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_RSI_1H_SHORT_MAX", "100")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_RSI_15_SHORT_MAX", "100")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_RSI_1H_SHORT_MIN", "0")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_RSI_15_SHORT_MIN", "0")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_MAX_EMA_EXTENSION_ATR", "12.0")

    cases = [
        ("BTC_USDT", 77000.0, 80500.0, 140.0, 120.0, 240.0),
        ("ETH_USDT", 2400.0, 2580.0, 5.0, 7.0, 12.0),
        ("SOL_USDT", 140.0, 151.0, 0.35, 0.55, 0.85),
    ]
    for symbol, level, start, prior_gap, first_break, second_break in cases:
        step = (start - (level + prior_gap)) / 517.0
        prices = [start - idx * step + math.sin(idx / 9.0) * prior_gap * 0.05 for idx in range(518)]
        prices[-1] = level + prior_gap
        prices.extend([level - first_break, level - second_break])
        signal = score_btc_futures_setup(
            _frame_from_prices(prices),
            replace(_config(), symbol=symbol, min_confidence_score=58.0, min_reward_risk=0.8),
        )

        assert signal is not None, symbol
        assert signal.side == "SHORT"
        assert signal.entry_signal == "MAJOR_THRESHOLD_SHORT"
        assert signal.metadata["major_threshold"] == 1.0
        assert signal.metadata["major_threshold_level"] == level
        assert signal.entry_price < level < signal.sl_price


def test_major_threshold_defaults_do_not_cover_unlisted_symbol(monkeypatch):
    _disable_competing_entry_paths(monkeypatch)
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ENABLED", "1")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_VOLUME_FLOOR", "0.10")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_TREND_24H_MIN", "0")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_TREND_6H_MIN", "0")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_RSI_1H_LONG_MAX", "100")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_RSI_15_LONG_MAX", "100")
    prices = [620 + idx * 0.35 + math.sin(idx / 9.0) * 1.2 for idx in range(518)]
    prices[-1] = 699.0
    prices.extend([701.5, 703.0])

    signal = score_btc_futures_setup(
        _frame_from_prices(prices),
        replace(_config(), symbol="BNB_USDT", min_confidence_score=58.0, min_reward_risk=0.8),
    )

    assert signal is None


def test_strategy_produces_btc_breakout_hold_long(monkeypatch):
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_ENABLED", "1")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_VOLUME_FLOOR", "0.40")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_RSI_15_MAX", "100")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_MAX_EMA_EXTENSION_ATR", "8.0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    base = [76000 + idx * 4 + math.sin(idx / 8.0) * 35 for idx in range(520)]
    anchor = 78600.0
    for offset in range(44):
        base[-48 + offset] = anchor - 520.0 + offset * 8.0 + math.sin(offset / 2.0) * 20.0
    base[-4:] = [79050.0, 79120.0, 79220.0, 79340.0]
    frame = _frame_from_prices(base)

    signal = score_btc_futures_setup(frame, replace(_config(), min_confidence_score=80.0, consolidation_max_range_pct=0.006))

    assert signal is not None
    assert signal.side == "LONG"
    assert signal.entry_signal == "BREAKOUT_HOLD_LONG"
    assert signal.metadata["breakout_hold"] == 1.0
    assert signal.sl_price < signal.metadata["breakout_hold_level"]


def test_btc_breakout_hold_counts_shelf_volume_after_quiet_reclaim(monkeypatch):
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_ENABLED", "1")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_VOLUME_FLOOR", "0.65")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_RSI_15_MAX", "100")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_MAX_EMA_EXTENSION_ATR", "8.0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "1")
    monkeypatch.setenv("MIN_NET_RR", "1.8")
    base = [76000 + idx * 4 + math.sin(idx / 8.0) * 35 for idx in range(520)]
    for offset in range(32):
        base[-48 + offset] = 77500.0 + offset * 34.0 + math.sin(offset / 3.0) * 15.0
    base[-16:] = [
        78747.6,
        78920.4,
        79201.6,
        79484.4,
        80171.4,
        80065.6,
        79655.0,
        79867.0,
        79976.7,
        79671.7,
        80191.7,
        80228.5,
        79982.4,
        80337.6,
        80393.9,
        80220.5,
    ]
    frame = _frame_from_prices(base)
    frame["volume"] = 1000.0
    frame.iloc[-16:-8, frame.columns.get_loc("volume")] = 2200.0
    frame.iloc[-8:, frame.columns.get_loc("volume")] = 350.0

    signal = score_btc_futures_setup(frame, replace(_config(), min_confidence_score=58.0, consolidation_max_range_pct=0.006))

    assert signal is not None
    assert signal.entry_signal == "BREAKOUT_HOLD_LONG"
    assert signal.score >= 80.0
    assert signal.metadata["volume_ratio"] < 0.65
    assert signal.metadata["impulse_window_volume_ratio"] < 0.65
    assert signal.metadata["breakout_hold_shelf_volume_ratio"] >= 0.65
    assert signal.metadata["breakout_hold_volume_ratio"] >= 0.65
    assert signal.metadata["cost_budget_mode"] == "enforce"
    assert signal.metadata["cost_budget_pass"] == 1.0


def test_strategy_rejoins_btc_round_level_break(monkeypatch):
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BTC_ROUND_LEVEL_LONG_ENABLED", "1")
    monkeypatch.setenv("FUTURES_BTC_ROUND_LEVEL_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_BTC_ROUND_LEVEL_VOLUME_FLOOR", "0.20")
    monkeypatch.setenv("FUTURES_BTC_ROUND_LEVEL_RSI_1H_MAX", "100")
    monkeypatch.setenv("FUTURES_BTC_ROUND_LEVEL_RSI_15_MAX", "100")
    monkeypatch.setenv("FUTURES_BTC_ROUND_LEVEL_MAX_EMA_EXTENSION_ATR", "10.0")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_ENABLED", "0")
    monkeypatch.setenv("FUTURES_IMPULSE_CONTINUATION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BREAKAWAY_ENABLED", "0")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_EVENT_CATALYST_ENABLED", "0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    base = [76000 + idx * 6 + math.sin(idx / 8.0) * 30 for idx in range(520)]
    anchor = 79620.0
    for offset in range(45):
        base[-48 + offset] = anchor + offset * 7.0 + math.sin(offset / 3.0) * 22.0
    base[-3:] = [80110.0, 80210.0, 80320.0]
    frame = _frame_from_prices(base)

    signal = score_btc_futures_setup(
        frame,
        replace(
            _config(),
            symbol="BTC_USDT",
            min_confidence_score=78.0,
            min_reward_risk=0.8,
            trend_24h_floor=0.50,
            trend_6h_floor=0.50,
        ),
    )

    assert signal is not None
    assert signal.side == "LONG"
    assert signal.entry_signal == "BTC_ROUND_LEVEL_LONG"
    assert signal.metadata["btc_round_level"] == 1.0
    assert signal.metadata["btc_round_level_price"] == 80000.0
    assert signal.sl_price < 80000.0


def test_btc_short_guard_blocks_impulse_short_in_bullish_context(monkeypatch):
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ENABLED", "0")
    monkeypatch.setenv("FUTURES_IMPULSE_CONTINUATION_ENABLED", "1")
    monkeypatch.setenv("FUTURES_IMPULSE_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_IMPULSE_MIN_MOVE_ATR", "0.30")
    monkeypatch.setenv("FUTURES_IMPULSE_MIN_MOVE_PCT", "0.002")
    monkeypatch.setenv("FUTURES_IMPULSE_VOLUME_FLOOR", "0.20")
    monkeypatch.setenv("FUTURES_IMPULSE_RSI_15_SHORT_MIN", "0")
    monkeypatch.setenv("FUTURES_BTC_ROUND_LEVEL_LONG_ENABLED", "0")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BREAKAWAY_ENABLED", "0")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_EVENT_CATALYST_ENABLED", "0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    base = [76000 + idx * 9 + math.sin(idx / 7.0) * 24 for idx in range(520)]
    anchor = base[-10]
    for offset in range(9):
        base[-9 + offset] = anchor * (1.0 - 0.00085 * (offset + 1))
    frame = _frame_from_prices(base)
    cfg = replace(_config(), symbol="BTC_USDT", min_confidence_score=54.0, trend_24h_floor=0.08, trend_6h_floor=0.04)

    monkeypatch.setenv("FUTURES_BTC_SHORT_UPTREND_GUARD", "1")
    assert score_btc_futures_setup(frame, cfg) is None

    monkeypatch.setenv("FUTURES_BTC_SHORT_UPTREND_GUARD", "0")
    signal = score_btc_futures_setup(frame, cfg)

    assert signal is not None
    assert signal.side == "SHORT"
    assert signal.entry_signal == "IMPULSE_EVENT_CONTINUATION_SHORT"


def test_strategy_produces_short_signal_on_downtrend_breakdown():
    base = [100000 - idx * 14 + math.sin(idx / 5.0) * 36 + math.cos(idx / 10.0) * 18 + ((idx % 5) - 2) * 12 for idx in range(520)]
    base[-20:-1] = [base[-21] + ((idx % 4) - 1) * 12 for idx in range(19)]
    base[-1] = min(base[-20:-1]) - 240
    frame = _frame_from_prices(base)

    signal = score_btc_futures_setup(frame, _config())

    assert signal is not None
    assert signal.side == "SHORT"
    assert 20 <= signal.leverage <= 50


def test_strategy_produces_impulse_event_continuation_long(monkeypatch):
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ENABLED", "0")
    monkeypatch.setenv("FUTURES_IMPULSE_CONTINUATION_ENABLED", "1")
    monkeypatch.setenv("FUTURES_IMPULSE_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_IMPULSE_MIN_MOVE_ATR", "0.50")
    monkeypatch.setenv("FUTURES_IMPULSE_MIN_MOVE_PCT", "0.006")
    monkeypatch.setenv("FUTURES_IMPULSE_VOLUME_FLOOR", "0.50")
    monkeypatch.setenv("FUTURES_IMPULSE_RSI_15_LONG_MAX", "100")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    base = [100000 + math.sin(idx / 6.0) * 35 + math.cos(idx / 13.0) * 25 for idx in range(520)]
    anchor = base[-10]
    for offset in range(9):
        base[-9 + offset] = anchor * (1.0 + 0.0011 * (offset + 1))
    frame = _frame_from_prices(base)

    signal = score_btc_futures_setup(frame, replace(_config(), trend_24h_floor=0.05, trend_6h_floor=0.02))

    assert signal is not None
    assert signal.side == "LONG"
    assert signal.entry_signal == "IMPULSE_EVENT_CONTINUATION_LONG"
    assert signal.metadata["impulse_move_pct"] > 0


def test_strategy_produces_impulse_event_continuation_short(monkeypatch):
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ENABLED", "0")
    monkeypatch.setenv("FUTURES_IMPULSE_CONTINUATION_ENABLED", "1")
    monkeypatch.setenv("FUTURES_IMPULSE_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_IMPULSE_MIN_MOVE_ATR", "0.50")
    monkeypatch.setenv("FUTURES_IMPULSE_MIN_MOVE_PCT", "0.006")
    monkeypatch.setenv("FUTURES_IMPULSE_VOLUME_FLOOR", "0.50")
    monkeypatch.setenv("FUTURES_IMPULSE_RSI_15_SHORT_MIN", "0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    base = [100000 + math.sin(idx / 6.0) * 35 + math.cos(idx / 13.0) * 25 for idx in range(520)]
    anchor = base[-10]
    for offset in range(9):
        base[-9 + offset] = anchor * (1.0 - 0.0011 * (offset + 1))
    frame = _frame_from_prices(base)

    signal = score_btc_futures_setup(frame, replace(_config(), trend_24h_floor=0.05, trend_6h_floor=0.02))

    assert signal is not None
    assert signal.side == "SHORT"
    assert signal.entry_signal == "IMPULSE_EVENT_CONTINUATION_SHORT"
    assert signal.metadata["impulse_move_pct"] < 0


def test_strategy_produces_btc_reversal_breakdown_short(monkeypatch):
    monkeypatch.setenv("FUTURES_BTC_REVERSAL_SHORT_ENABLED", "1")
    monkeypatch.setenv("FUTURES_BTC_REVERSAL_SHORT_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_BTC_REVERSAL_SHORT_VOLUME_FLOOR", "0.30")
    monkeypatch.setenv("FUTURES_BTC_REVERSAL_SHORT_MIN_DROP_ATR", "0.70")
    monkeypatch.setenv("FUTURES_BTC_REVERSAL_SHORT_MIN_DROP_PCT", "0.004")
    monkeypatch.setenv("FUTURES_BTC_REVERSAL_SHORT_RSI_1H_MAX", "100")
    monkeypatch.setenv("FUTURES_BTC_REVERSAL_SHORT_RSI_15_MAX", "100")
    monkeypatch.setenv("FUTURES_BTC_REVERSAL_SHORT_MIN_PRIOR_TREND_24H", "-0.05")
    monkeypatch.setenv("FUTURES_BTC_REVERSAL_SHORT_MIN_PRIOR_TREND_6H", "-0.05")
    monkeypatch.setenv("FUTURES_BTC_REVERSAL_SHORT_MAX_COUNTER_TREND_24H", "0.05")
    monkeypatch.setenv("FUTURES_BTC_REVERSAL_SHORT_MAX_COUNTER_TREND_6H", "0.02")
    monkeypatch.setenv("FUTURES_BTC_REVERSAL_SHORT_MIN_IMPULSE_MOVE_PCT", "0.001")
    monkeypatch.setenv("FUTURES_IMPULSE_CONTINUATION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_CONTINUATION_ENABLED", "false")
    monkeypatch.setenv("FUTURES_BREAKAWAY_ENABLED", "0")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BTC_ROUND_LEVEL_LONG_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_ENABLED", "0")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_EVENT_CATALYST_ENABLED", "0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    base = [79000 + idx * 8 + math.sin(idx / 6.0) * 60 for idx in range(520)]
    high_anchor = max(base[-40:-8]) + 900
    for offset in range(8):
        base[-8 + offset] = high_anchor - offset * 180
    frame = _frame_from_prices(base)
    last_reversal_index = frame.index[-2:]
    frame.loc[last_reversal_index, "open"] = frame.loc[last_reversal_index, "close"] * 1.004
    frame.loc[last_reversal_index, "high"] = frame.loc[last_reversal_index, "open"] * 1.001
    frame.loc[last_reversal_index, "low"] = frame.loc[last_reversal_index, "close"] * 0.9997
    cfg = replace(_config(), min_reward_risk=0.8, trend_24h_floor=0.0, trend_6h_floor=-0.05)

    signal = score_btc_futures_setup(frame, cfg)

    assert signal is not None
    assert signal.side == "SHORT"
    assert signal.entry_signal == "BTC_REVERSAL_BREAKDOWN_SHORT"
    assert signal.metadata["btc_reversal_short"] == 1.0
    assert signal.sl_price > signal.entry_price
    assert signal.tp_price < signal.entry_price


def test_sei_breakaway_long_rejects_overextended_24h_trend(monkeypatch):
    monkeypatch.setenv("FUTURES_BREAKAWAY_ENABLED", "1")
    monkeypatch.setenv("FUTURES_BREAKAWAY_SYMBOLS", "SEI_USDT")
    monkeypatch.setenv("FUTURES_BREAKAWAY_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_BREAKAWAY_TRIGGER_VOLUME_FLOOR", "0.10")
    monkeypatch.setenv("FUTURES_BREAKAWAY_WINDOW_VOLUME_FLOOR", "0.10")
    monkeypatch.setenv("FUTURES_BREAKAWAY_MIN_MOVE_ATR", "0.50")
    monkeypatch.setenv("FUTURES_BREAKAWAY_MIN_MOVE_PCT", "0.004")
    monkeypatch.setenv("FUTURES_BREAKAWAY_RSI_1H_LONG_MIN", "0")
    monkeypatch.setenv("FUTURES_BREAKAWAY_RSI_15_LONG_MIN", "0")
    monkeypatch.setenv("FUTURES_BREAKAWAY_RSI_15_LONG_MAX", "100")
    monkeypatch.setenv("FUTURES_BREAKAWAY_MAX_EMA_EXTENSION_ATR", "10")
    monkeypatch.setenv("FUTURES_CONTINUATION_ENABLED", "false")
    monkeypatch.setenv("FUTURES_IMPULSE_CONTINUATION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ENABLED", "0")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_EVENT_CATALYST_ENABLED", "0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    base = [0.050 + idx * 0.000012 + math.sin(idx / 7.0) * 0.00018 for idx in range(520)]
    for offset in range(12):
        base[-12 + offset] = base[-13] * (1.0 + 0.008 * (offset + 1))
    frame = _frame_from_prices(base)
    frame["open"] = frame["close"] * 0.997
    frame["high"] = frame["close"] * 1.002
    frame["low"] = frame["open"] * 0.998
    cfg = replace(_config(), symbol="SEI_USDT", min_confidence_score=70.0, trend_24h_floor=0.0, min_reward_risk=0.8)

    assert score_btc_futures_setup(frame, cfg) is None

    monkeypatch.setenv("FUTURES_SEIUSDT_BREAKAWAY_LONG_MAX_TREND_24H", "0.20")
    signal = score_btc_futures_setup(frame, cfg)

    assert signal is not None
    assert signal.side == "LONG"
    assert signal.entry_signal == "MOMENTUM_BREAKAWAY_LONG"


def test_strategy_produces_tao_range_expansion_long(monkeypatch):
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_ENABLED", "1")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_SYMBOLS", "TAO_USDT")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_MIN_TREND_24H", "0.012")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_VOLUME_FLOOR", "0.50")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_ADX_MIN", "0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    base = [100 + idx * 0.018 + math.sin(idx / 5.0) * 0.9 for idx in range(520)]
    anchor = base[-30]
    for offset in range(29):
        base[-29 + offset] = anchor + math.sin(offset / 2.0) * 2.0 + offset * 0.20
    base[-1] = max(base[-29:-1]) + 0.25
    frame = _frame_from_prices(base)

    signal = score_btc_futures_setup(frame, replace(_config(), symbol="TAO_USDT", min_reward_risk=0.8))

    assert signal is not None
    assert signal.side == "LONG"
    assert signal.entry_signal == "RANGE_EXPANSION_CONTINUATION_LONG"
    assert signal.metadata["range_expansion"] == 1.0


def test_strategy_produces_tao_range_expansion_short(monkeypatch):
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_ENABLED", "1")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_SYMBOLS", "TAO_USDT")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_MIN_TREND_24H", "0.012")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_VOLUME_FLOOR", "0.50")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_ADX_MIN", "0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    base = [160 - idx * 0.018 + math.sin(idx / 5.0) * 0.9 for idx in range(520)]
    anchor = base[-30]
    for offset in range(29):
        base[-29 + offset] = anchor - math.sin(offset / 2.0) * 2.0 - offset * 0.20
    base[-1] = min(base[-29:-1]) - 0.25
    frame = _frame_from_prices(base)

    signal = score_btc_futures_setup(frame, replace(_config(), symbol="TAO_USDT", min_reward_risk=0.8))

    assert signal is not None
    assert signal.side == "SHORT"
    assert signal.entry_signal == "RANGE_EXPANSION_CONTINUATION_SHORT"
    assert signal.metadata["range_expansion"] == 1.0


def test_strategy_produces_level_break_long_for_non_btc_pair(monkeypatch):
    monkeypatch.setenv("FUTURES_MAJOR_THRESHOLD_ENABLED", "0")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_ENABLED", "1")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_SYMBOLS", "ETH_USDT")
    monkeypatch.setenv("FUTURES_ETHUSDT_LEVEL_BREAK_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_ETHUSDT_LEVEL_BREAK_VOLUME_FLOOR", "0.20")
    monkeypatch.setenv("FUTURES_ETHUSDT_LEVEL_BREAK_MIN_BREAK_ATR", "0.20")
    monkeypatch.setenv("FUTURES_ETHUSDT_LEVEL_BREAK_MIN_BREAK_PCT", "0.002")
    monkeypatch.setenv("FUTURES_ETHUSDT_LEVEL_BREAK_RSI_15_LONG_MAX", "100")
    monkeypatch.setenv("FUTURES_ETHUSDT_LEVEL_BREAK_MAX_EMA_EXTENSION_ATR", "8.0")
    monkeypatch.setenv("FUTURES_IMPULSE_CONTINUATION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BREAKAWAY_ENABLED", "0")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_ENABLED", "0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    base = [2500 + idx * 0.65 + math.sin(idx / 7.0) * 8 for idx in range(520)]
    prior_level = 2925.0
    for offset in range(100):
        base[-104 + offset] = prior_level - 45.0 + math.sin(offset / 4.0) * 10.0
    base[-4:] = [2934.0, 2941.0, 2948.0, 2955.0]
    frame = _frame_from_prices(base)

    signal = score_btc_futures_setup(
        frame,
        replace(_config(), symbol="ETH_USDT", min_confidence_score=58.0, consolidation_max_range_pct=0.001, min_reward_risk=0.8),
    )

    assert signal is not None
    assert signal.side == "LONG"
    assert signal.entry_signal == "LEVEL_BREAK_LONG"
    assert signal.metadata["level_break"] == 1.0
    assert signal.metadata["level_break_level"] > 0
    assert signal.metadata["level_break_move_pct"] > 0


def test_strategy_produces_level_break_short_for_non_btc_pair(monkeypatch):
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_ENABLED", "1")
    monkeypatch.setenv("FUTURES_LEVEL_BREAK_SYMBOLS", "BNB_USDT")
    monkeypatch.setenv("FUTURES_BNBUSDT_LEVEL_BREAK_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_BNBUSDT_LEVEL_BREAK_VOLUME_FLOOR", "0.20")
    monkeypatch.setenv("FUTURES_BNBUSDT_LEVEL_BREAK_MIN_BREAK_ATR", "0.20")
    monkeypatch.setenv("FUTURES_BNBUSDT_LEVEL_BREAK_MIN_BREAK_PCT", "0.002")
    monkeypatch.setenv("FUTURES_BNBUSDT_LEVEL_BREAK_RSI_15_SHORT_MIN", "0")
    monkeypatch.setenv("FUTURES_BNBUSDT_LEVEL_BREAK_MAX_EMA_EXTENSION_ATR", "8.0")
    monkeypatch.setenv("FUTURES_IMPULSE_CONTINUATION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BREAKAWAY_ENABLED", "0")
    monkeypatch.setenv("FUTURES_RANGE_EXPANSION_ENABLED", "0")
    monkeypatch.setenv("FUTURES_BREAKOUT_HOLD_ENABLED", "0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    base = [720 - idx * 0.12 + math.sin(idx / 8.0) * 2.5 for idx in range(520)]
    prior_level = 650.0
    for offset in range(100):
        base[-104 + offset] = prior_level + 18.0 + math.sin(offset / 4.0) * 4.0
    base[-4:] = [646.0, 642.0, 638.0, 634.0]
    frame = _frame_from_prices(base)

    signal = score_btc_futures_setup(
        frame,
        replace(_config(), symbol="BNB_USDT", min_confidence_score=58.0, consolidation_max_range_pct=0.001, min_reward_risk=0.8),
    )

    assert signal is not None
    assert signal.side == "SHORT"
    assert signal.entry_signal == "LEVEL_BREAK_SHORT"
    assert signal.metadata["level_break"] == 1.0
    assert signal.metadata["level_break_level"] > 0
    assert signal.metadata["level_break_move_pct"] > 0


def test_side_specific_threshold_relief_is_directional(monkeypatch):
    monkeypatch.setenv("FUTURES_IMPULSE_CONTINUATION_ENABLED", "1")
    monkeypatch.setenv("FUTURES_IMPULSE_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_IMPULSE_MIN_MOVE_ATR", "0.50")
    monkeypatch.setenv("FUTURES_IMPULSE_MIN_MOVE_PCT", "0.006")
    monkeypatch.setenv("FUTURES_IMPULSE_VOLUME_FLOOR", "0.50")
    monkeypatch.setenv("FUTURES_IMPULSE_RSI_15_SHORT_MIN", "0")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    base = [100000 + math.sin(idx / 6.0) * 35 + math.cos(idx / 13.0) * 25 for idx in range(520)]
    anchor = base[-10]
    for offset in range(9):
        base[-9 + offset] = anchor * (1.0 - 0.0011 * (offset + 1))
    frame = _frame_from_prices(base)
    cfg = replace(_config(), min_confidence_score=80.0, trend_24h_floor=0.05, trend_6h_floor=0.02)

    assert score_btc_futures_setup(frame, cfg, long_threshold_offset=-8.0) is None
    signal = score_btc_futures_setup(frame, cfg, short_threshold_offset=-8.0)

    assert signal is not None
    assert signal.side == "SHORT"


def test_event_catalyst_creates_long_candidate_with_market_penalty(monkeypatch):
    monkeypatch.setenv("FUTURES_EVENT_CATALYST_ENABLED", "1")
    monkeypatch.setenv("FUTURES_EVENT_CATALYST_MIN_MOVE_ATR", "0.10")
    monkeypatch.setenv("FUTURES_EVENT_CATALYST_ADX_MIN", "0")
    monkeypatch.setenv("FUTURES_EVENT_CATALYST_VOLUME_FLOOR", "0.50")
    monkeypatch.setenv("FUTURES_EVENT_CATALYST_RSI_15_LONG_MAX", "100")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    base = [100000 + math.sin(idx / 7.0) * 80 - idx * 1.2 for idx in range(520)]
    anchor = base[-10]
    for offset in range(9):
        base[-9 + offset] = anchor * (1.0 + 0.0008 * (offset + 1))
    frame = _frame_from_prices(base)
    cfg = replace(_config(), min_confidence_score=52.0, trend_24h_floor=0.08, trend_6h_floor=0.04)

    signal = score_btc_futures_setup(
        frame,
        cfg,
        event_bias_score=0.95,
        event_max_severity=1.0,
        event_count=1,
    )

    assert signal is not None
    assert signal.side == "LONG"
    assert signal.entry_signal == "EVENT_CATALYST_LONG"
    assert signal.metadata["event_catalyst"] == 1.0
    assert signal.metadata["market_gate_penalty"] > 0


def test_signal_includes_shadow_net_rr_metadata_by_default(monkeypatch):
    monkeypatch.setenv("FUTURES_COST_BUDGET_MODE", "shadow")
    monkeypatch.setenv("FUTURES_BTCUSDT_DISABLED_ENTRY_SIGNALS", "none")
    monkeypatch.setenv("USE_COST_BUDGET_RR", "0")
    base = [90000 + idx * 12 + math.sin(idx / 5.0) * 38 + math.cos(idx / 11.0) * 22 + ((idx % 5) - 2) * 14 for idx in range(520)]
    base[-20:-1] = [base[-21] + ((idx % 4) - 1) * 15 for idx in range(19)]
    base[-1] = max(base[-20:-1]) + 220
    frame = _frame_from_prices(base)

    signal = score_btc_futures_setup(frame, _config())

    assert signal is not None
    assert signal.metadata["cost_budget_mode"] == "shadow"
    assert signal.metadata["gross_rr"] > 0
    assert signal.metadata["net_rr"] > 0
    assert "fee_bps" in signal.metadata


def test_impulse_rejection_diagnostic_contains_actionable_fields():
    frame = _frame_from_prices([100000 + math.sin(idx / 6.0) * 35 for idx in range(520)])

    reason = diagnose_impulse_rejection(frame, _config())

    assert reason.startswith("impulse_gate_block")
    assert "move_pct=" in reason
    assert "volume_ratio=" in reason
    assert "ema_extension_atr=" in reason