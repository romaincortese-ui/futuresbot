"""A trial must be scored on the trades it CAUSED.

`ts` on a feature row is the EXIT stamp. Counting trial 18 by exit time read 17
closes and +$2.58; by entry time it was 15 and -$2.04, because two positions
opened under trial 17's sizing settled inside 18. The rule is pre-registered in
docs/DECISION_RULE.md.

/status implemented it. /report and /simulation did not, so the two commands
printed different n and different netR for the same trial on the same day - and
/report is the one the verdict is read from.
"""
from __future__ import annotations

import inspect

from futuresbot.runtime import FuturesRuntime


def _src_of(marker: str) -> str:
    for name in dir(FuturesRuntime):
        try:
            s = inspect.getsource(getattr(FuturesRuntime, name))
        except Exception:
            continue
        if marker in s:
            return s
    raise AssertionError("no method containing %r" % marker)


def test_entry_time_is_derived_by_subtracting_the_hold():
    rt = FuturesRuntime.__new__(FuturesRuntime)
    assert rt._row_opened_at({"ts": 10_000.0, "hold_hours": 1.0}) == 10_000.0 - 3600.0
    assert rt._row_opened_at({"ts": 10_000.0}) == 10_000.0
    assert rt._row_opened_at({}) == 0.0


def test_a_carryover_is_excluded_from_the_trial():
    """A trade opened before the trial and closed inside it is NOT a trial
    trade, however tempting its P&L."""
    rt = FuturesRuntime.__new__(FuturesRuntime)
    start = 1_000_000.0
    carried = {"ts": start + 3600.0, "hold_hours": 5.0}     # opened before
    genuine = {"ts": start + 7200.0, "hold_hours": 1.0}     # opened after
    assert rt._row_opened_at(carried) < start
    assert rt._row_opened_at(genuine) >= start


def test_report_scores_the_trial_by_ENTRY_time():
    src = _src_of("KPI                  value")
    assert "_row_opened_at" in src, "/report is counting by exit time again"


def test_simulation_scores_the_trial_by_ENTRY_time():
    src = _src_of("Open positions, so the figure matches")
    assert "_row_opened_at" in src, "/simulation is counting by exit time again"


def test_status_still_scores_the_trial_by_ENTRY_time():
    src = _src_of("convex closes")
    assert "_row_opened_at" in src


def test_report_says_when_it_dropped_a_carryover():
    """The owner has seen these numbers under the old count. A figure that
    silently drops is worse than one that explains itself."""
    src = _src_of("KPI                  value")
    assert "opened before this trial" in src


def test_integrity_compares_RECORDED_closes_not_trial_trades():
    """REGRESSION, self-inflicted. Filtering the trial by entry time made the
    scorecard compare 25 entry-filtered rows against 27 exchange closes and
    report 'MISSING ROWS - the ledger is not trustworthy', which then set the
    whole report's INVESTIGATE banner. The two carryovers were ordinary, the
    ledger was fine, and this fired on the morning of a deposit.

    Integrity asks 'did we record every close' (exit time). Trial scoring asks
    'which trades belong to this trial' (entry time). Different questions."""
    from futuresbot.scorecard import build_scorecard

    rows = [{"ts": 100.0, "pnl_usdt": 1.0, "r_multiple": 0.5}] * 25
    kpis = build_scorecard(rows, days=6.3, exchange_closes=27,
                           recorded_closes=27)
    integrity = next(k for k in kpis if k.name == "Ledger integrity")
    assert integrity.verdict == "Good", integrity.value
    assert "opened before the trial" in integrity.note


def test_integrity_still_catches_a_genuinely_missing_row():
    """The check must not be defanged by the fix."""
    from futuresbot.scorecard import build_scorecard

    rows = [{"ts": 100.0, "pnl_usdt": 1.0, "r_multiple": 0.5}] * 25
    kpis = build_scorecard(rows, days=6.3, exchange_closes=27,
                           recorded_closes=26)
    integrity = next(k for k in kpis if k.name == "Ledger integrity")
    assert integrity.verdict == "Bad"


def test_recorded_closes_defaults_to_the_row_count():
    """Callers that do not filter by entry time must be unaffected."""
    from futuresbot.scorecard import build_scorecard

    rows = [{"ts": 100.0, "pnl_usdt": 1.0, "r_multiple": 0.5}] * 27
    kpis = build_scorecard(rows, days=6.3, exchange_closes=27)
    assert next(k for k in kpis if k.name == "Ledger integrity").verdict == "Good"
