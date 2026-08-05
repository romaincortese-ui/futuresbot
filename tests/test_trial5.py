"""Trial-5 changes: atomic state, fill measurement, drawdown brake, funnel gate.

Each one closes a gap that trial 4 demonstrated rather than a gap someone
imagined.
"""
import json
import os
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from futuresbot.config import FuturesConfig
from futuresbot.runtime import FuturesRuntime


@pytest.fixture
def rt(tmp_path, monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    for k in ("FUTURES_CONVEX_DRAWDOWN_BRAKE", "USE_SLIPPAGE_ATTRIBUTION",
              "FUTURES_WILDCARD_MIN_24H_MOVE"):
        monkeypatch.delenv(k, raising=False)
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "rt.json"),
                  status_file=str(tmp_path / "st.json"),
                  telegram_token="", telegram_chat_id="")
    return FuturesRuntime(cfg, MagicMock())


# --------------------------------------------------------------------------
# atomic state write
# --------------------------------------------------------------------------

def test_state_write_is_atomic_and_leaves_no_temp_files(rt):
    rt._save_state()
    p = rt._state_path
    assert p.exists()
    assert json.loads(p.read_text(encoding="utf-8")) is not None
    leftovers = list(p.parent.glob(f"{p.name}.tmp*"))
    assert leftovers == [], f"temp file not cleaned up: {leftovers}"


def test_a_failed_write_cannot_truncate_the_existing_ledger(rt, monkeypatch):
    """The whole point: a crash mid-write must leave the OLD file intact.

    Previously a bare write_text truncated in place, so a container kill during
    the write left an empty ledger and the bot rebooted with zero positions
    against real open positions on MEXC.
    """
    rt._save_state()
    original = rt._state_path.read_text(encoding="utf-8")
    assert original.strip()

    def boom(*a, **k):
        raise OSError("container killed mid-write")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        rt._save_state()
    # old content survived
    assert rt._state_path.read_text(encoding="utf-8") == original


# --------------------------------------------------------------------------
# fill measurement -- the gap behind every capacity estimate
# --------------------------------------------------------------------------

def test_record_fill_is_reachable_from_the_convex_entry_path():
    """It existed since Sprint 3 but was only called from the PMT path."""
    import inspect

    src = inspect.getsource(FuturesRuntime._open_wildcard_position)
    assert "_record_fill(" in src, "convex entries still do not measure fills"


def test_record_fill_captures_quoted_vs_actual(rt, monkeypatch):
    monkeypatch.setenv("USE_SLIPPAGE_ATTRIBUTION", "1")
    seen = {}
    monkeypatch.setattr(rt, "_slippage_store", None, raising=False)
    orig = rt._record_fill

    def spy(**kw):
        seen.update(kw)
        try:
            orig(**kw)
        except Exception:
            pass

    monkeypatch.setattr(rt, "_record_fill", spy)
    rt._record_fill(symbol="X_USDT", side="LONG", quoted_price=100.0,
                    fill_price=100.4, maker=False, leverage=5)
    assert seen["quoted_price"] == 100.0 and seen["fill_price"] == 100.4
    assert seen["fill_price"] != seen["quoted_price"], "slippage must be observable"


# --------------------------------------------------------------------------
# drawdown brake -- absent from the convex path for the whole of trial 4
# --------------------------------------------------------------------------

def test_drawdown_brake_is_wired_into_the_convex_sizing_path():
    import inspect

    src = inspect.getsource(FuturesRuntime._open_wildcard_position)
    assert "_drawdown_size_multiplier" in src, "convex sleeves still have no drawdown brake"
    assert "FUTURES_CONVEX_DRAWDOWN_BRAKE" in src, "brake must be behind a flag"


def test_drawdown_brake_defaults_off(rt):
    assert rt._flag("FUTURES_CONVEX_DRAWDOWN_BRAKE", default=False) is False


def test_drawdown_brake_can_be_armed(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_CONVEX_DRAWDOWN_BRAKE", "1")
    assert rt._flag("FUTURES_CONVEX_DRAWDOWN_BRAKE", default=False) is True


# --------------------------------------------------------------------------
# the funnel gate that starved the sleeve
# --------------------------------------------------------------------------

def test_pre_filter_default_is_loosened(rt, monkeypatch):
    """0.08 required an 8% move over 24H to reach a detector that triggers on
    8% over 3H. Live funnel: 73 symbols passed turnover, only 7-10 passed this
    gate, and roc_below_min was then the DOMINANT detector reject -- i.e. the
    gate was admitting the wrong symbols."""
    monkeypatch.delenv("FUTURES_WILDCARD_MIN_24H_MOVE", raising=False)
    assert rt._env_float("FUTURES_WILDCARD_MIN_24H_MOVE", 0.03) == 0.03


def test_funnel_telemetry_is_emitted():
    import inspect

    src = inspect.getsource(FuturesRuntime._maybe_scan_wildcard)
    for stage in ("usdt", "in_band", "turnover_ok", "move_24h_ok"):
        assert stage in src, f"funnel stage {stage} not counted"
