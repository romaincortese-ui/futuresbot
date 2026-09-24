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

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from futuresbot import runtime as rt_mod
from futuresbot.config import FuturesConfig
from futuresbot.models import FuturesPosition
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
    # _save_state is allowed since C19 (2026-09-24): persisting the path is the fix for
    # a restart erasing it. It writes state; it decides nothing.
    for forbidden in ("close_position", "place_", "cancel_", "sl_price", "tp_price"):
        assert forbidden not in body


# ---- C19: the path survives a restart (2026-09-24) ---------------------------------------
# State was saved only on events, so a restart lost every sample since the last one -
# measured 2026-09-23: 38% of ZEC's path and 25% of MARSCOIN's, mostly the post-peak fade.

def test_each_sample_is_saved_at_the_default_cadence(tmp_path, monkeypatch):
    t = {"now": 1_790_000_000.0}
    monkeypatch.setattr(rt_mod, "time", SimpleNamespace(time=lambda: t["now"]))
    rt = _rt(tmp_path, FUTURES_R_SERIES_INTERVAL_SECONDS=60.0)
    rt._save_state = MagicMock()
    p = _pos()
    for r in (0.10, 0.40, 0.20):
        rt._record_r_sample(p, r)
        t["now"] += 60.0
    assert rt._save_state.call_count == 3


def test_saves_are_at_most_one_a_minute_even_at_a_faster_cadence(tmp_path, clock):
    rt = _rt(tmp_path, FUTURES_R_SERIES_INTERVAL_SECONDS=5.0)   # the floor; the clock steps 10s
    saved_at = []
    rt._save_state = lambda: saved_at.append(clock.t)
    p = _pos()
    for i in range(12):                                          # 12 samples over 110s
        rt._record_r_sample(p, i / 10.0)
    assert p.metadata["r_series_n"] == 12
    assert len(saved_at) == 2
    assert saved_at[1] - saved_at[0] >= 60.0


def test_a_saved_stamp_from_the_future_does_not_suppress_saves(tmp_path, monkeypatch):
    """A backward clock step (or state from a host whose clock ran ahead) must not
    silence the saves until the wall clock catches up with the stamp."""
    t = {"now": 1_790_000_000.0}
    monkeypatch.setattr(rt_mod, "time", SimpleNamespace(time=lambda: t["now"]))
    rt = _rt(tmp_path, FUTURES_R_SERIES_INTERVAL_SECONDS=60.0)
    rt._save_state = MagicMock()
    p = _pos()
    p.metadata["r_series_saved_ts"] = t["now"] + 3600.0
    rt._record_r_sample(p, 0.1)
    assert rt._save_state.call_count == 1


def test_no_save_without_a_new_sample(tmp_path):
    rt = _rt(tmp_path, FUTURES_R_SERIES_INTERVAL_SECONDS=600.0)
    rt._save_state = MagicMock()
    p = _pos()
    rt._record_r_sample(p, 0.1)
    rt._record_r_sample(p, 0.9)                                  # inside the interval
    assert rt._save_state.call_count == 1


def test_a_failed_save_never_raises(tmp_path):
    rt = _rt(tmp_path, FUTURES_R_SERIES_INTERVAL_SECONDS=0.0)
    rt._save_state = MagicMock(side_effect=OSError("disk full"))
    p = _pos()
    rt._record_r_sample(p, 0.5)
    assert p.metadata["r_series_n"] == 1


class _Client:
    def get_open_positions(self, symbol=None):
        return [{"positionType": 1, "holdVol": 10}]

    def get_account_asset(self, currency: str = "USDT"):
        return {"availableBalance": "1000", "equity": "1000"}

    def get_updates(self, *, offset=None, limit: int = 5, timeout: int = 0):
        return []


def _real_runtime(tmp_path):
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "state.json"),
                  status_file=str(tmp_path / "status.json"),
                  telegram_token="t", telegram_chat_id="1", paper_trade=False)
    rt = FuturesRuntime(cfg, _Client())
    rt._shadow_ledger_path = lambda: str(tmp_path / "shadow.jsonl")
    return rt


def test_the_samples_survive_a_restart_and_flush_writes_one_row(tmp_path, monkeypatch):
    monkeypatch.delenv("FUTURES_R_SERIES_INTERVAL_SECONDS", raising=False)
    rt = _real_runtime(tmp_path)
    pos = FuturesPosition(symbol="ZEC_USDT", side="LONG", entry_price=100.0, contracts=10,
                          contract_size=1.0, leverage=5, margin_usdt=200.0, tp_price=110.0,
                          sl_price=98.0, position_id="7", order_id="1",
                          opened_at=datetime.now(timezone.utc) - timedelta(hours=1),
                          score=96.0, certainty=0.9, entry_signal="WILDCARD_LONG",
                          metadata={"wildcard": 1.0})
    rt.open_positions[pos.symbol] = pos
    real_time = rt_mod.time
    t = {"now": real_time.time()}
    monkeypatch.setattr(rt_mod, "time", SimpleNamespace(time=lambda: t["now"],
                                                       monotonic=real_time.monotonic))
    for r in (0.10, 0.60, 0.35, 0.05):                           # a peak, then the fade
        rt._record_r_sample(pos, r)
        t["now"] += 61.0
    before = [list(pt) for pt in pos.metadata["r_series"]]
    assert len(before) == 4

    # the process dies here: no event-driven save ran after the first sample
    monkeypatch.setattr(rt_mod, "time", real_time)
    rt2 = _real_runtime(tmp_path)                                # boots from the state file
    restored = rt2.open_positions["ZEC_USDT"]
    assert restored.metadata["r_series"] == before              # every sample, fade included
    assert restored.metadata["r_series_n"] == 4.0
    assert restored.metadata["r_series_start_ts"] == pos.metadata["r_series_start_ts"]

    trade = {"sleeve": "WILDCARD", "exit_reason": "EXCHANGE_CLOSE", "pnl_usdt": 1.0}
    rt2._flush_r_series(restored, trade)
    rt2._flush_r_series(restored, trade)                         # a second call writes nothing
    rows = [json.loads(line) for line in open(tmp_path / "futures_r_series.jsonl", encoding="utf-8")]
    assert len(rows) == 1
    assert rows[0]["series"] == before
