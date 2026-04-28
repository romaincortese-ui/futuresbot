"""Tests for assessment-driven P0 fixes (data window + env-key hygiene)."""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    # Clear any FUTURES_* env that could leak across tests in this module.
    import os

    for key in list(os.environ):
        if key.startswith("FUTURES_") or key in {"MEXC_API_KEY", "MEXC_API_SECRET"}:
            monkeypatch.delenv(key, raising=False)
    yield


def _config_module():
    return importlib.import_module("futuresbot.config")


# ---------------------------------------------------------------------------
# P0 §3.2 — env-key hygiene validator
# ---------------------------------------------------------------------------


def test_detect_misnamed_env_keys_flags_natural_underscore_form(monkeypatch):
    cfg = _config_module()
    monkeypatch.setenv("FUTURES_PEPE_USDT_LEVERAGE_MAX", "25")
    findings = cfg.detect_misnamed_symbol_env_keys(("PEPE_USDT",))
    assert findings == [("FUTURES_PEPE_USDT_LEVERAGE_MAX", "FUTURES_PEPEUSDT_LEVERAGE_MAX")]


def test_detect_misnamed_env_keys_clean_when_canonical(monkeypatch):
    cfg = _config_module()
    monkeypatch.setenv("FUTURES_PEPEUSDT_LEVERAGE_MAX", "25")
    assert cfg.detect_misnamed_symbol_env_keys(("PEPE_USDT",)) == []


def test_detect_misnamed_env_keys_skips_when_both_present(monkeypatch):
    """If the canonical key is also set the natural one is not silently
    dropped — the canonical wins, so no need to fail BOOT."""
    cfg = _config_module()
    monkeypatch.setenv("FUTURES_PEPE_USDT_LEVERAGE_MAX", "25")
    monkeypatch.setenv("FUTURES_PEPEUSDT_LEVERAGE_MAX", "25")
    assert cfg.detect_misnamed_symbol_env_keys(("PEPE_USDT",)) == []


def test_detect_misnamed_env_keys_ignores_symbols_without_underscore(monkeypatch):
    cfg = _config_module()
    # BTCUSDT has no underscore; FUTURES_BTCUSDT_* IS canonical, nothing to flag.
    monkeypatch.setenv("FUTURES_BTCUSDT_LEVERAGE_MAX", "20")
    assert cfg.detect_misnamed_symbol_env_keys(("BTCUSDT",)) == []


def test_from_env_raises_on_misnamed_per_symbol_key(monkeypatch):
    cfg = _config_module()
    monkeypatch.setenv("FUTURES_SYMBOLS", "PEPE_USDT")
    monkeypatch.setenv("FUTURES_PEPE_USDT_LEVERAGE_MAX", "25")
    with pytest.raises(cfg.MisnamedSymbolEnvKeyError) as excinfo:
        cfg.FuturesConfig.from_env()
    assert "FUTURES_PEPEUSDT_LEVERAGE_MAX" in str(excinfo.value)
    assert "FUTURES_PEPE_USDT_LEVERAGE_MAX" in str(excinfo.value)


def test_from_env_can_be_bypassed_with_disable_flag(monkeypatch):
    cfg = _config_module()
    monkeypatch.setenv("FUTURES_SYMBOLS", "PEPE_USDT")
    monkeypatch.setenv("FUTURES_PEPE_USDT_LEVERAGE_MAX", "25")
    monkeypatch.setenv("FUTURES_DISABLE_ENV_KEY_VALIDATION", "1")
    # Should not raise; the misnamed key remains silently ignored as before
    # (the bypass exists for emergencies, not as an endorsed posture).
    instance = cfg.FuturesConfig.from_env()
    assert instance.symbols == ("PEPE_USDT",)


# ---------------------------------------------------------------------------
# P0 §1 — data window must be wide enough for the strategy gate
# ---------------------------------------------------------------------------


def test_fetch_signal_window_covers_strategy_minimum_1h_bars():
    """The runtime fetch window must yield >=120 1h bars after resampling.

    The strategy hard-rejects with `insufficient_1h_bars=<n><120` if not.
    With a 15-min frame, that is >= 120 hours = >= 480 15-min bars. The
    runtime should target >= 1.25x of that for ATR/ADX/EMA100 warm-up.
    """
    import inspect

    runtime_module = importlib.import_module("futuresbot.runtime")
    src = inspect.getsource(runtime_module)
    # The token "900 * 720" encodes a 180h window (≈ 7.5 days, ~720 15-min
    # bars, ~180 1h bars after resample). Anything shorter than 900*480
    # fails the strategy gate. We assert the actual deployed value to
    # prevent silent regressions back to 900 * 260 (the bug fixed here).
    assert "900 * 720" in src, (
        "Futures runtime fetch window has been narrowed below the strategy "
        "minimum (>=120 1h bars after resample). See assessment §1."
    )
    assert "900 * 260" not in src, (
        "Regression: the broken 65h window (900 * 260) is back in runtime.py."
    )
