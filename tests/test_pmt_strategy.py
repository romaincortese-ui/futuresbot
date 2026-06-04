from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd

from futuresbot.backtest import FuturesBacktestEngine
from futuresbot.exits import evaluate_profit_lock_bar
from futuresbot.models import FuturesPosition
from futuresbot.pmt_strategy import (
    DEFAULT_PMT_PROFILES,
    ELIGIBLE_PMT_SYMBOLS,
    classify_pair_market_trend,
    mental_threshold_step,
    pmt_win_cooldown_exit_reason,
    pmt_symbol_allowed,
    score_pmt_threshold_signal,
)


def _frame(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range(datetime(2026, 6, 1, tzinfo=timezone.utc), periods=len(closes), freq="15min")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [price * 1.001 for price in closes],
            "low": [price * 0.999 for price in closes],
            "close": closes,
            "volume": [1000.0 for _ in closes[:-1]] + [1400.0],
        },
        index=index,
    )


def _config(symbol: str = "BTC_USDT") -> SimpleNamespace:
    return SimpleNamespace(symbol=symbol, min_confidence_score=70.0, leverage_min=15, leverage_max=25)


def _enable_pmt(monkeypatch, *, min_score: str = "70") -> None:
    for name in (
        "FUTURES_BTCUSDT_PMT_THRESHOLD_STEP",
        "FUTURES_ETHUSDT_PMT_THRESHOLD_STEP",
        "FUTURES_SOLUSDT_PMT_THRESHOLD_STEP",
        "FUTURES_BNBUSDT_PMT_THRESHOLD_STEP",
        "FUTURES_SEIUSDT_PMT_THRESHOLD_STEP",
        "FUTURES_ZECUSDT_PMT_THRESHOLD_STEP",
        "FUTURES_PMT_MIN_LEVERAGE",
        "FUTURES_PMT_MAX_LEVERAGE",
        "FUTURES_LEVERAGE_MIN",
        "FUTURES_LEVERAGE_MAX",
        "FUTURES_PMT_PROFIT_LOCK_TRIGGER_PCT",
        "FUTURES_PMT_PROFIT_LOCK_GIVEBACK_PCT",
        "FUTURES_PMT_PROFIT_LOCK_PULLBACK_FRACTION",
        "FUTURES_PMT_PROFIT_LOCK_EXIT_MIN_NET_PCT",
        "MEXC_PERP_DEFAULT_TAKER_FEE_RATE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FUTURES_STRATEGY_MODE", "pmt_threshold")
    monkeypatch.setenv("FUTURES_PMT_SYMBOLS", ",".join(ELIGIBLE_PMT_SYMBOLS))
    monkeypatch.setenv("FUTURES_PMT_MIN_SCORE", min_score)
    monkeypatch.setenv("FUTURES_PMT_PROFIT_LOCK_MIN_TP_PROGRESS", "0.0")


def test_pmt_defaults_allow_only_six_eligible_pairs(monkeypatch):
    monkeypatch.delenv("FUTURES_PMT_SYMBOLS", raising=False)

    assert all(pmt_symbol_allowed(symbol) for symbol in ELIGIBLE_PMT_SYMBOLS)
    assert pmt_symbol_allowed("DOGE_USDT") is False
    assert pmt_symbol_allowed("XRP_USDT") is False

    monkeypatch.setenv("FUTURES_PMT_SYMBOLS", "*")
    assert all(pmt_symbol_allowed(symbol) for symbol in ELIGIBLE_PMT_SYMBOLS)
    assert pmt_symbol_allowed("DOGE_USDT") is False


def test_pmt_win_cooldown_includes_peak_profit_lock():
    assert pmt_win_cooldown_exit_reason("TAKE_PROFIT") is True
    assert pmt_win_cooldown_exit_reason("PEAK_PROFIT_LOCK") is True
    assert pmt_win_cooldown_exit_reason("STOP_LOSS") is False


def test_each_eligible_pair_has_unique_pmt_and_mental_thresholds():
    assert tuple(DEFAULT_PMT_PROFILES) == ELIGIBLE_PMT_SYMBOLS

    mental_steps = [profile.threshold_step for profile in DEFAULT_PMT_PROFILES.values()]
    pmt_thresholds = [
        (profile.flat_24h_pct, profile.flash_6h_pct, profile.mega_12h_pct, profile.mega_24h_pct)
        for profile in DEFAULT_PMT_PROFILES.values()
    ]

    assert len(set(mental_steps)) == len(ELIGIBLE_PMT_SYMBOLS)
    assert len(set(pmt_thresholds)) == len(ELIGIBLE_PMT_SYMBOLS)


def test_pmt_mega_bullish_breakout_scores_long_for_each_eligible_pair(monkeypatch):
    _enable_pmt(monkeypatch)
    levels = {
        "BTC_USDT": 75000.0,
        "ETH_USDT": 1850.0,
        "SOL_USDT": 80.0,
        "BNB_USDT": 675.0,
        "SEI_USDT": 0.07,
        "ZEC_USDT": 600.0,
    }

    for symbol in ELIGIBLE_PMT_SYMBOLS:
        profile = DEFAULT_PMT_PROFILES[symbol]
        level = levels[symbol]
        step = mental_threshold_step(symbol)
        current = level + step * 0.12
        previous = level - step * 0.10
        start = current / (1.0 + profile.mega_12h_pct * 1.2)
        frame = _frame([start] * 105 + [previous, current])

        pmt = classify_pair_market_trend(frame, symbol)
        signal = score_pmt_threshold_signal(frame, _config(symbol))

        assert pmt is not None, symbol
        assert pmt.label == "MEGA_BULLISH", symbol
        assert signal is not None, symbol
        assert signal.side == "LONG", symbol
        assert signal.entry_signal == "PMT_THRESHOLD_LONG", symbol
        assert signal.metadata["mental_threshold_level"] == level
        assert signal.metadata["pmt_label"] == "MEGA_BULLISH"


def test_pmt_flat_threshold_breakdown_scores_short(monkeypatch):
    _enable_pmt(monkeypatch)
    frame = _frame([75100.0] * 110 + [75100.0, 74940.0])

    pmt = classify_pair_market_trend(frame, "BTC_USDT")
    signal = score_pmt_threshold_signal(frame, _config())

    assert pmt is not None
    assert pmt.label == "FLAT"
    assert signal is not None
    assert signal.side == "SHORT"
    assert signal.entry_signal == "PMT_THRESHOLD_SHORT"
    assert signal.metadata["mental_threshold_level"] == 75000.0


def test_pmt_mega_bearish_blocks_countertrend_long(monkeypatch):
    _enable_pmt(monkeypatch)
    frame = _frame([78000.0] * 105 + [74960.0, 75100.0])

    pmt = classify_pair_market_trend(frame, "BTC_USDT")
    signal = score_pmt_threshold_signal(frame, _config())

    assert pmt is not None
    assert pmt.label == "MEGA_BEARISH"
    assert signal is None


def test_pmt_mega_bearish_breakdown_targets_200pct_margin(monkeypatch):
    _enable_pmt(monkeypatch)
    frame = _frame([78000.0] * 105 + [75080.0, 74940.0])

    signal = score_pmt_threshold_signal(frame, _config())

    assert signal is not None
    assert signal.side == "SHORT"
    assert signal.leverage == 25
    assert signal.metadata["pmt_label"] == "MEGA_BEARISH"
    assert signal.metadata["tp_margin_pct"] == 200.0
    assert signal.metadata["sl_margin_pct"] <= 16.0
    assert signal.metadata["profit_lock_trigger_pct_override"] == 20.0
    assert signal.metadata["profit_lock_giveback_pct_override"] == 0.0
    assert signal.metadata["profit_lock_pullback_fraction_override"] == 0.70
    assert signal.metadata["profit_lock_min_tp_progress_override"] == 0.0
    assert signal.metadata["profit_lock_exit_min_net_pct_override"] == 20.0
    assert signal.tp_price == signal.entry_price * (1.0 - 2.0 / signal.leverage)
    assert signal.sl_price <= signal.entry_price * (1.0 + 0.16 / signal.leverage)


def test_pmt_backtest_contract_sizing_uses_full_balance(monkeypatch):
    _enable_pmt(monkeypatch)
    engine = object.__new__(FuturesBacktestEngine)
    engine.config = SimpleNamespace(margin_budget_usdt=75.0, leverage_min=15, leverage_max=50, min_confidence_score=70.0)
    engine.contract_size = 0.0001
    engine.min_vol = 1

    contracts, used_margin, leverage = engine._contracts_for_entry(
        entry_price=100.0,
        leverage=50,
        balance=123.45,
        sl_price=100.4,
        score=95.0,
    )

    assert contracts == 617250
    assert used_margin == 123.45
    assert leverage == 50


def test_profit_lock_fixed_giveback_exits_one_point_from_peak():
    position = FuturesPosition(
        symbol="BTC_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=50,
        contract_size=1.0,
        leverage=50,
        margin_usdt=100.0,
        tp_price=104.0,
        sl_price=99.6,
        position_id="pmt-test",
        order_id="pmt-test",
        opened_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        score=95.0,
        certainty=0.95,
        entry_signal="PMT_THRESHOLD_LONG",
        metadata={},
    )

    first_exit, changed = evaluate_profit_lock_bar(
        position,
        high=100.22,
        low=100.21,
        taker_fee_rate=0.0,
        trigger_pct=10.0,
        pullback_fraction=0.20,
        floor_pct=0.0,
        giveback_pct=1.0,
    )
    second_exit, _changed = evaluate_profit_lock_bar(
        position,
        high=100.22,
        low=100.19,
        taker_fee_rate=0.0,
        trigger_pct=10.0,
        pullback_fraction=0.20,
        floor_pct=0.0,
        giveback_pct=1.0,
    )

    assert first_exit is None
    assert changed
    assert second_exit == (100.2, "PEAK_PROFIT_LOCK")


def test_pmt_profit_lock_arms_above_20pct_without_tp_progress():
    position = FuturesPosition(
        symbol="ETH_USDT",
        side="SHORT",
        entry_price=100.0,
        contracts=50,
        contract_size=1.0,
        leverage=50,
        margin_usdt=100.0,
        tp_price=96.0,
        sl_price=100.28,
        position_id="pmt-eth-lock-test",
        order_id="pmt-eth-lock-test",
        opened_at=datetime(2026, 6, 3, 20, 49, tzinfo=timezone.utc),
        score=100.0,
        certainty=0.99,
        entry_signal="PMT_THRESHOLD_SHORT",
        metadata={
            "profit_lock_trigger_pct_override": 20.0,
            "profit_lock_giveback_pct_override": 0.0,
            "profit_lock_pullback_fraction_override": 0.70,
            "profit_lock_min_tp_progress_override": 0.0,
            "profit_lock_exit_min_net_pct_override": 20.0,
            "profit_lock_floor_pct_override": 0.0,
        },
    )

    early_peak_exit, changed = evaluate_profit_lock_bar(
        position,
        high=99.7,
        low=99.56,
        taker_fee_rate=0.0,
        trigger_pct=10.0,
        pullback_fraction=0.20,
        floor_pct=0.0,
        giveback_pct=1.0,
        min_tp_progress=0.95,
    )
    assert early_peak_exit is None
    assert changed
    assert round(position.metadata["profit_lock_stop_gross_pnl_pct"], 3) == 6.6

    below_min_net_exit, _changed = evaluate_profit_lock_bar(
        position,
        high=99.7,
        low=99.56,
        taker_fee_rate=0.0,
        trigger_pct=10.0,
        pullback_fraction=0.20,
        floor_pct=0.0,
        giveback_pct=1.0,
        min_tp_progress=0.95,
    )
    runner_peak_exit, _changed = evaluate_profit_lock_bar(
        position,
        high=98.7,
        low=98.616,
        taker_fee_rate=0.0,
        trigger_pct=10.0,
        pullback_fraction=0.20,
        floor_pct=0.0,
        giveback_pct=1.0,
        min_tp_progress=0.95,
    )
    final_exit, _changed = evaluate_profit_lock_bar(
        position,
        high=99.6,
        low=98.616,
        taker_fee_rate=0.0,
        trigger_pct=10.0,
        pullback_fraction=0.20,
        floor_pct=0.0,
        giveback_pct=1.0,
        min_tp_progress=0.95,
    )

    assert below_min_net_exit is None
    assert runner_peak_exit is None
    assert round(position.metadata["profit_lock_peak_gross_pnl_pct"], 3) == 69.2
    assert round(position.metadata["profit_lock_stop_gross_pnl_pct"], 3) == 20.76
    assert final_exit == (99.5848, "PEAK_PROFIT_LOCK")