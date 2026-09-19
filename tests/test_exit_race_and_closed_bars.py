"""2026-09-19 ZEC review defects.

- TREND gates were decided on the forming 15-min bar (a 7-minute burst met both
  gates mid-bar and stretched the stop to the burst's launch).
- A close that raced the exchange's own stop fill raised a false
  "Futures Stop Not Restored" alert.
"""
from __future__ import annotations

import inspect
import time

import pandas as pd
import pytest

from futuresbot import trend as T
from futuresbot.runtime import FuturesRuntime
from tests.test_assessment_fixes import _Client, _pos, _runtime


# --- exit race -------------------------------------------------------------

class _RaceClient(_Client):
    def __init__(self, rows, *, tpsl_raises=False):
        super().__init__(close_raises=True, tpsl_raises=tpsl_raises)
        self.rows = rows

    def get_open_positions(self, symbol=None):
        return self.rows


def _alerts(runtime):
    sent = []
    runtime._notify_once = lambda key, message, parse_mode="HTML": sent.append(key)
    return sent


def test_no_alert_when_the_exchange_already_closed_it(tmp_path):
    client = _RaceClient(rows=[], tpsl_raises=True)      # its own stop filled first: 2009
    runtime = _runtime(tmp_path, client)
    sent = _alerts(runtime)
    with pytest.raises(RuntimeError):
        runtime._close_position_for_exit(_pos(), current_price=89.0, reason="CONVEX_HARD_STOP")
    assert [c for c in client.calls if c[0] == "place_position_tpsl"]   # tried at once
    assert sent == []


def test_the_alert_still_fires_when_an_open_position_cannot_be_protected(tmp_path):
    client = _RaceClient(rows=[{"positionType": 1, "holdVol": 5}], tpsl_raises=True)
    runtime = _runtime(tmp_path, client)
    sent = _alerts(runtime)
    with pytest.raises(RuntimeError):
        runtime._close_position_for_exit(_pos(), current_price=89.0, reason="CONVEX_HARD_STOP")
    assert len(sent) == 1


def test_a_row_without_a_side_or_an_odd_payload_counts_as_open(tmp_path):
    runtime = _runtime(tmp_path, _RaceClient(rows=[{"holdVol": 5}]))
    assert runtime._exchange_position_open(_pos()) is True
    runtime = _runtime(tmp_path, _RaceClient(rows={"unexpected": True}))
    assert runtime._exchange_position_open(_pos()) is True


def test_stop_is_still_restored_when_the_position_is_open(tmp_path):
    client = _RaceClient(rows=[{"positionType": 1, "holdVol": 5}])
    runtime = _runtime(tmp_path, client)
    with pytest.raises(RuntimeError):
        runtime._close_position_for_exit(_pos(), current_price=89.0, reason="CONVEX_HARD_STOP")
    assert [c for c in client.calls if c[0] == "place_position_tpsl"]


def test_an_unreadable_exchange_counts_as_open(tmp_path):
    client = _Client(close_raises=True)                  # no get_open_positions at all
    runtime = _runtime(tmp_path, client)
    with pytest.raises(RuntimeError):
        runtime._close_position_for_exit(_pos(), current_price=89.0, reason="CONVEX_HARD_STOP")
    assert [c for c in client.calls if c[0] == "place_position_tpsl"]


# --- completed bars --------------------------------------------------------

def _frame(closes, *, forming: bool):
    """15-min bars ending now; the last one still forming when `forming`."""
    now = int(time.time()) // 900 * 900
    last_open = now if forming else now - 900
    idx = pd.to_datetime([last_open - 900 * (len(closes) - 1 - i) for i in range(len(closes))],
                         unit="s", utc=True)
    return pd.DataFrame({"open": closes, "high": [c * 1.002 for c in closes],
                         "low": [c * 0.998 for c in closes], "close": closes,
                         "volume": [1e3] * len(closes)}, index=idx)


def test_a_forming_bar_burst_no_longer_meets_the_gates():
    closes = [100.0] * 150 + [106.0]                     # only the forming bar moved
    full = _frame(closes, forming=True)
    assert T.detect_trend_signal(full, "ZEC_USDT") is not None   # the old read fired
    closed = FuturesRuntime._drop_incomplete_klines(full, interval_seconds=900)
    assert len(closed) == len(full) - 1
    reasons = []
    assert T.detect_trend_signal(closed, "ZEC_USDT", reasons) is None
    assert reasons == ["roc_below_min"]


def test_a_completed_bar_signal_is_repriced_at_the_latest_tick_with_its_distances():
    closes = [100.0 * (1.20 ** (1 / 199)) ** i for i in range(200)]
    full = _frame(closes + [closes[-1] * 1.01], forming=True)
    closed = FuturesRuntime._drop_incomplete_klines(full, interval_seconds=900)
    sig = T.detect_trend_signal(closed, "ZEC_USDT")
    assert sig is not None
    anchored = FuturesRuntime._anchor_trend_signal(sig, full, closed)
    assert anchored.entry_price == pytest.approx(closes[-1] * 1.01)
    assert anchored.gate_close == pytest.approx(sig.entry_price)
    f = lambda s: (s.entry_price - s.sl_price) / s.entry_price
    g = lambda s: (s.tp_price - s.entry_price) / s.entry_price
    assert f(anchored) == pytest.approx(f(sig)) and g(anchored) == pytest.approx(g(sig))
    assert FuturesRuntime._anchor_trend_signal(sig, closed, closed) is sig   # nothing trimmed


def test_the_scan_trims_before_detecting_and_runs_once_per_bar(monkeypatch):
    src = inspect.getsource(FuturesRuntime._maybe_scan_trend)
    assert src.index("_drop_incomplete_klines") < src.index("detect_trend_signal(closed")
    monkeypatch.setenv("FUTURES_TREND_ENABLED", "1")
    rt = object.__new__(FuturesRuntime)
    rt._paused = False
    rt._last_trend_scan_at = time.time() // 900 * 900 + 1   # already scanned this bar
    assert rt._maybe_scan_trend() is None                  # returns before any I/O


def test_a_signal_from_a_bar_that_closed_long_ago_is_not_taken():
    closes = [100.0 * (1.20 ** (1 / 199)) ** i for i in range(200)]
    old = _frame(closes, forming=False)                   # last bar closed at the boundary
    sig = T.detect_trend_signal(old, "ZEC_USDT")
    rt = object.__new__(FuturesRuntime)
    bar_close = old.index[-1].timestamp() + 900
    assert rt._trend_signal_stale(sig, old, bar_close + 60) is None
    assert rt._trend_signal_stale(sig, old, bar_close + 600) == "stale_bar"   # restart mid-bar


def test_a_breakout_that_already_failed_is_not_taken():
    closes = [100.0 * (1.20 ** (1 / 199)) ** i for i in range(200)]
    full = _frame(closes + [closes[-3]], forming=True)    # tick back under the prior high
    closed = FuturesRuntime._drop_incomplete_klines(full, interval_seconds=900)
    sig = FuturesRuntime._anchor_trend_signal(T.detect_trend_signal(closed, "ZEC_USDT"), full, closed)
    rt = object.__new__(FuturesRuntime)
    assert rt._trend_signal_stale(sig, closed, closed.index[-1].timestamp() + 960) == "breakout_failed"
