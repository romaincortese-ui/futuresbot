"""The polled R path (wc/GIVE, 2026-09-22). Telemetry only.

The bot floors positions on convex_peak_r, a point sample of a polled fair price that
lags the tape - MARSCOIN 2026-09-22 17:59Z: tape 0.2969R, recorded 0.0887R. Persisting
what the bot actually saw, at a known cadence, is what makes the retention axis
measurable. Nothing here may gate, size, arm or exit anything.
"""
import inspect
import json
import os
from types import SimpleNamespace

import pytest

from futuresbot import runtime as rt_mod
from futuresbot.runtime import EXIT_TELEMETRY_KEYS, FuturesRuntime


class _Clock:
    """A clock that advances 10s per reading, so the 5s cadence floor never masks a
    sample in a test that means to take several."""

    def __init__(self):
        self.t = 1_790_000_000.0

    def time(self):
        self.t += 10.0
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(rt_mod, "time", c)
    return c


def _rt(tmp_path, **env):
    rt = object.__new__(FuturesRuntime)
    rt._flag = lambda name, default=False: env.get(name, default)
    rt._env_float = lambda name, default=0.0: env.get(name, default)
    rt._shadow_ledger_path = lambda: str(tmp_path / "shadow.jsonl")
    return rt


def _pos(md=None):
    return SimpleNamespace(symbol="MARSCOIN_USDT", side="LONG", metadata=md if md is not None else {})


def test_samples_are_compact_and_track_the_peak(tmp_path, clock):
    rt = _rt(tmp_path, FUTURES_R_SERIES_INTERVAL_SECONDS=0.0)
    p = _pos()
    for r in (0.10, 0.79, 0.31):
        rt._record_r_sample(p, r)
        # the trail maintains convex_peak_r one line further down the same function,
        # so the sampler must fold it into the running max exactly as it does live
        p.metadata["convex_peak_r"] = max(float(p.metadata.get("convex_peak_r") or -1e9), r)
    md = p.metadata
    assert md["r_series_n"] == 3
    assert [pt[1] for pt in md["r_series"]] == [100, 790, 310]     # milli-R, integers
    assert [pt[2] for pt in md["r_series"]] == [100, 790, 790]     # running max, never falls
    assert all(isinstance(pt[0], int) for pt in md["r_series"])    # seconds since the first sample
    assert all(pt[0] >= 0 for pt in md["r_series"])                # never negative on a clock step
    assert md["r_series_peak_r"] == pytest.approx(0.79)            # the peak is the MAX, not the last
    assert md["r_series_peak_ts"] > 0


def test_negative_readings_are_recorded_and_do_not_set_a_peak(tmp_path):
    rt = _rt(tmp_path, FUTURES_R_SERIES_INTERVAL_SECONDS=0.0)
    p = _pos()
    rt._record_r_sample(p, -0.72)
    assert p.metadata["r_series"][0][1] == -720
    assert p.metadata["r_series"][0][2] == -720          # the running max starts at the first reading
    assert p.metadata["r_series_peak_r"] == pytest.approx(-0.72)


def test_the_cadence_is_throttled(tmp_path):
    rt = _rt(tmp_path, FUTURES_R_SERIES_INTERVAL_SECONDS=600.0)
    p = _pos()
    rt._record_r_sample(p, 0.1)
    rt._record_r_sample(p, 0.9)
    assert p.metadata["r_series_n"] == 1          # the second reading is inside the interval


def test_the_sample_cap_holds(tmp_path, clock):
    rt = _rt(tmp_path, FUTURES_R_SERIES_INTERVAL_SECONDS=0.0, FUTURES_R_SERIES_MAX_SAMPLES=60.0)
    p = _pos()
    for i in range(100):
        rt._record_r_sample(p, i / 100.0)
    assert len(p.metadata["r_series"]) == 60
    assert p.metadata["r_series_peak_r"] == pytest.approx(0.99)   # the peak still tracks past the cap


def test_it_is_disabled_by_one_flag(tmp_path):
    rt = _rt(tmp_path, FUTURES_R_SERIES_ENABLED=False, FUTURES_R_SERIES_INTERVAL_SECONDS=0.0)
    p = _pos()
    rt._record_r_sample(p, 0.5)
    assert p.metadata == {}


def test_a_missing_metadata_dict_never_raises(tmp_path):
    rt = _rt(tmp_path, FUTURES_R_SERIES_INTERVAL_SECONDS=0.0)
    p = _pos(md=None)
    p.metadata = None
    rt._record_r_sample(p, 0.5)
    assert p.metadata["r_series_n"] == 1


def test_close_writes_one_row_and_drops_the_series_from_state(tmp_path, clock):
    rt = _rt(tmp_path, FUTURES_R_SERIES_INTERVAL_SECONDS=0.0)
    p = _pos()
    for r in (0.10, 0.79, 0.31):
        rt._record_r_sample(p, r)
    p.metadata["convex_peak_r"] = 0.0887
    trade = {"sleeve": "WILDCARD", "entry_time": "2026-09-22T12:12:00+00:00",
             "exit_time": "2026-09-22T20:00:00+00:00", "exit_reason": "EXCHANGE_CLOSE",
             "risk_usdt": 22.99, "pnl_usdt": -22.99}
    rt._flush_r_series(p, trade)
    rows = [json.loads(l) for l in open(tmp_path / "futures_r_series.jsonl", encoding="utf-8")]
    assert len(rows) == 1
    assert rows[0]["symbol"] == "MARSCOIN_USDT" and len(rows[0]["series"]) == 3
    # convex_peak_r is the 1 Hz running max and is authoritative; r_series_peak_r is the
    # 60s decimation of the same stream and is <= it by construction.
    assert rows[0]["peak_r_recorded"] == 0.0887
    assert rows[0]["r_series_peak_r"] == pytest.approx(0.79)
    assert "r_series" not in p.metadata                  # the path is written, state stays small
    assert p.metadata["r_series_peak_r"] == pytest.approx(0.79)   # the summary survives


def test_a_position_with_no_samples_writes_nothing(tmp_path):
    rt = _rt(tmp_path)
    rt._flush_r_series(_pos(), {"sleeve": "TREND"})
    assert not os.path.exists(tmp_path / "futures_r_series.jsonl")


def test_the_file_is_bounded(tmp_path):
    rt = _rt(tmp_path, FUTURES_R_SERIES_INTERVAL_SECONDS=0.0, FUTURES_R_SERIES_MAX_MB=1.0)
    path = tmp_path / "futures_r_series.jsonl"
    path.write_text("x" * (1024 * 1024 + 10), encoding="utf-8")
    p = _pos()
    rt._record_r_sample(p, 0.5)
    rt._flush_r_series(p, {"sleeve": "WILDCARD"})
    assert path.read_text(encoding="utf-8").count("\n") == 0      # nothing appended
    assert rt._r_series_full_warned is True


def test_the_summary_reaches_the_closed_trade_record():
    for key in ("r_series_n", "r_series_peak_r", "r_series_peak_ts", "r_series_interval_s"):
        assert key in EXIT_TELEMETRY_KEYS


def test_it_is_wired_into_the_monitor_and_the_close():
    trail = inspect.getsource(FuturesRuntime._convex_runner_trail_exit)
    assert "_record_r_sample(position, r_now)" in trail
    close = inspect.getsource(FuturesRuntime._close_history_trade)
    assert "_flush_r_series" in close
    assert close.index("_flush_r_series") < close.index("self.trade_history.append(trade)")


def test_it_changes_no_exit_decision():
    """The sampler must sit between r_now and the arm test without touching either."""
    src = inspect.getsource(FuturesRuntime._record_r_sample)
    body = src.split('"""')[2]                       # the code, not the docstring
    for forbidden in ("close_position", "place_", "cancel_", "sl_price", "tp_price", "_save_state"):
        assert forbidden not in body
