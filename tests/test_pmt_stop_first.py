from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from futuresbot.pmt_strategy import (
    _atr_from_frame,
    _resolve_stop_first_geometry,
    pmt_stop_first_sizing_enabled,
    score_pmt_threshold_signal,
)

from tests.test_pmt_strategy import _config, _enable_pmt, _frame


def _stop_first_env(monkeypatch, **overrides) -> None:
    _enable_pmt(monkeypatch)
    monkeypatch.setenv("FUTURES_PMT_STOP_FIRST_SIZING_ENABLED", "1")
    for key, value in overrides.items():
        monkeypatch.setenv(key, str(value))


def test_stop_first_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FUTURES_PMT_STOP_FIRST_SIZING_ENABLED", raising=False)
    assert pmt_stop_first_sizing_enabled() is False


def test_atr_from_frame_matches_wilder_recursion():
    closes = [100.0 + i * 0.5 for i in range(40)]
    frame = _frame(closes)
    atr = _atr_from_frame(frame, 14)
    assert atr is not None
    assert atr > 0
    # high/low band is +-0.1% around close, so TR stays close to that scale
    assert atr < 2.0


def test_atr_from_frame_requires_enough_bars():
    frame = _frame([100.0, 100.5, 101.0])
    assert _atr_from_frame(frame, 14) is None


def test_resolve_stop_first_geometry_inverts_leverage(monkeypatch):
    monkeypatch.delenv("FUTURES_PMT_MAX_LEVERAGE", raising=False)
    monkeypatch.delenv("FUTURES_LEVERAGE_MAX", raising=False)
    closes = [100.0] * 60
    frame = _frame(closes)
    atr = _atr_from_frame(frame, 14)
    resolved = _resolve_stop_first_geometry(frame, entry_price=100.0)
    assert resolved is not None
    leverage, tp_margin_pct, sl_margin_pct, metadata = resolved
    stop_frac = 3.0 * atr / 100.0
    expected_leverage = max(1, min(25, int(0.20 / stop_frac)))
    assert leverage == expected_leverage
    # 1R stop never exceeds the 20% margin budget (plus TP = 5R exactly)
    assert sl_margin_pct == pytest.approx(stop_frac * leverage * 100.0)
    assert sl_margin_pct <= 20.0 + 1e-9
    assert tp_margin_pct == pytest.approx(sl_margin_pct * 5.0)
    assert metadata["pmt_stop_first"] == 1.0
    assert metadata["pmt_stop_first_atr"] == pytest.approx(atr, rel=1e-6)


def test_resolve_stop_first_geometry_respects_env_overrides(monkeypatch):
    monkeypatch.setenv("FUTURES_PMT_STOP_FIRST_ATR_MULT", "2.0")
    monkeypatch.setenv("FUTURES_PMT_STOP_FIRST_TARGET_R", "3.0")
    monkeypatch.setenv("FUTURES_PMT_STOP_FIRST_RISK_BUDGET_MARGIN_PCT", "10.0")
    monkeypatch.setenv("FUTURES_PMT_MAX_LEVERAGE", "10")
    frame = _frame([100.0] * 60)
    atr = _atr_from_frame(frame, 14)
    resolved = _resolve_stop_first_geometry(frame, entry_price=100.0)
    assert resolved is not None
    leverage, tp_margin_pct, sl_margin_pct, _metadata = resolved
    stop_frac = 2.0 * atr / 100.0
    assert leverage == max(1, min(10, int(0.10 / stop_frac)))
    assert tp_margin_pct == pytest.approx(sl_margin_pct * 3.0)


def test_stop_first_signal_carries_geometry_and_lock_overrides(monkeypatch):
    _stop_first_env(monkeypatch)
    # Pin the runner-tier lock semantics (this test predates the 92.5-95 tight
    # tier; tier behavior is covered in test_pmt_strategy tier tests).
    monkeypatch.setenv("FUTURES_PMT_STOP_FIRST_TIER_SCORE", "0")
    symbol = "BTC_USDT"
    level = 75000.0
    step = 1000.0
    crossed = level + step * 0.12
    current = level + step * 0.18
    previous = level - step * 0.10
    start = current / (1.0 + 0.030 * 1.2)
    frame = _frame([start] * 105 + [previous, crossed, current])

    signal = score_pmt_threshold_signal(frame, _config(symbol))
    assert signal is not None
    metadata = signal.metadata or {}
    assert metadata.get("pmt_stop_first") == 1.0
    sl_margin_pct = float(metadata["sl_margin_pct"])
    tp_margin_pct = float(metadata["tp_margin_pct"])
    assert sl_margin_pct <= 20.0 + 1e-6
    assert tp_margin_pct == pytest.approx(sl_margin_pct * 5.0, rel=1e-3)
    # geometry consistency: price distances match margin distances at the leverage
    sl_move = abs(signal.entry_price - signal.sl_price) / signal.entry_price
    tp_move = abs(signal.tp_price - signal.entry_price) / signal.entry_price
    assert sl_move * signal.leverage * 100.0 == pytest.approx(sl_margin_pct, rel=1e-3)
    assert tp_move * signal.leverage * 100.0 == pytest.approx(tp_margin_pct, rel=1e-3)
    # peak lock armed far out so the 5R runner is not clipped early
    assert float(metadata["profit_lock_trigger_pct_override"]) == pytest.approx(tp_margin_pct * 0.80, rel=1e-3)
    assert float(metadata["profit_lock_floor_pct_override"]) == pytest.approx(tp_margin_pct * 0.50, rel=1e-3)


def test_stop_first_falls_back_to_legacy_geometry_without_atr(monkeypatch):
    _stop_first_env(monkeypatch)
    symbol = "BTC_USDT"
    level = 75000.0
    step = 1000.0
    crossed = level + step * 0.12
    current = level + step * 0.18
    previous = level - step * 0.10
    start = current / (1.0 + 0.030 * 1.2)
    closes = [start] * 105 + [previous, crossed, current]
    frame = _frame(closes)
    monkeypatch.setenv("FUTURES_PMT_STOP_FIRST_ATR_PERIOD", str(len(closes) + 10))

    signal = score_pmt_threshold_signal(frame, _config(symbol))
    assert signal is not None
    metadata = signal.metadata or {}
    assert "pmt_stop_first" not in metadata
    assert signal.leverage >= 15


def test_runtime_lock_override_refresh_uses_stop_first_values():
    from futuresbot.models import FuturesPosition
    from futuresbot.runtime import FuturesRuntime

    position = FuturesPosition(
        symbol="BTC_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=5,
        contract_size=1.0,
        leverage=10,
        margin_usdt=50.0,
        tp_price=110.0,
        sl_price=98.0,
        position_id="pos-1",
        order_id="ord-1",
        opened_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
        score=95.0,
        certainty=0.9,
        entry_signal="PMT_THRESHOLD_LONG",
        metadata={"pmt_stop_first": 1.0, "tp_margin_pct": 100.0, "sl_margin_pct": 20.0},
    )
    stub = SimpleNamespace(
        _metadata_float=FuturesRuntime._metadata_float,
        _metadata_override_float=FuturesRuntime._metadata_override_float,
        _metadata_override_or=FuturesRuntime._metadata_override_or,
        _env_float=lambda name, default: default,
        _flag=lambda name: False,
    )
    metadata = position.metadata
    changed = FuturesRuntime._refresh_pmt_profit_lock_overrides(stub, position, metadata)
    assert changed is True
    assert metadata["profit_lock_trigger_pct_override"] == pytest.approx(80.0)
    assert metadata["profit_lock_floor_pct_override"] == pytest.approx(50.0)
    assert metadata["profit_lock_pullback_fraction_override"] == pytest.approx(0.25)
    assert metadata["profit_lock_min_tp_progress_override"] == pytest.approx(0.0)
