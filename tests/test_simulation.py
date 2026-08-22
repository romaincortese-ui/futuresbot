"""/simulation — this trial's result on a bigger opening balance.

Sizing is a FRACTION of the balance, so scaling the opening balance scales every
stake and every P&L by the same factor. The simulation is that scaling, and these
pin it — plus the thing that does NOT scale, which is the order book.

An earlier version reconstructed the equity path from each trade's risk fraction
and R multiple. It had to model trade overlap and committed margin, got both
wrong in turn (+20.94% then -8.3% against a real +18.33%), and was replaced.
`test_scaling_reproduces_the_account_at_its_own_opening` is the property that
version could not satisfy.
"""
import pytest

from futuresbot.simulation import (SIM_BALANCES, capacity_notional, realised_pnl,
                                   risk_fraction, simulate, trial_opening_equity)


def _row(pnl, **kw):
    row = {"pnl_usdt": pnl, "r_multiple": 1.0, "risk_pct_actual": 2.0,
           "kind": "WILDCARD", "equity_at_entry": 100.0, "equity_at_close_usdt": 100.0,
           "margin_used": 10.0, "leverage": 3, "sl_margin_pct": 20.0}
    row.update(kw)
    return row


# --- the identity the whole module rests on --------------------------------

def test_scaling_reproduces_the_account_at_its_own_opening():
    """At k=1 the model must return exactly what the account did. Any deviation
    is a modelling error, and this is the check the reconstruction failed."""
    rows = [_row(10.0), _row(-4.0), _row(19.5)]
    out = simulate(rows, 139.61, actual_opening=139.61)
    assert out["scale"] == pytest.approx(1.0)
    assert out["realised"] == pytest.approx(25.5)
    assert out["equity"] == pytest.approx(139.61 + 25.5)


def test_pnl_scales_linearly_and_the_return_does_not_move():
    rows = [_row(25.54)]
    a = simulate(rows, 1000.0, actual_opening=139.61)
    b = simulate(rows, 10000.0, actual_opening=139.61)
    assert b["realised"] == pytest.approx(a["realised"] * 10.0)
    assert a["return_pct"] == pytest.approx(b["return_pct"])
    # ...and it equals the account's own return
    assert a["return_pct"] == pytest.approx(25.54 / 139.61 * 100.0)


def test_a_losing_trial_shrinks_the_simulated_account():
    out = simulate([_row(-25.0)], 10000.0, actual_opening=100.0)
    assert out["realised"] == pytest.approx(-2500.0)
    assert out["equity"] == pytest.approx(7500.0)


def test_open_positions_are_scaled_but_kept_separate():
    """Only realised is banked; the account still shows both."""
    out = simulate([_row(10.0)], 1000.0, actual_opening=100.0, open_unrealised=5.0)
    assert out["realised"] == pytest.approx(100.0)
    assert out["unrealised"] == pytest.approx(50.0)
    assert out["equity"] == pytest.approx(1150.0)


def test_degenerate_inputs_are_graceful():
    assert simulate([], 5000.0, actual_opening=0.0)["equity"] == 5000.0
    assert simulate([_row(1.0)], 0.0, actual_opening=100.0)["equity"] == 0.0
    assert simulate([], 5000.0, actual_opening=100.0)["return_pct"] == 0.0


# --- deriving the trial's own starting balance -----------------------------

def test_opening_equity_prefers_todays_equity_minus_the_trials_gains():
    rows = [_row(20.0), _row(5.54)]
    got = trial_opening_equity(rows, current_equity=173.21, open_unrealised=8.0)
    assert got == pytest.approx(173.21 - 25.54 - 8.0)


def test_opening_equity_falls_back_to_the_store_alone():
    """Same identity read from the last close's stamp when no live equity is on
    hand — used by the CLI twin, which has only the file."""
    rows = [_row(20.0, equity_at_close_usdt=0.0), _row(5.54, equity_at_close_usdt=165.15)]
    assert trial_opening_equity(rows) == pytest.approx(165.15 - 25.54)


def test_opening_equity_is_zero_when_nothing_can_be_derived():
    assert trial_opening_equity([]) == 0.0


def test_realised_pnl_skips_unparseable_rows():
    assert realised_pnl([_row(3.0), {"pnl_usdt": "x"}, _row(2.0)]) == pytest.approx(5.0)


# --- risk_fraction is reporting-only now, but still has to be right --------

def test_risk_fraction_prefers_the_stamped_value():
    assert risk_fraction(_row(1.0, risk_pct_actual=2.41)) == pytest.approx(0.0241)


def test_risk_fraction_falls_back_through_the_chain():
    assert risk_fraction({"risk_usdt": 3.0, "equity_at_entry": 150.0}) == pytest.approx(0.02)
    geometry = {"margin_used": 20.0, "sl_margin_pct": 15.0, "equity_at_entry": 200.0}
    assert risk_fraction(geometry) == pytest.approx(0.015)


def test_risk_fraction_is_zero_when_unpriceable():
    """Better a missing number than a fabricated one."""
    assert risk_fraction({"r_multiple": 5.0}) == 0.0


# --- capacity: the one thing that does NOT scale harmlessly ----------------

def test_notional_scales_with_the_balance():
    """A $165 account carrying ~$44 of notional carries ~$2,670 on $10,000,
    against a measured median top-10 depth of about $20k — which is why the
    report warns instead of implying linearity holds forever."""
    rows = [_row(1.0, margin_used=22.0, leverage=2)]
    cap = capacity_notional(rows, 10000.0, actual_opening=165.0)
    assert cap["n"] == 1
    assert cap["median"] == pytest.approx(44.0 * (10000.0 / 165.0))


def test_capacity_ignores_rows_it_cannot_price():
    assert capacity_notional([{"pnl_usdt": 1.0}], 10000.0, actual_opening=165.0)["n"] == 0
    assert capacity_notional([_row(1.0)], 10000.0, actual_opening=0.0)["n"] == 0


def test_capacity_reports_median_and_max_separately():
    rows = [_row(1.0, margin_used=m, leverage=1) for m in (1.0, 2.0, 50.0)]
    cap = capacity_notional(rows, 100.0, actual_opening=100.0)
    assert cap["median"] == pytest.approx(2.0)
    assert cap["max"] == pytest.approx(50.0)


def test_sim_balances_span_the_capacity_question():
    assert SIM_BALANCES == (1000.0, 2000.0, 5000.0, 10000.0)
