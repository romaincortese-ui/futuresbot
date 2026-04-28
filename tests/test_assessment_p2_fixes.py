"""Tests for assessment-driven P2 fixes.

Covers:
- §6 #11 — carry/basis monitor decommission (methods removed; deprecation
  warning emitted at boot for legacy env flags).
- §6 #12 — boot-time SYMBOL_NOTICE warning when SILVER/XAUT are active.
- §6 #13 — structured [AUDIT] JSON event emitter.
- §6 #14 — repo sync diff helper.
"""

from __future__ import annotations

import importlib
import json
import logging
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    import os

    for key in list(os.environ):
        if key.startswith("FUTURES_") or key.startswith("USE_") or key in {"MEXC_API_KEY", "MEXC_API_SECRET"}:
            monkeypatch.delenv(key, raising=False)
    yield


# ---------------------------------------------------------------------------
# §6 #11 — monitor decommission
# ---------------------------------------------------------------------------


def test_monitor_methods_removed_from_runtime():
    runtime = importlib.import_module("futuresbot.runtime")
    cls = runtime.FuturesRuntime
    assert not hasattr(cls, "_monitor_quarter2_funding_carry"), \
        "Legacy carry monitor should be removed per P2 §6 #11"
    assert not hasattr(cls, "_monitor_quarter2_basis"), \
        "Legacy basis monitor should be removed per P2 §6 #11"


def test_warn_deprecated_monitor_flags_logs_when_set(monkeypatch, caplog):
    runtime = importlib.import_module("futuresbot.runtime")
    monkeypatch.setenv("USE_FUNDING_CARRY_MONITOR", "1")
    rt = SimpleNamespace(_warn_deprecated_monitor_flags=runtime.FuturesRuntime._warn_deprecated_monitor_flags)
    with caplog.at_level(logging.WARNING):
        runtime.FuturesRuntime._warn_deprecated_monitor_flags(rt)  # type: ignore[arg-type]
    assert any("[DEPRECATED]" in rec.message for rec in caplog.records)


def test_warn_deprecated_monitor_flags_silent_when_unset(caplog):
    runtime = importlib.import_module("futuresbot.runtime")
    rt = SimpleNamespace()
    with caplog.at_level(logging.WARNING):
        runtime.FuturesRuntime._warn_deprecated_monitor_flags(rt)  # type: ignore[arg-type]
    assert not any("[DEPRECATED]" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# §6 #12 — SILVER/XAUT advisory warning
# ---------------------------------------------------------------------------


def test_warn_unsuitable_symbols_flags_silver_xaut(caplog):
    runtime = importlib.import_module("futuresbot.runtime")
    rt = SimpleNamespace(_active_symbols=("BTC_USDT", "SILVER_USDT", "XAUT_USDT"))
    with caplog.at_level(logging.WARNING):
        runtime.FuturesRuntime._warn_unsuitable_symbols(rt)  # type: ignore[arg-type]
    matches = [r for r in caplog.records if "[SYMBOL_NOTICE]" in r.message]
    assert len(matches) == 1
    assert "SILVER_USDT" in matches[0].message
    assert "XAUT_USDT" in matches[0].message


def test_warn_unsuitable_symbols_silent_when_clean(caplog):
    runtime = importlib.import_module("futuresbot.runtime")
    rt = SimpleNamespace(_active_symbols=("BTC_USDT", "ETH_USDT"))
    with caplog.at_level(logging.WARNING):
        runtime.FuturesRuntime._warn_unsuitable_symbols(rt)  # type: ignore[arg-type]
    assert not any("[SYMBOL_NOTICE]" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# §6 #13 — structured [AUDIT] JSON event
# ---------------------------------------------------------------------------


def test_emit_audit_event_writes_parseable_json(caplog):
    runtime = importlib.import_module("futuresbot.runtime")
    rt = SimpleNamespace(config=SimpleNamespace(paper_trade=True))
    with caplog.at_level(logging.INFO):
        runtime.FuturesRuntime._emit_audit_event(  # type: ignore[arg-type]
            rt, "ENTRY", {"symbol": "BTC_USDT", "side": "LONG", "leverage": 5}
        )
    audit_lines = [r.message for r in caplog.records if "[AUDIT]" in r.message]
    assert len(audit_lines) == 1
    json_part = audit_lines[0].split("[AUDIT] ", 1)[1]
    parsed = json.loads(json_part)
    assert parsed["event_type"] == "ENTRY"
    assert parsed["mode"] == "paper"
    assert parsed["payload"]["symbol"] == "BTC_USDT"
    assert parsed["payload"]["leverage"] == 5
    assert parsed["schema_version"] == 1


def test_emit_audit_event_swallows_unserialisable_payload(caplog):
    runtime = importlib.import_module("futuresbot.runtime")
    rt = SimpleNamespace(config=SimpleNamespace(paper_trade=False))

    class _NotJsonable:
        def __repr__(self):
            raise RuntimeError("boom")

    # Default str-fallback should still produce *something* without raising.
    with caplog.at_level(logging.DEBUG):
        runtime.FuturesRuntime._emit_audit_event(  # type: ignore[arg-type]
            rt, "WEIRD", {"x": _NotJsonable()}
        )
    # No exception escaped. Either an [AUDIT] line was produced (default=str
    # succeeded) or a debug "Audit emit failed" line was logged.
    assert any("[AUDIT]" in r.message or "Audit emit failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# §6 #14 — repo sync helper
# ---------------------------------------------------------------------------


def _load_sync_module():
    # Lazy import so the test still passes if the module path moves.
    repo_root = Path(__file__).resolve().parents[1]
    tools_dir = repo_root / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    return importlib.import_module("check_repo_sync")


def _make_pkg(root: Path, files: dict[str, str]):
    pkg = root / "futuresbot"
    pkg.mkdir(parents=True)
    for rel, content in files.items():
        target = pkg / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


def test_diff_packages_detects_drift(tmp_path):
    sync = _load_sync_module()
    a = tmp_path / "standalone"
    b = tmp_path / "vendored"
    _make_pkg(a, {"runtime.py": "x = 1\n", "config.py": "y = 1\n", "extra.py": "z = 1\n"})
    _make_pkg(b, {"runtime.py": "x = 2\n", "config.py": "y = 1\n"})
    only_a, only_b, modified = sync.diff_packages(a, b)
    only_a_names = {p.as_posix() for p in only_a}
    modified_names = {p.as_posix() for p in modified}
    assert only_a_names == {"extra.py"}
    assert only_b == []
    assert modified_names == {"runtime.py"}


def test_diff_packages_clean(tmp_path):
    sync = _load_sync_module()
    a = tmp_path / "standalone"
    b = tmp_path / "vendored"
    files = {"runtime.py": "x = 1\n", "config.py": "y = 1\n"}
    _make_pkg(a, files)
    _make_pkg(b, files)
    only_a, only_b, modified = sync.diff_packages(a, b)
    assert only_a == [] and only_b == [] and modified == []


def test_diff_packages_skips_pycache(tmp_path):
    sync = _load_sync_module()
    a = tmp_path / "standalone"
    b = tmp_path / "vendored"
    _make_pkg(a, {"runtime.py": "x = 1\n"})
    _make_pkg(b, {"runtime.py": "x = 1\n"})
    # Add a __pycache__ noise file with different bytes — must be ignored.
    (a / "futuresbot" / "__pycache__").mkdir()
    (a / "futuresbot" / "__pycache__" / "runtime.cpython-311.pyc").write_bytes(b"\x00\x01")
    (b / "futuresbot" / "__pycache__").mkdir()
    (b / "futuresbot" / "__pycache__" / "runtime.cpython-311.pyc").write_bytes(b"\xff")
    only_a, only_b, modified = sync.diff_packages(a, b)
    assert (only_a, only_b, modified) == ([], [], [])
