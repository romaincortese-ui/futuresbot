"""/status must say WHEN an open position closes, not only what could close it.

2026-09-08. With PONS_USDT open the owner asked "I don't know when it will close
if it doesn't hit SL or the trail or TP". Every other exit had a representation
in the position row - SL and TP as prices, the trail as TP progress - and the 24h
hard clock, the second most frequent exit in the scored book, had none.

The line is a DEADLINE, so the failure that matters is printing one that is not
real. Most of the tests below are that: a clock that cannot fire must return
None rather than a zero, a dash, or a time in the past dressed up as a future.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime

NOW = datetime(2026, 9, 7, 18, 25, tzinfo=timezone.utc)


def _pos(opened=None, signal="WILDCARD_SHORT", **kw):
    return FuturesPosition(
        symbol=kw.get("symbol", "PONS_USDT"), side=kw.get("side", "SHORT"),
        entry_price=0.7214, contracts=3, contract_size=100.0, leverage=2,
        margin_usdt=108.21, tp_price=0.12, sl_price=0.78,
        position_id="p1", order_id="o1",
        opened_at=opened if opened is not None else NOW - timedelta(hours=2, minutes=42),
        score=96.0, certainty=0.9, entry_signal=signal,
    )


@pytest.fixture
def rt(monkeypatch):
    r = FuturesRuntime.__new__(FuturesRuntime)
    monkeypatch.setattr(FuturesRuntime, "_is_wildcard_convex", lambda self, p: True)
    monkeypatch.setattr(FuturesRuntime, "_env_float",
                        lambda self, k, d=0.0: 24.0 if "TIME_STOP" in k else d)
    return r


# --- the number itself ----------------------------------------------------

def test_it_reports_the_remaining_time_and_the_wall_clock_deadline(rt):
    out = rt._time_stop_line(_pos(), now=NOW)
    assert "21h 18m" in out, out
    assert "Tue 08 Sep 15:43 UTC" in out, out
    assert "held 2h 42m" in out, out


def test_the_deadline_is_opened_at_plus_the_configured_hours(rt):
    opened = datetime(2026, 9, 7, 15, 42, tzinfo=timezone.utc)
    out = rt._time_stop_line(_pos(opened), now=NOW)
    assert "Tue 08 Sep 15:42 UTC" in out, out
    assert "held 2h 43m" in out, out


def test_a_non_default_clock_is_honoured(monkeypatch):
    r = FuturesRuntime.__new__(FuturesRuntime)
    monkeypatch.setattr(FuturesRuntime, "_is_wildcard_convex", lambda self, p: True)
    monkeypatch.setattr(FuturesRuntime, "_env_float", lambda self, k, d=0.0: 48.0)
    assert "Wed 09 Sep 15:42 UTC" in r._time_stop_line(
        _pos(datetime(2026, 9, 7, 15, 42, tzinfo=timezone.utc)), now=NOW)


def test_an_overdue_position_says_due_now_not_a_negative_countdown(rt):
    out = rt._time_stop_line(_pos(NOW - timedelta(hours=25)), now=NOW)
    assert "due now" in out
    assert "-" not in out.split("held")[0].replace("—", "")
    assert "held 1d 1h" in out


# --- a deadline that is not real must not be printed ----------------------

def test_a_non_convex_position_has_no_clock(monkeypatch):
    r = FuturesRuntime.__new__(FuturesRuntime)
    monkeypatch.setattr(FuturesRuntime, "_is_wildcard_convex", lambda self, p: False)
    monkeypatch.setattr(FuturesRuntime, "_env_float", lambda self, k, d=0.0: 24.0)
    assert r._time_stop_line(_pos(signal="PMT_LONG"), now=NOW) is None


def test_a_disabled_clock_returns_nothing_rather_than_zero(monkeypatch):
    """FUTURES_CONVEX_TIME_STOP_HOURS=0 disables the exit. Printing '0m' would
    read as an imminent close."""
    r = FuturesRuntime.__new__(FuturesRuntime)
    monkeypatch.setattr(FuturesRuntime, "_is_wildcard_convex", lambda self, p: True)
    monkeypatch.setattr(FuturesRuntime, "_env_float", lambda self, k, d=0.0: 0.0)
    assert r._time_stop_line(_pos(), now=NOW) is None


@pytest.mark.parametrize("bad", [None, "nonsense", 0, float("nan")])
def test_a_missing_or_junk_opened_at_returns_none(rt, bad):
    p = _pos()
    object.__setattr__(p, "opened_at", bad) if hasattr(p, "__setattr__") else None
    p.opened_at = bad
    assert rt._time_stop_line(p, now=NOW) is None


def test_a_naive_opened_at_is_treated_as_utc_not_crashed_on(rt):
    """Persisted timestamps have round-tripped through JSON; a tz-naive one must
    not raise inside /status."""
    out = rt._time_stop_line(_pos(datetime(2026, 9, 7, 15, 42)), now=NOW)
    assert out is not None and "15:42 UTC" in out


def test_clock_skew_does_not_print_a_negative_age(rt):
    """opened_at in the future (skew, or a bad persisted row) must not render as
    a negative held time."""
    out = rt._time_stop_line(_pos(NOW + timedelta(hours=3)), now=NOW)
    assert "held 0m" in out and "-" not in out.split("(")[0]


# --- formatting -----------------------------------------------------------

@pytest.mark.parametrize("secs,want", [
    (0, "0m"), (59, "0m"), (60, "1m"), (3599, "59m"),
    (3600, "1h 00m"), (9720, "2h 42m"), (86399, "23h 59m"),
    (86400, "1d 0h"), (90000, "1d 1h"),
])
def test_duration_formatting(secs, want):
    assert FuturesRuntime._short_duration(secs) == want


def test_duration_never_goes_negative():
    assert FuturesRuntime._short_duration(-500) == "0m"


# --- it is actually wired into /status ------------------------------------

def test_status_calls_it_for_every_open_position():
    import inspect

    src = inspect.getsource(FuturesRuntime._build_status_message)
    assert "_time_stop_line" in src, "the clock is not wired into /status"
    # It must sit inside the per-position loop, after the risk line, not once
    # for the whole message.
    assert src.index("Risk at SL") < src.index("_time_stop_line")


# =========================================================================
# THE TRAIL LINE
#
# Added on the owner's instruction to express it in dollars: "translate the R
# into $, it's easier to read". The defect it fixes is not a missing line but a
# WRONG one - once the trail arms, the floor is the binding exit and the SL
# price the row prints is no longer what closes the trade.
# =========================================================================

def _trail_rt(monkeypatch, *, one_r=18.46, peak_r=None, retain=0.50, arm=1.0,
              convex=True, flag=True, lev=2, risk_pct=17.06):
    r = FuturesRuntime.__new__(FuturesRuntime)
    env = {"FUTURES_CONVEX_TRAIL_ARM_R": arm,
           "FUTURES_CONVEX_TRAIL_RETAIN_FRAC": retain,
           "FUTURES_CONVEX_TRAIL_RATCHET_R": 3.0,
           "FUTURES_CONVEX_TRAIL_RATCHET_RETAIN": 0.75,
           "FUTURES_CONVEX_COST_PCT": 0.190,
           "FUTURES_CONVEX_COST_FLOOR_MULT": 1.5}
    monkeypatch.setattr(FuturesRuntime, "_is_wildcard_convex", lambda self, p: convex)
    monkeypatch.setattr(FuturesRuntime, "_flag", lambda self, k, default=False: flag)
    monkeypatch.setattr(FuturesRuntime, "_env_float",
                        lambda self, k, d=0.0: env.get(k, d))
    monkeypatch.setattr(FuturesRuntime, "_position_stop_risk_usdt", lambda self, p: one_r)
    monkeypatch.setattr(FuturesRuntime, "_position_stop_risk_pct_of_margin",
                        lambda self, p: risk_pct)
    monkeypatch.setattr(FuturesRuntime, "_metadata_float",
                        lambda self, md, k: md.get(k))
    p = _pos()
    p.leverage = lev
    p.metadata = {} if peak_r is None else {"convex_peak_r": peak_r}
    return r, p


def test_before_arming_it_says_what_dollar_peak_arms_the_trail(monkeypatch):
    """The owner's example: 'it will arm at +$7'."""
    r, p = _trail_rt(monkeypatch, peak_r=0.7037)
    out = r._trail_line(p)
    assert "peak <b>$+12.99</b>" in out, out
    assert "arms at <b>$+18.46</b>" in out, out
    assert "ARMED" not in out


def test_a_position_that_never_moved_still_shows_the_arm_level(monkeypatch):
    r, p = _trail_rt(monkeypatch, peak_r=None)
    out = r._trail_line(p)
    assert "peak <b>$+0.00</b>" in out and "arms at <b>$+18.46</b>" in out


def test_once_armed_it_shows_the_dollar_floor_and_says_it_binds(monkeypatch):
    """peak 2R = $36.92, retain 0.50 -> floor 1R = $18.46."""
    r, p = _trail_rt(monkeypatch, peak_r=2.0)
    out = r._trail_line(p)
    assert "ARMED" in out
    assert "peak <b>$+36.92</b>" in out, out
    assert "exits at <b>$+18.46</b>" in out, out
    assert "keeps 50%" in out
    assert "binds before SL" in out


def test_the_ratchet_above_3R_is_reflected(monkeypatch):
    """peak 4R = $73.84, retain ratchets 0.50 -> 0.75, floor 3R = $55.38."""
    r, p = _trail_rt(monkeypatch, peak_r=4.0)
    out = r._trail_line(p)
    assert "exits at <b>$+55.38</b>" in out, out
    assert "keeps 75%" in out, out


def test_the_cost_floor_can_lift_the_exit_above_the_plain_retention(monkeypatch):
    """A tight stop makes the round trip expensive in R, so the breakeven guard
    raises the floor above 0.50 x peak."""
    r, p = _trail_rt(monkeypatch, peak_r=1.0, lev=20, risk_pct=2.0)
    out = r._trail_line(p)
    # sl_frac = 2.0/(20*100) = 0.001 -> cost_r = 0.0019/0.001 = 1.9R; x1.5 = 2.85R
    # 2.85 >= peak 1.0, so the exit path refuses to trail at all
    assert "cannot trail" in out, out
    assert "SL/TP/clock only" in out


def test_a_trail_that_cannot_fire_says_so_rather_than_printing_a_floor(monkeypatch):
    r, p = _trail_rt(monkeypatch, peak_r=1.2, lev=20, risk_pct=2.0)
    out = r._trail_line(p)
    assert "cannot trail" in out
    assert "exits at" not in out


def test_1R_is_the_same_number_as_the_risk_at_SL_line(monkeypatch):
    """The two lines are computed from one quantity and must never drift: the
    trail's r_now is (pnl % of margin) / (stop risk % of margin), so 1R IS the
    Risk at SL dollar figure."""
    r, p = _trail_rt(monkeypatch, one_r=40.00, peak_r=1.0)
    out = r._trail_line(p)
    assert "peak <b>$+40.00</b>" in out, out
    assert "exits at <b>$+20.00</b>" in out, out


# --- a floor that cannot be reached must not be printed -------------------

def test_non_convex_has_no_trail(monkeypatch):
    r, p = _trail_rt(monkeypatch, peak_r=2.0, convex=False)
    assert r._trail_line(p) is None


def test_the_runner_trail_flag_off_prints_nothing(monkeypatch):
    r, p = _trail_rt(monkeypatch, peak_r=2.0, flag=False)
    assert r._trail_line(p) is None


@pytest.mark.parametrize("bad", [None, 0.0, -5.0, float("nan")])
def test_no_usable_stop_distance_prints_nothing(monkeypatch, bad):
    """Without a stop distance there is no R, so there is no dollar floor."""
    r, p = _trail_rt(monkeypatch, one_r=bad, peak_r=2.0)
    assert r._trail_line(p) is None


def test_a_nan_peak_prints_nothing(monkeypatch):
    r, p = _trail_rt(monkeypatch, peak_r=float("nan"))
    assert r._trail_line(p) is None


def test_status_shows_the_trail_before_the_clock():
    import inspect

    src = inspect.getsource(FuturesRuntime._build_status_message)
    assert "_trail_line" in src, "the trail is not wired into /status"
    assert src.index("Risk at SL") < src.index("_trail_line") < src.index("_time_stop_line")
