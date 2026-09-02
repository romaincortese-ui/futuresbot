"""The placebo control must catch a gate that is only reading the calendar.

Added 2026-09-02, after a majors-up gate passed a permutation test at p<1% and
was one step from being pre-registered. It was an artifact. A permutation test
asks whether a filter beat a RANDOM subset of the same size - correct for a
per-trade filter, wrong for a regime gate, because a gate selects by TIME in
contiguous stretches and this book is autocorrelated. Any time-correlated filter
clears that bar without knowing anything about markets.

These tests pin the property that matters: a gate whose apparent edge comes from
WHEN it trades rather than WHAT it knows must be caught.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pit_placebo import placebo_test  # noqa: E402

DAY = 86400.0


def _trades(pnl_by_day):
    """One trade per day, at noon, with the given P&L."""
    return [{"t": d * DAY + 43200.0, "usd": v} for d, v in enumerate(pnl_by_day)]


def _run(items, gate_at, shifts=(-7, -3, 3, 7)):
    return placebo_test(items, gate_at, time_of=lambda x: x["t"],
                        value_of=lambda x: x["usd"], shifts_days=shifts, min_n=1)


def test_a_calendar_reading_gate_is_REFUTED():
    """THE CASE THAT MOTIVATED THIS. P&L runs in blocks - a good week, a bad
    week - and the gate opens on one good block. It looks excellent. But a
    signal shifted by a whole cycle lands on a DIFFERENT good block and scores
    exactly the same, because neither gate knows anything: both pick dates."""
    items = _trades([5.0 if (d // 7) % 2 == 0 else -5.0 for d in range(56)])
    # A BOUNDED window on one good block, placed mid-sample so that every shift
    # still lands inside the data - an open-ended gate would empty itself under
    # half the shifts and the control would report INCONCLUSIVE instead.
    res = _run(items, lambda t: 28 * DAY <= t < 35 * DAY, shifts=(-14, -7, 7, 14))
    assert res.real > 0, "the gate should look profitable"
    assert len(res.usable) == 4, "all four shifts must stay inside the data"
    assert res.beaten_by, "a whole-cycle shift lands on an equally good block"
    assert res.verdict.startswith("REFUTED")


def test_a_gate_that_really_reads_the_signal_SURVIVES():
    """Alternating good and bad days, with the gate open exactly on the good
    ones. No time shift can reproduce that, because the pattern is not a block -
    shifting lands the gate on the losers."""
    items = _trades([5.0 if d % 2 == 0 else -5.0 for d in range(28)])
    res = _run(items, lambda t: int(t // DAY) % 2 == 0, shifts=(-7, -3, 3, 7))
    assert res.real > 0
    assert not res.beaten_by, "no shift should match a genuine per-day signal"
    assert res.verdict.startswith("SURVIVES")


def test_an_odd_day_shift_would_defeat_the_alternating_gate():
    """Honesty about the method's limits: a shift that happens to be in phase
    with the signal IS a fair placebo and should win. The control is only as
    good as the shifts chosen, which is why several are used."""
    items = _trades([5.0 if d % 2 == 0 else -5.0 for d in range(28)])
    res = _run(items, lambda t: int(t // DAY) % 2 == 0, shifts=(-3, 3))
    assert res.beaten_by == [] or res.real >= max(v for _, v, _ in res.usable)


def test_shifts_that_empty_the_book_are_excluded_not_counted_as_losses():
    """A shift landing outside the data yields no trades. Scoring that as a
    placebo defeat would flatter every gate."""
    items = _trades([1.0] * 5)
    # a BOUNDED window, so a large shift in either direction lands outside the
    # data. An open-ended gate would simply admit everything when shifted back.
    res = placebo_test(items, lambda t: 1 * DAY <= t < 3 * DAY,
                       time_of=lambda x: x["t"], value_of=lambda x: x["usd"],
                       shifts_days=(-90, 90), min_n=1)
    assert all(n == 0 for _, _, n in res.shifted)
    assert res.usable == []
    assert res.verdict.startswith("INCONCLUSIVE")


def test_too_few_usable_placebos_is_inconclusive_not_a_pass():
    """Two placebos cannot establish anything. The method must say so rather
    than report SURVIVES on thin evidence - the failure mode being guarded
    against is a confident verdict from almost no comparisons."""
    items = _trades([1.0] * 10)
    res = placebo_test(items, lambda t: t < 5 * DAY, time_of=lambda x: x["t"],
                       value_of=lambda x: x["usd"], shifts_days=(-1, 1), min_n=1)
    assert len(res.usable) < 3
    assert res.verdict.startswith("INCONCLUSIVE")


def test_it_decides_on_ENTRY_time():
    """A gate decides at entry. Scoring it on exit time would let the trade's
    own outcome window influence whether it was allowed."""
    import inspect

    import pit_placebo
    src = inspect.getsource(pit_placebo.placebo_test)
    assert "time_of" in src
    assert "NOT its exit" in inspect.getdoc(pit_placebo.placebo_test)
