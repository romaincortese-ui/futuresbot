from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from futuresbot.config import DEFAULT_FUTURES_SYMBOLS, FuturesConfig
from futuresbot.exits import evaluate_adverse_peak_trail_bar, evaluate_micro_lock_bar, evaluate_no_progress_loss_exit, evaluate_profit_lock_bar, evaluate_trailing_bar, trailing_stop_price
from futuresbot.marketdata import MexcApiError
from futuresbot.models import FuturesPosition, FuturesSignal
from futuresbot.runtime import FuturesRuntime


@pytest.fixture(autouse=True)
def _clear_pmt_strategy_env(monkeypatch):
    for name in (
        "FUTURES_STRATEGY_MODE",
        "FUTURES_PMT_STRATEGY_ENABLED",
        "FUTURES_PMT_SYMBOLS",
        "FUTURES_PMT_MIN_SCORE",
        "FUTURES_PMT_MIN_LEVERAGE",
        "FUTURES_PMT_MAX_LEVERAGE",
        "FUTURES_PMT_MENTAL_THRESHOLD_STEPS",
        "FUTURES_PMT_PROFIT_LOCK_TRIGGER_PCT",
        "FUTURES_PMT_PROFIT_LOCK_GIVEBACK_PCT",
        "FUTURES_PMT_PROFIT_LOCK_PULLBACK_FRACTION",
        "FUTURES_PMT_PROFIT_LOCK_MIN_TP_PROGRESS",
        "FUTURES_PMT_PROFIT_LOCK_EXIT_MIN_NET_PCT",
        "FUTURES_PMT_TP_COOLDOWN_HOURS",
        "FUTURES_SYMBOLS",
        "FUTURES_BACKTEST_SYMBOLS",
        "FUTURES_FULL_BALANCE_SIZING_ENABLED",
        "FUTURES_FULL_BALANCE_RISK_PCT",
        "FUTURES_LEVERAGE_MIN",
        "FUTURES_LEVERAGE_MAX",
        "FUTURES_ENTRY_MIN_SCORE",
        "FUTURES_ENTRY_LEVERAGE_MIN",
        "FUTURES_ENTRY_LEVERAGE_HIGH",
        "FUTURES_RESUME_ON_BOOT",
        "USE_NAV_RISK_SIZING",
        "USE_FUTURES_PROFIT_LOCK",
        "FUTURES_PROFIT_LOCK_TRIGGER_PCT",
        "FUTURES_PROFIT_LOCK_GIVEBACK_PCT",
        "FUTURES_PROFIT_LOCK_FLOOR_PCT",
        "FUTURES_PROFIT_LOCK_MIN_TP_PROGRESS",
        "FUTURES_PROFIT_LOCK_EXIT_MIN_NET_PCT",
        "FUTURES_MICRO_LOCK_ENABLED",
        "FUTURES_ADVERSE_PEAK_TRAIL_ENABLED",
        "FUTURES_NO_PROGRESS_EXIT_ENABLED",
        "FUTURES_STAGNATION_EXIT_ENABLED",
        "FUTURES_TRAILING_EXIT_DRAWDOWN_PCT",
        "MEXC_PERP_DEFAULT_TAKER_FEE_RATE",
        "MEXC_PERP_FEE_TIER_VERIFIED",
        "USE_DRAWDOWN_KILL",
        "IGNORE_HALT",
        "FUTURES_ALLOW_LIVE_HALT_OVERRIDE",
        "DRAWDOWN_SOFT_PCT",
        "DRAWDOWN_HALT_PCT",
    ):
        monkeypatch.delenv(name, raising=False)


class StubClient:
    def __init__(self) -> None:
        prices = [90000 + idx * 10 for idx in range(100)]
        index = pd.date_range("2026-04-14", periods=len(prices), freq="15min", tz="UTC")
        self.frame = pd.DataFrame(
            {
                "open": prices,
                "high": [price * 1.001 for price in prices],
                "low": [price * 0.999 for price in prices],
                "close": prices,
                "volume": [1000 + idx for idx in range(len(prices))],
            },
            index=index,
        )

    def get_klines(self, symbol: str, *, interval: str = "Min15", start: int | None = None, end: int | None = None) -> pd.DataFrame:
        return self.frame

    def get_ticker(self, symbol: str) -> dict[str, str]:
        return {"priceChangePercent": "5.25", "lastPrice": "91000"}

    def get_fair_price(self, symbol: str) -> float:
        return 91000.0

    def get_account_asset(self, currency: str = "USDT") -> dict[str, str]:
        return {"availableBalance": "123.45", "equity": "150.50"}

    def get_updates(self, *, offset: int | None = None, limit: int = 5, timeout: int = 0):
        return []

    def close_position(
        self,
        *,
        symbol: str,
        side: int,
        vol: int,
        leverage: int,
        open_type: int = 1,
        position_mode: int = 2,
        position_id: str | int | None = None,
    ):
        return {"orderId": "close-1"}

    def get_order(self, order_id: str) -> dict[str, str]:
        return {"dealAvgPrice": "91234.5"}

    def cancel_all_tpsl(self, *, position_id: str | None = None, symbol: str | None = None):
        return {"success": True}


class FundedStubClient(StubClient):
    def get_account_asset(self, currency: str = "USDT") -> dict[str, str]:
        return {"availableBalance": "201.4589", "equity": "201.4589"}


def _config(tmp_path) -> FuturesConfig:
    return replace(
        FuturesConfig.from_env(),
        runtime_state_file=str(tmp_path / "futures_state.json"),
        status_file=str(tmp_path / "futures_status.json"),
        telegram_token="",
        telegram_chat_id="",
    )


def test_resume_on_boot_env_clears_persisted_pause(tmp_path, monkeypatch):
    (tmp_path / "futures_state.json").write_text(json.dumps({"paused": True}), encoding="utf-8")
    monkeypatch.setenv("FUTURES_RESUME_ON_BOOT", "1")

    runtime = FuturesRuntime(_config(tmp_path), StubClient())

    assert runtime._paused is False
    assert any("Boot: entries resumed by FUTURES_RESUME_ON_BOOT" in item for item in runtime._recent_activity)


def test_pmt_scan_symbols_ignore_overlay_candidates(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_STRATEGY_MODE", "pmt_threshold")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    runtime._sharp_event_overlay_symbols_for_cycle = lambda: ("XRP_USDT", "DOGE_USDT")

    assert runtime._scan_symbols_for_cycle() == tuple(runtime._active_symbols)


def test_pmt_validation_keeps_eligible_symbol_on_detail_rate_limit(tmp_path, monkeypatch):
    class RateLimitedDetailClient(StubClient):
        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            if symbol == "BNB_USDT":
                raise RuntimeError("rate limit")
            return {"maxLeverage": "100"}

    monkeypatch.setenv("FUTURES_STRATEGY_MODE", "pmt_threshold")
    config = replace(_config(tmp_path), symbols=("BTC_USDT", "BNB_USDT"))
    runtime = FuturesRuntime(config, RateLimitedDetailClient())

    runtime._validate_symbols()

    assert runtime._active_symbols == ("BTC_USDT", "BNB_USDT")


def test_crypto_event_policy_reduces_live_signal_size_and_leverage(tmp_path):
    config = replace(_config(tmp_path), leverage_min=1, leverage_max=20)
    runtime = FuturesRuntime(config, StubClient())
    now = datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc)
    signal = FuturesSignal(
        symbol="BTC_USDT",
        side="LONG",
        score=90.0,
        certainty=0.9,
        entry_price=90000.0,
        tp_price=93000.0,
        sl_price=88500.0,
        leverage=10,
        entry_signal="BREAKOUT_HOLD_LONG",
        metadata={},
    )
    state = {
        "generated_at": now.isoformat(),
        "ttl_seconds": 1800,
        "market_risk_score": 0.70,
    }

    adjusted = runtime._apply_crypto_event_overlay(signal, state, now)

    assert adjusted is not None
    assert adjusted.leverage == 7
    assert adjusted.metadata["crypto_event_size_multiplier"] == 0.65
    assert adjusted.metadata["crypto_event_leverage_multiplier"] == 0.70
    assert "market" in adjusted.metadata["crypto_event_policy_reasons"]


def test_drop_incomplete_klines_removes_still_forming_15m_bar():
    index = pd.DatetimeIndex(
        [
            datetime(2026, 5, 6, 13, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 6, 13, 15, tzinfo=timezone.utc),
        ]
    )
    frame = pd.DataFrame(
        {
            "open": [82000.0, 82070.0],
            "high": [82100.0, 82131.3],
            "low": [81900.0, 81838.5],
            "close": [82070.0, 82102.1],
            "volume": [1000.0, 500.0],
        },
        index=index,
    )

    cleaned = FuturesRuntime._drop_incomplete_klines(
        frame,
        interval_seconds=900,
        now_ts=datetime(2026, 5, 6, 13, 18, tzinfo=timezone.utc).timestamp(),
    )
    completed = FuturesRuntime._drop_incomplete_klines(
        frame,
        interval_seconds=900,
        now_ts=datetime(2026, 5, 6, 13, 30, tzinfo=timezone.utc).timestamp(),
    )

    assert list(cleaned.index) == [index[0]]
    assert float(cleaned["close"].iloc[-1]) == 82070.0
    assert len(completed) == 2


def test_breakout_hold_long_can_bypass_vol_shock_with_cost_and_shelf_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv("REGIME_ALLOW_BREAKOUT_HOLD_VOL_SHOCK", "1")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    classification = SimpleNamespace(
        label="VOL_SHOCK",
        allow_coil_breakout=False,
        allow_mean_reversion=False,
        allow_long=False,
        allow_short=False,
        reason="realised_vol_pct=98.1>=shock(90.0)",
        realised_vol_pct=98.1,
    )
    signal = FuturesSignal(
        symbol="BTC_USDT",
        side="LONG",
        score=83.45,
        certainty=0.9,
        entry_price=80356.5,
        tp_price=83733.03,
        sl_price=78691.81,
        leverage=12,
        entry_signal="BREAKOUT_HOLD_LONG",
        metadata={
            "breakout_hold": 1.0,
            "breakout_hold_shelf_volume_ratio": 1.699,
            "cost_budget_pass": 1.0,
        },
    )

    assert not runtime._regime_allows(classification, "LONG", "coil_breakout")
    assert runtime._regime_breakout_hold_override(classification, signal)


def test_breakout_hold_vol_shock_override_requires_cost_budget_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("REGIME_ALLOW_BREAKOUT_HOLD_VOL_SHOCK", "1")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    classification = SimpleNamespace(label="VOL_SHOCK", realised_vol_pct=98.1)
    signal = FuturesSignal(
        symbol="BTC_USDT",
        side="LONG",
        score=83.45,
        certainty=0.9,
        entry_price=80356.5,
        tp_price=83733.03,
        sl_price=78691.81,
        leverage=12,
        entry_signal="BREAKOUT_HOLD_LONG",
        metadata={
            "breakout_hold": 1.0,
            "breakout_hold_shelf_volume_ratio": 1.699,
            "cost_budget_pass": 0.0,
        },
    )

    assert not runtime._regime_breakout_hold_override(classification, signal)


def test_level_break_can_bypass_vol_shock_with_cost_score_and_volume(tmp_path, monkeypatch):
    monkeypatch.setenv("REGIME_ALLOW_LEVEL_BREAK_VOL_SHOCK", "1")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    classification = SimpleNamespace(
        label="VOL_SHOCK",
        allow_coil_breakout=False,
        allow_mean_reversion=False,
        allow_long=False,
        allow_short=False,
        reason="realised_vol_pct=97.5>=shock(90.0)",
        realised_vol_pct=97.5,
    )
    signal = FuturesSignal(
        symbol="TAO_USDT",
        side="SHORT",
        score=101.4,
        certainty=0.9,
        entry_price=345.0,
        tp_price=331.0,
        sl_price=352.0,
        leverage=8,
        entry_signal="LEVEL_BREAK_SHORT",
        metadata={
            "level_break": 1.0,
            "level_break_volume_ratio": 1.12,
            "level_break_confirm_close_ratio": 1.0,
            "cost_budget_pass": 1.0,
        },
    )

    assert not runtime._regime_allows(classification, "SHORT", "coil_breakout")
    assert runtime._regime_level_break_override(classification, signal)


def test_level_break_vol_shock_override_requires_confirmed_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("REGIME_ALLOW_LEVEL_BREAK_VOL_SHOCK", "1")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    classification = SimpleNamespace(label="VOL_SHOCK", realised_vol_pct=97.5)
    signal = FuturesSignal(
        symbol="TAO_USDT",
        side="SHORT",
        score=101.4,
        certainty=0.9,
        entry_price=345.0,
        tp_price=331.0,
        sl_price=352.0,
        leverage=8,
        entry_signal="LEVEL_BREAK_SHORT",
        metadata={
            "level_break": 1.0,
            "level_break_volume_ratio": 0.2,
            "level_break_confirm_close_ratio": 1.0,
            "cost_budget_pass": 1.0,
        },
    )

    assert not runtime._regime_level_break_override(classification, signal)


def test_build_status_message_includes_signal_context_and_btc_trends(tmp_path):
    runtime = FuturesRuntime(replace(_config(tmp_path), paper_trade=False), StubClient())

    message = runtime._build_status_message(
        price=91000.0,
        signal={
            "side": "LONG",
            "entry_signal": "COIL_BREAKOUT_LONG",
            "leverage": 32,
            "score": 63.5,
            "certainty": 0.78,
        },
    )

    assert "BTC: 1h" in message
    assert "Scanning <b>6</b> futures pairs (production pruned universe)" in message
    assert "Signal: <b>LONG</b> COIL_BREAKOUT_LONG | x32 | score 63.5 | cert 78%" in message
    assert "Avail: <b>$123.45</b> | Equity: <b>$150.50</b> | Trades: <b>0</b>" in message


def test_status_message_flags_custom_symbol_override(tmp_path):
    runtime = FuturesRuntime(
        replace(_config(tmp_path), symbols=("BTC_USDT", "ETH_USDT"), symbol="BTC_USDT"),
        StubClient(),
    )
    runtime._active_symbols = ("BTC_USDT", "ETH_USDT")

    message = runtime._build_status_message(price=91000.0)

    assert "Scanning <b>2</b> futures pairs (custom override; production default is 6 pairs)" in message


def test_build_status_message_includes_open_position_pnl_and_last_trade(tmp_path):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    runtime.open_position = FuturesPosition(
        symbol="BTC_USDT",
        side="LONG",
        entry_price=90000.0,
        contracts=1,
        contract_size=0.01,
        leverage=25,
        margin_usdt=36.0,
        tp_price=93000.0,
        sl_price=88800.0,
        position_id="paper",
        order_id="paper",
        opened_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        score=65.0,
        certainty=0.8,
        entry_signal="COIL_BREAKOUT_LONG",
    )
    runtime.trade_history.append({"symbol": "BTC_USDT", "exit_reason": "TAKE_PROFIT", "pnl_usdt": 24.5, "pnl_pct": 8.1})

    message = runtime._build_status_message(price=91500.0)

    assert "<b>LONG</b> BTC_USDT x25 | COIL_BREAKOUT_LONG | margin <b>$36.00</b>" in message
    assert "PnL: <b>$+15.00</b> (+41.67% of margin) | TP 50%" in message
    assert "Risk at SL: <b>$12.00</b> (33.33% of margin)" in message
    assert "Last: <b>BTC_USDT</b> Take profit | <b>$+24.50</b> (+8.10% of margin)" in message


def test_status_message_ignores_stale_reference_price_for_tiny_position(tmp_path):
    class TinyPriceClient(StubClient):
        def get_fair_price(self, symbol: str) -> float:
            if symbol == "PEPE_USDT":
                return 0.0000040117
            return 80337.40

    runtime = FuturesRuntime(_config(tmp_path), TinyPriceClient())
    runtime.open_position = FuturesPosition(
        symbol="PEPE_USDT",
        side="LONG",
        entry_price=0.0000040663,
        contracts=1,
        contract_size=10_000_000.0,
        leverage=5,
        margin_usdt=8.1529315,
        tp_price=0.0000043,
        sl_price=0.0000039,
        position_id="pos-pepe",
        order_id="entry-pepe",
        opened_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
        score=79.2,
        certainty=0.38,
        entry_signal="MOMENTUM_BREAKAWAY_LONG",
    )

    message = runtime._build_status_message(price=80337.40)

    assert "Mark <b>$0.00000401</b>" in message
    assert "PnL: <b>$-0.55</b>" in message
    assert "80337.40" not in message


def test_cycle_summary_uses_active_position_mark_for_tiny_position(tmp_path, caplog):
    class TinyPriceClient(StubClient):
        def get_fair_price(self, symbol: str) -> float:
            if symbol == "PEPE_USDT":
                return 0.0000040117
            return 80337.40

    runtime = FuturesRuntime(_config(tmp_path), TinyPriceClient())
    runtime.open_position = FuturesPosition(
        symbol="PEPE_USDT",
        side="LONG",
        entry_price=0.0000040663,
        contracts=1,
        contract_size=10_000_000.0,
        leverage=5,
        margin_usdt=8.1529315,
        tp_price=0.0000043,
        sl_price=0.0000039,
        position_id="pos-pepe",
        order_id="entry-pepe",
        opened_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
        score=79.2,
        certainty=0.38,
        entry_signal="MOMENTUM_BREAKAWAY_LONG",
    )

    with caplog.at_level(logging.INFO, logger="futuresbot.runtime"):
        runtime._log_cycle_summary(price=80337.40, signal=None)

    line = next(record.message for record in caplog.records if "Futures cycle: open_position" in record.message)
    assert "symbol=PEPE_USDT" in line
    assert "price=0.00000401" in line
    assert "pnl_usdt=-0.55" in line
    assert "80337.40" not in line


def test_force_close_position_closes_paper_trade_and_records_history(tmp_path):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    runtime.open_position = FuturesPosition(
        symbol="BTC_USDT",
        side="LONG",
        entry_price=90000.0,
        contracts=1,
        contract_size=0.01,
        leverage=25,
        margin_usdt=36.0,
        tp_price=93000.0,
        sl_price=88800.0,
        position_id="paper",
        order_id="paper",
        opened_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        score=65.0,
        certainty=0.8,
        entry_signal="COIL_BREAKOUT_LONG",
    )

    ok, message = runtime._force_close_position(reason="MANUAL_CLOSE")

    assert ok is True
    assert "Closed paper LONG BTC_USDT" in message
    assert runtime.open_position is None
    assert runtime.trade_history[-1]["exit_reason"] == "MANUAL_CLOSE"
    assert any("Manual close" in line for line in runtime._recent_activity)


def test_hourly_live_exit_uses_exchange_mode_and_position_id(tmp_path):
    class ModeAwareCloseClient(StubClient):
        def __init__(self) -> None:
            super().__init__()
            self.close_calls: list[dict[str, object]] = []

        def get_position_mode(self):
            return {"success": True, "data": {"positionMode": 1}}

        def close_position(self, **kwargs):
            self.close_calls.append(dict(kwargs))
            return {"orderId": "close-live-1"}

    cfg = replace(
        _config(tmp_path),
        paper_trade=False,
        early_exit_tp_progress=0.5,
        early_exit_min_profit_pct=0.005,
        trailing_exit_drawdown_pct=0.0,
    )
    client = ModeAwareCloseClient()
    runtime = FuturesRuntime(cfg, client)
    position = FuturesPosition(
        symbol="BNB_USDT",
        side="LONG",
        entry_price=90000.0,
        contracts=3,
        contract_size=0.01,
        leverage=5,
        margin_usdt=54.0,
        tp_price=91050.0,
        sl_price=88800.0,
        position_id="987654321",
        order_id="entry-live-1",
        opened_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        score=65.0,
        certainty=0.8,
        entry_signal="MOMENTUM_BREAKAWAY_LONG",
    )
    runtime._register_position(position)

    assert runtime._hourly_exit(position, current_price=91000.0) is True

    assert client.close_calls[-1]["position_mode"] == 1
    assert client.close_calls[-1]["position_id"] == "987654321"
    assert client.close_calls[-1]["side"] == 4
    assert runtime.open_position is None


def test_hourly_exit_arms_and_closes_trailing_take_profit(tmp_path):
    cfg = replace(
        _config(tmp_path),
        trailing_exit_drawdown_pct=0.02,
        trailing_exit_activation_progress=1.0,
        early_exit_min_profit_pct=0.01,
    )
    runtime = FuturesRuntime(cfg, StubClient())
    position = FuturesPosition(
        symbol="BTC_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=10,
        contract_size=0.1,
        leverage=20,
        margin_usdt=5.0,
        tp_price=110.0,
        sl_price=96.0,
        position_id="paper-trail-1",
        order_id="entry-trail-1",
        opened_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        score=70.0,
        certainty=0.8,
        entry_signal="MOMENTUM_BREAKAWAY_LONG",
    )
    runtime._register_position(position)

    assert runtime._hourly_exit(position, current_price=110.0) is False
    assert runtime.open_position is position
    assert position.metadata["trailing_exit_armed"] is True
    assert trailing_stop_price(position, 0.02) == 107.8

    assert runtime._hourly_exit(position, current_price=112.0) is False
    assert round(trailing_stop_price(position, 0.02), 2) == 109.76

    assert runtime._hourly_exit(position, current_price=109.5) is True
    assert runtime.open_position is None
    assert runtime.trade_history[-1]["exit_reason"] == "TRAILING_TAKE_PROFIT"
    assert runtime.trade_history[-1]["exit_price"] == 109.5


def test_profit_lock_closes_after_peak_pullback(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_FUTURES_PROFIT_LOCK", "1")
    monkeypatch.setenv("FUTURES_MID_PROFIT_LOCK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_ALLOWED_LANES", "SOL_USDT:IMPULSE_EVENT_CONTINUATION_LONG")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_TRIGGER_PCT", "20")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_PULLBACK_FRACTION", "0.35")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_FLOOR_PCT", "5")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    position = FuturesPosition(
        symbol="ZEC_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=10,
        contract_size=0.1,
        leverage=20,
        margin_usdt=10.0,
        tp_price=112.0,
        sl_price=96.0,
        position_id="paper-profit-lock",
        order_id="entry-profit-lock",
        opened_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
        score=72.0,
        certainty=0.8,
        entry_signal="IMPULSE_EVENT_CONTINUATION_LONG",
    )
    runtime._register_position(position)

    assert runtime._hourly_exit(position, current_price=104.0) is False
    assert round(position.metadata["profit_lock_peak_gross_pnl_pct"], 3) == 40.000
    assert round(position.metadata["profit_lock_peak_pnl_pct"], 3) == 38.368
    assert round(position.metadata["profit_lock_stop_gross_pnl_pct"], 3) == 26.000
    assert round(position.metadata["profit_lock_stop_pnl_pct"], 3) == 24.939

    assert runtime._hourly_exit(position, current_price=102.5) is True
    assert runtime.open_position is None
    assert runtime.trade_history[-1]["exit_reason"] == "PEAK_PROFIT_LOCK"
    assert runtime.trade_history[-1]["pnl_usdt"] > 0


def test_profit_lock_uses_gross_peak_trigger_with_net_exit_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_FUTURES_PROFIT_LOCK", "1")
    monkeypatch.setenv("FUTURES_MID_PROFIT_LOCK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_ALLOWED_LANES", "BTC_USDT:COIL_BREAKOUT_LONG")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_TRIGGER_PCT", "5")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_PULLBACK_FRACTION", "0.35")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_FLOOR_PCT", "2")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    position = FuturesPosition(
        symbol="SEI_USDT",
        side="SHORT",
        entry_price=100.0,
        contracts=12,
        contract_size=0.1,
        leverage=12,
        margin_usdt=10.0,
        tp_price=94.5,
        sl_price=102.5,
        position_id="paper-profit-lock-gross",
        order_id="entry-profit-lock-gross",
        opened_at=datetime(2026, 5, 19, tzinfo=timezone.utc),
        score=85.0,
        certainty=0.8,
        entry_signal="TREND_CONTINUATION_SHORT",
    )
    runtime._register_position(position)

    assert runtime._hourly_exit(position, current_price=99.5) is False
    assert round(position.metadata["profit_lock_peak_gross_pnl_pct"], 3) == 6.000
    assert round(position.metadata["profit_lock_peak_pnl_pct"], 3) == 4.085
    assert round(position.metadata["profit_lock_stop_gross_pnl_pct"], 3) == 3.900
    assert round(position.metadata["profit_lock_stop_pnl_pct"], 3) == 2.655

    assert runtime._hourly_exit(position, current_price=99.68) is True
    assert runtime.open_position is None
    assert runtime.trade_history[-1]["exit_reason"] == "PEAK_PROFIT_LOCK"
    assert runtime.trade_history[-1]["pnl_usdt"] > 0


def test_stagnation_exit_flattens_late_chase_retrace(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_FUTURES_PROFIT_LOCK", "0")
    monkeypatch.setenv("FUTURES_MICRO_LOCK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_STAGNATION_EXIT_ENABLED", "1")
    monkeypatch.setenv("FUTURES_STAGNATION_EXIT_MINUTES", "180")
    monkeypatch.setenv("FUTURES_STAGNATION_EXIT_MAX_PEAK_TP_PROGRESS", "0.35")
    monkeypatch.setenv("FUTURES_STAGNATION_EXIT_MIN_PEAK_TP_PROGRESS", "0.10")
    monkeypatch.setenv("FUTURES_STAGNATION_EXIT_RETRACE_FRACTION", "0.65")
    monkeypatch.setenv("FUTURES_STAGNATION_EXIT_MIN_NET_PNL_PCT", "-2.5")
    monkeypatch.setenv("FUTURES_ADVERSE_PEAK_TRAIL_ENABLED", "0")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    opened_at = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    position = FuturesPosition(
        symbol="SEI_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=10,
        contract_size=0.1,
        leverage=8,
        margin_usdt=10.0,
        tp_price=120.0,
        sl_price=96.0,
        position_id="paper-stagnation",
        order_id="entry-stagnation",
        opened_at=opened_at,
        score=66.0,
        certainty=0.7,
        entry_signal="IMPULSE_EVENT_CONTINUATION_LONG",
        metadata={"late_impulse_chase_watch": 1.0},
    )
    runtime._register_position(position)

    assert runtime._hourly_exit(position, current_price=104.0, now=datetime(2026, 5, 21, 14, 0, tzinfo=timezone.utc)) is False

    assert runtime._hourly_exit(position, current_price=100.8, now=datetime(2026, 5, 21, 14, 15, tzinfo=timezone.utc)) is True
    assert runtime.open_position is None
    assert runtime.trade_history[-1]["exit_reason"] == "STAGNATION_EXIT"


def test_stagnation_exit_ignores_breakout_hold_retrace(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_FUTURES_PROFIT_LOCK", "0")
    monkeypatch.setenv("FUTURES_MICRO_LOCK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_STAGNATION_EXIT_ENABLED", "1")
    monkeypatch.setenv("FUTURES_STAGNATION_EXIT_MINUTES", "180")
    monkeypatch.setenv("FUTURES_ADVERSE_PEAK_TRAIL_ENABLED", "0")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    opened_at = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
    position = FuturesPosition(
        symbol="BTC_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=10,
        contract_size=0.1,
        leverage=8,
        margin_usdt=10.0,
        tp_price=120.0,
        sl_price=96.0,
        position_id="paper-breakout-stagnation",
        order_id="entry-breakout-stagnation",
        opened_at=opened_at,
        score=82.0,
        certainty=0.7,
        entry_signal="BREAKOUT_HOLD_LONG",
        metadata={"late_impulse_chase_watch": 1.0},
    )
    runtime._register_position(position)

    assert runtime._hourly_exit(position, current_price=104.0, now=datetime(2026, 5, 21, 14, 0, tzinfo=timezone.utc)) is False
    assert runtime._hourly_exit(position, current_price=100.8, now=datetime(2026, 5, 21, 14, 15, tzinfo=timezone.utc)) is False
    assert runtime.open_position is position


def test_adverse_peak_trail_flattens_small_peak_reversal(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_FUTURES_PROFIT_LOCK", "0")
    monkeypatch.setenv("FUTURES_MICRO_LOCK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_STAGNATION_EXIT_ENABLED", "0")
    monkeypatch.setenv("FUTURES_ADVERSE_PEAK_TRAIL_ENABLED", "1")
    monkeypatch.setenv("FUTURES_ADVERSE_PEAK_TRAIL_TRIGGER_PCT", "0.25")
    monkeypatch.setenv("FUTURES_ADVERSE_PEAK_TRAIL_GIVEBACK_PCT", "1.25")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    position = FuturesPosition(
        symbol="SEI_USDT",
        side="SHORT",
        entry_price=100.0,
        contracts=10,
        contract_size=1.0,
        leverage=8,
        margin_usdt=100.0,
        tp_price=95.0,
        sl_price=103.0,
        position_id="paper-adverse-peak",
        order_id="entry-adverse-peak",
        opened_at=datetime(2026, 5, 24, 14, 19, tzinfo=timezone.utc),
        score=79.0,
        certainty=0.95,
        entry_signal="IMPULSE_EVENT_CONTINUATION_SHORT",
    )
    runtime._register_position(position)

    assert runtime._hourly_exit(position, current_price=99.95, now=datetime(2026, 5, 24, 14, 20, tzinfo=timezone.utc)) is False
    assert round(position.metadata["adverse_peak_trail_peak_gross_pnl_pct"], 3) == 0.5
    assert round(position.metadata["adverse_peak_trail_stop_gross_pnl_pct"], 3) == -0.75

    assert runtime._hourly_exit(position, current_price=100.10, now=datetime(2026, 5, 24, 14, 24, tzinfo=timezone.utc)) is True
    assert runtime.open_position is None
    assert runtime.trade_history[-1]["exit_reason"] == "ADVERSE_PEAK_TRAIL"
    assert runtime.trade_history[-1]["pnl_usdt"] < 0


def test_adverse_peak_trail_bar_waits_until_after_activation_bar():
    position = FuturesPosition(
        symbol="SEI_USDT",
        side="SHORT",
        entry_price=100.0,
        contracts=10,
        contract_size=1.0,
        leverage=8,
        margin_usdt=100.0,
        tp_price=95.0,
        sl_price=103.0,
        position_id="paper-adverse-peak-bar",
        order_id="entry-adverse-peak-bar",
        opened_at=datetime(2026, 5, 24, 14, 19, tzinfo=timezone.utc),
        score=79.0,
        certainty=0.95,
        entry_signal="IMPULSE_EVENT_CONTINUATION_SHORT",
    )

    exit_signal, changed = evaluate_adverse_peak_trail_bar(
        position,
        high=100.20,
        low=99.95,
        trigger_pct=0.25,
        giveback_pct=1.25,
    )
    assert exit_signal is None
    assert changed is True

    exit_signal, changed = evaluate_adverse_peak_trail_bar(
        position,
        high=100.10,
        low=100.0,
        trigger_pct=0.25,
        giveback_pct=1.25,
    )
    assert changed is False
    assert exit_signal == (100.075, "ADVERSE_PEAK_TRAIL")


def test_adverse_peak_trail_ignores_moves_below_trigger():
    position = FuturesPosition(
        symbol="SEI_USDT",
        side="SHORT",
        entry_price=100.0,
        contracts=10,
        contract_size=1.0,
        leverage=8,
        margin_usdt=100.0,
        tp_price=95.0,
        sl_price=103.0,
        position_id="paper-adverse-peak-inactive",
        order_id="entry-adverse-peak-inactive",
        opened_at=datetime(2026, 5, 24, 14, 19, tzinfo=timezone.utc),
        score=79.0,
        certainty=0.95,
        entry_signal="IMPULSE_EVENT_CONTINUATION_SHORT",
    )

    exit_signal, changed = evaluate_adverse_peak_trail_bar(
        position,
        high=100.20,
        low=99.98,
        trigger_pct=0.25,
        giveback_pct=1.25,
    )
    assert exit_signal is None
    assert changed is True
    assert "adverse_peak_trail_stop_gross_pnl_pct" not in position.metadata


def test_no_progress_exit_closes_after_warmup_loss(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_FUTURES_PROFIT_LOCK", "0")
    monkeypatch.setenv("FUTURES_MICRO_LOCK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_ADVERSE_PEAK_TRAIL_ENABLED", "0")
    monkeypatch.setenv("FUTURES_STAGNATION_EXIT_ENABLED", "0")
    monkeypatch.setenv("FUTURES_NO_PROGRESS_EXIT_ENABLED", "1")
    monkeypatch.setenv("FUTURES_NO_PROGRESS_EXIT_MINUTES", "60")
    monkeypatch.setenv("FUTURES_NO_PROGRESS_EXIT_LOSS_PCT", "1.75")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    position = FuturesPosition(
        symbol="SEI_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=10,
        contract_size=1.0,
        leverage=8,
        margin_usdt=100.0,
        tp_price=105.0,
        sl_price=97.0,
        position_id="paper-no-progress",
        order_id="entry-no-progress",
        opened_at=datetime(2026, 5, 24, 14, 0, tzinfo=timezone.utc),
        score=79.0,
        certainty=0.95,
        entry_signal="IMPULSE_EVENT_CONTINUATION_LONG",
    )
    runtime._register_position(position)

    assert runtime._hourly_exit(position, current_price=99.80, now=datetime(2026, 5, 24, 14, 45, tzinfo=timezone.utc)) is False

    assert runtime._hourly_exit(position, current_price=99.80, now=datetime(2026, 5, 24, 15, 5, tzinfo=timezone.utc)) is True
    assert runtime.open_position is None
    assert runtime.trade_history[-1]["exit_reason"] == "NO_PROGRESS_LOSS_EXIT"
    assert runtime.trade_history[-1]["pnl_usdt"] < 0


def test_no_progress_exit_ignores_trade_with_favorable_spark():
    position = FuturesPosition(
        symbol="SEI_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=10,
        contract_size=1.0,
        leverage=8,
        margin_usdt=100.0,
        tp_price=105.0,
        sl_price=97.0,
        position_id="paper-no-progress-spark",
        order_id="entry-no-progress-spark",
        opened_at=datetime(2026, 5, 24, 14, 0, tzinfo=timezone.utc),
        score=79.0,
        certainty=0.95,
        entry_signal="IMPULSE_EVENT_CONTINUATION_LONG",
    )

    exit_signal, changed = evaluate_no_progress_loss_exit(
        position,
        100.03,
        now=datetime(2026, 5, 24, 14, 15, tzinfo=timezone.utc),
        activation_minutes=60,
        max_favorable_pct=0.25,
        loss_pct=1.75,
        tighten_after_minutes=180,
        tightened_loss_pct=0.75,
    )
    assert exit_signal is None
    assert changed is True
    assert round(position.metadata["no_progress_exit_peak_gross_pnl_pct"], 3) == 0.3

    exit_signal, changed = evaluate_no_progress_loss_exit(
        position,
        99.70,
        now=datetime(2026, 5, 24, 15, 30, tzinfo=timezone.utc),
        activation_minutes=60,
        max_favorable_pct=0.25,
        loss_pct=1.75,
        tighten_after_minutes=180,
        tightened_loss_pct=0.75,
    )
    assert exit_signal is None
    assert changed is False


def test_no_progress_exit_loss_limit_tightens_with_age():
    position = FuturesPosition(
        symbol="SEI_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=10,
        contract_size=1.0,
        leverage=8,
        margin_usdt=100.0,
        tp_price=105.0,
        sl_price=97.0,
        position_id="paper-no-progress-tighten",
        order_id="entry-no-progress-tighten",
        opened_at=datetime(2026, 5, 24, 14, 0, tzinfo=timezone.utc),
        score=79.0,
        certainty=0.95,
        entry_signal="IMPULSE_EVENT_CONTINUATION_LONG",
    )

    exit_signal, changed = evaluate_no_progress_loss_exit(
        position,
        99.90,
        now=datetime(2026, 5, 24, 15, 5, tzinfo=timezone.utc),
        activation_minutes=60,
        max_favorable_pct=0.25,
        loss_pct=1.75,
        tighten_after_minutes=180,
        tightened_loss_pct=0.75,
    )
    assert exit_signal is None
    assert changed is True

    exit_signal, changed = evaluate_no_progress_loss_exit(
        position,
        99.90,
        now=datetime(2026, 5, 24, 17, 5, tzinfo=timezone.utc),
        activation_minutes=60,
        max_favorable_pct=0.25,
        loss_pct=1.75,
        tighten_after_minutes=180,
        tightened_loss_pct=0.75,
    )
    assert changed is True
    assert exit_signal == (99.90, "NO_PROGRESS_LOSS_EXIT")
    assert round(position.metadata["no_progress_exit_loss_limit_gross_pnl_pct"], 3) == -0.75


def test_no_progress_exit_uses_stop_risk_cap_reason_for_oversized_loss(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_MAX_STOP_RISK_PCT_OF_MARGIN", "20")
    monkeypatch.setenv("FUTURES_NO_PROGRESS_EXIT_ENABLED", "1")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    position = FuturesPosition(
        symbol="BNB_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=1,
        contract_size=1.0,
        leverage=20,
        margin_usdt=100.0,
        tp_price=110.0,
        sl_price=80.0,
        position_id="paper-stop-risk-cap",
        order_id="entry-stop-risk-cap",
        opened_at=datetime(2026, 5, 24, 14, 0, tzinfo=timezone.utc),
        score=95.9,
        certainty=0.99,
        entry_signal="SIMPLE_TREND_LONG",
    )
    runtime._register_position(position)

    assert runtime._no_progress_loss_exit(position, current_price=73.0, now=datetime(2026, 5, 24, 15, 5, tzinfo=timezone.utc)) is True
    assert runtime.trade_history[-1]["exit_reason"] == "STOP_RISK_CAP_EXIT"


def test_breakeven_profit_lock_blocks_winner_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_FUTURES_PROFIT_LOCK", "1")
    monkeypatch.setenv("FUTURES_MID_PROFIT_LOCK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_ALLOWED_LANES", "SOL_USDT:IMPULSE_EVENT_CONTINUATION_LONG")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_TRIGGER_PCT", "50")
    monkeypatch.setenv("FUTURES_BREAKEVEN_ARM_PCT", "10")
    monkeypatch.setenv("FUTURES_BREAKEVEN_FLOOR_PCT", "3")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    position = FuturesPosition(
        symbol="ZEC_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=10,
        contract_size=0.1,
        leverage=20,
        margin_usdt=10.0,
        tp_price=112.0,
        sl_price=96.0,
        position_id="paper-breakeven-lock",
        order_id="entry-breakeven-lock",
        opened_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
        score=72.0,
        certainty=0.8,
        entry_signal="IMPULSE_EVENT_CONTINUATION_LONG",
    )
    runtime._register_position(position)

    assert runtime._hourly_exit(position, current_price=101.2) is False
    assert position.metadata["breakeven_profit_lock_armed"] is True

    assert runtime._hourly_exit(position, current_price=100.2) is True
    assert runtime.open_position is None
    assert runtime.trade_history[-1]["exit_reason"] == "BREAKEVEN_PROFIT_LOCK"
    assert runtime.trade_history[-1]["pnl_usdt"] > 0


def test_breakeven_profit_lock_exits_when_gap_erases_floor(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_FUTURES_PROFIT_LOCK", "1")
    monkeypatch.setenv("FUTURES_BREAKEVEN_FLOOR_PCT", "0.5")
    monkeypatch.setenv("FUTURES_BREAKEVEN_EXIT_SLIPPAGE_BUFFER_BPS", "3")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    position = FuturesPosition(
        symbol="ZEC_USDT",
        side="SHORT",
        entry_price=524.63,
        contracts=173,
        contract_size=0.01,
        leverage=12,
        margin_usdt=76.22137891,
        tp_price=498.52,
        sl_price=529.18,
        position_id="paper-net-breakeven-lock",
        order_id="entry-net-breakeven-lock",
        opened_at=datetime(2026, 5, 18, 13, 46, tzinfo=timezone.utc),
        score=67.1,
        certainty=0.55,
        entry_signal="EVENT_CATALYST_SHORT",
        metadata={"breakeven_profit_lock_armed": True},
    )
    runtime._register_position(position)

    assert runtime._hourly_exit(position, current_price=524.59) is True
    assert runtime.open_position is None
    assert runtime.trade_history[-1]["exit_reason"] == "BREAKEVEN_PROTECTION_GAP_EXIT"


def test_peak_protection_gap_exit_is_not_labeled_profit_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_FUTURES_PROFIT_LOCK", "1")
    monkeypatch.setenv("FUTURES_MID_PROFIT_LOCK_ENABLED", "0")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_ALLOWED_LANES", "SOL_USDT:IMPULSE_EVENT_CONTINUATION_LONG")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_TRIGGER_PCT", "4")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_PULLBACK_FRACTION", "0.35")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_FLOOR_PCT", "2")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)
    position = FuturesPosition(
        symbol="DASH_USDT",
        side="LONG",
        entry_price=48.24,
        contracts=911,
        contract_size=0.01,
        leverage=12,
        margin_usdt=36.88587838,
        tp_price=54.86,
        sl_price=46.80,
        position_id="paper-dash-gap",
        order_id="entry-dash-gap",
        opened_at=datetime(2026, 5, 20, 13, 2, tzinfo=timezone.utc),
        score=109.0,
        certainty=0.99,
        entry_signal="SHARP_EVENT_BREAKOUT_LONG",
    )
    runtime._register_position(position)

    assert runtime._hourly_exit(position, current_price=48.76) is False
    assert position.metadata["profit_lock_peak_gross_pnl_pct"] > 4.0

    assert runtime._hourly_exit(position, current_price=47.47) is True
    assert runtime.open_position is None
    assert runtime.trade_history[-1]["exit_reason"] == "PEAK_PROTECTION_GAP_EXIT"
    assert runtime.trade_history[-1]["pnl_usdt"] < 0
    assert "PROTECTION EXIT" in sent_messages[0]
    assert "PROFIT TAKEN" not in sent_messages[0]
    assert "Peak protection gap exit" in sent_messages[-1]


def test_open_position_guard_closes_near_peak_floor(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_FUTURES_PROFIT_LOCK", "1")
    monkeypatch.setenv("USE_LIQ_BUFFER_GUARD", "0")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_TRIGGER_PCT", "4")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_PULLBACK_FRACTION", "0.20")
    monkeypatch.setenv("FUTURES_PROFIT_LOCK_FLOOR_PCT", "2")

    class GuardClient(StubClient):
        def __init__(self) -> None:
            super().__init__()
            self.prices = [100.605, 100.48]

        def get_fair_price(self, symbol: str) -> float:
            return self.prices.pop(0)

    runtime = FuturesRuntime(_config(tmp_path), GuardClient())
    runtime.get_symbol_taker_fee_rate = lambda symbol: 0.0
    position = FuturesPosition(
        symbol="DASH_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=1,
        contract_size=1.0,
        leverage=12,
        margin_usdt=8.33333333,
        tp_price=112.0,
        sl_price=98.0,
        position_id="paper-dash-guard",
        order_id="entry-dash-guard",
        opened_at=datetime(2026, 5, 20, 13, 2, tzinfo=timezone.utc),
        score=104.1,
        certainty=0.99,
        entry_signal="SHARP_EVENT_BREAKOUT_LONG",
    )
    runtime._register_position(position)

    assert runtime._monitor_open_positions_once() is False
    assert round(position.metadata["profit_lock_peak_gross_pnl_pct"], 2) == 7.26
    assert round(position.metadata["profit_lock_stop_gross_pnl_pct"], 2) == 5.81

    assert runtime._monitor_open_positions_once() is True
    assert runtime.open_position is None
    assert runtime.trade_history[-1]["exit_reason"] == "PEAK_PROFIT_LOCK"
    assert runtime.trade_history[-1]["pnl_pct"] > 5.0


def test_trailing_bar_waits_until_after_activation_bar_to_exit():
    position = FuturesPosition(
        symbol="BCH_USDT",
        side="LONG",
        entry_price=454.99,
        contracts=16,
        contract_size=0.01,
        leverage=20,
        margin_usdt=14.6,
        tp_price=464.93,
        sl_price=450.54,
        position_id="backtest-trail-1",
        order_id="entry-trail-1",
        opened_at=datetime(2026, 5, 5, tzinfo=timezone.utc),
        score=70.0,
        certainty=0.8,
        entry_signal="MOMENTUM_BREAKAWAY_LONG",
    )

    first, changed = evaluate_trailing_bar(
        position,
        high=466.53,
        low=462.42,
        activation_progress=1.0,
        min_profit_pct=0.012,
        drawdown_pct=0.02,
    )
    assert first is None
    assert changed is True
    assert position.metadata["trailing_exit_armed"] is True

    second, _changed = evaluate_trailing_bar(
        position,
        high=488.91,
        low=469.70,
        activation_progress=1.0,
        min_profit_pct=0.012,
        drawdown_pct=0.02,
    )
    assert second == (488.91 * 0.98, "TRAILING_TAKE_PROFIT")


def test_profit_lock_bar_waits_until_after_activation_bar_to_exit():
    position = FuturesPosition(
        symbol="ZEC_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=100,
        contract_size=0.01,
        leverage=1,
        margin_usdt=100.0,
        tp_price=112.0,
        sl_price=96.0,
        position_id="backtest-profit-lock-1",
        order_id="entry-profit-lock-1",
        opened_at=datetime(2026, 5, 5, tzinfo=timezone.utc),
        score=70.0,
        certainty=0.8,
        entry_signal="IMPULSE_EVENT_CONTINUATION_LONG",
    )

    first, changed = evaluate_profit_lock_bar(
        position,
        high=104.5,
        low=102.0,
        taker_fee_rate=0.0,
        trigger_pct=4.0,
        pullback_fraction=0.35,
        floor_pct=2.0,
    )
    assert first is None
    assert changed is True
    assert round(position.metadata["profit_lock_peak_gross_pnl_pct"], 3) == 4.5
    assert round(position.metadata["profit_lock_stop_gross_pnl_pct"], 3) == 2.925

    second, _changed = evaluate_profit_lock_bar(
        position,
        high=104.4,
        low=102.8,
        taker_fee_rate=0.0,
        trigger_pct=4.0,
        pullback_fraction=0.35,
        floor_pct=2.0,
    )
    assert second is not None
    assert round(second[0], 3) == 102.925
    assert second[1] == "PEAK_PROFIT_LOCK"


def test_profit_lock_bar_tracks_runner_peak_after_steady_fade():
    position = FuturesPosition(
        symbol="ZEC_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=100,
        contract_size=0.01,
        leverage=1,
        margin_usdt=100.0,
        tp_price=118.0,
        sl_price=96.0,
        position_id="runner-peak-lock-1",
        order_id="entry-runner-peak-lock-1",
        opened_at=datetime(2026, 5, 5, tzinfo=timezone.utc),
        score=105.0,
        certainty=0.99,
        entry_signal="IMPULSE_EVENT_CONTINUATION_LONG",
        metadata={
            "winner_study_runner_candidate": 1.0,
            "profit_lock_trigger_pct_override": 4.0,
            "profit_lock_pullback_fraction_override": 0.15,
            "profit_lock_floor_pct_override": 2.0,
            "micro_profit_lock_trigger_pct_override": 99.0,
            "adverse_peak_trail_trigger_pct_override": 4.0,
            "adverse_peak_trail_pullback_fraction_override": 0.15,
        },
    )

    first, changed = evaluate_profit_lock_bar(
        position,
        high=110.0,
        low=108.5,
        taker_fee_rate=0.0,
        trigger_pct=99.0,
        pullback_fraction=0.95,
        floor_pct=0.0,
    )
    assert first is None
    assert changed is True
    assert round(position.metadata["profit_lock_stop_gross_pnl_pct"], 3) == 8.5

    second, _changed = evaluate_profit_lock_bar(
        position,
        high=109.5,
        low=107.5,
        taker_fee_rate=0.0,
        trigger_pct=99.0,
        pullback_fraction=0.95,
        floor_pct=0.0,
    )
    assert second == (108.5, "PEAK_PROFIT_LOCK")


def test_adverse_peak_trail_bar_tracks_runner_peak_after_steady_fade():
    position = FuturesPosition(
        symbol="ZEC_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=100,
        contract_size=0.01,
        leverage=1,
        margin_usdt=100.0,
        tp_price=118.0,
        sl_price=96.0,
        position_id="runner-adverse-peak-lock-1",
        order_id="entry-runner-adverse-peak-lock-1",
        opened_at=datetime(2026, 5, 5, tzinfo=timezone.utc),
        score=105.0,
        certainty=0.99,
        entry_signal="IMPULSE_EVENT_CONTINUATION_LONG",
        metadata={
            "winner_study_runner_candidate": 1.0,
            "micro_profit_lock_trigger_pct_override": 99.0,
            "adverse_peak_trail_trigger_pct_override": 4.0,
            "adverse_peak_trail_giveback_pct_override": 1.25,
            "adverse_peak_trail_pullback_fraction_override": 0.15,
        },
    )

    first, changed = evaluate_adverse_peak_trail_bar(
        position,
        high=110.0,
        low=108.5,
        trigger_pct=0.25,
        giveback_pct=1.25,
        pullback_fraction=0.45,
        max_loss_pct=2.0,
    )
    assert first is None
    assert changed is True
    assert round(position.metadata["adverse_peak_trail_stop_gross_pnl_pct"], 3) == 8.5

    second, _changed = evaluate_adverse_peak_trail_bar(
        position,
        high=109.5,
        low=107.5,
        trigger_pct=0.25,
        giveback_pct=1.25,
        pullback_fraction=0.45,
        max_loss_pct=2.0,
    )
    assert second == (108.5, "ADVERSE_PEAK_TRAIL")


def test_micro_lock_bar_protects_high_beta_alt_after_activation_bar():
    position = FuturesPosition(
        symbol="SEI_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=10,
        contract_size=0.1,
        leverage=10,
        margin_usdt=10.0,
        tp_price=120.0,
        sl_price=96.0,
        position_id="micro-lock-bar",
        order_id="entry-micro-lock-bar",
        opened_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        score=72.0,
        certainty=0.8,
        entry_signal="IMPULSE_EVENT_CONTINUATION_LONG",
    )

    first, changed = evaluate_micro_lock_bar(
        position,
        high=100.5,
        low=100.1,
        taker_fee_rate=0.0006,
        trigger_pct=2.0,
        pullback_fraction=0.45,
        floor_pct=0.65,
        min_exit_net_pct=0.05,
    )

    assert first is None
    assert changed is True
    assert round(position.metadata["micro_profit_lock_peak_gross_pnl_pct"], 3) == 5.0
    assert round(position.metadata["micro_profit_lock_stop_gross_pnl_pct"], 3) == 2.75

    second, _changed = evaluate_micro_lock_bar(
        position,
        high=100.52,
        low=100.2,
        taker_fee_rate=0.0006,
        trigger_pct=2.0,
        pullback_fraction=0.45,
        floor_pct=0.65,
        min_exit_net_pct=0.05,
    )

    assert second is not None
    assert round(second[0], 4) == 100.286
    assert second[1] == "MICRO_PROFIT_LOCK"


def test_micro_lock_bar_ignores_default_excluded_major():
    position = FuturesPosition(
        symbol="BTC_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=10,
        contract_size=0.1,
        leverage=10,
        margin_usdt=10.0,
        tp_price=120.0,
        sl_price=96.0,
        position_id="micro-lock-btc",
        order_id="entry-micro-lock-btc",
        opened_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        score=82.0,
        certainty=0.8,
        entry_signal="IMPULSE_EVENT_CONTINUATION_LONG",
        metadata={"atr_15m_pct": 0.02},
    )

    exit_result, changed = evaluate_micro_lock_bar(
        position,
        high=101.0,
        low=100.0,
        taker_fee_rate=0.0006,
        trigger_pct=2.0,
        pullback_fraction=0.45,
        floor_pct=0.65,
        min_exit_net_pct=0.05,
    )

    assert exit_result is None
    assert changed is False


def test_micro_lock_bar_protects_recovered_high_beta_alt():
    position = FuturesPosition(
        symbol="ZEC_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=10,
        contract_size=0.1,
        leverage=10,
        margin_usdt=10.0,
        tp_price=0.0,
        sl_price=0.0,
        position_id="micro-lock-recovered-zec",
        order_id="",
        opened_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        score=0.0,
        certainty=0.0,
        entry_signal="RECOVERED",
    )

    first, changed = evaluate_micro_lock_bar(
        position,
        high=100.5,
        low=100.1,
        taker_fee_rate=0.0006,
        trigger_pct=2.0,
        pullback_fraction=0.45,
        floor_pct=0.65,
        min_exit_net_pct=0.05,
    )

    assert first is None
    assert changed is True
    assert round(position.metadata["micro_profit_lock_peak_gross_pnl_pct"], 3) == 5.0

    second, _changed = evaluate_micro_lock_bar(
        position,
        high=100.52,
        low=100.2,
        taker_fee_rate=0.0006,
        trigger_pct=2.0,
        pullback_fraction=0.45,
        floor_pct=0.65,
        min_exit_net_pct=0.05,
    )

    assert second is not None
    assert second[1] == "MICRO_PROFIT_LOCK"


def test_micro_lock_bar_keeps_recovered_major_excluded():
    position = FuturesPosition(
        symbol="BTC_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=10,
        contract_size=0.1,
        leverage=10,
        margin_usdt=10.0,
        tp_price=0.0,
        sl_price=0.0,
        position_id="micro-lock-recovered-btc",
        order_id="",
        opened_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        score=0.0,
        certainty=0.0,
        entry_signal="RECOVERED",
    )

    exit_result, changed = evaluate_micro_lock_bar(
        position,
        high=101.0,
        low=100.0,
        taker_fee_rate=0.0006,
        trigger_pct=2.0,
        pullback_fraction=0.45,
        floor_pct=0.65,
        min_exit_net_pct=0.05,
    )

    assert exit_result is None
    assert changed is False


def test_micro_lock_bar_honors_position_overrides():
    position = FuturesPosition(
        symbol="SEI_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=10,
        contract_size=0.1,
        leverage=10,
        margin_usdt=10.0,
        tp_price=120.0,
        sl_price=96.0,
        position_id="micro-lock-overrides",
        order_id="entry-micro-lock-overrides",
        opened_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        score=72.0,
        certainty=0.8,
        entry_signal="IMPULSE_EVENT_CONTINUATION_LONG",
        metadata={
            "micro_profit_lock_trigger_pct_override": 1.0,
            "micro_profit_lock_floor_pct_override": 0.9,
            "micro_profit_lock_pullback_fraction_override": 0.25,
        },
    )

    first, changed = evaluate_micro_lock_bar(
        position,
        high=100.12,
        low=100.10,
        taker_fee_rate=0.0,
        trigger_pct=2.0,
        pullback_fraction=0.45,
        floor_pct=0.65,
        min_exit_net_pct=0.0,
    )

    assert first is None
    assert changed is True
    assert round(position.metadata["micro_profit_lock_stop_gross_pnl_pct"], 3) == 0.9

    second, _changed = evaluate_micro_lock_bar(
        position,
        high=100.13,
        low=100.08,
        taker_fee_rate=0.0,
        trigger_pct=2.0,
        pullback_fraction=0.45,
        floor_pct=0.65,
        min_exit_net_pct=0.0,
    )

    assert second is not None
    assert round(second[0], 4) == 100.0975
    assert second[1] == "MICRO_PROFIT_LOCK"


def test_micro_lock_bar_protects_trend_lane_by_default():
    position = FuturesPosition(
        symbol="SEI_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=10,
        contract_size=0.1,
        leverage=10,
        margin_usdt=10.0,
        tp_price=120.0,
        sl_price=96.0,
        position_id="micro-lock-trend",
        order_id="entry-micro-lock-trend",
        opened_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        score=72.0,
        certainty=0.8,
        entry_signal="TREND_CONTINUATION_LONG",
    )

    exit_result, changed = evaluate_micro_lock_bar(
        position,
        high=101.0,
        low=100.0,
        taker_fee_rate=0.0006,
        trigger_pct=2.0,
        pullback_fraction=0.45,
        floor_pct=0.65,
        min_exit_net_pct=0.05,
    )

    assert exit_result is None
    assert changed is True
    assert round(position.metadata["micro_profit_lock_peak_gross_pnl_pct"], 3) == 10.0
    assert round(position.metadata["micro_profit_lock_stop_gross_pnl_pct"], 3) == 5.5

    second, _changed = evaluate_micro_lock_bar(
        position,
        high=101.0,
        low=100.2,
        taker_fee_rate=0.0006,
        trigger_pct=2.0,
        pullback_fraction=0.45,
        floor_pct=0.65,
        min_exit_net_pct=0.05,
    )

    assert second is not None
    assert round(second[0], 4) == 100.55
    assert second[1] == "MICRO_PROFIT_LOCK"


def test_micro_lock_bar_protects_any_lane_even_with_old_env_lane_list():
    position = FuturesPosition(
        symbol="SEI_USDT",
        side="SHORT",
        entry_price=100.0,
        contracts=10,
        contract_size=0.1,
        leverage=10,
        margin_usdt=10.0,
        tp_price=92.0,
        sl_price=103.0,
        position_id="micro-lock-mean-reversion",
        order_id="entry-micro-lock-mean-reversion",
        opened_at=datetime(2026, 5, 22, 12, 20, tzinfo=timezone.utc),
        score=73.0,
        certainty=0.7,
        entry_signal="MEAN_REVERSION",
    )

    first, changed = evaluate_micro_lock_bar(
        position,
        high=99.8,
        low=99.5,
        taker_fee_rate=0.0006,
        trigger_pct=2.0,
        pullback_fraction=0.45,
        floor_pct=0.65,
        min_exit_net_pct=0.05,
        entry_signals="IMPULSE_EVENT_CONTINUATION_LONG,IMPULSE_EVENT_CONTINUATION_SHORT",
    )

    assert first is None
    assert changed is True
    assert round(position.metadata["micro_profit_lock_peak_gross_pnl_pct"], 3) == 5.0

    second, _changed = evaluate_micro_lock_bar(
        position,
        high=99.8,
        low=99.5,
        taker_fee_rate=0.0006,
        trigger_pct=2.0,
        pullback_fraction=0.45,
        floor_pct=0.65,
        min_exit_net_pct=0.05,
        entry_signals="IMPULSE_EVENT_CONTINUATION_LONG,IMPULSE_EVENT_CONTINUATION_SHORT",
    )

    assert second is not None
    assert round(second[0], 4) == 99.725
    assert second[1] == "MICRO_PROFIT_LOCK"


def test_micro_lock_protects_sharp_event_breakout_even_with_old_env_lane_list():
    position = FuturesPosition(
        symbol="INJ_USDT",
        side="LONG",
        entry_price=5.492,
        contracts=39,
        contract_size=1.0,
        leverage=5,
        margin_usdt=42.9661128,
        tp_price=6.08,
        sl_price=5.40,
        position_id="inj-sharp-event",
        order_id="entry-inj-sharp-event",
        opened_at=datetime(2026, 5, 22, 12, 20, tzinfo=timezone.utc),
        score=86.0,
        certainty=0.9,
        entry_signal="SHARP_EVENT_BREAKOUT_LONG",
        metadata={"sharp_event_synthetic_signal": 1.0},
    )

    first, changed = evaluate_micro_lock_bar(
        position,
        high=5.526,
        low=5.514,
        taker_fee_rate=0.0006,
        trigger_pct=2.0,
        pullback_fraction=0.45,
        floor_pct=0.65,
        min_exit_net_pct=0.05,
        entry_signals="IMPULSE_EVENT_CONTINUATION_LONG,IMPULSE_EVENT_CONTINUATION_SHORT",
    )

    assert first is None
    assert changed is True
    assert round(position.metadata["micro_profit_lock_peak_gross_pnl_pct"], 2) == 3.09
    assert round(position.metadata["micro_profit_lock_peak_pnl_pct"], 2) == 2.49
    assert position.metadata["micro_profit_lock_stop_gross_pnl_pct"] > 1.6

    second, _changed = evaluate_micro_lock_bar(
        position,
        high=5.526,
        low=5.500,
        taker_fee_rate=0.0006,
        trigger_pct=2.0,
        pullback_fraction=0.45,
        floor_pct=0.65,
        min_exit_net_pct=0.05,
        entry_signals="IMPULSE_EVENT_CONTINUATION_LONG,IMPULSE_EVENT_CONTINUATION_SHORT",
    )

    assert second is not None
    assert round(second[0], 4) == 5.5107
    assert second[1] == "MICRO_PROFIT_LOCK"


def test_one_way_close_side_uses_opposite_reduce_only_direction(tmp_path):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    long_position = FuturesPosition(
        symbol="BCH_USDT",
        side="LONG",
        entry_price=90000.0,
        contracts=3,
        contract_size=0.01,
        leverage=5,
        margin_usdt=54.0,
        tp_price=91050.0,
        sl_price=88800.0,
        position_id="long-1",
        order_id="entry-long-1",
        opened_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        score=65.0,
        certainty=0.8,
        entry_signal="MOMENTUM_BREAKAWAY_LONG",
    )
    short_position = replace(long_position, side="SHORT", position_id="short-1", order_id="entry-short-1")

    assert runtime._close_side(long_position, position_mode=1) == 4
    assert runtime._close_side(short_position, position_mode=1) == 2
    assert runtime._close_side(long_position, position_mode=2) == 3
    assert runtime._close_side(short_position, position_mode=2) == 1


def test_reconcile_clears_stale_live_position_with_missing_history(tmp_path):
    class NoExchangePositionClient(StubClient):
        def get_open_positions(self, symbol: str | None = None):
            return []

        def get_historical_positions(self, symbol: str | None = None, page_num: int = 1, page_size: int = 20):
            return []

    runtime = FuturesRuntime(replace(_config(tmp_path), paper_trade=False), NoExchangePositionClient())
    runtime._register_position(
        FuturesPosition(
            symbol="BNB_USDT",
            side="LONG",
            entry_price=90000.0,
            contracts=3,
            contract_size=0.01,
            leverage=5,
            margin_usdt=54.0,
            tp_price=91050.0,
            sl_price=88800.0,
            position_id="stale-123",
            order_id="entry-stale-1",
            opened_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
            score=65.0,
            certainty=0.8,
            entry_signal="MOMENTUM_BREAKAWAY_LONG",
        )
    )

    runtime._reconcile_closed_position()

    assert runtime.open_positions == {}
    assert runtime.trade_history == []
    assert any("Cleared stale local position" in line for line in runtime._recent_activity)


def test_build_pnl_message_includes_realized_and_open_pnl(tmp_path):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    runtime.open_position = FuturesPosition(
        symbol="BTC_USDT",
        side="LONG",
        entry_price=90000.0,
        contracts=1,
        contract_size=0.01,
        leverage=25,
        margin_usdt=36.0,
        tp_price=93000.0,
        sl_price=88800.0,
        position_id="paper",
        order_id="paper",
        opened_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        score=65.0,
        certainty=0.8,
        entry_signal="COIL_BREAKOUT_LONG",
    )
    runtime.trade_history.append({"symbol": "BTC_USDT", "exit_reason": "TAKE_PROFIT", "pnl_usdt": 24.5, "pnl_pct": 8.1, "exit_time": datetime.now(timezone.utc).isoformat()})

    message = runtime._build_pnl_message(price=91500.0)

    assert "💰 <b>Futures P&L</b>" in message
    assert "Today: <b>$+24.50</b> | Closed trades: <b>1</b>" in message
    assert "Session: <b>$+24.50</b> | 1W 0L" in message
    assert "Open P&L: <b>$+15.00</b>" in message


def test_build_logs_message_uses_recent_activity(tmp_path):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    runtime._record_activity("Loaded calibration")
    runtime._record_activity("Opened LONG BTC_USDT")

    message = runtime._build_logs_message()

    assert "🧾 <b>Recent Activity</b>" in message
    assert "Loaded calibration" in message
    assert "Opened LONG BTC_USDT" in message


def test_send_startup_message_uses_live_account_snapshot(tmp_path):
    runtime = FuturesRuntime(replace(_config(tmp_path), paper_trade=False, telegram_token="token", telegram_chat_id="1"), StubClient())
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    runtime._send_startup_message()

    assert len(sent_messages) == 1
    assert "Scanning <b>6</b> futures pairs (production pruned universe):" in sent_messages[0]
    assert "Active symbols differ" not in sent_messages[0]
    assert "Avail: <b>$123.45</b> | Equity: <b>$150.50</b>" in sent_messages[0]
    assert "Budget:" not in sent_messages[0]


def test_send_startup_message_warns_on_custom_symbol_override(tmp_path):
    runtime = FuturesRuntime(
        replace(
            _config(tmp_path),
            symbols=("BTC_USDT", "ETH_USDT"),
            symbol="BTC_USDT",
            telegram_token="token",
            telegram_chat_id="1",
        ),
        StubClient(),
    )
    runtime._active_symbols = ("BTC_USDT", "ETH_USDT")
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    runtime._send_startup_message()

    assert len(sent_messages) == 1
    assert "custom override; production default is 6 pairs" in sent_messages[0]
    assert "Active symbols differ from the production pruned default" in sent_messages[0]
    assert ", ".join(DEFAULT_FUTURES_SYMBOLS) in sent_messages[0]


def test_handle_telegram_commands_supports_status_and_close(tmp_path):
    runtime = FuturesRuntime(replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1"), StubClient())
    runtime.telegram.get_updates = lambda **kwargs: [
        {"update_id": 1, "message": {"chat": {"id": "1"}, "text": "/status"}},
        {"update_id": 2, "message": {"chat": {"id": "1"}, "text": "/close"}},
    ]
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)
    runtime.open_position = FuturesPosition(
        symbol="BTC_USDT",
        side="LONG",
        entry_price=90000.0,
        contracts=1,
        contract_size=0.01,
        leverage=25,
        margin_usdt=36.0,
        tp_price=93000.0,
        sl_price=88800.0,
        position_id="paper",
        order_id="paper",
        opened_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        score=65.0,
        certainty=0.8,
        entry_signal="COIL_BREAKOUT_LONG",
    )

    runtime._handle_telegram_commands()

    assert any("📋 <b>Status</b>" in message for message in sent_messages)
    assert any("🚨 <b>Futures Close</b>" in message for message in sent_messages)
    assert runtime.open_position is None


def test_handle_telegram_commands_supports_pnl_logs_and_pause_resume(tmp_path):
    runtime = FuturesRuntime(replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1"), StubClient())
    runtime.telegram.get_updates = lambda **kwargs: [
        {"update_id": 3, "message": {"chat": {"id": "1"}, "text": "/pnl"}},
        {"update_id": 4, "message": {"chat": {"id": "1"}, "text": "/logs"}},
        {"update_id": 5, "message": {"chat": {"id": "1"}, "text": "/pause"}},
        {"update_id": 6, "message": {"chat": {"id": "1"}, "text": "/resume"}},
    ]
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    runtime._handle_telegram_commands()

    assert any("💰 <b>Futures P&L</b>" in message for message in sent_messages)
    assert any("🧾 <b>Recent Activity</b>" in message for message in sent_messages)
    assert any("⏸️ <b>Futures entries paused.</b>" in message for message in sent_messages)
    assert any("▶️ <b>Futures entries resumed.</b>" in message for message in sent_messages)
    assert runtime._paused is False
    assert runtime._last_telegram_update == 6


def test_handle_telegram_commands_resume_is_idempotent_when_active(tmp_path):
    runtime = FuturesRuntime(replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1"), StubClient())
    runtime.telegram.get_updates = lambda **kwargs: [
        {"update_id": 7, "message": {"chat": {"id": "1"}, "text": "/resume"}},
    ]
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    runtime._handle_telegram_commands()

    assert sent_messages == []
    assert runtime._paused is False
    assert runtime._last_telegram_update == 7


def test_handle_telegram_commands_accepts_bot_suffix_and_persists_offset(tmp_path):
    config = replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1")
    runtime = FuturesRuntime(config, StubClient())
    runtime.telegram.get_updates = lambda **kwargs: [
        {"update_id": 42, "message": {"chat": {"id": "1"}, "text": "/status@FuturesHealthBot"}},
    ]
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    runtime._handle_telegram_commands()

    assert any("📋 <b>Status</b>" in message for message in sent_messages)
    assert runtime._last_telegram_update == 42

    reloaded = FuturesRuntime(config, StubClient())
    assert reloaded._last_telegram_update == 42


def test_handle_telegram_commands_confirms_processed_update_with_telegram(tmp_path):
    runtime = FuturesRuntime(replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1"), StubClient())
    calls: list[dict[str, object]] = []

    def fake_updates(**kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("offset") in (None, 0):
            return [{"update_id": 42, "message": {"chat": {"id": "1"}, "text": "/status"}}]
        return []

    runtime.telegram.get_updates = fake_updates
    runtime._notify = lambda message, parse_mode="HTML": None

    runtime._handle_telegram_commands()

    assert runtime._last_telegram_update == 42
    assert calls[-1]["offset"] == 43
    assert calls[-1]["limit"] == 1


def test_handle_telegram_commands_does_not_reprocess_duplicate_update(tmp_path):
    runtime = FuturesRuntime(replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1"), StubClient())

    def fake_updates(**kwargs):
        return [{"update_id": 42, "message": {"chat": {"id": "1"}, "text": "/status"}}]

    runtime.telegram.get_updates = fake_updates
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    runtime._handle_telegram_commands()
    runtime._handle_telegram_commands()

    assert sum("📋 <b>Status</b>" in message for message in sent_messages) == 1
    assert runtime._last_telegram_update == 42


def test_status_command_resets_heartbeat_timer(tmp_path, monkeypatch):
    config = replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1", heartbeat_seconds=300)
    runtime = FuturesRuntime(config, StubClient())
    runtime._last_heartbeat_at = 0.0
    runtime.telegram.get_updates = lambda **kwargs: [
        {"update_id": 43, "message": {"chat": {"id": "1"}, "text": "/status"}},
    ]
    runtime._notify = lambda message, parse_mode="HTML": None

    monkeypatch.setattr("futuresbot.runtime.time.time", lambda: 1_000.0)
    runtime._handle_telegram_commands()

    assert runtime._last_heartbeat_at == 1_000.0


def test_startup_telegram_sync_discards_stale_commands_without_processing(tmp_path):
    runtime = FuturesRuntime(replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1"), StubClient())
    runtime.open_position = _make_position("BTC_USDT")
    calls: list[dict[str, object]] = []

    def fake_updates(**kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("offset") == -1:
            return [{"update_id": 77, "message": {"chat": {"id": "1"}, "text": "/close"}}]
        return []

    runtime.telegram.get_updates = fake_updates
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    runtime._sync_telegram_update_offset_on_startup()

    assert runtime._last_telegram_update == 77
    assert calls[-1]["offset"] == 78
    assert runtime.open_position is not None
    assert sent_messages == []


def test_startup_telegram_sync_discards_stale_commands_even_with_saved_offset(tmp_path):
    runtime = FuturesRuntime(replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1"), StubClient())
    runtime._last_telegram_update = 40
    runtime._telegram_command_started_after_ts = 2_000.0
    calls: list[dict[str, object]] = []

    def fake_updates(**kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("offset") == -1:
            return [{"update_id": 77, "message": {"chat": {"id": "1"}, "text": "/status", "date": 1_000}}]
        return []

    runtime.telegram.get_updates = fake_updates
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    runtime._sync_telegram_update_offset_on_startup()

    assert runtime._last_telegram_update == 77
    assert calls[-1]["offset"] == 78
    assert sent_messages == []


def test_startup_telegram_sync_confirms_saved_offset(tmp_path):
    runtime = FuturesRuntime(replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1"), StubClient())
    runtime._last_telegram_update = 77
    calls: list[dict[str, object]] = []

    def fake_updates(**kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("offset") == -1:
            return [{"update_id": 77, "message": {"chat": {"id": "1"}, "text": "/status", "date": 1_000}}]
        return []

    runtime.telegram.get_updates = fake_updates

    runtime._sync_telegram_update_offset_on_startup()

    assert runtime._last_telegram_update == 77
    assert calls[-1]["offset"] == 78
    assert calls[-1]["limit"] == 1


def test_startup_telegram_sync_discards_fresh_preboot_command(tmp_path):
    runtime = FuturesRuntime(replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1"), StubClient())
    runtime._telegram_command_started_after_ts = 2_000.0
    calls: list[dict[str, object]] = []

    def fake_updates(**kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("offset") == -1:
            return [{"update_id": 78, "message": {"chat": {"id": "1"}, "text": "/status", "date": 2_001}}]
        return []

    runtime.telegram.get_updates = fake_updates
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    runtime._sync_telegram_update_offset_on_startup()

    assert runtime._last_telegram_update == 78
    assert calls[-1]["offset"] == 79
    assert sent_messages == []


def test_handle_telegram_commands_skips_stale_status_resume_pause_backlog(tmp_path):
    runtime = FuturesRuntime(replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1"), StubClient())
    runtime._paused = True
    runtime._telegram_command_started_after_ts = 2_000.0
    runtime.telegram.get_updates = lambda **kwargs: [
        {"update_id": 30, "message": {"chat": {"id": "1"}, "text": "/status", "date": 1_000}},
        {"update_id": 31, "message": {"chat": {"id": "1"}, "text": "/resume", "date": 1_001}},
        {"update_id": 32, "message": {"chat": {"id": "1"}, "text": "/pause", "date": 1_002}},
    ]
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    runtime._handle_telegram_commands()

    assert sent_messages == []
    assert runtime._paused is True
    assert runtime._last_telegram_update == 32


def test_handle_telegram_commands_drains_short_stale_batches(tmp_path):
    runtime = FuturesRuntime(replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1"), StubClient())
    runtime._telegram_command_started_after_ts = 2_000.0
    calls: list[dict[str, object]] = []

    def fake_updates(**kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("offset") is None:
            return [{"update_id": 40, "message": {"chat": {"id": "1"}, "text": "/status", "date": 1_000}}]
        if kwargs.get("offset") == 41:
            return [{"update_id": 41, "message": {"chat": {"id": "1"}, "text": "/pause", "date": 1_001}}]
        return []

    runtime.telegram.get_updates = fake_updates
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    runtime._handle_telegram_commands()

    assert sent_messages == []
    assert runtime._last_telegram_update == 41
    assert any(call.get("offset") == 41 for call in calls)
    assert calls[-1]["offset"] == 42


def test_handle_telegram_commands_force_syncs_when_stale_backlog_hits_cap(tmp_path, monkeypatch):
    import futuresbot.runtime as runtime_module

    monkeypatch.setattr(runtime_module, "TELEGRAM_COMMAND_MAX_BATCHES", 1)
    runtime = FuturesRuntime(replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1"), StubClient())
    runtime._telegram_command_started_after_ts = 2_000.0
    calls: list[dict[str, object]] = []

    def fake_updates(**kwargs):
        calls.append(dict(kwargs))
        offset = kwargs.get("offset")
        if offset is None:
            return [{"update_id": 40, "message": {"chat": {"id": "1"}, "text": "/status", "date": 1_000}}]
        if offset == -1:
            return [{"update_id": 99, "message": {"chat": {"id": "1"}, "text": "/pause", "date": 1_001}}]
        return []

    runtime.telegram.get_updates = fake_updates
    runtime._notify = lambda message, parse_mode="HTML": None

    runtime._handle_telegram_commands()

    assert runtime._last_telegram_update == 99
    assert any(call.get("offset") == -1 for call in calls)
    assert calls[-1]["offset"] == 100


def test_heartbeat_waits_for_interval_and_persists_timestamp(tmp_path, monkeypatch):
    config = replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1", heartbeat_seconds=21_600)
    runtime = FuturesRuntime(config, StubClient())
    runtime._last_heartbeat_at = 100.0
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    monkeypatch.setattr("futuresbot.runtime.time.time", lambda: 21_699.0)
    runtime._send_heartbeat(price=91_000.0, signal=None)

    assert sent_messages == []

    monkeypatch.setattr("futuresbot.runtime.time.time", lambda: 21_700.0)
    runtime._send_heartbeat(price=91_000.0, signal=None)

    assert len(sent_messages) == 1
    assert "💓 <b>Heartbeat</b>" in sent_messages[0]
    reloaded = FuturesRuntime(config, StubClient())
    assert reloaded._last_heartbeat_at == 21_700.0


def test_heartbeat_can_be_disabled_for_command_only_telegram(tmp_path, monkeypatch):
    config = replace(_config(tmp_path), telegram_token="token", telegram_chat_id="1", heartbeat_seconds=0)
    runtime = FuturesRuntime(config, StubClient())
    runtime._last_heartbeat_at = 0.0
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    monkeypatch.setattr("futuresbot.runtime.time.time", lambda: 10_000.0)
    runtime._send_heartbeat(price=91_000.0, signal=None)

    assert sent_messages == []
    assert runtime._last_heartbeat_at == 0.0


# ---------------------------------------------------------------------------
# Multi-position / portfolio / session / funding coverage (Stages 2+3)
# ---------------------------------------------------------------------------


def _make_position(symbol: str, margin: float = 36.0) -> FuturesPosition:
    return FuturesPosition(
        symbol=symbol,
        side="LONG",
        entry_price=90000.0,
        contracts=1,
        contract_size=0.01,
        leverage=25,
        margin_usdt=margin,
        tp_price=93000.0,
        sl_price=88800.0,
        position_id="paper",
        order_id="paper",
        opened_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        score=65.0,
        certainty=0.8,
        entry_signal="COIL_BREAKOUT_LONG",
    )


def test_register_and_clear_positions_track_total_margin(tmp_path):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())

    runtime._register_position(_make_position("BTC_USDT", margin=40.0))
    runtime._register_position(_make_position("ETH_USDT", margin=60.0))

    assert set(runtime.open_positions) == {"BTC_USDT", "ETH_USDT"}
    assert runtime._total_open_margin() == 100.0

    runtime._clear_position("BTC_USDT")
    assert set(runtime.open_positions) == {"ETH_USDT"}
    assert runtime._total_open_margin() == 60.0


def test_bucket_open_count_and_available_slots(tmp_path):
    cfg = replace(
        _config(tmp_path),
        max_concurrent_positions=3,
        correlation_buckets={"BTC_USDT": "major", "ETH_USDT": "major", "SOL_USDT": "alt"},
    )
    runtime = FuturesRuntime(cfg, StubClient())
    runtime._register_position(_make_position("BTC_USDT"))

    assert runtime._available_slots() == 2
    assert runtime._bucket_open_count("major") == 1
    assert runtime._bucket_open_count("alt") == 0

    runtime._register_position(_make_position("ETH_USDT"))
    assert runtime._bucket_open_count("major") == 2
    assert runtime._available_slots() == 1


def test_open_position_setter_upserts_and_clears(tmp_path):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    runtime.open_position = _make_position("BTC_USDT")
    runtime.open_position = _make_position("ETH_USDT")

    assert set(runtime.open_positions) == {"BTC_USDT", "ETH_USDT"}

    runtime.open_position = None
    assert runtime.open_positions == {}


def test_is_in_session_supports_empty_range_and_wrap(tmp_path):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())

    assert runtime._is_in_session(replace(runtime.config, session_hours_utc="")) is True
    assert runtime._is_in_session(replace(runtime.config, session_hours_utc="garbage")) is True

    now_hour = datetime.now(timezone.utc).hour
    start = now_hour
    end = (now_hour + 1) % 24
    assert runtime._is_in_session(replace(runtime.config, session_hours_utc=f"{start}-{end}")) is True

    off_start = (now_hour + 2) % 24
    off_end = (now_hour + 3) % 24
    assert runtime._is_in_session(replace(runtime.config, session_hours_utc=f"{off_start}-{off_end}")) is False

    # Wrap-around range that always includes current hour: 0-(now+1) OR covers via wrap.
    # Construct a wrap range that explicitly excludes now_hour to exercise the wrap branch negative case.
    excl_start = (now_hour + 1) % 24
    excl_end = now_hour  # wraps; excludes [now_hour, now_hour+1)
    if excl_start != excl_end:
        assert runtime._is_in_session(replace(runtime.config, session_hours_utc=f"{excl_start}-{excl_end}")) is False


def test_funding_gate_zero_cap_disables(tmp_path):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    scoped = replace(runtime.config, symbol="BTC_USDT", funding_rate_abs_max=0.0)
    assert runtime._funding_gate_ok(scoped) is True


def test_funding_gate_blocks_when_rate_exceeds_cap(tmp_path):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    runtime.client.get_funding_rate = lambda symbol: 0.01  # type: ignore[attr-defined]
    scoped = replace(runtime.config, symbol="BTC_USDT", funding_rate_abs_max=0.003)
    assert runtime._funding_gate_ok(scoped) is False


def test_funding_gate_allows_when_rate_within_cap(tmp_path):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    runtime.client.get_funding_rate = lambda symbol: 0.0005  # type: ignore[attr-defined]
    scoped = replace(runtime.config, symbol="BTC_USDT", funding_rate_abs_max=0.003)
    assert runtime._funding_gate_ok(scoped) is True


def test_funding_gate_fails_open_when_client_lacks_method(tmp_path):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    # StubClient has no get_funding_rate; should not block.
    assert not hasattr(runtime.client, "get_funding_rate")
    scoped = replace(runtime.config, symbol="BTC_USDT", funding_rate_abs_max=0.003)
    assert runtime._funding_gate_ok(scoped) is True


def test_log_net_rr_shadow_emits_cost_breakdown(tmp_path, caplog):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    signal = SimpleNamespace(
        symbol="BTC_USDT",
        side="LONG",
        entry_signal="COIL_BREAKOUT_LONG",
        metadata={
            "cost_budget_mode": "shadow",
            "gross_rr": 2.1,
            "fee_bps": 8.0,
            "slippage_bps": 25.0,
            "funding_bps": 0.5,
            "total_cost_bps": 33.5,
            "net_rr": 1.82,
            "min_net_rr": 1.8,
            "cost_budget_pass": 1.0,
        },
    )

    with caplog.at_level(logging.INFO, logger="futuresbot.runtime"):
        runtime._log_net_rr_shadow(signal)

    assert any("[NET_RR_SHADOW]" in record.message and "gross_rr=2.10" in record.message for record in caplog.records)


def test_fetch_signal_passes_fresh_event_context_to_strategy(tmp_path, monkeypatch):
    runtime = FuturesRuntime(replace(_config(tmp_path), symbols=("BTC_USDT",), redis_url=""), StubClient())
    runtime._active_symbols = ("BTC_USDT",)
    event_state = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events": [{"title": "ETF approval", "direction": "risk_on", "severity": "high", "symbols": ["BTCUSDT"]}],
    }
    runtime._refresh_crypto_event_state = lambda: event_state  # type: ignore[method-assign]
    captured: dict[str, object] = {}

    def fake_score(frame, config, **kwargs):
        captured.update(kwargs)
        return FuturesSignal(
            symbol="BTC_USDT",
            side="LONG",
            score=82.0,
            certainty=0.8,
            entry_price=91000.0,
            tp_price=93000.0,
            sl_price=90000.0,
            leverage=20,
            entry_signal="EVENT_CATALYST_LONG",
            metadata={"net_rr": 1.9, "gross_rr": 2.0, "cost_budget_mode": "shadow"},
        )

    monkeypatch.setattr("futuresbot.runtime.score_btc_futures_setup", fake_score)

    signal = runtime._fetch_signal()

    assert signal is not None
    assert captured["event_bias_score"] > 0
    assert captured["event_max_severity"] >= 1.0
    assert captured["event_count"] >= 1


def test_fetch_signal_returns_none_when_strategies_retired(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_STRATEGIES_RETIRED", "1")
    runtime = FuturesRuntime(replace(_config(tmp_path), symbols=("BTC_USDT",), redis_url=""), StubClient())
    runtime._active_symbols = ("BTC_USDT",)

    assert runtime._fetch_signal() is None


def test_missed_opportunity_report_records_and_persists_blocked_move(tmp_path, caplog):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())

    with caplog.at_level(logging.INFO, logger="futuresbot.runtime"):
        runtime._record_missed_opportunity(
            symbol="BTC_USDT",
            frame_15m=runtime.client.frame,
            reason="volume_ratio=0.8<1.0",
            impulse_reason="impulse_score=40<55",
        )
    runtime._save_state()

    record = runtime.missed_opportunities["BTC_USDT"]
    assert record["blocking_gate"] == "volume_ratio=0.8<1.0"
    assert record["abs_move_pct"] > 0.0
    assert "mfe_r" in record
    assert any("[MISSED_OPPORTUNITY]" in entry.message for entry in caplog.records)

    reloaded = FuturesRuntime(_config(tmp_path), StubClient())
    assert reloaded.missed_opportunities["BTC_USDT"]["blocking_gate"] == "volume_ratio=0.8<1.0"
    assert reloaded._status_payload()["missed_opportunities"]["BTC_USDT"]["abs_move_pct"] == record["abs_move_pct"]


def test_paused_cycle_does_not_replay_stale_gate_summary(tmp_path, caplog):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    runtime._paused = True
    runtime._last_cycle_gate_blocks = {"BTC_USDT": "adx=12.5<18.0"}
    runtime._last_cycle_symbol_count = 1

    with caplog.at_level(logging.INFO, logger="futuresbot.runtime"):
        runtime._log_cycle_summary(price=91000.0, signal=None)

    assert runtime._last_cycle_gate_blocks == {}
    assert not any("[CYCLE_SUMMARY]" in entry.message for entry in caplog.records)
    assert any("paused=True" in entry.message for entry in caplog.records)


def test_drawdown_halt_blocks_without_manual_pause(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("USE_DRAWDOWN_KILL", "1")
    monkeypatch.setenv("IGNORE_HALT", "false")
    config = replace(_config(tmp_path), margin_budget_usdt=100.0)
    runtime = FuturesRuntime(config, StubClient())
    runtime.trade_history = [
        {"pnl_usdt": 25.0, "closed_at": "2026-05-01T00:00:00+00:00"},
        {"pnl_usdt": -45.0, "closed_at": "2026-05-02T00:00:00+00:00"},
    ]

    with caplog.at_level(logging.INFO, logger="futuresbot.runtime"):
        multiplier = runtime._drawdown_size_multiplier()

    assert multiplier == 0.0
    assert runtime._paused is False
    assert any("Drawdown HALT active" in entry.message for entry in caplog.records)


def test_live_drawdown_halt_ignores_stale_override_without_confirmation(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("USE_DRAWDOWN_KILL", "1")
    monkeypatch.setenv("IGNORE_HALT", "true")
    monkeypatch.delenv("FUTURES_ALLOW_LIVE_HALT_OVERRIDE", raising=False)
    config = replace(_config(tmp_path), margin_budget_usdt=100.0, paper_trade=False)
    runtime = FuturesRuntime(config, StubClient())
    runtime.trade_history = [
        {"pnl_usdt": 100.0, "closed_at": "2026-05-01T00:00:00+00:00"},
        {"pnl_usdt": -100.0, "closed_at": "2026-05-02T00:00:00+00:00"},
    ]

    with caplog.at_level(logging.WARNING, logger="futuresbot.runtime"):
        multiplier = runtime._drawdown_size_multiplier()

    assert multiplier == 0.0
    assert any("IGNORE_HALT requested but ignored in live mode" in entry.message for entry in caplog.records)


def test_live_drawdown_uses_current_equity_after_deposit(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("USE_DRAWDOWN_KILL", "1")
    config = replace(_config(tmp_path), margin_budget_usdt=75.0, paper_trade=False)
    runtime = FuturesRuntime(config, FundedStubClient())
    runtime.trade_history = [
        {"pnl_usdt": 1.42, "closed_at": "2026-05-01T00:00:00+00:00"},
        {"pnl_usdt": -13.3021, "closed_at": "2026-05-02T00:00:00+00:00"},
    ]

    with caplog.at_level(logging.INFO, logger="futuresbot.runtime"):
        multiplier = runtime._drawdown_size_multiplier()

    assert multiplier == 1.0
    assert not any("Drawdown HALT active" in entry.message for entry in caplog.records)


def test_enter_trade_rejects_duplicate_symbol(tmp_path):
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    runtime._register_position(_make_position("BTC_USDT"))

    signal = {
        "side": "LONG",
        "entry_price": 91000.0,
        "leverage": 25,
        "symbol": "BTC_USDT",
        "tp_price": 93000.0,
        "sl_price": 88000.0,
        "score": 60.0,
        "certainty": 0.7,
        "entry_signal": "COIL_BREAKOUT_LONG",
    }
    assert runtime._enter_trade(signal) is False


def test_enter_trade_blocks_recent_same_signal_reentry(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_REENTRY_COOLDOWN_SECONDS", "900")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    runtime._last_exit_by_symbol["ZEC_USDT"] = {
        "closed_at": datetime.now(timezone.utc).isoformat(),
        "side": "SHORT",
        "entry_signal": "EVENT_CATALYST_SHORT",
        "exit_reason": "BREAKEVEN_PROFIT_LOCK",
    }

    signal = {
        "side": "SHORT",
        "entry_price": 524.12,
        "leverage": 12,
        "symbol": "ZEC_USDT",
        "tp_price": 497.71,
        "sl_price": 529.12,
        "score": 67.1,
        "certainty": 0.55,
        "entry_signal": "EVENT_CATALYST_SHORT",
    }

    assert runtime._enter_trade(signal) is False
    assert "ZEC_USDT" not in runtime.open_positions


def test_enter_trade_returns_false_when_strategies_retired(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_STRATEGIES_RETIRED", "1")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())

    signal = {
        "side": "LONG",
        "entry_price": 91000.0,
        "leverage": 20,
        "symbol": "BTC_USDT",
        "tp_price": 93000.0,
        "sl_price": 88000.0,
        "score": 95.0,
        "certainty": 0.9,
        "entry_signal": "COIL_BREAKOUT_LONG",
    }

    assert runtime._enter_trade(signal) is False


def test_hourly_exit_skips_strategy_exits_when_strategies_retired(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_STRATEGIES_RETIRED", "1")
    runtime = FuturesRuntime(_config(tmp_path), StubClient())
    position = _make_position("BTC_USDT")

    # Without retirement mode this would hit fixed TP for a LONG.
    assert runtime._hourly_exit(position, current_price=93100.0) is False


def test_enter_trade_respects_portfolio_margin_cap(tmp_path):
    cfg = replace(
        _config(tmp_path),
        max_concurrent_positions=2,
        max_total_margin_usdt=50.0,  # explicit cap below two margin budgets
    )

    class ContractClient(StubClient):
        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            return {"contractSize": 0.0001, "minVol": 1}

    runtime = FuturesRuntime(cfg, ContractClient())
    runtime._register_position(_make_position("BTC_USDT", margin=40.0))

    signal = {
        "side": "LONG",
        "entry_price": 3000.0,
        "leverage": 20,
        "symbol": "ETH_USDT",
        "tp_price": 3300.0,
        "sl_price": 2850.0,
        "score": 60.0,
        "certainty": 0.7,
        "entry_signal": "COIL_BREAKOUT_LONG",
    }
    # With margin_budget_usdt default, projected margin ≈ margin_budget (e.g. 30). 40 + 30 > 50 → reject.
    assert runtime._enter_trade(signal) is False
    assert "ETH_USDT" not in runtime.open_positions


def test_enter_trade_caps_opportunity_bucket_with_nav_risk(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_OPPORTUNITY_BUCKET_SIZING_ENABLED", "1")
    monkeypatch.setenv("USE_NAV_RISK_SIZING", "1")
    monkeypatch.setenv("FUTURES_OPPORTUNITY_NAV_RISK_PCT", "0.04")
    for name in (
        "FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE6",
        "FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE6_7",
        "FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE7",
        "FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE8",
        "FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE9",
        "FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE10",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FUTURES_CONFIDENCE_RISK_SIZING_ENABLED", "0")
    monkeypatch.setenv("NAV_LEVERAGE_MIN", "1")
    monkeypatch.setenv("NAV_LEVERAGE_MAX", "20")
    cfg = replace(
        _config(tmp_path),
        margin_budget_usdt=200.0,
        paper_trade=True,
        leverage_min=1,
        leverage_max=20,
        max_total_margin_usdt=0.0,
    )

    class ContractClient(StubClient):
        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            return {"contractSize": 1.0, "minVol": 1}

    runtime = FuturesRuntime(cfg, ContractClient())
    signal = {
        "side": "LONG",
        "entry_price": 10.0,
        "leverage": 2,
        "symbol": "BTC_USDT",
        "tp_price": 12.0,
        "sl_price": 9.0,
        "score": 85.0,
        "certainty": 0.8,
        "entry_signal": "COIL_BREAKOUT_LONG",
    }

    assert runtime._enter_trade(signal) is True
    position = runtime.open_positions["BTC_USDT"]
    assert position.margin_usdt == 40.0
    assert position.contracts == 8
    assert position.leverage == 2
    assert position.metadata["opportunity_score_10"] == 9
    assert position.metadata["opportunity_balance_fraction"] == 0.75
    assert position.metadata["opportunity_nav_risk_pct"] == 0.04
    assert position.metadata["opportunity_margin_budget_usdt"] == 150.0


def test_live_enter_trade_does_not_register_without_exchange_position(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_ATTEMPTS", "1")
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_SLEEP_SECONDS", "0")

    class UnconfirmedEntryClient(StubClient):
        def __init__(self) -> None:
            super().__init__()
            self.cancelled: list[str] = []

        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            return {"contractSize": 1.0, "minVol": 1}

        def change_position_mode(self, position_mode: int):
            return {"success": True}

        def change_leverage(self, *, symbol: str, leverage: int, position_type: int, open_type: int = 1, position_id: str | None = None):
            return {"success": True}

        def place_order(self, **kwargs):
            return {"orderId": "entry-1"}

        def get_order(self, order_id: str) -> dict[str, str]:
            return {"orderId": order_id}

        def get_open_positions(self, symbol: str | None = None):
            return []

        def cancel_order(self, order_id: str):
            self.cancelled.append(order_id)
            return {"success": True}

    runtime = FuturesRuntime(replace(_config(tmp_path), paper_trade=False, margin_budget_usdt=50.0), UnconfirmedEntryClient())
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    signal = {
        "side": "LONG",
        "entry_price": 100.0,
        "leverage": 5,
        "symbol": "BTC_USDT",
        "tp_price": 104.0,
        "sl_price": 98.0,
        "score": 70.0,
        "certainty": 0.75,
        "entry_signal": "EVENT_CATALYST_LONG",
        "metadata": {},
    }

    assert runtime._enter_trade(signal) is False
    assert runtime.open_positions == {}
    assert runtime.client.cancelled == ["entry-1"]
    assert any("Futures Entry Not Confirmed" in message for message in sent_messages)
    assert not any("Futures Position Opened" in message for message in sent_messages)


def test_live_enter_trade_can_skip_low_score_taker_fallback_after_unfilled_maker(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_MAKER_LADDER", "1")
    monkeypatch.setenv("MAKER_LADDER_MAX_POLLS", "1")
    monkeypatch.setenv("MAKER_LADDER_POLL_SECONDS", "0")
    monkeypatch.setenv("MAKER_LADDER_TAKER_FALLBACK_MIN_SCORE", "70")

    class UnfilledMakerClient(StubClient):
        def __init__(self) -> None:
            super().__init__()
            self.orders: list[dict[str, object]] = []
            self.cancelled: list[str] = []

        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            return {"contractSize": 1.0, "minVol": 1}

        def get_ticker(self, symbol: str) -> dict[str, str]:
            return {"bid1": "99.99", "ask1": "100.01", "lastPrice": "100.0"}

        def change_position_mode(self, position_mode: int):
            return {"success": True}

        def change_leverage(self, *, symbol: str, leverage: int, position_type: int, open_type: int = 1, position_id: str | None = None):
            return {"success": True}

        def place_order(self, **kwargs):
            self.orders.append(dict(kwargs))
            return {"orderId": f"maker-{len(self.orders)}"}

        def get_order(self, order_id: str) -> dict[str, str]:
            return {"orderId": order_id, "dealVol": "0"}

        def cancel_order(self, order_id: str):
            self.cancelled.append(order_id)
            return {"success": True}

    client = UnfilledMakerClient()
    runtime = FuturesRuntime(replace(_config(tmp_path), paper_trade=False, margin_budget_usdt=50.0), client)
    runtime._notify = lambda message, parse_mode="HTML": None
    signal = {
        "side": "SHORT",
        "entry_price": 100.0,
        "leverage": 5,
        "symbol": "BTC_USDT",
        "tp_price": 96.0,
        "sl_price": 102.0,
        "score": 64.0,
        "certainty": 0.49,
        "entry_signal": "EVENT_CATALYST_SHORT",
        "metadata": {},
    }

    assert runtime._enter_trade(signal) is False
    assert [order["order_type"] for order in client.orders] == [2]
    assert client.cancelled == ["maker-1"]
    assert runtime.open_positions == {}


def test_pmt_live_enter_trade_bypasses_maker_ladder_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_STRATEGY_MODE", "pmt_threshold")
    monkeypatch.setenv("USE_MAKER_LADDER", "1")
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_ATTEMPTS", "1")
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_SLEEP_SECONDS", "0")
    monkeypatch.setenv("USE_NAV_RISK_SIZING", "0")
    monkeypatch.setenv("USE_DRAWDOWN_KILL", "0")
    monkeypatch.setenv("USE_FUNDING_AWARE_ENTRY", "0")
    monkeypatch.setenv("USE_PORTFOLIO_VAR", "0")

    class PmtFastEntryClient(StubClient):
        def __init__(self) -> None:
            super().__init__()
            self.orders: list[dict[str, object]] = []

        def get_account_asset(self, currency: str = "USDT") -> dict[str, str]:
            return {"availableBalance": "100.0", "equity": "100.0"}

        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            return {"contractSize": 1.0, "minVol": 1}

        def get_ticker(self, symbol: str) -> dict[str, str]:
            raise AssertionError("PMT fast entry should not quote maker ladder")

        def change_position_mode(self, position_mode: int):
            return {"success": True}

        def change_leverage(self, *, symbol: str, leverage: int, position_type: int, open_type: int = 1, position_id: str | None = None):
            return {"success": True}

        def place_order(self, **kwargs):
            self.orders.append(dict(kwargs))
            return {"orderId": "entry-pmt-fast"}

        def get_order(self, order_id: str) -> dict[str, str]:
            volume = str(self.orders[-1]["vol"])
            return {"orderId": order_id, "dealAvgPrice": "100.0", "dealVol": volume, "positionId": "pos-pmt-fast"}

        def get_open_positions(self, symbol: str | None = None):
            volume = str(self.orders[-1]["vol"])
            margin = float(self.orders[-1]["vol"]) * 100.0 / float(self.orders[-1]["leverage"])
            return [
                {
                    "symbol": "BTC_USDT",
                    "positionType": 2,
                    "holdVol": volume,
                    "holdAvgPrice": "100.0",
                    "im": str(margin),
                    "leverage": str(self.orders[-1]["leverage"]),
                    "positionId": "pos-pmt-fast",
                }
            ]

    client = PmtFastEntryClient()
    runtime = FuturesRuntime(replace(_config(tmp_path), paper_trade=False, margin_budget_usdt=50.0), client)
    runtime._notify = lambda message, parse_mode="HTML": None
    signal = {
        "side": "SHORT",
        "entry_price": 100.0,
        "leverage": 5,
        "symbol": "BTC_USDT",
        "tp_price": 95.0,
        "sl_price": 102.0,
        "score": 92.0,
        "certainty": 0.92,
        "entry_signal": "PMT_THRESHOLD_SHORT",
        "metadata": {"tp_margin_pct": 25.0, "sl_margin_pct": 10.0},
    }

    assert runtime._enter_trade(signal) is True
    assert [order["order_type"] for order in client.orders] == [5]
    assert runtime.open_positions["BTC_USDT"].position_id == "pos-pmt-fast"


def test_live_enter_trade_registers_only_confirmed_exchange_position(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_ATTEMPTS", "1")
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_SLEEP_SECONDS", "0")

    class ConfirmedEntryClient(StubClient):
        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            return {"contractSize": 1.0, "minVol": 1}

        def change_position_mode(self, position_mode: int):
            return {"success": True}

        def change_leverage(self, *, symbol: str, leverage: int, position_type: int, open_type: int = 1, position_id: str | None = None):
            return {"success": True}

        def place_order(self, **kwargs):
            return {"orderId": "entry-2"}

        def get_order(self, order_id: str) -> dict[str, str]:
            return {"orderId": order_id, "dealAvgPrice": "100.10", "dealVol": "2", "positionId": "pos-2"}

        def get_open_positions(self, symbol: str | None = None):
            return [
                {
                    "symbol": "BTC_USDT",
                    "positionType": 1,
                    "holdVol": "2",
                    "holdAvgPrice": "100.25",
                    "im": "40.20",
                    "leverage": "5",
                    "positionId": "pos-2",
                }
            ]

    runtime = FuturesRuntime(replace(_config(tmp_path), paper_trade=False, margin_budget_usdt=50.0), ConfirmedEntryClient())
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    signal = {
        "side": "LONG",
        "entry_price": 100.0,
        "leverage": 5,
        "symbol": "BTC_USDT",
        "tp_price": 104.0,
        "sl_price": 98.0,
        "score": 70.0,
        "certainty": 0.75,
        "entry_signal": "EVENT_CATALYST_LONG",
        "metadata": {},
    }

    assert runtime._enter_trade(signal) is True
    position = runtime.open_positions["BTC_USDT"]
    assert position.position_id == "pos-2"
    assert position.order_id == "entry-2"
    assert position.contracts == 2
    assert position.entry_price == 100.25
    assert position.margin_usdt == 40.2
    assert any("Futures Position Opened" in message for message in sent_messages)


def test_live_enter_trade_caps_order_to_available_balance(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_ATTEMPTS", "1")
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_SLEEP_SECONDS", "0")
    monkeypatch.setenv("USE_NAV_RISK_SIZING", "0")
    monkeypatch.setenv("FUTURES_MAX_MARGIN_FRACTION", "0.85")

    class LowBalanceEntryClient(StubClient):
        def __init__(self) -> None:
            super().__init__()
            self.orders: list[dict[str, object]] = []

        def get_account_asset(self, currency: str = "USDT") -> dict[str, str]:
            return {"availableBalance": "42.74957342270529", "equity": "150.0"}

        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            return {"contractSize": 1.0, "minVol": 1}

        def change_position_mode(self, position_mode: int):
            return {"success": True}

        def change_leverage(self, *, symbol: str, leverage: int, position_type: int, open_type: int = 1, position_id: str | None = None):
            return {"success": True}

        def place_order(self, **kwargs):
            self.orders.append(dict(kwargs))
            return {"orderId": "entry-low-balance"}

        def get_order(self, order_id: str) -> dict[str, str]:
            volume = str(self.orders[-1]["vol"])
            return {"orderId": order_id, "dealAvgPrice": "100.0", "dealVol": volume, "positionId": "pos-low-balance"}

        def get_open_positions(self, symbol: str | None = None):
            volume = str(self.orders[-1]["vol"])
            margin = float(self.orders[-1]["vol"]) * 100.0 / float(self.orders[-1]["leverage"])
            return [
                {
                    "symbol": "BTC_USDT",
                    "positionType": 1,
                    "holdVol": volume,
                    "holdAvgPrice": "100.0",
                    "im": str(margin),
                    "leverage": str(self.orders[-1]["leverage"]),
                    "positionId": "pos-low-balance",
                }
            ]

    runtime = FuturesRuntime(replace(_config(tmp_path), paper_trade=False, margin_budget_usdt=150.0), LowBalanceEntryClient())
    runtime._notify = lambda message, parse_mode="HTML": None
    signal = {
        "side": "LONG",
        "entry_price": 100.0,
        "leverage": 5,
        "symbol": "BTC_USDT",
        "tp_price": 104.0,
        "sl_price": 98.0,
        "score": 70.0,
        "certainty": 0.75,
        "entry_signal": "EVENT_CATALYST_LONG",
        "metadata": {},
    }

    assert runtime._enter_trade(signal) is True
    order = runtime.client.orders[-1]
    order_margin = order["vol"] * 1.0 * signal["entry_price"] / order["leverage"]
    uncapped_contracts = int((150.0 * order["leverage"] / signal["entry_price"]) / 1.0)
    assert order["vol"] < uncapped_contracts
    assert order_margin <= 42.74957342270529 * 0.85
    position = runtime.open_positions["BTC_USDT"]
    assert position.contracts == order["vol"]
    assert position.metadata["live_margin_budget_capped"] is True


def test_live_enter_trade_full_balance_uses_all_available_margin(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_ATTEMPTS", "1")
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_SLEEP_SECONDS", "0")
    monkeypatch.setenv("FUTURES_FULL_BALANCE_SIZING_ENABLED", "1")
    monkeypatch.setenv("FUTURES_FULL_BALANCE_RISK_PCT", "1.0")
    monkeypatch.setenv("FUTURES_ENTRY_LEVERAGE_MIN", "12")
    monkeypatch.setenv("FUTURES_ENTRY_LEVERAGE_HIGH", "20")
    monkeypatch.setenv("FUTURES_ENTRY_HIGH_SCORE", "95")
    monkeypatch.setenv("FUTURES_MAX_MARGIN_FRACTION", "0.20")
    monkeypatch.setenv("USE_NAV_RISK_SIZING", "1")
    monkeypatch.setenv("USE_SESSION_LEVERAGE", "1")
    monkeypatch.setenv("SESSION_ASIA_LEVERAGE_CAP", "5")
    monkeypatch.setenv("USE_DRAWDOWN_KILL", "0")
    monkeypatch.setenv("USE_PORTFOLIO_VAR", "0")

    class FullBalanceEntryClient(StubClient):
        def __init__(self) -> None:
            super().__init__()
            self.orders: list[dict[str, object]] = []

        def get_account_asset(self, currency: str = "USDT") -> dict[str, str]:
            return {"availableBalance": "50.0", "equity": "50.0"}

        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            return {"contractSize": 1.0, "minVol": 1}

        def change_position_mode(self, position_mode: int):
            return {"success": True}

        def change_leverage(self, *, symbol: str, leverage: int, position_type: int, open_type: int = 1, position_id: str | None = None):
            return {"success": True}

        def place_order(self, **kwargs):
            self.orders.append(dict(kwargs))
            return {"orderId": "entry-full-balance"}

        def get_order(self, order_id: str) -> dict[str, str]:
            volume = str(self.orders[-1]["vol"])
            return {"orderId": order_id, "dealAvgPrice": "100.0", "dealVol": volume, "positionId": "pos-full-balance"}

        def get_open_positions(self, symbol: str | None = None):
            volume = str(self.orders[-1]["vol"])
            margin = float(self.orders[-1]["vol"]) * 100.0 / float(self.orders[-1]["leverage"])
            return [
                {
                    "symbol": "BTC_USDT",
                    "positionType": 1,
                    "holdVol": volume,
                    "holdAvgPrice": "100.0",
                    "im": str(margin),
                    "leverage": str(self.orders[-1]["leverage"]),
                    "positionId": "pos-full-balance",
                }
            ]

    runtime = FuturesRuntime(replace(_config(tmp_path), paper_trade=False, leverage_min=1, leverage_max=20, max_total_margin_usdt=10.0), FullBalanceEntryClient())
    runtime._notify = lambda message, parse_mode="HTML": None
    signal = {
        "side": "LONG",
        "entry_price": 100.0,
        "leverage": 10,
        "symbol": "BTC_USDT",
        "tp_price": 104.0,
        "sl_price": 98.0,
        "score": 96.0,
        "certainty": 0.75,
        "entry_signal": "EVENT_CATALYST_LONG",
        "metadata": {},
    }

    assert runtime._enter_trade(signal) is True
    order = runtime.client.orders[-1]
    assert order["vol"] == 10
    assert order["vol"] * 100.0 / order["leverage"] == 50.0
    assert order["leverage"] == 20
    assert "live_margin_budget_capped" not in runtime.open_positions["BTC_USDT"].metadata


def test_enter_trade_normalizes_margin_risk_cap_percent_value(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_MAX_STOP_RISK_PCT_OF_MARGIN", "20")
    monkeypatch.setenv("FUTURES_ENTRY_LEVERAGE_HIGH", "20")
    monkeypatch.setenv("FUTURES_ENTRY_HIGH_SCORE", "95")
    monkeypatch.setenv("USE_NAV_RISK_SIZING", "0")
    monkeypatch.setenv("FUTURES_OPPORTUNITY_BUCKET_SIZING_ENABLED", "0")
    monkeypatch.setenv("USE_SESSION_LEVERAGE", "0")
    monkeypatch.setenv("USE_DRAWDOWN_KILL", "0")
    monkeypatch.setenv("USE_FUNDING_AWARE_ENTRY", "0")
    monkeypatch.setenv("USE_PORTFOLIO_VAR", "0")

    class ContractClient(StubClient):
        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            return {"contractSize": 0.01, "minVol": 1}

    runtime = FuturesRuntime(
        replace(_config(tmp_path), paper_trade=True, leverage_min=1, leverage_max=20, margin_budget_usdt=10.0),
        ContractClient(),
    )
    runtime._notify = lambda message, parse_mode="HTML": None
    signal = {
        "side": "SHORT",
        "entry_price": 635.0,
        "leverage": 12,
        "symbol": "BNB_USDT",
        "tp_price": 611.64,
        "sl_price": 643.77,
        "score": 95.9,
        "certainty": 0.99,
        "entry_signal": "SIMPLE_TREND_SHORT",
        "metadata": {},
    }

    assert runtime._enter_trade(signal) is True
    position = runtime.open_positions["BNB_USDT"]
    assert position.leverage == 20
    assert round(position.sl_price, 2) == 641.35
    assert position.metadata["sl_distance_cap_applied"] == 1.0
    assert round(runtime._position_stop_risk_pct_of_margin(position), 2) == 20.0


def test_pmt_live_enter_trade_reanchors_protection_to_confirmed_fill(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_STRATEGY_MODE", "pmt_threshold")
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_ATTEMPTS", "1")
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_SLEEP_SECONDS", "0")
    monkeypatch.setenv("FUTURES_MAX_STOP_RISK_PCT_OF_MARGIN", "20")
    monkeypatch.setenv("USE_NAV_RISK_SIZING", "0")
    monkeypatch.setenv("USE_DRAWDOWN_KILL", "0")
    monkeypatch.setenv("USE_FUNDING_AWARE_ENTRY", "0")
    monkeypatch.setenv("USE_PORTFOLIO_VAR", "0")

    class BnbFillClient(StubClient):
        def __init__(self) -> None:
            super().__init__()
            self.orders: list[dict[str, object]] = []
            self.position_tpsl: list[dict[str, object]] = []

        def get_account_asset(self, currency: str = "USDT") -> dict[str, str]:
            return {"availableBalance": "50.0", "equity": "50.0"}

        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            return {"contractSize": 0.01, "minVol": 1}

        def change_position_mode(self, position_mode: int):
            return {"success": True}

        def change_leverage(self, *, symbol: str, leverage: int, position_type: int, open_type: int = 1, position_id: str | None = None):
            return {"success": True}

        def place_order(self, **kwargs):
            self.orders.append(dict(kwargs))
            return {"orderId": "entry-bnb-fill"}

        def get_order(self, order_id: str) -> dict[str, str]:
            volume = str(self.orders[-1]["vol"])
            return {"orderId": order_id, "dealAvgPrice": "573.9", "dealVol": volume, "positionId": "pos-bnb-fill"}

        def get_open_positions(self, symbol: str | None = None):
            volume = str(self.orders[-1]["vol"])
            leverage = float(self.orders[-1]["leverage"])
            margin = float(self.orders[-1]["vol"]) * 0.01 * 573.9 / leverage
            return [
                {
                    "symbol": "BNB_USDT",
                    "positionType": 2,
                    "holdVol": volume,
                    "holdAvgPrice": "573.9",
                    "im": str(margin),
                    "leverage": str(self.orders[-1]["leverage"]),
                    "positionId": "pos-bnb-fill",
                }
            ]

        def place_position_tpsl(self, **kwargs):
            self.position_tpsl.append(dict(kwargs))
            return {"success": True}

    intended_entry = 579.7
    fill_price = 573.9
    leverage = 22
    tp_margin_pct = 200.0
    sl_margin_pct = 16.5
    stale_tp = intended_entry * (1.0 - (tp_margin_pct / 100.0) / leverage)
    stale_sl = intended_entry * (1.0 + (sl_margin_pct / 100.0) / leverage)
    expected_tp = fill_price * (1.0 - (tp_margin_pct / 100.0) / leverage)
    expected_sl = fill_price * (1.0 + (sl_margin_pct / 100.0) / leverage)

    client = BnbFillClient()
    runtime = FuturesRuntime(
        replace(_config(tmp_path), paper_trade=False, leverage_min=5, leverage_max=25, margin_budget_usdt=50.0),
        client,
    )
    runtime._notify = lambda message, parse_mode="HTML": None
    signal = {
        "side": "SHORT",
        "entry_price": intended_entry,
        "leverage": leverage,
        "symbol": "BNB_USDT",
        "tp_price": stale_tp,
        "sl_price": stale_sl,
        "score": 92.06,
        "certainty": 0.9206,
        "entry_signal": "PMT_THRESHOLD_SHORT",
        "metadata": {"tp_margin_pct": tp_margin_pct, "sl_margin_pct": sl_margin_pct},
    }

    assert runtime._enter_trade(signal) is True
    position = runtime.open_positions["BNB_USDT"]
    assert position.entry_price == fill_price
    assert position.tp_price == pytest.approx(expected_tp)
    assert position.sl_price == pytest.approx(expected_sl)
    assert position.sl_price < 581.2
    assert round(runtime._position_stop_risk_pct_of_margin(position), 2) == sl_margin_pct
    assert position.metadata["fill_anchored_protection"] == 1.0
    assert position.metadata["fill_anchored_tpsl_placed"] == 1.0
    assert client.orders[-1]["stop_loss_price"] == pytest.approx(stale_sl)
    assert client.position_tpsl[-1]["side"] == "SHORT"
    assert client.position_tpsl[-1]["stop_loss_price"] == pytest.approx(expected_sl)


def test_live_enter_trade_retries_lower_contracts_on_balance_insufficient(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_ATTEMPTS", "1")
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_SLEEP_SECONDS", "0")
    monkeypatch.setenv("USE_NAV_RISK_SIZING", "0")
    monkeypatch.setenv("FUTURES_MAX_MARGIN_FRACTION", "0.85")
    monkeypatch.setenv("FUTURES_BALANCE_GUARD_BUFFER", "0.95")

    class BalanceRetryClient(StubClient):
        def __init__(self) -> None:
            super().__init__()
            self.orders: list[dict[str, object]] = []

        def get_account_asset(self, currency: str = "USDT") -> dict[str, str]:
            return {"availableBalance": "27.82940349334529", "equity": "150.0"}

        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            return {"contractSize": 1.0, "minVol": 1}

        def change_position_mode(self, position_mode: int):
            return {"success": True}

        def change_leverage(self, *, symbol: str, leverage: int, position_type: int, open_type: int = 1, position_id: str | None = None):
            return {"success": True}

        def place_order(self, **kwargs):
            self.orders.append(dict(kwargs))
            if len(self.orders) == 1:
                payload = {
                    "success": False,
                    "code": 2005,
                    "message": "Balance insufficient",
                    "_extend": {"cost": 35.6001366, "available": 27.82940349334529},
                }
                raise MexcApiError(
                    f"MEXC futures private POST failed for /api/v1/private/order/create: {payload}",
                    path="/api/v1/private/order/create",
                    payload=payload,
                )
            return {"orderId": "entry-balance-retry"}

        def get_order(self, order_id: str) -> dict[str, str]:
            volume = str(self.orders[-1]["vol"])
            return {"orderId": order_id, "dealAvgPrice": "10.0", "dealVol": volume, "positionId": "pos-balance-retry"}

        def get_open_positions(self, symbol: str | None = None):
            volume = str(self.orders[-1]["vol"])
            margin = float(self.orders[-1]["vol"]) * 10.0 / float(self.orders[-1]["leverage"])
            return [
                {
                    "symbol": "BTC_USDT",
                    "positionType": 1,
                    "holdVol": volume,
                    "holdAvgPrice": "10.0",
                    "im": str(margin),
                    "leverage": str(self.orders[-1]["leverage"]),
                    "positionId": "pos-balance-retry",
                }
            ]

    runtime = FuturesRuntime(replace(_config(tmp_path), paper_trade=False, margin_budget_usdt=150.0), BalanceRetryClient())
    runtime._notify = lambda message, parse_mode="HTML": None
    signal = {
        "side": "LONG",
        "entry_price": 10.0,
        "leverage": 5,
        "symbol": "BTC_USDT",
        "tp_price": 10.4,
        "sl_price": 9.8,
        "score": 70.0,
        "certainty": 0.75,
        "entry_signal": "EVENT_CATALYST_LONG",
        "metadata": {},
    }

    assert runtime._enter_trade(signal) is True
    assert len(runtime.client.orders) == 2
    first_order, retry_order = runtime.client.orders
    assert retry_order["vol"] < first_order["vol"]
    assert retry_order["vol"] == int(first_order["vol"] * (27.82940349334529 / 35.6001366) * 0.95)
    position = runtime.open_positions["BTC_USDT"]
    assert position.contracts == retry_order["vol"]
    assert position.metadata["live_balance_guard_capped"] is True
    assert position.metadata["live_balance_guard_available_usdt"] == 27.8294


def test_live_enter_trade_enforces_production_leverage_bounds(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_ATTEMPTS", "1")
    monkeypatch.setenv("FUTURES_ENTRY_CONFIRM_SLEEP_SECONDS", "0")
    monkeypatch.setenv("USE_NAV_RISK_SIZING", "1")
    monkeypatch.setenv("USE_SESSION_LEVERAGE", "1")

    class LeverageClient(StubClient):
        def __init__(self) -> None:
            super().__init__()
            self.leverage_changes: list[dict[str, object]] = []
            self.orders: list[dict[str, object]] = []

        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            return {"contractSize": 0.01, "minVol": 1}

        def change_position_mode(self, position_mode: int):
            return {"success": True}

        def change_leverage(self, *, symbol: str, leverage: int, position_type: int, open_type: int = 1, position_id: str | None = None):
            self.leverage_changes.append(
                {
                    "symbol": symbol,
                    "leverage": leverage,
                    "position_type": position_type,
                    "open_type": open_type,
                }
            )
            return {"success": True}

        def place_order(self, **kwargs):
            self.orders.append(dict(kwargs))
            return {"orderId": "entry-20"}

        def get_order(self, order_id: str) -> dict[str, str]:
            return {"orderId": order_id, "dealAvgPrice": "100.10", "dealVol": "25", "positionId": "pos-20"}

        def get_open_positions(self, symbol: str | None = None):
            return [
                {
                    "symbol": "BTC_USDT",
                    "positionType": 1,
                    "holdVol": "25",
                    "holdAvgPrice": "100.25",
                    "im": "1.25",
                    "leverage": "20",
                    "positionId": "pos-20",
                }
            ]

    runtime = FuturesRuntime(replace(_config(tmp_path), paper_trade=False, margin_budget_usdt=50.0), LeverageClient())
    runtime._notify = lambda message, parse_mode="HTML": None
    signal = {
        "side": "LONG",
        "entry_price": 100.0,
        "leverage": 5,
        "symbol": "BTC_USDT",
        "tp_price": 104.0,
        "sl_price": 98.0,
        "score": 70.0,
        "certainty": 0.75,
        "entry_signal": "EVENT_CATALYST_LONG",
        "metadata": {},
    }

    assert runtime._enter_trade(signal) is True
    assert runtime.client.leverage_changes[-1]["leverage"] == 20
    assert runtime.client.orders[-1]["leverage"] == 20
    assert runtime.client.orders[-1]["take_profit_price"] is None
    assert runtime.client.orders[-1]["stop_loss_price"] == 98.0
    assert runtime.open_positions["BTC_USDT"].leverage == 20


def test_reconcile_drops_stale_local_live_position_without_exchange_id(tmp_path):
    class EmptyExchangeClient(StubClient):
        def get_open_positions(self, symbol: str | None = None):
            return []

        def get_historical_positions(self, symbol: str, *, page_num: int = 1, page_size: int = 20):
            raise AssertionError("history should not be queried for local positions without exchange ids")

    runtime = FuturesRuntime(replace(_config(tmp_path), paper_trade=False), EmptyExchangeClient())
    runtime._register_position(
        FuturesPosition(
            symbol="ZEC_USDT",
            side="LONG",
            entry_price=417.18,
            contracts=1,
            contract_size=0.1,
            leverage=5,
            margin_usdt=11.74,
            tp_price=432.03,
            sl_price=412.08,
            position_id="",
            order_id="entry-zec",
            opened_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
            score=60.4,
            certainty=0.36,
            entry_signal="IMPULSE_EVENT_CONTINUATION_LONG",
        )
    )
    sent_messages: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent_messages.append(message)

    runtime._reconcile_closed_position()

    assert runtime.open_positions == {}
    assert any("Futures Local Position Cleared" in message for message in sent_messages)


def test_capital_scaling_increases_margin_only_after_clean_fills(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_CAPITAL_SCALE_REQUIRE_LIVE", "0")
    monkeypatch.setenv("FUTURES_CAPITAL_SCALE_MIN_CLEAN_FILLS", "3")
    monkeypatch.setenv("FUTURES_CAPITAL_SCALE_INCREMENT", "0.5")
    monkeypatch.setenv("FUTURES_CAPITAL_SCALE_MAX_MULT", "1.5")

    class ContractClient(StubClient):
        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            return {"contractSize": 0.01, "minVol": 1}

    runtime = FuturesRuntime(replace(_config(tmp_path), margin_budget_usdt=50.0), ContractClient())
    for _ in range(3):
        runtime.trade_history.append(
            {
                "pnl_usdt": 5.0,
                "fees_usdt": 1.0,
                "execution_quality": {
                    "mode": "paper",
                    "entry_slippage_bps": 0.0,
                    "exit_slippage_bps": 0.0,
                    "estimated_round_trip_fee_usdt": 1.0,
                    "fees_usdt": 1.0,
                },
            }
        )

    multiplier, details = runtime._capital_scaling_multiplier()
    assert multiplier == 1.5
    assert details["clean_fills"] == 3

    signal = {
        "side": "LONG",
        "entry_price": 100.0,
        "leverage": 5,
        "symbol": "BTC_USDT",
        "tp_price": 104.0,
        "sl_price": 98.0,
        "score": 70.0,
        "certainty": 0.75,
        "entry_signal": "EVENT_CATALYST_LONG",
        "metadata": {},
    }

    assert runtime._enter_trade(signal) is True
    position = runtime.open_position
    assert position is not None
    assert position.margin_usdt > 50.0
    assert position.metadata["setup_regime"] == "EVENT_CATALYST_LONG"


def test_first_trade_execution_canary_reports_on_close(tmp_path, caplog):
    class ContractClient(StubClient):
        def get_contract_detail(self, symbol: str) -> dict[str, object]:
            return {"contractSize": 0.01, "minVol": 1}

    runtime = FuturesRuntime(replace(_config(tmp_path), margin_budget_usdt=50.0), ContractClient())
    signal = {
        "side": "LONG",
        "entry_price": 100.0,
        "leverage": 5,
        "symbol": "BTC_USDT",
        "tp_price": 104.0,
        "sl_price": 98.0,
        "score": 70.0,
        "certainty": 0.75,
        "entry_signal": "EVENT_CATALYST_LONG",
        "metadata": {},
    }

    assert runtime._enter_trade(signal) is True
    position = runtime.open_position
    assert position is not None
    assert "execution_canary" in position.metadata

    with caplog.at_level(logging.INFO, logger="futuresbot.runtime"):
        runtime._close_history_trade(position, exit_price=104.0, reason="TAKE_PROFIT")

    assert runtime.trade_history[-1]["execution_canary_reported"] is True
    assert "execution_quality" in runtime.trade_history[-1]
    assert runtime.trade_history[-1]["execution_canary"]["realized_pnl_usdt"] > 0
    assert any("[EXECUTION_CANARY]" in record.message for record in caplog.records)


def test_state_round_trip_preserves_multiple_positions(tmp_path):
    runtime_a = FuturesRuntime(_config(tmp_path), StubClient())
    runtime_a._register_position(_make_position("BTC_USDT", margin=40.0))
    runtime_a._register_position(_make_position("ETH_USDT", margin=60.0))
    runtime_a._save_state()

    runtime_b = FuturesRuntime(_config(tmp_path), StubClient())
    assert set(runtime_b.open_positions) == {"BTC_USDT", "ETH_USDT"}
    assert runtime_b._total_open_margin() == 100.0