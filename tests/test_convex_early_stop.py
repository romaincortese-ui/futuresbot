"""The early stop: a tight stop for the first N minutes, widening after.

2026-09-08. Shipped default-OFF on a WEAK result — bootstrap 95% CI
[-$47.81, +$218.93], P(delta<=0) = 0.095, grid-corrected permutation p = 0.042.
The tests below are therefore mostly about what it must NOT do: fire when it is
off, fire outside its window, fire on TREND, or fire on a bad denominator.

The denominator guard is the one that matters operationally. r_now divides by the
LIVE stop distance; if that reads too small, |r_now| inflates and the rule would
cut every position inside the window. That is the failure mode that turns a
+$115/month rule into an account-wide stop-out, and it is tested here directly.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def _pos(opened_min_ago=10.0, md=None, signal="WILDCARD_LONG", side="LONG"):
    p = FuturesPosition(
        symbol="MAGMA_USDT", side=side, entry_price=0.273, contracts=154,
        contract_size=1.0, leverage=3, margin_usdt=140.14, tp_price=0.40,
        sl_price=0.25, position_id="p1", order_id="o1",
        opened_at=NOW - timedelta(minutes=opened_min_ago),
        score=96.0, certainty=0.9, entry_signal=signal,
    )
    p.metadata = {"wildcard": 1.0, "sl_margin_pct": 16.58} if md is None else md
    return p


def _rt(monkeypatch, *, env=None, gross=-10.0, risk_pct=16.58, convex=True,
        kind="WILDCARD"):
    """gross is pnl as % of margin; risk_pct is the stop as % of margin.
    r_now = gross / risk_pct, so gross=-10 / 16.58 = -0.60R."""
    r = FuturesRuntime.__new__(FuturesRuntime)
    e = dict(env or {})
    closed = []
    monkeypatch.setattr(FuturesRuntime, "_is_wildcard_convex", lambda self, p: convex)
    monkeypatch.setattr(FuturesRuntime, "_sleeve_kind", staticmethod(lambda p: kind))
    monkeypatch.setattr(FuturesRuntime, "_env_float",
                        lambda self, k, d=0.0: e.get(k, d))
    monkeypatch.setattr(FuturesRuntime, "_position_stop_risk_pct_of_margin",
                        lambda self, p: risk_pct)
    monkeypatch.setattr(FuturesRuntime, "_position_pnl_pct", lambda self, p, px: gross)
    monkeypatch.setattr(FuturesRuntime, "_metadata_float",
                        lambda self, md, k: md.get(k))
    monkeypatch.setattr(FuturesRuntime, "_position_stop_risk_usdt", lambda self, p: 25.16)
    monkeypatch.setattr(FuturesRuntime, "_format_price", lambda self, x: str(x))
    monkeypatch.setattr(FuturesRuntime, "_save_state", lambda self: None)
    monkeypatch.setattr(FuturesRuntime, "_close_position_for_exit",
                        lambda self, p, *, current_price, reason: closed.append(reason) or True)
    return r, closed


ON = {"FUTURES_WILDCARD_EARLY_STOP_R": 0.5, "FUTURES_WILDCARD_EARLY_STOP_MINUTES": 30.0}


# --- it must not fire when it should not ----------------------------------

def test_default_is_off_so_deploying_it_changes_nothing(monkeypatch):
    """The whole safety case. With no env set, this is inert."""
    r, closed = _rt(monkeypatch, env={})
    assert r._convex_early_stop_exit(_pos(), 0.25, now=NOW) is False
    assert closed == []


def test_it_does_not_fire_outside_the_window(monkeypatch):
    r, closed = _rt(monkeypatch, env=ON)
    assert r._convex_early_stop_exit(_pos(opened_min_ago=31.0), 0.25, now=NOW) is False
    assert closed == []


def test_it_does_not_fire_above_the_threshold(monkeypatch):
    """gross -8.0 / 16.58 = -0.48R, shallower than -0.50R."""
    r, closed = _rt(monkeypatch, env=ON, gross=-8.0)
    assert r._convex_early_stop_exit(_pos(), 0.25, now=NOW) is False


def test_a_non_convex_position_is_untouched(monkeypatch):
    r, closed = _rt(monkeypatch, env=ON, convex=False)
    assert r._convex_early_stop_exit(_pos(signal="PMT_LONG"), 0.25, now=NOW) is False


# --- THE DENOMINATOR GUARD -------------------------------------------------

def test_a_collapsed_live_stop_distance_does_NOT_trigger_a_cut(monkeypatch):
    """THE OPERATIONAL FAILURE MODE. If the live stop distance reads far below the
    one sized at entry, |r_now| inflates and the naive rule cuts everything inside
    the window. Entry recorded 16.58%; live reads 4.0%, so gross -10 would compute
    as -2.5R. The rule must refuse."""
    r, closed = _rt(monkeypatch, env=ON, risk_pct=4.0)
    assert r._convex_early_stop_exit(_pos(), 0.25, now=NOW) is False
    assert closed == []


def test_a_mildly_lower_live_stop_still_acts(monkeypatch):
    """The guard is at half the entry value, not any deviation. 9.0 vs 16.58 is
    above half, so -10/9.0 = -1.11R is a real breach and must fire."""
    r, closed = _rt(monkeypatch, env=ON, risk_pct=9.0)
    assert r._convex_early_stop_exit(_pos(), 0.25, now=NOW) is True
    assert closed == ["CONVEX_EARLY_STOP"]


def test_no_entry_risk_recorded_means_no_guard_but_still_works(monkeypatch):
    r, closed = _rt(monkeypatch, env=ON)
    assert r._convex_early_stop_exit(_pos(md={"wildcard": 1.0}), 0.25, now=NOW) is True


# --- it fires when it should, and records why ------------------------------

def test_it_fires_inside_the_window_below_the_threshold(monkeypatch):
    r, closed = _rt(monkeypatch, env=ON)
    p = _pos(opened_min_ago=7.0)
    assert r._convex_early_stop_exit(p, 0.25, now=NOW) is True
    assert closed == ["CONVEX_EARLY_STOP"]


def test_every_fire_records_the_counterfactual(monkeypatch):
    """Without this the pre-registered kill criterion cannot be scored and the
    rule is unfalsifiable in production."""
    r, _ = _rt(monkeypatch, env=ON)
    p = _pos(opened_min_ago=7.0, md={"wildcard": 1.0, "sl_margin_pct": 16.58,
                                     "convex_peak_r": 0.31})
    r._convex_early_stop_exit(p, 0.25, now=NOW)
    assert p.metadata["early_stop_fired"] == 1.0
    assert p.metadata["early_stop_r_now"] == pytest.approx(-0.6031, abs=1e-3)
    assert p.metadata["early_stop_minutes"] == pytest.approx(7.0)
    assert p.metadata["early_stop_peak_r"] == 0.31


# --- per-sleeve scoping ----------------------------------------------------

def test_trend_is_off_even_when_the_shared_default_is_on(monkeypatch):
    """TREND prices at -$7.57/mo because its touched trades are its runners. An
    explicit per-sleeve zero must beat the shared value."""
    env = {"FUTURES_CONVEX_EARLY_STOP_R": 0.5, "FUTURES_TREND_EARLY_STOP_R": 0.0}
    r, closed = _rt(monkeypatch, env=env, kind="TREND")
    assert r._convex_early_stop_exit(_pos(signal="TREND_LONG"), 0.25, now=NOW) is False


def test_the_sleeve_override_beats_the_shared_value(monkeypatch):
    env = {"FUTURES_CONVEX_EARLY_STOP_R": 0.0, "FUTURES_WILDCARD_EARLY_STOP_R": 0.5,
           "FUTURES_WILDCARD_EARLY_STOP_MINUTES": 30.0}
    r, closed = _rt(monkeypatch, env=env)
    assert r._convex_early_stop_exit(_pos(), 0.25, now=NOW) is True


def test_shorts_are_not_excluded(monkeypatch):
    """No side restriction: shorts fired 0 of 10 in sample, so there is no
    evidence either way and an untested arm is not a harmful one."""
    r, closed = _rt(monkeypatch, env=ON)
    assert r._convex_early_stop_exit(_pos(side="SHORT"), 0.25, now=NOW) is True


# --- THE SHADOW DIAGNOSTIC, which runs whether or not the rule is armed -----

def test_the_diagnostic_records_depth_timings_while_the_rule_is_OFF(monkeypatch):
    """The free half of the finding: X is a ridge and must never be refit from the
    same rows it was read off. Recording time-to-depth live makes the axis
    tunable from the bot's own data at zero behavioural cost."""
    r, closed = _rt(monkeypatch, env={}, gross=-10.0)
    p = _pos(opened_min_ago=7.0)
    assert r._convex_early_stop_exit(p, 0.25, now=NOW) is False
    assert closed == []
    assert p.metadata["t_adverse_25"] == pytest.approx(7.0)
    assert p.metadata["t_adverse_50"] == pytest.approx(7.0)
    assert "t_adverse_75" not in p.metadata


def test_each_depth_is_stamped_once_at_FIRST_touch(monkeypatch):
    r, _ = _rt(monkeypatch, env={}, gross=-5.0)
    p = _pos(opened_min_ago=3.0)
    r._convex_early_stop_exit(p, 0.25, now=NOW)
    assert p.metadata["t_adverse_25"] == pytest.approx(3.0)
    assert "t_adverse_50" not in p.metadata
    # deeper, later — the shallow mark must not move
    monkeypatch.setattr(FuturesRuntime, "_position_pnl_pct", lambda self, p, px: -14.0)
    r._convex_early_stop_exit(p, 0.25, now=NOW + timedelta(minutes=9))
    assert p.metadata["t_adverse_25"] == pytest.approx(3.0)
    assert p.metadata["t_adverse_50"] == pytest.approx(12.0)
    assert p.metadata["t_adverse_75"] == pytest.approx(12.0)


def test_the_diagnostic_keeps_running_outside_the_window(monkeypatch):
    """The window bounds the ACTION, not the measurement."""
    r, closed = _rt(monkeypatch, env=ON)
    p = _pos(opened_min_ago=120.0)
    assert r._convex_early_stop_exit(p, 0.25, now=NOW) is False
    assert p.metadata["t_adverse_50"] == pytest.approx(120.0)


def test_a_bad_denominator_suppresses_the_diagnostic_too(monkeypatch):
    """A poisoned denominator would write nonsense marks."""
    r, _ = _rt(monkeypatch, env={}, risk_pct=4.0)
    p = _pos()
    r._convex_early_stop_exit(p, 0.25, now=NOW)
    assert "t_adverse_25" not in p.metadata


# --- /status ---------------------------------------------------------------

def test_status_shows_the_level_and_the_expiry_while_it_can_fire(monkeypatch):
    r, _ = _rt(monkeypatch, env=ON)
    out = r._early_stop_line(_pos(opened_min_ago=8.0), now=NOW)
    assert "$-12.58" in out, out
    assert "22m" in out, out


def test_status_shows_nothing_once_the_window_has_passed(monkeypatch):
    r, _ = _rt(monkeypatch, env=ON)
    assert r._early_stop_line(_pos(opened_min_ago=31.0), now=NOW) is None


def test_status_shows_nothing_when_the_rule_is_off(monkeypatch):
    r, _ = _rt(monkeypatch, env={})
    assert r._early_stop_line(_pos(), now=NOW) is None


def test_status_is_wired_into_the_position_block():
    import inspect
    src = inspect.getsource(FuturesRuntime._build_status_message)
    assert "_early_stop_line" in src
    assert src.index("Risk at SL") < src.index("_early_stop_line")


# --- /report ---------------------------------------------------------------

def test_report_says_nothing_until_it_has_fired(monkeypatch):
    r = FuturesRuntime.__new__(FuturesRuntime)
    r.trade_history = [{"symbol": "X", "pnl_usdt": -1.0}]
    monkeypatch.setattr(FuturesRuntime, "_metadata_float", lambda self, md, k: md.get(k))
    assert r._early_stop_report_line() is None


def test_report_counts_fires_and_flags_cuts_above_1R(monkeypatch):
    """The live proxy for the kill criterion: a fire on a trade that had already
    been meaningfully positive is the bad case, and it is countable."""
    r = FuturesRuntime.__new__(FuturesRuntime)
    monkeypatch.setattr(FuturesRuntime, "_metadata_float", lambda self, md, k: md.get(k))
    r.trade_history = [
        {"early_stop_fired": 1.0, "early_stop_r_now": -0.52, "early_stop_peak_r": 0.10},
        {"early_stop_fired": 1.0, "early_stop_r_now": -0.55, "early_stop_peak_r": 1.30},
        {"pnl_usdt": -1.0},
    ]
    out = r._early_stop_report_line()
    assert "2 fires" in out
    assert "-0.54R" in out or "-0.53R" in out
    assert "+1.30R" in out
    assert "cut above 1R: <b>1</b>" in out
    assert "⚠" in out


# --- wiring ----------------------------------------------------------------

def test_it_runs_before_the_trail_and_the_clock():
    import inspect
    src = inspect.getsource(FuturesRuntime._hourly_exit)
    assert src.index("_convex_early_stop_exit") < src.index("_convex_runner_trail_exit")
    assert src.index("_convex_early_stop_exit") < src.index("_convex_time_stop_exit")


def test_the_diagnostic_survives_the_close():
    """Five metadata fields have been silently dropped at close in this codebase.
    These must be promoted explicitly or the diagnostic is worthless."""
    import inspect
    src = inspect.getsource(FuturesRuntime._close_history_trade)
    for key in ("t_adverse_25", "t_adverse_50", "t_adverse_75",
                "early_stop_fired", "early_stop_r_now", "early_stop_peak_r"):
        assert key in src, key


def test_report_line_survives_a_runtime_with_no_trade_history(monkeypatch):
    """Regression: the first version accessed self.trade_history directly and
    broke /report for any partially-constructed runtime. /report is the command a
    withdrawal is decided from; a summary line must never be able to break it."""
    r = FuturesRuntime.__new__(FuturesRuntime)
    monkeypatch.setattr(FuturesRuntime, "_metadata_float", lambda self, md, k: md.get(k))
    assert r._early_stop_report_line() is None


def test_report_wraps_the_line_defensively():
    import inspect
    src = inspect.getsource(FuturesRuntime._build_report_message)
    i = src.index("_early_stop_report_line")
    seg = src[max(0, i - 300):i + 300]
    assert "try:" in seg and "except Exception" in seg
