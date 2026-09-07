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
