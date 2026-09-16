"""Regression tests for the 2026-09-16 defect fixes (independent assessment P2-P5).

Each test pins the BEHAVIOUR that was wrong, not the implementation:
  - a failed close must leave the exchange stop in place;
  - a sleeve may carry its own risk dial without moving the others;
  - a set-but-inert drawdown variable must announce itself.
The trigger-price-type fix (P2) lives in tests/test_marketdata.py.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from futuresbot.config import FuturesConfig
from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime


class _Client:
    def __init__(self, *, close_raises: bool = False, tpsl_raises: bool = False) -> None:
        self.close_raises = close_raises
        self.tpsl_raises = tpsl_raises
        self.calls: list[tuple[str, dict]] = []

    # --- used by the exit path ---
    def cancel_all_tpsl(self, *, position_id=None, symbol=None):
        self.calls.append(("cancel_all_tpsl", {"position_id": position_id, "symbol": symbol}))
        return {"success": True}

    def close_position(self, **kwargs):
        self.calls.append(("close_position", kwargs))
        if self.close_raises:
            raise RuntimeError("MEXC futures private POST failed")
        return {"orderId": "1"}

    def place_position_tpsl(self, **kwargs):
        self.calls.append(("place_position_tpsl", kwargs))
        if self.tpsl_raises:
            raise RuntimeError("stop rejected")
        return {"success": True}

    def get_order(self, order_id):
        return {"dealAvgPrice": 100.0}

    # --- generic plumbing ---
    def get_account_asset(self, currency: str = "USDT"):
        return {"availableBalance": "1000", "equity": "1000"}

    def get_updates(self, *, offset=None, limit: int = 5, timeout: int = 0):
        return []


def _runtime(tmp_path, client: _Client) -> FuturesRuntime:
    config = replace(
        FuturesConfig.from_env(),
        symbol="BTC_USDT", symbols=("BTC_USDT",),
        runtime_state_file=str(tmp_path / "state.json"),
        status_file=str(tmp_path / "status.json"),
        telegram_token="token", telegram_chat_id="1",
        paper_trade=False,
    )
    runtime = FuturesRuntime(config, client)
    runtime._notify = lambda message, parse_mode="HTML": None
    runtime._notify_once = lambda key, message, parse_mode="HTML": None
    return runtime


def _pos(symbol: str = "ZEC_USDT", side: str = "LONG") -> FuturesPosition:
    return FuturesPosition(
        symbol=symbol, side=side, entry_price=100.0, contracts=5,
        contract_size=1.0, leverage=5, margin_usdt=100.0,
        tp_price=130.0, sl_price=90.0, position_id="777", order_id="1",
        opened_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        score=96.0, certainty=0.9, entry_signal="TREND_LONG",
        metadata={"wildcard": 1.0, "trend": 1.0, "sl_margin_pct": 50.0},
    )


# --- P3: the exit path must not leave a position without its exchange stop ----

def test_failed_close_restores_the_exchange_stop(tmp_path):
    client = _Client(close_raises=True)
    runtime = _runtime(tmp_path, client)
    position = _pos()
    runtime.open_positions[position.symbol] = position

    with pytest.raises(RuntimeError):
        runtime._close_position_for_exit(position, current_price=95.0, reason="STOP_LOSS")

    names = [name for name, _ in client.calls]
    assert names == ["cancel_all_tpsl", "close_position", "place_position_tpsl"]
    restored = client.calls[-1][1]
    assert restored["stop_loss_price"] == 90.0
    assert restored["take_profit_price"] == 130.0
    assert restored["side"] == "LONG"
    assert restored["vol"] == 5
    # the position is still tracked: nothing was booked as closed
    assert runtime.open_positions.get(position.symbol) is position


def test_successful_close_does_not_re_place_a_stop(tmp_path):
    client = _Client()
    runtime = _runtime(tmp_path, client)
    position = _pos()
    runtime.open_positions[position.symbol] = position

    assert runtime._close_position_for_exit(position, current_price=95.0, reason="STOP_LOSS") is True
    assert "place_position_tpsl" not in [name for name, _ in client.calls]
    assert position.symbol not in runtime.open_positions


def test_restore_failure_is_reported_and_never_raises(tmp_path):
    client = _Client(close_raises=True, tpsl_raises=True)
    runtime = _runtime(tmp_path, client)
    sent: list[str] = []
    runtime._notify_once = lambda key, message, parse_mode="HTML": sent.append(message)
    position = _pos()
    runtime.open_positions[position.symbol] = position

    with pytest.raises(RuntimeError):
        runtime._close_position_for_exit(position, current_price=95.0, reason="STOP_LOSS")

    assert sent and "Stop Not Restored" in sent[0]


def test_paper_trade_exit_never_touches_the_exchange(tmp_path):
    client = _Client(close_raises=True)
    runtime = _runtime(tmp_path, client)
    runtime.config = replace(runtime.config, paper_trade=True)
    position = _pos()
    runtime.open_positions[position.symbol] = position

    assert runtime._close_position_for_exit(position, current_price=95.0, reason="STOP_LOSS") is True
    assert client.calls == []


# --- P1/decision: one sleeve's stake must move without the others -------------

class _Sig:
    symbol = "ZEC_USDT"
    side = "LONG"
    entry_price = 100.0
    leverage = 5
    sl_margin_pct = 20.0
    tp_margin_pct = 60.0
    balance_fraction = 0.12
    roc_pct = 0.05
    rsi = 70.0


def test_sleeve_risk_pct_overrides_only_its_own_sleeve(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_RISK_TARGETED", "1")
    monkeypatch.setenv("FUTURES_WILDCARD_RISK_PCT", "0.0241")
    monkeypatch.delenv("FUTURES_TREND_RISK_PCT", raising=False)
    runtime = _runtime(tmp_path, _Client())
    sig = _Sig()

    base_wild = runtime._entry_margin(sig, 1000.0, kind="WILDCARD", symbol="ZEC_USDT")
    base_trend = runtime._entry_margin(sig, 1000.0, kind="TREND", symbol="ZEC_USDT")
    assert base_wild == pytest.approx(base_trend)

    monkeypatch.setenv("FUTURES_TREND_RISK_PCT", "0.01205")           # half
    halved_trend = runtime._entry_margin(sig, 1000.0, kind="TREND", symbol="ZEC_USDT")
    unchanged_wild = runtime._entry_margin(sig, 1000.0, kind="WILDCARD", symbol="ZEC_USDT")
    assert halved_trend == pytest.approx(base_trend / 2.0, rel=1e-6)
    assert unchanged_wild == pytest.approx(base_wild)


def test_unset_sleeve_risk_pct_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_RISK_TARGETED", "1")
    monkeypatch.setenv("FUTURES_WILDCARD_RISK_PCT", "0.0241")
    for key in ("FUTURES_TREND_RISK_PCT", "FUTURES_SQUEEZE_RISK_PCT", "FUTURES_SNIPER_RISK_PCT"):
        monkeypatch.delenv(key, raising=False)
    runtime = _runtime(tmp_path, _Client())
    sig = _Sig()
    expected = 0.0241 * 1000.0 * 100.0 / 20.0
    for kind in ("WILDCARD", "TREND", "SQUEEZE", "SNIPER"):
        assert runtime._entry_margin(sig, 1000.0, kind=kind, symbol="ZEC_USDT") == pytest.approx(expected)


# --- P4: a set-but-inert safety variable must announce itself ------------------

def test_inert_drawdown_kill_warns_on_boot(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("USE_DRAWDOWN_KILL", "1")
    monkeypatch.delenv("FUTURES_CONVEX_DRAWDOWN_BRAKE", raising=False)
    runtime = _runtime(tmp_path, _Client())
    with caplog.at_level(logging.WARNING):
        assert runtime._warn_inert_drawdown_kill() is True
    assert any("USE_DRAWDOWN_KILL=1 has NO effect" in r.message for r in caplog.records)


def test_no_warning_when_the_brake_is_on_or_the_kill_is_off(tmp_path, monkeypatch, caplog):
    runtime = _runtime(tmp_path, _Client())
    monkeypatch.setenv("USE_DRAWDOWN_KILL", "1")
    monkeypatch.setenv("FUTURES_CONVEX_DRAWDOWN_BRAKE", "1")
    assert runtime._warn_inert_drawdown_kill() is False
    monkeypatch.delenv("USE_DRAWDOWN_KILL", raising=False)
    monkeypatch.delenv("FUTURES_CONVEX_DRAWDOWN_BRAKE", raising=False)
    assert runtime._warn_inert_drawdown_kill() is False
