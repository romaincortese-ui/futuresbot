"""/simulation — this trial's result on a bigger opening balance.

The bot sizes as a FRACTION of equity, so the percentage equity curve is identical
at any starting balance. That makes the simulation arithmetic rather than a
forecast, and these pin the arithmetic — plus the two things that are easy to get
wrong: which rows are in scope, and the fact that notional does NOT scale
harmlessly.
"""
import pytest

from futuresbot.simulation import (SIM_BALANCES, capacity_notional,
                                   risk_fraction, simulate)


def _row(r, risk_pct=2.0, **kw):
    row = {"r_multiple": r, "risk_pct_actual": risk_pct, "kind": "WILDCARD",
           "equity_at_entry": 100.0, "margin_used": 10.0, "leverage": 3,
           "sl_margin_pct": 20.0, "ts": 0.0, "hold_hours": 0.0}
    row.update(kw)
    return row


def test_risk_fraction_prefers_the_stamped_value():
    """risk_pct_actual is written at entry and already includes the regime
    multiplier, so it reproduces the real allocation rather than a guess."""
    assert risk_fraction(_row(1.0, risk_pct=2.41)) == pytest.approx(0.0241)


def test_risk_fraction_falls_back_through_the_chain():
    no_pct = {"risk_usdt": 3.0, "equity_at_entry": 150.0}
    assert risk_fraction(no_pct) == pytest.approx(0.02)
    geometry = {"margin_used": 20.0, "sl_margin_pct": 15.0, "equity_at_entry": 200.0}
    assert risk_fraction(geometry) == pytest.approx(0.015)


def test_an_unpriceable_row_contributes_nothing():
    """Better a missing trade than a fabricated one."""
    assert risk_fraction({"r_multiple": 5.0}) == 0.0
    out = simulate([{"r_multiple": 5.0}], 1000.0)
    assert out["realised"] == 0.0 and out["equity"] == 1000.0


def test_single_trade_is_balance_times_risk_times_r():
    out = simulate([_row(2.0, risk_pct=2.0)], 1000.0)
    assert out["realised"] == pytest.approx(40.0)      # 1000 * 0.02 * 2
    assert out["equity"] == pytest.approx(1040.0)


def test_it_compounds_when_trades_do_not_overlap():
    """Sequential trades: the second is sized off what the first produced."""
    a = _row(1.0, ts=1000.0, hold_hours=0.1)
    b = _row(1.0, ts=2000.0, hold_hours=0.1)
    out = simulate([a, b], 1000.0)                     # 2% risk, +1R each
    assert out["equity"] == pytest.approx(1040.40)     # 1000 -> 1020 -> 1040.40


def test_overlapping_trades_are_sized_at_entry_not_at_close():
    """THE correction. This book runs up to five slots, so trades that were open
    at the same time were each sized off an equity that did NOT yet contain the
    others' P&L. Compounding them in close order sizes the second off gains that
    had not landed — on trial 15 that read +20.94% against a real +18.33%."""
    # both open at t=0, close at t=100 and t=200
    a = _row(1.0, ts=100.0, hold_hours=100.0 / 3600.0)
    b = _row(1.0, ts=200.0, hold_hours=200.0 / 3600.0)
    out = simulate([a, b], 1000.0)
    # both staked 2% of 1000 = 20 at entry, both +1R -> +40 flat, NOT 40.40
    assert out["equity"] == pytest.approx(1040.00)


def test_capital_freed_by_a_close_is_available_to_a_later_entry():
    a = _row(1.0, ts=100.0, hold_hours=100.0 / 3600.0)   # opens 0, closes 100
    b = _row(1.0, ts=300.0, hold_hours=100.0 / 3600.0)   # opens 200
    out = simulate([a, b], 1000.0)
    assert out["equity"] == pytest.approx(1040.40)


def test_percentage_return_is_identical_at_every_opening_balance():
    """THE core property: fractional sizing means the % curve does not depend on
    the starting balance, so P&L scales exactly. This is a result, not an
    approximation, and the report says so."""
    rows = [_row(2.0), _row(-1.0), _row(0.5)]
    pcts = [simulate(rows, b)["return_pct"] for b in SIM_BALANCES]
    assert all(p == pytest.approx(pcts[0]) for p in pcts)
    # ...and dollars scale with the balance
    a = simulate(rows, 1000.0)["realised"]
    b = simulate(rows, 10000.0)["realised"]
    assert b == pytest.approx(a * 10.0)


def test_a_losing_trial_shrinks_the_simulated_account():
    out = simulate([_row(-1.0, risk_pct=2.41)], 10000.0)
    assert out["realised"] == pytest.approx(-241.0)
    assert out["equity"] == pytest.approx(9759.0)


def test_open_positions_are_marked_but_kept_separate():
    """Only realised is banked; the account still shows both."""
    out = simulate([_row(1.0)], 1000.0, open_positions=[(0.02, 3.0)])
    assert out["realised"] == pytest.approx(20.0)
    assert out["unrealised"] == pytest.approx(1020.0 * 0.02 * 3.0)
    assert out["equity"] == pytest.approx(1020.0 + 61.2)


def test_empty_trial_is_graceful():
    out = simulate([], 5000.0)
    assert out["equity"] == 5000.0 and out["return_pct"] == 0.0


# --- capacity: the one thing that does NOT scale harmlessly ----------------

def test_notional_scales_with_the_balance():
    """margin x leverage x (balance/equity). A $165 account carrying $50 of
    notional carries ~$3,000 on $10,000, against a measured median top-10 book
    depth of about $20k — which is why the report warns rather than implying
    linearity holds forever."""
    rows = [_row(1.0, margin_used=22.0, leverage=2, equity_at_entry=165.0)]
    cap = capacity_notional(rows, 10000.0)
    assert cap["n"] == 1
    assert cap["median"] == pytest.approx(22.0 * 2 * (10000.0 / 165.0))
    assert cap["max"] == pytest.approx(cap["median"])


def test_capacity_ignores_rows_it_cannot_price():
    assert capacity_notional([{"r_multiple": 1.0}], 10000.0)["n"] == 0


def test_capacity_reports_median_and_max_separately():
    rows = [_row(1.0, margin_used=m, leverage=1, equity_at_entry=100.0)
            for m in (1.0, 2.0, 50.0)]
    cap = capacity_notional(rows, 100.0)
    assert cap["median"] == pytest.approx(2.0)
    assert cap["max"] == pytest.approx(50.0)
