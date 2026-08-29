"""The two flags that decide which exit stack the live convex sleeves run.

Both have code defaults that select the OTHER stack, both read like stale
trial-era config, and until 2026-08-29 neither was documented. The dangerous
property found by the health review is that NOTHING IN THIS SUITE FAILED when
either was cleared: every _hourly_exit test runs with FUTURES_STRATEGY_MODE
unset, so the suite's default posture was the broken configuration. 1046 tests
stayed green while live trades would have started being cut at ~-0.1R.

These tests exist to make that impossible: they pin the blast radius of each
flag, and they pin the boot warnings that announce a deviation. They do not
assert what production is set to - a test cannot see Railway - they assert that
the alarm still works and that the gating still means what the docs say.

See docs/LIVE_CONFIG.md section 6.
"""
from __future__ import annotations

import logging

import pytest

from futuresbot.runtime import FuturesRuntime
from tests.test_trail_ratchet import _pos, rt  # noqa: F401  (shared fixtures)


# --- flag 1: FUTURES_WILDCARD_CONVEX_EXIT_ENABLED --------------------------

def test_convex_flag_off_disables_the_retention_trail(rt, monkeypatch):  # noqa: F811
    """Clearing it removes the exit that does most of the live work.

    MAGMA (+2.93R), HNT (+0.61R) and BLESS (+0.69R) all closed on
    CONVEX_RETENTION_TRAIL. With the flag off none of them would have.
    """
    monkeypatch.delenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", raising=False)
    monkeypatch.setattr(rt, "_close_position_for_exit", lambda p, **k: True)
    monkeypatch.setattr(rt, "_save_state", lambda *a, **k: None)
    monkeypatch.setattr(rt, "_maybe_record_peak_notify", lambda *a, **k: None)
    p = _pos()
    # a price that WOULD trail out with the flag on (see test_trail_ratchet)
    assert rt._convex_runner_trail_exit(p, 135.0) is False
    assert rt._convex_runner_trail_exit(p, 125.0) is False, \
        "the retention trail fired with the convex flag OFF"


def test_convex_flag_off_rearms_the_discretionary_locks(rt, monkeypatch):  # noqa: F811
    """It does not merely disable a feature - it swaps in the other stack.

    _skips_discretionary_locks is what enforces floor-not-bank. With the flag
    off, the margin-percent profit-lock and micro-lock family comes back on
    every convex position, which is the early banking this project measured as
    harmful.
    """
    p = _pos()
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    assert rt._is_wildcard_convex(p) is True
    assert rt._skips_discretionary_locks(p) is True

    monkeypatch.delenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", raising=False)
    assert rt._is_wildcard_convex(p) is False
    assert rt._skips_discretionary_locks(p) is False, \
        "the discretionary profit-lock stack is armed on a convex position"


def test_convex_flag_code_default_is_off(rt, monkeypatch):  # noqa: F811
    """Stated as a test because it is the surprising half: UNSET means OFF.

    Anyone reasoning 'the variable is not set, so the default applies, so the
    convex exits run' has it backwards.
    """
    monkeypatch.delenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", raising=False)
    assert rt._flag("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", default=False) is False


# --- flag 2: FUTURES_STRATEGY_MODE -----------------------------------------

def test_strategy_mode_gates_the_legacy_exit_stack(monkeypatch):
    """pmt_strategy_enabled() is the only thing holding back six unguarded
    exits in _hourly_exit. It reads as leftover PMT config."""
    from futuresbot.pmt_strategy import pmt_strategy_enabled

    monkeypatch.setenv("FUTURES_STRATEGY_MODE", "pmt_threshold")
    assert pmt_strategy_enabled() is True
    monkeypatch.setenv("FUTURES_STRATEGY_MODE", "")
    assert pmt_strategy_enabled() is False


# --- the boot alarms -------------------------------------------------------

def _boot_warnings(rt, caplog) -> str:  # noqa: F811
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="futuresbot.runtime"):
        try:
            rt._log_boot_manifest()
        except Exception:            # the manifest touches config we do not stub
            pass
    return "\n".join(r.getMessage() for r in caplog.records)


def test_boot_warns_when_the_convex_flag_is_off(rt, monkeypatch, caplog):  # noqa: F811
    monkeypatch.delenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", raising=False)
    monkeypatch.setenv("FUTURES_STRATEGY_MODE", "pmt_threshold")
    assert "FUTURES_WILDCARD_CONVEX_EXIT_ENABLED is OFF" in _boot_warnings(rt, caplog)


def test_boot_warns_when_strategy_mode_is_cleared(rt, monkeypatch, caplog):  # noqa: F811
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setenv("FUTURES_STRATEGY_MODE", "")
    assert "is NOT 'pmt_threshold'" in _boot_warnings(rt, caplog)


def test_boot_is_quiet_when_both_flags_are_correct(rt, monkeypatch, caplog):  # noqa: F811
    """The alarm must not cry wolf, or it will be tuned out."""
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setenv("FUTURES_STRATEGY_MODE", "pmt_threshold")
    out = _boot_warnings(rt, caplog)
    assert "FUTURES_WILDCARD_CONVEX_EXIT_ENABLED is OFF" not in out
    assert "is NOT 'pmt_threshold'" not in out
