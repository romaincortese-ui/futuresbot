"""Shadow stop-ladder marks and the early-stop trough fix (wc/SL, 2026-09-23).

Both are decision-free: they write telemetry and are never read by any entry or exit.
The marks make every future fill a data point for the pre-registered TREND -0.8R review;
the trough fix makes mae_r true on the poll where the early stop fires (BR 2026-09-17
recorded -0.18R and was cut at -0.61R).
"""
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from futuresbot.runtime import EXIT_TELEMETRY_KEYS, FuturesRuntime


def _rt():
    return object.__new__(FuturesRuntime)


def _pos(md=None):
    return SimpleNamespace(symbol="BR_USDT", side="LONG", metadata={} if md is None else md,
                           opened_at=datetime.now(timezone.utc) - timedelta(minutes=10))


def test_the_ladder_rungs_are_recorded():
    keys = [k for _, k in FuturesRuntime._ADVERSE_MARKS]
    for k in ("t_adverse_60", "t_adverse_70", "t_adverse_80", "t_adverse_90"):
        assert k in keys
    depths = [d for d, _ in FuturesRuntime._ADVERSE_MARKS]
    assert depths == sorted(depths)


def test_a_touch_stamps_every_rung_it_passed_and_no_deeper():
    rt, p = _rt(), _pos()
    rt._stamp_adverse_marks(p, -0.85, 12.5)
    md = p.metadata
    for k in ("t_adverse_25", "t_adverse_50", "t_adverse_60", "t_adverse_70",
              "t_adverse_75", "t_adverse_80"):
        assert md[k] == 12.5
    assert "t_adverse_90" not in md


def test_each_rung_is_stamped_once_at_its_first_touch():
    rt, p = _rt(), _pos()
    rt._stamp_adverse_marks(p, -0.82, 5.0)
    rt._stamp_adverse_marks(p, -0.95, 40.0)
    assert p.metadata["t_adverse_80"] == 5.0          # first touch wins
    assert p.metadata["t_adverse_90"] == 40.0


def test_the_marks_reach_the_closed_trade_record():
    for k in ("t_adverse_60", "t_adverse_70", "t_adverse_80", "t_adverse_90"):
        assert k in EXIT_TELEMETRY_KEYS


def _early_stop_rt(r_now):
    rt = _rt()
    rt._is_wildcard_convex = lambda p: True
    rt._position_stop_risk_pct_of_margin = lambda p: 10.0
    rt._position_pnl_pct = lambda p, px: r_now * 10.0
    rt._metadata_float = lambda md, k: (float(md[k]) if md.get(k) is not None else None)
    rt._sleeve_kind = lambda p: "WILDCARD"
    rt._env_float = lambda name, default=0.0: {"FUTURES_WILDCARD_EARLY_STOP_R": 0.5,
                                               "FUTURES_WILDCARD_EARLY_STOP_MINUTES": 30.0
                                               }.get(name, default)
    rt._save_state = lambda: None
    rt._format_price = lambda px: str(px)
    rt.closed = []
    rt._close_position_for_exit = lambda p, current_price, reason: rt.closed.append(reason) or True
    return rt


def test_the_trough_is_written_on_the_poll_the_early_stop_fires():
    """The trail runs AFTER the early stop, so on the firing poll it never ran and the
    trade record kept the trough from before the cut."""
    rt = _early_stop_rt(-0.61)
    p = _pos({"convex_trough_r": -0.18, "sl_margin_pct": 10.0})
    assert rt._convex_early_stop_exit(p, 1.0) is True
    assert rt.closed == ["CONVEX_EARLY_STOP"]
    assert p.metadata["convex_trough_r"] == pytest.approx(-0.61)


def test_the_trough_is_written_even_when_the_early_stop_does_not_fire():
    rt = _early_stop_rt(-0.30)
    p = _pos({"convex_trough_r": -0.10, "sl_margin_pct": 10.0})
    assert rt._convex_early_stop_exit(p, 1.0) is False
    assert p.metadata["convex_trough_r"] == pytest.approx(-0.30)


def test_the_trough_never_moves_up():
    rt = _early_stop_rt(-0.20)
    p = _pos({"convex_trough_r": -0.45, "sl_margin_pct": 10.0})
    rt._convex_early_stop_exit(p, 1.0)
    assert p.metadata["convex_trough_r"] == pytest.approx(-0.45)


def test_nothing_here_reads_a_mark():
    """Decision-free by construction: no entry or exit path reads the new marks."""
    for name in ("_convex_early_stop_exit", "_convex_runner_trail_exit",
                 "_maybe_breakeven_stop", "_convex_time_stop_exit"):
        src = inspect.getsource(getattr(FuturesRuntime, name))
        for k in ("t_adverse_60", "t_adverse_70", "t_adverse_80", "t_adverse_90"):
            assert k not in src
