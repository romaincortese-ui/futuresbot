from __future__ import annotations

import pytest

from futuresbot.drawdown_kill import compute_drawdown_state


def _curve(points):
    return list(points)


def test_drawdown_state_normal_when_flat_curve():
    now = 1_700_000_000.0
    curve = [(now - i * 86400, 1_000.0) for i in range(100, 0, -1)]
    state = compute_drawdown_state(curve)
    assert state.label == "NORMAL"
    assert state.size_multiplier == 1.0


def test_drawdown_state_throttle_on_30d_bleed():
    now = 1_700_000_000.0
    # Peak 1000 at D-25, currently 920 -> 8% DD in 30d window.
    curve = [
        (now - 25 * 86400, 1_000.0),
        (now - 10 * 86400, 960.0),
        (now, 920.0),
    ]
    state = compute_drawdown_state(curve)
    assert state.label == "THROTTLE"
    assert state.size_multiplier == 0.5
    assert state.dd_30d == pytest.approx(0.08)


def test_drawdown_state_halt_on_90d_bleed():
    now = 1_700_000_000.0
    # Peak 1000 at D-60, currently 840 -> 16% DD in 90d window.
    curve = [
        (now - 60 * 86400, 1_000.0),
        (now, 840.0),
    ]
    state = compute_drawdown_state(curve)
    assert state.label == "HALT"
    assert state.size_multiplier == 0.0


def test_drawdown_state_ignores_points_outside_window():
    now = 1_700_000_000.0
    # Peak 1000 at D-120 (outside 90d window). Current 850. 30d window flat 850.
    curve = [
        (now - 120 * 86400, 1_000.0),
        (now - 10 * 86400, 850.0),
        (now, 850.0),
    ]
    state = compute_drawdown_state(curve)
    assert state.label == "NORMAL"


def test_drawdown_state_empty_curve():
    state = compute_drawdown_state([])
    assert state.label == "NORMAL"
    assert state.size_multiplier == 1.0
