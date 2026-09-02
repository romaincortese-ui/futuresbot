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


def _run(items, gate_at, shifts=None):
    """Uses the DENSE default unless a specific set is given. The control needs
    >= 30 usable placebos to report a percentile at all."""
    kw = {} if shifts is None else {"shifts_days": shifts}
    return placebo_test(items, gate_at, time_of=lambda x: x["t"],
                        value_of=lambda x: x["usd"], min_n=1, **kw)


def test_a_calendar_reading_gate_is_REFUTED():
    """THE CASE THAT MOTIVATED THIS. P&L runs in blocks - a good week, a bad
    week - and the gate opens on one good block. It looks excellent. But a
    signal shifted by a whole cycle lands on a DIFFERENT good block and scores
    exactly the same, because neither gate knows anything: both pick dates."""
    # 200 days on a 14-day cycle, gate open on one good block mid-sample. Any
    # shift landing a whole number of cycles away hits an equally good block.
    items = _trades([5.0 if (d // 7) % 2 == 0 else -5.0 for d in range(200)])
    res = _run(items, lambda t: 98 * DAY <= t < 105 * DAY)
    assert res.real > 0, "the gate should look profitable"
    assert len(res.usable) >= 30, "the dense null must produce a percentile"
    assert res.beaten_by, "whole-cycle shifts land on equally good blocks"
    assert res.verdict.startswith("REFUTED")


def test_a_gate_that_really_reads_the_signal_SURVIVES():
    """A NON-PERIODIC signal, with the gate open exactly on the good days.

    Non-periodic matters: an alternating pattern would be reproduced by any
    even-day shift, so the placebo would rightly refute it. Here nothing
    repeats, so no shift can land on the winners and the control must pass it.
    """
    import random
    rng = random.Random(7)
    good = {d for d in range(200) if rng.random() < 0.4}
    items = _trades([5.0 if d in good else -5.0 for d in range(200)])
    res = _run(items, lambda t: int(t // DAY) in good)
    assert res.real > 0
    assert len(res.usable) >= 30
    assert not res.beaten_by, "no shift should match a genuine per-day signal"
    assert res.verdict.startswith("SURVIVES")


def test_a_PERIODIC_signal_is_refuted_and_that_is_correct():
    """Honesty about what the control can and cannot establish. If a signal
    simply alternates, a shift in phase with it reproduces it exactly - so the
    control refutes it. That is the RIGHT answer: a periodic pattern is
    indistinguishable from a calendar rule, whatever generated it."""
    items = _trades([5.0 if d % 2 == 0 else -5.0 for d in range(200)])
    res = _run(items, lambda t: int(t // DAY) % 2 == 0)
    assert res.beaten_by, "even-day shifts reproduce an alternating signal"


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
    assert len(res.usable) < 30
    assert res.verdict.startswith("INCONCLUSIVE")


def test_the_default_null_is_dense_enough_to_mean_something():
    """The first version shipped with six shifts, so the strongest possible
    verdict was 'beat all six' - which a null gate reaches ~1 time in 7. Pointed
    at ten known-null regime hypotheses it called five of them survivors."""
    from pit_placebo import DEFAULT_SHIFTS_DAYS as D
    assert len(D) >= 100, "a percentile needs a dense null"
    assert 100.0 / len(D) <= 1.0, "best achievable rank must be under 1%"
    assert min(abs(x) for x in D) >= 4.0, (
        "shifts shorter than the signal lookback are blurred copies, not placebos")


def test_it_decides_on_ENTRY_time():
    """A gate decides at entry. Scoring it on exit time would let the trade's
    own outcome window influence whether it was allowed."""
    import inspect

    import pit_placebo
    src = inspect.getsource(pit_placebo.placebo_test)
    assert "time_of" in src
    assert "NOT its exit" in inspect.getdoc(pit_placebo.placebo_test)
