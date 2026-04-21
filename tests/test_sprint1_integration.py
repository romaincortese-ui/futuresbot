"""Integration smoke test for Sprint 1 flags.

Ensures that when all Sprint 1 flags are ON, the futures config, strategy cost
gate, and runtime helpers import cleanly and behave as documented.
"""
from __future__ import annotations

import importlib

import pytest


SPRINT1_FLAGS = (
    "USE_NAV_RISK_SIZING",
    "USE_COST_BUDGET_RR",
    "USE_STRICT_RECV_WINDOW",
    "USE_LIQ_BUFFER_GUARD",
    "USE_HARD_LOSS_CAP_TIGHT",
    "USE_DRAWDOWN_KILL",
    "USE_SESSION_LEVERAGE",
)


@pytest.fixture(autouse=True)
def _clear_flags(monkeypatch):
    for flag in SPRINT1_FLAGS:
        monkeypatch.delenv(flag, raising=False)
    for name in (
        "STRICT_RECV_WINDOW_SECONDS",
        "HARD_LOSS_CAP_TIGHT_PCT",
        "NAV_RISK_PCT",
        "NAV_LEVERAGE_MIN",
        "NAV_LEVERAGE_MAX",
        "MIN_NET_RR",
        "LIQ_BUFFER_ATR_THRESHOLD",
        "DRAWDOWN_SOFT_PCT",
        "DRAWDOWN_HALT_PCT",
        "SESSION_FULL_LEVERAGE_CAP",
        "SESSION_ASIA_LEVERAGE_CAP",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


def _load_config():
    import futuresbot.config as cfg

    importlib.reload(cfg)
    return cfg


def test_strict_recv_window_clamps_when_flag_on(monkeypatch):
    monkeypatch.setenv("FUTURES_RECV_WINDOW_SECONDS", "30")
    monkeypatch.setenv("USE_STRICT_RECV_WINDOW", "1")
    cfg = _load_config()
    config = cfg.FuturesConfig.from_env()
    assert config.recv_window_seconds == 5


def test_strict_recv_window_noop_when_flag_off(monkeypatch):
    monkeypatch.setenv("FUTURES_RECV_WINDOW_SECONDS", "30")
    cfg = _load_config()
    config = cfg.FuturesConfig.from_env()
    assert config.recv_window_seconds == 30


def test_tight_hard_loss_cap_clamps_when_flag_on(monkeypatch):
    monkeypatch.setenv("FUTURES_HARD_LOSS_CAP_PCT", "0.75")
    monkeypatch.setenv("USE_HARD_LOSS_CAP_TIGHT", "1")
    cfg = _load_config()
    config = cfg.FuturesConfig.from_env()
    assert config.hard_loss_cap_pct == pytest.approx(0.40)


def test_tight_hard_loss_cap_respects_already_lower_value(monkeypatch):
    monkeypatch.setenv("FUTURES_HARD_LOSS_CAP_PCT", "0.30")
    monkeypatch.setenv("USE_HARD_LOSS_CAP_TIGHT", "1")
    cfg = _load_config()
    config = cfg.FuturesConfig.from_env()
    assert config.hard_loss_cap_pct == pytest.approx(0.30)


def test_cost_budget_gate_blocks_sub_economic_trade(monkeypatch):
    monkeypatch.setenv("USE_COST_BUDGET_RR", "1")
    monkeypatch.setenv("MIN_NET_RR", "1.8")
    import futuresbot.strategy as strategy

    importlib.reload(strategy)
    # Entry 100, TP 101.5 (+1.5%), SL 99.0 (−1.0%). At leverage 10 and default
    # funding + slippage the effective R:R is < 1.8 so the gate must block.
    assert not strategy._passes_cost_budget_gate(
        entry_price=100.0,
        tp_price=101.5,
        sl_price=99.0,
        leverage=10,
    )


def test_cost_budget_gate_passes_clean_trade(monkeypatch):
    monkeypatch.setenv("USE_COST_BUDGET_RR", "1")
    monkeypatch.setenv("MIN_NET_RR", "1.8")
    import futuresbot.strategy as strategy

    importlib.reload(strategy)
    assert strategy._passes_cost_budget_gate(
        entry_price=100.0,
        tp_price=104.0,
        sl_price=99.0,
        leverage=10,
    )


def test_cost_budget_gate_noop_when_flag_off():
    import futuresbot.strategy as strategy

    importlib.reload(strategy)
    # Same sub-economic trade as above — should pass because the gate is off.
    assert strategy._passes_cost_budget_gate(
        entry_price=100.0,
        tp_price=101.5,
        sl_price=99.0,
        leverage=10,
    )
