"""Trial 27 - WILDCARD only, TREND not traded (wc/TRIAL27/PREREG.md, sha256 28ea4eadd078f6ba...).

FUTURES_RANDOM_TREND_SOURCE gains "off": the 15m L0 evaluation and its log run exactly as under
"natural", every firing is logged with decision "trend_off" and nothing opens - not at the 15m
closes, not at the 6h ticks, not from the legacy TREND scan. WILDCARD and FX90 are trial 26's.
Unset = trial 25 and natural = trial 26 stay pinned, unchanged, by tests/test_random_mode.py and
tests/test_random_trend_natural.py.
"""
from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import pytest

import futuresbot.runtime as R
from futuresbot import random_mode as RM
from tests.test_random_mode import (  # noqa: F401  (live_env is a fixture)
    T, FakeClient, _cand, _on, _plan, _pos, _rt, _scan, _sig, _tick_runtime, live_env)
from tests.test_random_trend_natural import (
    MILD, S, T26_ENV, UP, UP2, _ext, _fx, _log, _long, _series_runtime, _walk)

T27_ENV = {**T26_ENV, "FUTURES_RANDOM_TREND_SOURCE": "off"}
OFF = {"FUTURES_RANDOM_TREND_SOURCE": "off"}


def _t27(monkeypatch, **extra):
    for k, v in {**T27_ENV, **extra}.items():
        monkeypatch.setenv(k, v)


# =====================================================================================
# the setting and the tag
# =====================================================================================

def test_the_trial_27_configuration_and_its_tag(live_env):
    _t27(live_env)
    cfg = RM.config()
    assert cfg.valid and cfg.trend_off and cfg.trend_event and not cfg.trend_natural and cfg.fx90_on
    assert cfg.prereg == RM.PREREG27_TAG == "28ea4eadd078f6ba" and cfg.trial == "trial 27"
    assert RM.PREREG27_SHA256 == "28ea4eadd078f6baffaeb80c72dfd5e89f496bcbf3708f68246306590983c9de"
    assert cfg.fields() == {"random_tick_hours": 6.0, "random_side_mode": "natural",
                            "random_trend_sl_mult": 3.5, "random_wc_min_turnover": 2e6}
    assert cfg.event_fields() == {"random_trend_source": "off", "random_fx90": "on"}
    d = cfg.describe()
    assert "TREND source off (TREND off (logged only): L0 at every 15m close, never traded)" in d
    assert "FX90 on" in d and d.endswith("PREREG 28ea4eadd078f6ba")
    live_env.setenv("FUTURES_RANDOM_TREND_SOURCE", " off ")            # surrounding spaces ignored
    assert RM.config() == cfg
    # trials 24 / 25 / 26 keep their tags; the map gains exactly one key
    assert RM.REGISTERED == {
        (12, "coin", 3.0, 2_000_000.0, "tick", "off"): "29fabd853a4f5d77",
        (6, "natural", 3.5, 2_000_000.0, "tick", "off"): "23840ce65807b549",
        (6, "natural", 3.5, 2_000_000.0, "natural", "on"): "cbbff32d4bf5d887",
        (6, "natural", 3.5, 2_000_000.0, "off", "on"): "28ea4eadd078f6ba"}
    live_env.setenv("FUTURES_RANDOM_TREND_SOURCE", "natural")           # REVERT = trial 26
    assert RM.config().prereg == RM.PREREG26_TAG and RM.config().trial == "trial 26"


@pytest.mark.parametrize("env", [
    {"FUTURES_RANDOM_FX90": "off"},
    {"FUTURES_RANDOM_FX90": ""},                                        # blank = off
    {"FUTURES_TREND_SL_ATR_MULT": "3.0"},
    {"FUTURES_RANDOM_TICK_HOURS": "12"},
    {"FUTURES_RANDOM_SIDE_MODE": "coin"},
    {"FUTURES_RANDOM_WC_MIN_TURNOVER": "10000000"},
])
def test_off_in_any_other_combination_is_unregistered(live_env, env):
    _t27(live_env, **env)
    cfg = RM.config()
    assert cfg.valid and cfg.trend_off and cfg.prereg == RM.UNREGISTERED and cfg.trial == "UNREGISTERED"


@pytest.mark.parametrize("raw", ["Off", "OFF", "none", "0", "false", "disabled", "no", "logged"])
def test_an_invalid_value_still_stops_trading_with_an_alert(tmp_path, live_env, raw):
    _t27(live_env, FUTURES_RANDOM_TREND_SOURCE=raw)
    cfg = RM.config()
    assert not cfg.valid and cfg.errors == (
        f"FUTURES_RANDOM_TREND_SOURCE={raw!r} (allowed: tick, natural, off)",)
    calls: list = []
    clock = {"now": T + 30}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    rt = _tick_runtime(tmp_path, live_env, calls)
    sent: list = []
    rt._notify_once = lambda key, msg, **k: sent.append(key)
    rt._maybe_random_tick()
    assert calls == [] and not rt._random_mode_state and sent == [f"random_config_invalid_{T}"]
    rt._random_trend_select = lambda s, c: pytest.fail("evaluated with invalid settings")
    clock["now"] = S + 2
    rt._maybe_random_trend_eval()
    assert not rt._random_trend_state and not (tmp_path / "futures_random_trend_evals.jsonl").exists()
    assert "invalid settings" in rt._random_mode_status_line()


# =====================================================================================
# the 15m evaluation: logged as under natural, nothing opens
# =====================================================================================

def test_every_firing_is_logged_trend_off_and_nothing_opens(tmp_path, live_env):
    series = {"ETH_USDT": _ext(UP), "XRP_USDT": _ext(UP2), "ZEC_USDT": _ext(MILD)}
    clock = {"now": S + 2}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    rt, client = _series_runtime(tmp_path, live_env, series, env=OFF)
    assert RM.config().prereg == RM.PREREG27_TAG
    rt._random_open = lambda *a, **k: pytest.fail("a TREND entry was attempted")
    rt._btc_exhaustion_flag = lambda asof=None: pytest.fail("no attempt: the BTC flag is not read")
    rt._maybe_random_trend_eval()
    assert client.orders == [] and rt.open_positions == {}
    (row,) = _log(tmp_path)
    assert (row["s"], row["s_utc"], row["prereg"], row["trigger"], row["paused"]) == \
        (S, "2026-10-02T12:45:00Z", RM.PREREG27_TAG, "L0", False)
    assert (row["random_trend_source"], row["random_fx90"], row["random_tick_hours"]) == ("off", "on", 6.0)
    assert [(r["symbol"], r["fire"], r["decision"]) for r in row["rows"]] == [
        ("ETH_USDT", True, "trend_off"), ("XRP_USDT", True, "trend_off"), ("ZEC_USDT", False, "no_fire")]
    assert [(d["decision"], d["symbol"], d["rank"], d["status"]) for d in row["decisions"]] == [
        ("trend_off", "ETH_USDT", 1, "trigger"), ("trend_off", "XRP_USDT", 2, "trigger")]
    eth = RM.trend_eval_row("ETH_USDT", client.klines["ETH_USDT"], S)    # the same L0 as natural
    assert row["rows"][0]["new_high"] is True and row["rows"][0]["prio"] == pytest.approx(eth["roc24h"])
    assert row["book"] == {"held": [], "trend_open": 0, "trend_slots": 2} and row["btc_flag"] is None
    assert json.loads((tmp_path / "state.json").read_text())["random_trend"]["last_eval"] == S
    assert rt._random_trend_state["summary"] == "trend_off:ETH_USDT, trend_off:XRP_USDT"
    # once only: same process, and after a restart
    clock["now"] = S + 60
    rt._maybe_random_trend_eval()
    rt2 = _rt(tmp_path, client)
    rt2._trend_rotation_symbol = lambda: None
    clock["now"] = S + 120
    rt2._maybe_random_trend_eval()
    assert len(_log(tmp_path)) == 1
    # every later close is logged, paused or not, and nothing ever opens
    clock["now"] = S + 900 + 2
    rt._maybe_random_trend_eval()
    rt._paused = True
    clock["now"] = S + 1800 + 2
    rt._maybe_random_trend_eval()
    rows = _log(tmp_path)
    assert [r["s"] for r in rows] == [S, S + 900, S + 1800]
    assert [r["paused"] for r in rows] == [False, False, True]
    for r in rows:
        fired = [x for x in r["rows"] if x["fire"]]
        assert fired and all(x["decision"] == "trend_off" for x in fired)
        assert [d["decision"] for d in r["decisions"]] == ["trend_off"] * len(fired)
    assert client.orders == [] and rt.open_positions == {}


def test_held_symbols_and_the_book_are_still_logged(tmp_path, live_env):
    series = {"ETH_USDT": _ext(UP), "XRP_USDT": _ext(UP2), "ZEC_USDT": _ext(MILD)}
    live_env.setattr(R.time, "time", lambda: S + 2)
    rt, client = _series_runtime(tmp_path, live_env, series, env=OFF)
    rt.open_positions["ETH_USDT"] = _pos("ETH_USDT", "WILDCARD")       # a WILDCARD holds ETH
    rt._maybe_random_trend_eval()
    (row,) = _log(tmp_path)
    assert row["book"] == {"held": ["ETH_USDT"], "trend_open": 0, "trend_slots": 2}
    assert [r["decision"] for r in row["rows"]] == ["trend_off", "trend_off", "no_fire"]
    assert client.orders == [] and list(rt.open_positions) == ["ETH_USDT"]


# =====================================================================================
# no code path can open TREND
# =====================================================================================

def test_no_trend_entry_path_can_open_under_off(tmp_path, live_env):
    _on(live_env)
    _t27(live_env)
    client = FakeClient({"ETH_USDT": 100.0})
    client.get_contract_detail = lambda s: pytest.fail("an exchange call on a TREND entry path")
    rt = _rt(tmp_path, client)
    cand = _cand("ETH_USDT", "TREND", 0.09, status="trigger")
    plan = _plan({"TREND": [cand]})
    plan["config"] = RM.config()
    # the last guard: _random_open itself (both callers: the tick and the 15m evaluation)
    for p in (plan, {k: v for k, v in plan.items() if k != "config"}):   # with or without the plan's read
        d = rt._random_open(p, "TREND", cand, 1, 1, None, [], side="LONG")
        assert d["decision"] == "trend_off" and d["symbol"] == "ETH_USDT"
    # the 15m evaluation without its config read: the live settings say off
    ev = {"tick": S, "rows": [{"symbol": "ETH_USDT", "usable": True, "fire": True, "prio": 0.1}],
          "frames": {"WILDCARD": {}, "TREND": {}}, "config": None}
    assert [d["decision"] for d in rt._random_trend_execute(ev)] == ["trend_off"]
    # the legacy path (no tick context) refuses as in every random-mode trial
    assert rt._open_wildcard_position(_sig("ETH_USDT", entry=100.0), 1000.0, kind="TREND") is False
    assert client.orders == [] and rt.open_positions == {}
    # the legacy TREND scan logs its pick as a shadow row and opens nothing
    (tmp_path / "scan").mkdir()
    opened, rows, preempted = _scan(tmp_path / "scan", live_env, "1", sleeve="TREND")
    assert opened == [] and preempted == [] and rows == [("ETH_USDT", "random_mode")]


def _tick(tmp_path, live_env, env):
    _on(live_env)
    for k, v in {**T26_ENV, **env}.items():
        live_env.setenv(k, v)
    live_env.setattr(RM, "coin", lambda: pytest.fail("a coin was drawn"))
    client = FakeClient({"ETH_USDT": 100.0, "L1_USDT": 1.0, "S1_USDT": 1.0})
    tmp_path.mkdir()
    rt = _rt(tmp_path, client, paper=True)
    rt._btc_flag_asof = (T, False, {"trend_flag": 0.0})
    pas = {"side": "LONG", "roc_pct": 0.09, "prior_close_extreme": 98.0, "leverage": 10}
    plan = _plan({"TREND": [_cand("ETH_USDT", "TREND", 0.09, status="pass", det=pas)],
                  "WC_LONG": [_cand("L1_USDT", "WC_LONG", 0.2, gate=1.0)],
                  "WC_SHORT": [_cand("S1_USDT", "WC_SHORT", -0.2, gate=1.0)]})
    plan["config"] = RM.config()
    decisions = rt._random_tick_execute(plan)
    rt._random_journal(plan, decisions, T + 1)
    (row,) = [json.loads(x) for x in (tmp_path / "futures_random_ticks.jsonl").read_text().splitlines()]
    return rt, client, decisions, row


def test_at_a_tick_trend_is_off_and_wildcard_is_trial_26s(tmp_path, live_env):
    rt26, c26, d26, j26 = _tick(tmp_path / "t26", live_env, {})
    rt27, c27, d27, j27 = _tick(tmp_path / "t27", live_env, OFF)
    assert [(d["bucket"], d["decision"]) for d in d27] == [
        ("TREND", "trend_off"), ("WC_LONG", "opened"), ("WC_SHORT", "opened")]
    assert d26[0]["decision"] == "event_time_only" and d27[1:] == d26[1:]     # WILDCARD: the same decisions
    assert sorted(rt27.open_positions) == sorted(rt26.open_positions) == ["L1_USDT", "S1_USDT"]
    assert c27.orders == c26.orders
    for sym in ("L1_USDT", "S1_USDT"):
        p26, p27 = rt26.open_positions[sym], rt27.open_positions[sym]
        assert (p27.side, p27.entry_price, p27.sl_price, p27.tp_price, p27.leverage, p27.contracts) == \
            (p26.side, p26.entry_price, p26.sl_price, p26.tp_price, p26.leverage, p26.contracts)
        m26 = {k: v for k, v in p26.metadata.items() if k.startswith("random_")}
        m27 = {k: v for k, v in p27.metadata.items() if k.startswith("random_")}
        assert (m27.pop("random_prereg"), m27.pop("random_trend_source")) == (RM.PREREG27_TAG, "off")
        assert (m26.pop("random_prereg"), m26.pop("random_trend_source")) == (RM.PREREG26_TAG, "natural")
        assert m27 == m26
    # the TREND ranking is still journalled at the tick
    assert j27["buckets"]["TREND"][0]["symbol"] == "ETH_USDT" and j27["prereg"] == RM.PREREG27_TAG
    assert (j27["random_trend_source"], j27["random_fx90"]) == ("off", "on")


def test_the_cycle_wakes_at_every_15m_close_and_the_tick_waits_for_the_evaluation(tmp_path, live_env):
    _on(live_env)
    _t27(live_env)
    rt = _rt(tmp_path, MagicMock())
    live_env.setattr(R.time, "time", lambda: T + 700.5)
    assert rt._random_mode_sleep_seconds(300) == 201                     # 1 s after 12:15Z, as trial 26
    calls: list = []
    clock = {"now": T + 30}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    (tmp_path / "w").mkdir()
    rt = _tick_runtime(tmp_path / "w", live_env, calls)
    rt._maybe_random_tick()
    assert calls == [] and rt._random_tick_pending == T, "as trial 26: the tick waits for the 12:00Z evaluation"
    rt._random_trend_state = {"last_eval": T}
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"]


# =====================================================================================
# /status, boot log, FX90
# =====================================================================================

def test_status_and_boot_log_say_trend_off_logged_only(tmp_path, live_env, caplog):
    _on(live_env)
    _t27(live_env)
    rt = _rt(tmp_path, MagicMock())
    live_env.setattr(R.time, "time", lambda: T + 3600)
    rt._random_trend_state = {"last_eval": T + 2700, "summary": "trend_off:ETH_USDT"}
    line = rt._random_mode_status_line()
    assert "(trial 27): WILDCARD entries only at 00:00Z / 06:00Z / 12:00Z / 18:00Z, TREND off (logged only)" in line
    assert "every 6h · natural · TREND stop 3.5x ATR · WILDCARD turnover ≥ $2,000,000 · PREREG 28ea4eadd078f6ba" in line
    assert "TREND source off: TREND off (logged only), L0 at every 15m close, never traded · FX90 on" in line
    assert "last TREND evaluation 12:45Z: trend_off:ETH_USDT" in line
    sent: list = []
    rt._notify_once = lambda key, msg, **k: sent.append(key)
    with caplog.at_level(logging.WARNING):
        rt._random_mode_boot_log()
    text = caplog.text
    assert "[RANDOM_MODE] ON (trial 27, PREREG 28ea4eadd078f6ba)" in text
    assert "[RANDOM_MODE] trial-27 settings: TREND source off - TREND off (logged only)" in text
    assert "FX90 on (exit at 0.90 x peak R once the peak reaches +2.0R, every position)" in text
    assert "Last TREND evaluation: 2026-10-02T12:45:00Z" in text and sent == []


def test_fx90_is_on_for_every_position_under_trial_27(tmp_path, live_env):
    rt, closed = _fx(tmp_path, live_env, **OFF)
    assert RM.config().prereg == RM.PREREG27_TAG and rt._random_fx90_on() is True
    pos = _long("WILDCARD")
    assert _walk(rt, pos, [103.0, 106.0, 106.3, 105.8, 105.6]) == [False, False, False, False, True]
    assert pos.metadata["fx90_armed_r"] == pytest.approx(2.0) and closed == [("RECORD_TP_FLOOR", 105.6)]
