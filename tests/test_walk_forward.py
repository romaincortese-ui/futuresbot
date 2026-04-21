from __future__ import annotations

from futuresbot.walk_forward import (
    WalkForwardMetrics,
    evaluate_walk_forward,
)


def _m(trades: int, pf: float, wr: float = 0.5, ex: float = 1.0) -> WalkForwardMetrics:
    return WalkForwardMetrics(trades=trades, profit_factor=pf, win_rate=wr, expectancy=ex)


def test_accepts_healthy_oos():
    gate = evaluate_walk_forward(
        is_metrics=_m(100, 1.8),
        oos_metrics=_m(40, 1.5),
    )
    assert gate.accepted is True
    assert gate.degradation > 0  # oos is modestly worse


def test_rejects_insufficient_oos_trades():
    gate = evaluate_walk_forward(
        is_metrics=_m(100, 2.0),
        oos_metrics=_m(5, 3.0),
        min_oos_trades=20,
    )
    assert gate.accepted is False
    assert "oos_trades" in gate.reason


def test_rejects_oos_pf_below_floor():
    gate = evaluate_walk_forward(
        is_metrics=_m(100, 1.5),
        oos_metrics=_m(30, 1.05),
        min_oos_pf=1.15,
    )
    assert gate.accepted is False
    assert "oos_pf" in gate.reason


def test_rejects_excessive_degradation():
    # IS=3.0, OOS=1.5 -> degradation 0.5, above 0.4 default; OOS passes 1.15 floor
    gate = evaluate_walk_forward(
        is_metrics=_m(100, 3.0),
        oos_metrics=_m(40, 1.5),
    )
    assert gate.accepted is False
    assert "degradation" in gate.reason


def test_rejects_on_degenerate_is_pf():
    gate = evaluate_walk_forward(
        is_metrics=_m(100, 0.0),
        oos_metrics=_m(30, 1.5),
    )
    assert gate.accepted is False
