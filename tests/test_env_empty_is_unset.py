"""C26: an EMPTY env var reads as UNSET, never as OFF.

Blanking a Railway variable used to switch OFF every default-on switch read through
`FuturesRuntime._flag` or `config.env_bool` - among them FUTURES_CONVEX_RUNNER_TRAIL,
which also takes the 0.90R breakeven stop with it. Empty or whitespace-only now returns
the default; every other spelling parses exactly as before.
"""
from __future__ import annotations

import importlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from futuresbot import config as cfg_mod
from futuresbot import shadow_ledger
from futuresbot.config import FuturesConfig
from futuresbot.models import FuturesPosition
from futuresbot.replay.exits import _parse_flag
from futuresbot.runtime import FuturesRuntime

VAR = "FUTURES_C26_TEST_SWITCH"
TRUE_SPELLINGS = ("1", "true", "yes", "y", "on", " TRUE ", "On")
FALSE_SPELLINGS = ("0", "false", "no", "off", "n", "2", "enabled")    # today's parse: not in the set


def _runtime_flag(name, default):
    return FuturesRuntime._flag(name, default=default)


HELPERS = [_runtime_flag, cfg_mod.env_bool]
# module-local copies of the same parse that default-on switches are read through
LOCAL_HELPERS = [(m, fn) for m, fn in (
    ("calibration", "_env_bool"), ("dynamic_leverage", "_env_bool"), ("event_quality", "_env_bool"),
    ("opportunity_score", "_env_bool"), ("partial_bank", "_env_bool"), ("pmt_strategy", "_env_bool"),
    ("strategy", "_env_bool"), ("sniper", "_b"), ("wildcard", "_b"))]


@pytest.mark.parametrize("helper", HELPERS + [getattr(importlib.import_module(f"futuresbot.{m}"), fn)
                                              for m, fn in LOCAL_HELPERS])
@pytest.mark.parametrize("blank", ["", "   ", "\t"])
@pytest.mark.parametrize("default", [True, False])
def test_empty_or_whitespace_returns_the_default(monkeypatch, helper, blank, default):
    monkeypatch.setenv(VAR, blank)
    assert helper(VAR, default) is default


@pytest.mark.parametrize("helper", HELPERS)
@pytest.mark.parametrize("default", [True, False])
def test_unset_returns_the_default(monkeypatch, helper, default):
    monkeypatch.delenv(VAR, raising=False)
    assert helper(VAR, default) is default


@pytest.mark.parametrize("helper", HELPERS)
@pytest.mark.parametrize("raw", TRUE_SPELLINGS)
def test_true_spellings_are_unchanged(monkeypatch, helper, raw):
    monkeypatch.setenv(VAR, raw)
    assert helper(VAR, False) is True


@pytest.mark.parametrize("helper", HELPERS)
@pytest.mark.parametrize("raw", FALSE_SPELLINGS)
def test_false_spellings_are_unchanged(monkeypatch, helper, raw):
    monkeypatch.setenv(VAR, raw)
    assert helper(VAR, True) is False


@pytest.mark.parametrize("raw", ("", "   ", None) + TRUE_SPELLINGS + FALSE_SPELLINGS)
@pytest.mark.parametrize("default", [True, False])
def test_the_replay_mirror_parses_exactly_like_the_live_flag(monkeypatch, raw, default):
    if raw is None:
        monkeypatch.delenv(VAR, raising=False)
    else:
        monkeypatch.setenv(VAR, raw)
    assert _parse_flag(raw, default) is FuturesRuntime._flag(VAR, default=default)


def test_inline_default_on_reads_treat_blank_as_unset(monkeypatch):
    for name in ("FUTURES_TREND_TRAIL_ENABLED", "USE_FUTURES_FAIR_PRICE_WS"):
        monkeypatch.setenv(name, "  ")
    rt = object.__new__(FuturesRuntime)
    assert rt._futures_fair_price_ws_enabled() is True
    assert shadow_ledger.convex_trail_enabled("TREND") is True
    monkeypatch.setenv("USE_FUTURES_FAIR_PRICE_WS", "0")
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ENABLED", "off")
    assert rt._futures_fair_price_ws_enabled() is False                 # an explicit off still wins
    assert shadow_ledger.convex_trail_enabled("TREND") is False


# ---- the master trail switch, at the level it is read ----------------------------------

class _Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def cancel_all_tpsl(self, *, position_id=None, symbol=None, **kw):
        self.calls.append(("cancel", {"position_id": position_id, "symbol": symbol, **kw}))
        return {"success": True}

    def place_position_tpsl(self, **kw):
        self.calls.append(("place", kw))
        return {"success": True}

    def get_open_positions(self, symbol=None):
        return [{"positionType": 1, "holdVol": 10}]

    def get_account_asset(self, currency: str = "USDT"):
        return {"availableBalance": "1000", "equity": "1000"}

    def get_updates(self, *, offset=None, limit: int = 5, timeout: int = 0):
        return []


def _trail_runtime(tmp_path, monkeypatch, trail_value):
    monkeypatch.setenv("FUTURES_CONVEX_RUNNER_TRAIL", trail_value)
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setenv("FUTURES_CONVEX_BREAKEVEN_ARM_R", "0.90")
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "s.json"), status_file=str(tmp_path / "st.json"),
                  telegram_token="t", telegram_chat_id="1", paper_trade=False)
    client = _Client()
    rt = FuturesRuntime(cfg, client)
    rt._notify = lambda *a, **k: None
    rt._notify_once = lambda *a, **k: None
    rt._save_state = lambda: None
    pos = FuturesPosition(symbol="ZEC_USDT", side="LONG", entry_price=100.0, contracts=10,
                          contract_size=1.0, leverage=5, margin_usdt=200.0, tp_price=110.0,
                          sl_price=98.0, position_id="7", order_id="1",
                          opened_at=datetime.now(timezone.utc) - timedelta(minutes=20),
                          score=96.0, certainty=0.9, entry_signal="WILDCARD_LONG",
                          metadata={"wildcard": 1.0, "sl_margin_pct": 10.0})
    return rt, client, pos


def test_a_blank_master_trail_switch_keeps_the_trail_and_the_breakeven_stop(tmp_path, monkeypatch):
    rt, client, pos = _trail_runtime(tmp_path, monkeypatch, "")
    assert rt._trail_enabled_for(pos) is True
    rt._convex_runner_trail_exit(pos, 101.9)                      # +0.95R, past the 0.90R arm
    assert [c for c in client.calls if c[0] == "place"], "the breakeven stop must still move"
    assert pos.metadata["be_stop_price"] > 100.0
    assert pos.metadata["convex_peak_r"] == pytest.approx(0.95)   # the trail ran


def test_an_explicit_zero_still_switches_both_off(tmp_path, monkeypatch):
    rt, client, pos = _trail_runtime(tmp_path, monkeypatch, "0")
    assert rt._trail_enabled_for(pos) is False
    rt._convex_runner_trail_exit(pos, 101.9)
    assert client.calls == [] and "be_stop_price" not in pos.metadata


def test_main_py_production_defaults_treat_a_blank_value_as_unset():
    """Gate C26-m1: main.py's setdefault left a blank value in place, so ~40 switches that are ON
    in production still read a blank Railway variable as OFF."""
    import ast
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
    assert "os.environ.setdefault(" not in src
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_setdefault")
    ns = {"os": __import__("os")}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "main.py", "exec"), ns)
    env = {"A": "", "B": "   ", "C": "0", "D": "7"}
    import os
    old = {k: os.environ.get(k) for k in env}
    try:
        for k, v in env.items():
            os.environ[k] = v
        for k in env:
            ns["_setdefault"](k, "1")
        assert [os.environ[k] for k in "ABCD"] == ["1", "1", "0", "7"]
        os.environ.pop("E_UNSET_C26", None)
        ns["_setdefault"]("E_UNSET_C26", "1")
        assert os.environ.pop("E_UNSET_C26") == "1"
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
