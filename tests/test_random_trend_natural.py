"""Trial 26 - TREND in event time and the +2R floor (wc/TRIAL26/PREREG.md, sha256 cbbff32d4bf5d887...).

Two settings on top of trial 25, read once per cycle (random_mode.config):
  - FUTURES_RANDOM_TREND_SOURCE (tick | natural; unset = tick = trial 25): natural = TREND opens only at
    the 15m closes, LONG only, when trigger L0 (the live detector's LONG verdict on completed bars)
    fires; never at the 6h ticks, never short (C3), every evaluation logged (C6);
  - FUTURES_RANDOM_FX90 (off | on; unset = off): every position also exits at 0.90 x its running peak
    R once the peak has reached +2.0R, polled with the retention trail (C2, RECORD_TP_FLOOR).
These tests pin: unset = trial 25, the trial-26 tag, invalid values refused with an alert, the L0
verdict, the C3 decision rules, once-only processing, the tick ordering, the FX90 floor, logging.
"""
from __future__ import annotations

import inspect
import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

import futuresbot.runtime as R
from futuresbot import random_mode as RM
from futuresbot import scorecard
from futuresbot.runtime import FuturesRuntime
from futuresbot.trend import detect_trend_signal
from tests.test_random_mode import (  # noqa: F401  (live_env is a fixture)
    T, T25_ENV, FakeClient, _cand, _frame, _on, _plan, _pos, _rt, _t25, _tick_runtime, live_env)

T26_ENV = {**T25_ENV, "FUTURES_RANDOM_TREND_SOURCE": "natural", "FUTURES_RANDOM_FX90": "on"}
NEW = ("FUTURES_RANDOM_TREND_SOURCE", "FUTURES_RANDOM_FX90")
S = T + 3 * 900                                 # 12:45Z: a 15m close that is not a 6h tick


def _t26(monkeypatch, **extra):
    for k, v in {**T26_ENV, **extra}.items():
        monkeypatch.setenv(k, v)


# =====================================================================================
# the settings
# =====================================================================================

@pytest.mark.parametrize("raw", [None, "", "   "])
def test_unset_or_blank_is_trial_25_exactly(live_env, raw):
    _t25(live_env)
    for k in NEW:
        if raw is None:
            live_env.delenv(k, raising=False)
        else:
            live_env.setenv(k, raw)
    cfg = RM.config()
    assert cfg.valid and (cfg.trend_source, cfg.fx90) == ("tick", "off")
    assert not cfg.trend_natural and not cfg.fx90_on
    assert cfg.prereg == RM.PREREG25_TAG and cfg.trial == "trial 25"
    assert cfg.fields() == {"random_tick_hours": 6.0, "random_side_mode": "natural",
                            "random_trend_sl_mult": 3.5, "random_wc_min_turnover": 2e6}
    assert cfg.event_fields() == {"random_trend_source": "tick", "random_fx90": "off"}
    live_env.setenv("FUTURES_RANDOM_TREND_SOURCE", "tick")             # REVERT writes the literals
    live_env.setenv("FUTURES_RANDOM_FX90", "off")
    assert RM.config() == cfg
    for k in T25_ENV:                                                   # trial 24 keeps its tag too
        live_env.delenv(k)
    assert RM.config().prereg == RM.PREREG_TAG


def test_the_trial_26_configuration_and_its_tag(live_env):
    _t26(live_env)
    cfg = RM.config()
    assert cfg.valid and cfg.trend_natural and cfg.fx90_on
    assert cfg.prereg == RM.PREREG26_TAG == "cbbff32d4bf5d887" and cfg.trial == "trial 26"
    assert RM.PREREG26_SHA256.startswith(RM.PREREG26_TAG) and len(RM.PREREG26_SHA256) == 64
    d = cfg.describe()
    assert "TREND source natural (L0 at every 15m close, LONG only, never at the ticks)" in d
    assert "FX90 on" in d and d.endswith("PREREG cbbff32d4bf5d887") and "3.5x" in d
    live_env.setenv("FUTURES_RANDOM_TREND_SOURCE", " natural ")        # surrounding spaces ignored
    assert RM.config().prereg == RM.PREREG26_TAG
    assert (RM.FX90_ARM_R, RM.FX90_FRAC) == (2.0, 0.90)


@pytest.mark.parametrize("env", [
    {"FUTURES_RANDOM_FX90": "off"},                                     # natural TREND without FX90
    {"FUTURES_RANDOM_TREND_SOURCE": "tick"},                            # FX90 without natural TREND
    {"FUTURES_TREND_SL_ATR_MULT": "3.0"},
    {"FUTURES_RANDOM_TICK_HOURS": "12"},
    {"FUTURES_RANDOM_SIDE_MODE": "coin"},
    {"FUTURES_RANDOM_WC_MIN_TURNOVER": "10000000"},
])
def test_any_other_combination_is_unregistered(live_env, env):
    _t26(live_env, **env)
    cfg = RM.config()
    assert cfg.valid and cfg.prereg == RM.UNREGISTERED and cfg.trial == "UNREGISTERED"


@pytest.mark.parametrize("name,raw", [
    ("FUTURES_RANDOM_TREND_SOURCE", "Natural"), ("FUTURES_RANDOM_TREND_SOURCE", "NATURAL"),
    ("FUTURES_RANDOM_TREND_SOURCE", "events"), ("FUTURES_RANDOM_TREND_SOURCE", "L0"),
    ("FUTURES_RANDOM_TREND_SOURCE", "1"), ("FUTURES_RANDOM_TREND_SOURCE", "Tick"),
    ("FUTURES_RANDOM_FX90", "On"), ("FUTURES_RANDOM_FX90", "ON"), ("FUTURES_RANDOM_FX90", "1"),
    ("FUTURES_RANDOM_FX90", "true"), ("FUTURES_RANDOM_FX90", "yes"), ("FUTURES_RANDOM_FX90", "0.9"),
    ("FUTURES_RANDOM_FX90", "Off"),
])
def test_an_invalid_value_stops_trading_with_an_alert(tmp_path, live_env, name, raw):
    _t26(live_env)
    live_env.setenv(name, raw)
    cfg = RM.config()
    assert not cfg.valid and len(cfg.errors) == 1 and name in cfg.errors[0] and repr(raw) in cfg.errors[0]
    # the tick: not processed, not marked, alerted
    calls: list = []
    clock = {"now": T + 30}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    rt = _tick_runtime(tmp_path, live_env, calls)
    sent: list = []
    rt._notify_once = lambda key, msg, **k: sent.append((key, msg))
    rt._maybe_random_tick()
    assert calls == [] and not rt._random_mode_state
    assert [k for k, _m in sent] == [f"random_config_invalid_{T}"] and name in sent[0][1]
    # the 15m TREND evaluation: not processed, nothing read, nothing logged
    rt._random_trend_select = lambda s, c: pytest.fail("evaluated with invalid settings")
    clock["now"] = S + 2
    rt._maybe_random_trend_eval()
    assert not rt._random_trend_state and not (tmp_path / "futures_random_trend_evals.jsonl").exists()
    assert "invalid settings" in rt._random_mode_status_line() and name in rt._random_mode_status_line()
    sent.clear()
    rt._random_mode_boot_log()
    assert [k for k, _m in sent] == ["random_config_invalid_boot"]
    # an invalid FX90 value holds the floor off; a valid one is kept while another setting is invalid
    assert cfg.fx90_on is (name != "FUTURES_RANDOM_FX90")


# =====================================================================================
# trigger L0
# =====================================================================================

UP = [100.0] * 300 + list(np.linspace(100, 112, 100))          # +11.6% / 24h at a new closing high
UP2 = [100.0] * 300 + list(np.linspace(100, 106, 100))         # +5.8%
MILD = [100.0] * 300 + list(np.linspace(100, 103, 100))        # +2.9%: below the 4% floor
DOWN = [100.0] * 300 + list(np.linspace(100, 88, 100))         # the detector's SHORT verdict
PULLBACK = [100.0] * 300 + list(np.linspace(100, 112, 99)) + [111.0]   # +10% but not a new high


def test_l0_is_the_live_detectors_long_verdict_on_completed_bars(live_env):
    rows = {n: RM.trend_eval_row("ETH_USDT", _frame(c), T) for n, c in
            (("up", UP), ("mild", MILD), ("down", DOWN), ("pullback", PULLBACK))}
    up = rows["up"]
    assert up["fire"] and up["new_high"] and up["prio"] == up["roc24h"] == pytest.approx(112 / UP[-97] - 1)
    assert up["status"] == "trigger" and up["detector"]["side"] == "LONG"
    assert not rows["mild"]["fire"] and rows["mild"]["new_high"] and rows["mild"]["reject"] == "roc_below_min"
    assert not rows["down"]["fire"] and rows["down"]["detector"]["side"] == "SHORT"     # LONG only
    assert rows["down"]["prio"] is None and rows["down"]["new_high"] is False
    assert not rows["pullback"]["fire"] and rows["pullback"]["reject"] == "no_new_extreme"
    # the forming bar and anything after s is never read; a missing last bar is not a verdict
    late = pd.concat([_frame(UP), _frame([50.0, 50.0], end_tick=T + 1800)])
    assert RM.trend_eval_row("ETH_USDT", late, T) == up
    stale = RM.trend_eval_row("ETH_USDT", _frame(UP).iloc[:-1], T)
    assert stale["usable"] is False and stale["why"] == "stale_or_missing_bar" and stale["fire"] is False
    assert RM.trend_eval_row("ETH_USDT", None, T)["why"] == "kline_error"
    # = detect_trend_signal's LONG verdict on the completed bars, on random walks
    rng = np.random.default_rng(26)
    n_fire = 0
    for _ in range(300):
        c = 100.0 * np.exp(np.cumsum(rng.normal(0.0006, 0.006, 400)))
        fr = _frame(list(c))
        row = RM.trend_eval_row("X_USDT", fr, T)
        sig = detect_trend_signal(RM.completed(fr, T, RM.TREND_BARS)[["open", "high", "low", "close", "volume"]],
                                  "X_USDT")
        assert row["fire"] is (sig is not None and sig.side == "LONG")
        hi = bool(c[-1] >= c[-97:-1].max())
        assert row["new_high"] is hi and (not row["fire"] or (hi and c[-1] / c[-97] - 1 >= 0.04))
        n_fire += row["fire"]
    assert 10 < n_fire < 290


def test_firings_go_by_24h_roc_then_symbol():
    rows = [{"symbol": "ZEC_USDT", "fire": True, "prio": 0.05}, {"symbol": "ETH_USDT", "fire": True, "prio": 0.05},
            {"symbol": "XRP_USDT", "fire": True, "prio": 0.09}, {"symbol": "AKE_USDT", "fire": False, "prio": None}]
    assert [r["symbol"] for r in RM.trend_firings(rows)] == ["XRP_USDT", "ETH_USDT", "ZEC_USDT"]


# =====================================================================================
# the 15m evaluation, end to end
# =====================================================================================

def _series_runtime(tmp_path, live_env, series, *, last=S + 3 * 900, paper=False, min_vol=1, env=None):
    """A runtime whose klines are `series` (closes; the last bar closes at `last`)."""
    _on(live_env)
    _t26(live_env, **(env or {}))
    client = FakeClient({sym: c[-1] for sym, c in series.items()} | {"BTC_USDT": 60000.0}, min_vol=min_vol)
    client.klines = {sym: _frame(c, end_tick=last) for sym, c in series.items()}
    rt = _rt(tmp_path, client, paper=paper)
    rt._trend_rotation_symbol = lambda: None
    rt._btc_exhaustion_flag = lambda asof=None: (False, {"trend_flag": 0.0})
    return rt, client


def _ext(c, n=3, step=1.002):
    """`c` continued for n more 15m bars (so the series covers S .. S + n*900)."""
    out = list(c)
    for _ in range(n):
        out.append(out[-1] * step)
    return out


def _log(tmp_path):
    p = tmp_path / "futures_random_trend_evals.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_a_firing_opens_trend_long_at_its_15m_close_once(tmp_path, live_env):
    series = {"ETH_USDT": _ext(UP), "XRP_USDT": _ext(UP2), "ZEC_USDT": _ext(MILD)}
    clock = {"now": S + 2}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    rt, client = _series_runtime(tmp_path, live_env, series)
    rt._maybe_random_trend_eval()
    (order,) = client.orders
    pos = rt.open_positions["ETH_USDT"]
    md = pos.metadata
    assert order["side"] == 1 and pos.side == "LONG" and md["trend"] == 1.0, "TREND LONG"
    eth = RM.trend_eval_row("ETH_USDT", client.klines["ETH_USDT"], S)
    ref = series["ETH_USDT"][-1]                                        # FakeClient's last price
    assert order["stop_loss_price"] == pytest.approx(ref * (1 - 3.5 * eth["atr_pct"]))   # 3.5x ATR
    assert order["take_profit_price"] == pytest.approx(ref * (1 + 3 * 3.5 * eth["atr_pct"]))  # 3R
    assert (md["random_bucket"], md["random_tick_ts"], md["random_status"], md["random_side"]) == \
        ("TREND", float(S), "trigger", "LONG")
    assert md["random_coin"] is None and md["random_fallback"] == 0.0
    assert (md["random_rank"], md["random_field"]) == (1.0, 2.0)
    assert md["random_key_value"] == pytest.approx(eth["roc24h"])
    assert (md["random_prereg"], md["random_trend_source"], md["random_fx90"]) == (RM.PREREG26_TAG, "natural", "on")
    assert "15m close 12:45Z · TREND #1 (trigger) · natural trigger L0 → <b>LONG</b>" in rt._random_entry_line(md)
    (row,) = _log(tmp_path)
    assert (row["s"], row["s_utc"], row["prereg"], row["trigger"]) == (S, "2026-10-02T12:45:00Z", RM.PREREG26_TAG, "L0")
    assert (row["random_trend_source"], row["random_fx90"], row["random_tick_hours"]) == ("natural", "on", 6.0)
    assert [(r["symbol"], r["fire"], r["decision"]) for r in row["rows"]] == [
        ("ETH_USDT", True, "opened"), ("XRP_USDT", True, "not_taken"), ("ZEC_USDT", False, "no_fire")]
    assert row["rows"][0]["new_high"] is True and row["rows"][0]["prio"] == pytest.approx(eth["roc24h"])
    assert row["book"] == {"held": [], "trend_open": 0, "trend_slots": 2} and row["paused"] is False
    assert json.loads((tmp_path / "state.json").read_text())["random_trend"]["last_eval"] == S
    # once only: same process, and after a restart
    clock["now"] = S + 60
    rt._maybe_random_trend_eval()
    rt2 = _rt(tmp_path, client)
    rt2._trend_rotation_symbol = lambda: None
    clock["now"] = S + 120
    rt2._maybe_random_trend_eval()
    assert len(client.orders) == 1 and len(_log(tmp_path)) == 1
    # the next close: ETH is held (skipped), XRP still fires -> XRP opens
    clock["now"] = S + 900 + 2
    rt._maybe_random_trend_eval()
    assert [o["symbol"] for o in client.orders] == ["ETH_USDT", "XRP_USDT"]
    assert [(r["symbol"], r["decision"]) for r in _log(tmp_path)[-1]["rows"]][:2] == [
        ("ETH_USDT", "held"), ("XRP_USDT", "opened")]
    assert rt.open_positions["XRP_USDT"].metadata["random_held_symbols"] == "ETH_USDT"
    # both TREND slots full: the whole turn is slot_full
    clock["now"] = S + 1800 + 2
    rt._maybe_random_trend_eval()
    last = _log(tmp_path)[-1]
    assert len(client.orders) == 2 and last["decisions"][0]["decision"] == "slot_full"
    assert [r["decision"] for r in last["rows"]] == ["slot_full", "slot_full", "no_fire"]
    assert last["book"]["trend_open"] == 2


def test_one_attempt_per_close_a_refusal_consumes_the_turn(tmp_path, live_env):
    series = {"ETH_USDT": _ext(UP), "XRP_USDT": _ext(UP2), "ZEC_USDT": _ext(MILD)}
    live_env.setattr(R.time, "time", lambda: S + 2)
    rt, client = _series_runtime(tmp_path, live_env, series, min_vol=10_000)
    rt._maybe_random_trend_eval()
    assert client.orders == [] and rt.open_positions == {}
    (row,) = _log(tmp_path)
    assert [(r["symbol"], r["decision"]) for r in row["rows"]] == [
        ("ETH_USDT", "refused"), ("XRP_USDT", "not_taken"), ("ZEC_USDT", "no_fire")]
    assert row["decisions"][-1]["decision"] == "min_vol" and row["decisions"][-1]["side"] == "LONG"


def test_held_by_either_sleeve_is_skipped_and_the_book_is_the_book_at_the_close(tmp_path, live_env):
    series = {"ETH_USDT": _ext(UP), "XRP_USDT": _ext(UP2), "ZEC_USDT": _ext(MILD)}
    live_env.setattr(R.time, "time", lambda: S + 2)
    rt, client = _series_runtime(tmp_path, live_env, series)
    rt.open_positions["ETH_USDT"] = _pos("ETH_USDT", "WILDCARD")       # a WILDCARD holds ETH
    iso = lambda ts: datetime.fromtimestamp(ts, timezone.utc).isoformat()  # noqa: E731
    # a TREND position open at the close and closed 20 s after it still held its slot
    rt.trade_history = [{"symbol": "AKE_USDT", "sleeve": "TREND", "entry_time": iso(S - 3600),
                         "exit_time": iso(S + 20)}]
    rt._maybe_random_trend_eval()
    assert [o["symbol"] for o in client.orders] == ["XRP_USDT"]
    row = _log(tmp_path)[-1]
    assert row["book"] == {"held": ["AKE_USDT", "ETH_USDT"], "trend_open": 1, "trend_slots": 2}
    assert [d["decision"] for d in row["decisions"]] == ["held", "opened"]


def test_never_short_never_a_coin_and_nothing_without_a_firing(tmp_path, live_env):
    # side mode coin (unregistered) cannot make TREND short or draw a coin at a 15m close
    live_env.setattr(RM, "coin", lambda: pytest.fail("a coin was drawn"))
    series = {"ETH_USDT": _ext(DOWN), "XRP_USDT": _ext(UP2), "ZEC_USDT": _ext(PULLBACK)}
    live_env.setattr(R.time, "time", lambda: S + 2)
    rt, client = _series_runtime(tmp_path, live_env, series, env={"FUTURES_RANDOM_SIDE_MODE": "coin"})
    assert RM.config().prereg == RM.UNREGISTERED
    rt._maybe_random_trend_eval()
    assert [(o["symbol"], o["side"]) for o in client.orders] == [("XRP_USDT", 1)]       # 1 = open LONG
    assert rt.open_positions["XRP_USDT"].metadata["random_prereg"] == RM.UNREGISTERED
    # only the SHORT verdict fires on the detector: nothing opens, the row says why
    (tmp_path / "s").mkdir()
    rt, client = _series_runtime(tmp_path / "s", live_env, {"ETH_USDT": _ext(DOWN), "XRP_USDT": _ext(MILD),
                                                           "ZEC_USDT": _ext(PULLBACK)})
    rt._maybe_random_trend_eval()
    (row,) = _log(tmp_path / "s")
    assert client.orders == [] and row["decisions"] == []
    assert row["rows"][0]["detector_side"] == "SHORT" and row["rows"][0]["fire"] is False


def test_paused_evaluations_are_logged_open_nothing_and_never_rerun(tmp_path, live_env):
    series = {"ETH_USDT": _ext(UP), "XRP_USDT": _ext(UP2), "ZEC_USDT": _ext(MILD)}
    clock = {"now": S + 2}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    rt, client = _series_runtime(tmp_path, live_env, series)
    rt._paused = True
    rt._maybe_random_trend_eval()
    (row,) = _log(tmp_path)
    assert row["paused"] is True and row["decisions"] == [{"tick": S, "bucket": "TREND", "decision": "paused"}]
    assert [r["decision"] for r in row["rows"]] == ["paused", "paused", "no_fire"] and client.orders == []
    rt._paused = False                                             # /resume inside the bar: not re-run
    clock["now"] = S + 300
    rt._maybe_random_trend_eval()
    assert client.orders == [] and len(_log(tmp_path)) == 1
    clock["now"] = S + 900 + 1                                     # the next close trades
    rt._maybe_random_trend_eval()
    assert [o["symbol"] for o in client.orders] == ["ETH_USDT"]


def test_the_evaluation_waits_for_positions_whose_24h_clock_ends_at_it(tmp_path, live_env):
    series = {"ETH_USDT": _ext(UP), "XRP_USDT": _ext(UP2), "ZEC_USDT": _ext(MILD)}
    clock = {"now": S + 2}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    rt, client = _series_runtime(tmp_path, live_env, series)
    rt.open_positions["OLD_USDT"] = _pos("OLD_USDT", "TREND", md={"random_tick_ts": float(S - 86400)},
                                         opened=datetime.fromtimestamp(S - 86400 + 5, timezone.utc))
    rt._maybe_random_trend_eval()
    assert rt._random_trend_pending == S and _log(tmp_path) == [] and client.orders == []
    assert rt._random_mode_sleep_seconds(300) == 5
    assert "TREND evaluation waiting on a 24h clock" in rt._random_mode_status_line()
    clock["now"] = S + RM.TICK_DEFER_SECONDS + 1                   # bounded
    rt._maybe_random_trend_eval()
    assert rt._random_trend_pending is None and [o["symbol"] for o in client.orders] == ["ETH_USDT"]
    # OLD_USDT never closed here (the wait is bounded): still open, it holds one of the 2 slots
    assert _log(tmp_path)[-1]["book"]["trend_open"] == 1


def test_a_kline_outage_is_retried_inside_the_grace(tmp_path, live_env):
    series = {"ETH_USDT": _ext(UP), "XRP_USDT": _ext(UP2), "ZEC_USDT": _ext(MILD)}
    clock = {"now": S + 2}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    rt, client = _series_runtime(tmp_path, live_env, series)
    good = client.get_klines
    client.get_klines = lambda symbol, **kw: (_ for _ in ()).throw(RuntimeError("down")) \
        if symbol != "ZEC_USDT" else good(symbol, **kw)
    rt._maybe_random_trend_eval()
    assert not rt._random_trend_state and _log(tmp_path) == []
    client.get_klines = good
    clock["now"] = S + 60
    rt._maybe_random_trend_eval()
    assert [o["symbol"] for o in client.orders] == ["ETH_USDT"]


def test_source_tick_or_mode_off_evaluates_nothing(tmp_path, live_env):
    live_env.setattr(R.time, "time", lambda: S + 2)
    for env in (T25_ENV, {**T25_ENV, "FUTURES_RANDOM_FX90": "on"}):
        _on(live_env)
        for k in NEW:
            live_env.delenv(k, raising=False)
        for k, v in env.items():
            live_env.setenv(k, v)
        rt = _rt(tmp_path, MagicMock())
        rt._random_trend_select = lambda s, c: pytest.fail("evaluated with TREND source tick")
        rt._maybe_random_trend_eval()
        rt._save_state()
        assert "random_trend" not in json.loads((tmp_path / "state.json").read_text())
        assert not (tmp_path / "futures_random_trend_evals.jsonl").exists()
    _t26(live_env)
    _on(live_env, False)
    rt._maybe_random_trend_eval()
    assert not rt._random_trend_state


# =====================================================================================
# the ticks under trial 26
# =====================================================================================

def test_no_trend_open_at_a_tick_and_wildcard_unchanged(tmp_path, live_env):
    _on(live_env)
    _t26(live_env)
    live_env.setattr(RM, "coin", lambda: pytest.fail("a coin was drawn"))
    client = FakeClient({"ETH_USDT": 100.0, "L1_USDT": 1.0, "S1_USDT": 1.0})
    rt = _rt(tmp_path, client, paper=True)
    rt._btc_flag_asof = (T, False, {"trend_flag": 0.0})
    pas = {"side": "LONG", "roc_pct": 0.09, "prior_close_extreme": 98.0, "leverage": 10}
    buckets = {"TREND": [_cand("ETH_USDT", "TREND", 0.09, status="pass", det=pas)],
               "WC_LONG": [_cand("L1_USDT", "WC_LONG", 0.2, gate=1.0)],
               "WC_SHORT": [_cand("S1_USDT", "WC_SHORT", -0.2, gate=1.0)]}
    plan = _plan(buckets)
    plan["config"] = RM.config()
    decisions = rt._random_tick_execute(plan)
    assert [(d["bucket"], d["decision"]) for d in decisions] == [
        ("TREND", "event_time_only"), ("WC_LONG", "opened"), ("WC_SHORT", "opened")]
    assert sorted(rt.open_positions) == ["L1_USDT", "S1_USDT"]
    assert rt.open_positions["S1_USDT"].side == "SHORT"
    for p in rt.open_positions.values():
        assert (p.metadata["random_prereg"], p.metadata["random_trend_source"], p.metadata["random_fx90"]) == \
            (RM.PREREG26_TAG, "natural", "on")
    # the TREND ranking is still journalled at the tick (arm (b) of the primary replays it)
    rt._random_journal(plan, decisions, T + 1)
    (row,) = [json.loads(x) for x in (tmp_path / "futures_random_ticks.jsonl").read_text().splitlines()]
    assert row["buckets"]["TREND"][0]["symbol"] == "ETH_USDT" and row["prereg"] == RM.PREREG26_TAG
    assert (row["random_trend_source"], row["random_fx90"]) == ("natural", "on")
    # unset (trial 25): the tick still opens TREND, and its rows say tick / off
    for k in NEW:
        live_env.delenv(k)
    (tmp_path / "t25").mkdir()
    rt = _rt(tmp_path / "t25", FakeClient({"ETH_USDT": 100.0}), paper=True)
    rt._btc_flag_asof = (T, False, {"trend_flag": 0.0})
    plan = _plan({"TREND": buckets["TREND"]})
    plan["config"] = RM.config()
    d = rt._random_tick_execute(plan)[0]
    assert d["decision"] == "opened" and d["side"] == "LONG"
    assert rt.open_positions["ETH_USDT"].metadata["random_trend_source"] == "tick"
    assert rt.open_positions["ETH_USDT"].metadata["random_prereg"] == RM.PREREG25_TAG


def test_at_a_tick_trend_goes_first_the_tick_waits_for_it(tmp_path, live_env):
    _t26(live_env)
    calls: list = []
    clock = {"now": T + 30}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    rt = _tick_runtime(tmp_path, live_env, calls)
    rt._maybe_random_tick()
    assert calls == [] and rt._random_tick_pending == T, "waits for the TREND evaluation of 12:00Z"
    rt._random_trend_state = {"last_eval": T}
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"]
    # bounded: a TREND evaluation that never lands does not lose the tick
    (tmp_path / "b").mkdir()
    calls.clear()
    rt = _tick_runtime(tmp_path / "b", live_env, calls)
    clock["now"] = T + RM.TICK_DEFER_SECONDS + 1
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"]
    # trial 25 (unset): no wait
    for k in NEW:
        live_env.delenv(k)
    (tmp_path / "c").mkdir()
    calls.clear()
    rt = _tick_runtime(tmp_path / "c", live_env, calls)
    clock["now"] = T + 30
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"]
    # the cycle runs the TREND evaluation before the tick, and reads the settings once
    src = inspect.getsource(FuturesRuntime.run)
    assert src.index("self._maybe_random_trend_eval()") < src.index("self._maybe_random_tick()")
    assert src.index("self._random_cycle_cfg = random_mode.config()") < src.index("self._maybe_random_trend_eval()")


def test_the_cycle_sleep_lands_on_every_15m_close_only_under_natural(tmp_path, live_env):
    _on(live_env)
    rt = _rt(tmp_path, MagicMock())
    live_env.setattr(R.time, "time", lambda: T + 700.5)
    _t25(live_env)
    assert rt._random_mode_sleep_seconds(300) == 300                     # next 6h tick is far
    _t26(live_env)
    assert rt._random_mode_sleep_seconds(300) == 201                     # 1 s after 12:15Z
    live_env.setenv("FUTURES_RANDOM_TREND_SOURCE", "bogus")
    assert rt._random_mode_sleep_seconds(300) == 300


def test_status_boot_and_journal_print_the_effective_values(tmp_path, live_env, caplog):
    _on(live_env)
    rt = _rt(tmp_path, MagicMock())
    live_env.setattr(R.time, "time", lambda: T + 3600)
    _t25(live_env)
    line = rt._random_mode_status_line()
    assert "trial 25" in line and "TREND source tick · FX90 off" in line
    _t26(live_env)
    rt._random_trend_state = {"last_eval": T + 2700, "summary": "opened:ETH_USDT LONG"}
    line = rt._random_mode_status_line()
    assert "trial 26" in line and "PREREG cbbff32d4bf5d887" in line and "every 6h · natural · TREND stop 3.5x ATR" in line
    assert "TREND source natural: L0 at every 15m close, LONG only, never at the ticks · FX90 on" in line
    assert "last TREND evaluation 12:45Z: opened:ETH_USDT LONG" in line
    assert "WILDCARD entries only at 00:00Z / 06:00Z / 12:00Z / 18:00Z, TREND at every 15m close" in line
    sent: list = []
    rt._notify_once = lambda key, msg, **k: sent.append(key)
    with caplog.at_level(logging.WARNING):
        rt._random_mode_boot_log()
    text = caplog.text
    assert "TREND source natural" in text and "FX90 on" in text and "PREREG cbbff32d4bf5d887" in text
    assert "Last TREND evaluation: 2026-10-02T12:45:00Z" in text and sent == []
    live_env.setenv("FUTURES_RANDOM_FX90", "off")                         # unregistered: boot alert
    rt._random_mode_boot_log()
    assert sent == ["random_config_unregistered_boot"]
    assert {"random_trend_source", "random_fx90"} <= set(RM.STAMP_KEYS)


# =====================================================================================
# FX90: the +2R / 90%-of-peak floor
# =====================================================================================

def _fx(tmp_path, live_env, fx="on", **env):
    _on(live_env)
    _t26(live_env, FUTURES_RANDOM_FX90=fx, **env)
    client = FakeClient({"ETH_USDT": 100.0})
    rt = _rt(tmp_path, client)
    closed: list = []
    rt._close_position_for_exit = lambda p, current_price, reason: closed.append((reason, current_price)) or True
    return rt, closed


def _long(sleeve="TREND"):
    # entry 100, stop 97, x5: 1R = 3% of price = 15% of margin; R = (price - 100) / 3
    return _pos("ETH_USDT", sleeve, "LONG", entry=100.0, sl=97.0, tp=109.0 if sleeve == "TREND" else 115.0,
                lev=5, opened=datetime.now(timezone.utc) - timedelta(hours=2))


def _walk(rt, pos, prices):
    out = []
    for px in prices:
        out.append(rt._convex_runner_trail_exit(pos, px))
    return out


def test_fx90_arms_at_2r_and_exits_at_90_percent_of_the_running_peak(tmp_path, live_env):
    rt, closed = _fx(tmp_path, live_env)
    pos = _long()
    # 1R, 1.97R (not armed), back to 1.67R: no FX exit, the trail floor (0.98R) holds
    assert _walk(rt, pos, [103.0, 105.9, 105.0]) == [False, False, False] and closed == []
    assert "fx90_armed_ts" not in pos.metadata
    assert _walk(rt, pos, [106.0]) == [False]                           # 2.0R: arms, no exit on this poll
    assert pos.metadata["fx90_armed_r"] == pytest.approx(2.0) and pos.metadata["fx90_armed_ts"]
    assert _walk(rt, pos, [106.3, 105.8]) == [False, False]             # peak 2.1R; 1.93R > 1.89R
    assert pos.metadata["convex_peak_r"] == round((106.3 - 100) / 3, 4)
    assert _walk(rt, pos, [105.6]) == [True]                            # 1.867R <= 0.9 x 2.1R
    assert closed == [("RECORD_TP_FLOOR", 105.6)]


def test_fx90_off_or_unset_is_the_trial_25_trail(tmp_path, live_env):
    for fx in ("off", None):
        (tmp_path / str(fx)).mkdir()
        rt, closed = _fx(tmp_path / str(fx), live_env, fx=fx or "off")
        if fx is None:
            live_env.delenv("FUTURES_RANDOM_FX90")
        pos = _long()
        assert _walk(rt, pos, [103.0, 106.0, 106.3, 105.6, 104.0]) == [False] * 5 and closed == []
        assert "fx90_armed_ts" not in pos.metadata
        assert _walk(rt, pos, [103.1]) == [True] and closed == [("CONVEX_RETENTION_TRAIL", 103.1)]   # 0.5 x 2.1R


def test_fx90_takes_the_label_when_both_floors_are_crossed_and_ignores_the_trend_trail_switch(tmp_path, live_env):
    rt, closed = _fx(tmp_path, live_env)
    pos = _long()
    _walk(rt, pos, [106.0, 106.3])
    assert _walk(rt, pos, [101.0]) == [True] and closed == [("RECORD_TP_FLOOR", 101.0)]   # a gap through both
    (tmp_path / "off").mkdir()
    rt, closed = _fx(tmp_path / "off", live_env, FUTURES_TREND_TRAIL_ENABLED="0")
    pos = _long()
    assert _walk(rt, pos, [106.0, 106.3, 104.0]) == [False, False, True]
    assert closed == [("RECORD_TP_FLOOR", 104.0)]


def test_fx90_arms_only_on_a_new_peak_poll_and_covers_every_sleeve_and_side(tmp_path, live_env):
    rt, closed = _fx(tmp_path, live_env, fx="off")
    pos = _long("WILDCARD")
    _walk(rt, pos, [106.3])                                               # peak 2.1R while off
    live_env.setenv("FUTURES_RANDOM_FX90", "on")
    assert _walk(rt, pos, [105.0]) == [False] and closed == []           # not armed: no new peak yet
    assert _walk(rt, pos, [106.5, 105.8]) == [False, True]               # arms at 2.167R; 1.93 <= 1.95
    assert closed == [("RECORD_TP_FLOOR", 105.8)]
    (tmp_path / "s").mkdir()
    rt, closed = _fx(tmp_path / "s", live_env)
    short = _pos("S1_USDT", "WILDCARD", "SHORT", entry=1.0, sl=1.03, tp=0.85, lev=5,
                 opened=datetime.now(timezone.utc) - timedelta(hours=2))
    assert _walk(rt, short, [0.94, 0.935, 0.942]) == [False, False, True]   # 2.0R, 2.167R, 1.933R
    assert closed == [("RECORD_TP_FLOOR", 0.942)]


def test_fx90_reads_the_cycles_settings_and_the_record_keeps_the_arm(tmp_path, live_env):
    _on(live_env)
    _t26(live_env)
    client = FakeClient({"ETH_USDT": 100.0})
    rt = _rt(tmp_path, client, paper=True)
    rt._random_cycle_cfg = RM.config()                    # read at the top of the cycle ...
    live_env.setenv("FUTURES_RANDOM_FX90", "off")         # ... a later change waits for the next cycle
    pos = _long()
    pos.metadata.update({"random_mode": 1.0, "random_fx90": "on"})
    rt.open_positions["ETH_USDT"] = pos
    assert _walk(rt, pos, [106.0, 106.3, 105.6]) == [False, False, True]
    rec = rt.trade_history[-1]
    assert rec["exit_rule"] == "RECORD_TP_FLOOR" and rec["fx90_armed_r"] == pytest.approx(2.0)
    assert rec["random_fx90"] == "on" and rec["peak_r"] == pytest.approx(2.1)
    assert "RECORD_TP_FLOOR" in scorecard.SANCTIONED_EXITS, "a sanctioned exit, not an M5 anomaly"
    rt._random_cycle_cfg = None
    assert rt._random_fx90_on() is False                  # read now: off
