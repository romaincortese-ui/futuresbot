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


# ---- the trough lag (ZEC 2026-09-23: filled at -1.07R, recorded mae_r -1.67R) ----

def _held(side="LONG", entry=100.0, sl=90.0, md=None):
    return SimpleNamespace(symbol="ZEC_USDT", side=side, entry_price=entry, sl_price=sl,
                           metadata={} if md is None else md)


def test_the_trough_stops_counting_once_the_stop_is_crossed():
    """After the fair price crosses the stop, the exchange has closed the trade; the
    polls that follow until reconciliation notices are about a position we no longer
    hold and must not deepen its MAE."""
    rt, p = _rt(), _held()
    rt._note_trough(p, -0.50, 95.0)                   # held, above the stop
    rt._note_trough(p, -1.02, 89.8)                   # the crossing poll is recorded
    rt._note_trough(p, -1.60, 84.0)                   # the lag: must be ignored
    rt._note_trough(p, -1.90, 81.0)
    assert p.metadata["convex_trough_r"] == pytest.approx(-1.02)
    assert p.metadata["trough_frozen_ts"] > 0


def test_a_short_freezes_on_the_way_up():
    rt, p = _rt(), _held(side="SHORT", entry=100.0, sl=110.0)
    rt._note_trough(p, -0.4, 104.0)
    rt._note_trough(p, -1.01, 110.1)
    rt._note_trough(p, -1.7, 117.0)
    assert p.metadata["convex_trough_r"] == pytest.approx(-1.01)


def test_an_armed_breakeven_stop_is_the_one_that_counts():
    """Once the breakeven stop is resting, crossing back to entry closes the trade."""
    rt, p = _rt(), _held(md={"be_stop_price": 100.19})
    rt._note_trough(p, 0.40, 104.0)
    rt._note_trough(p, 0.01, 100.18)                  # crossed the breakeven stop
    rt._note_trough(p, -0.60, 94.0)                   # the lag
    assert p.metadata["convex_trough_r"] == pytest.approx(0.01)


def test_a_real_gap_through_the_stop_is_kept_at_its_real_depth():
    """The crossing poll is recorded as it is, so a gap is not clamped away."""
    rt, p = _rt(), _held()
    rt._note_trough(p, -0.30, 97.0)
    rt._note_trough(p, -3.79, 62.1)                   # gapped straight through
    assert p.metadata["convex_trough_r"] == pytest.approx(-3.79)


def test_no_stop_price_means_the_old_behaviour():
    rt, p = _rt(), _held(sl=0.0)
    rt._note_trough(p, -1.2, 80.0)
    rt._note_trough(p, -1.6, 70.0)
    assert p.metadata["convex_trough_r"] == pytest.approx(-1.6)
    assert "trough_frozen_ts" not in p.metadata


def test_both_writers_go_through_the_stop_aware_helper():
    for name in ("_convex_early_stop_exit", "_convex_runner_trail_exit"):
        src = inspect.getsource(getattr(FuturesRuntime, name))
        assert "_note_trough(position, r_now, current_price)" in src
        assert 'metadata["convex_trough_r"] =' not in src
    assert "trough_frozen_ts" in EXIT_TELEMETRY_KEYS
