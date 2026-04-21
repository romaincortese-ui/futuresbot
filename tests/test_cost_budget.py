from __future__ import annotations

import pytest

from futuresbot.cost_budget import compute_cost_bps, passes_cost_adjusted_rr


def test_compute_cost_bps_fee_only_short_hold():
    # 0.04% taker * 2 = 8 bps fees. Leverage 10: entry slip 5bps, exit 7.5bps.
    # Funding 0.01%/8h over 1h hold = 0.0001 * (1/8) * 10_000 = 0.125 bps.
    c = compute_cost_bps(leverage=10, hold_hours=1.0, funding_rate_8h=0.0001)
    assert c.fees_bps == pytest.approx(8.0)
    assert c.slippage_bps == pytest.approx(5.0 + 7.5)
    assert c.funding_bps == pytest.approx(0.125)
    assert c.total_bps == pytest.approx(c.fees_bps + c.slippage_bps + c.funding_bps)


def test_compute_cost_bps_negative_funding_still_costs_bps():
    # Absolute funding magnitude matters for cost budgeting; direction is a
    # separate concern handled by §2.3.
    c = compute_cost_bps(leverage=5, hold_hours=16.0, funding_rate_8h=-0.0005)
    assert c.funding_bps > 0


def test_passes_cost_adjusted_rr_gates_sub_economic_trades():
    # TP 1.5%, SL 1.0%, cost 50 bps (0.5%) -> effective R:R = 1.5 / 1.5 = 1.0 < 1.8.
    assert not passes_cost_adjusted_rr(
        tp_distance_pct=0.015,
        sl_distance_pct=0.010,
        cost_bps=50.0,
    )


def test_passes_cost_adjusted_rr_accepts_clean_geometry():
    # TP 3%, SL 1%, cost 10 bps (0.1%) -> 3.0 / 1.1 = 2.73 >= 1.8.
    assert passes_cost_adjusted_rr(
        tp_distance_pct=0.03,
        sl_distance_pct=0.01,
        cost_bps=10.0,
    )


def test_passes_cost_adjusted_rr_rejects_zero_distances():
    assert not passes_cost_adjusted_rr(tp_distance_pct=0.0, sl_distance_pct=0.01, cost_bps=10.0)
    assert not passes_cost_adjusted_rr(tp_distance_pct=0.02, sl_distance_pct=0.0, cost_bps=10.0)
