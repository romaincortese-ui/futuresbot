"""Stop-on-book verification (wc/CARD, 2026-09-23). SHADOW ONLY.

The stop band is the best instrument in this book and it only ever measures where a
stop SETTLED. Nothing confirmed a stop was ever resting on the exchange while the
position was open - and on 2026-09-21 a precision error left a position bare for six
minutes. These tests hold the line that this code reads and records and does nothing
else, and that it never calls a readable-but-empty answer "bare".

Row schema verified against the live account 2026-09-23: `data` is a bare list here,
superseded orders stay in it with isFinished=1, and the live row carries state=1 and
isFinished=0.
"""
import inspect
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from futuresbot.marketdata import MexcFuturesClient
from futuresbot.runtime import EXIT_TELEMETRY_KEYS, FuturesRuntime

LIVE = {"id": 566637126, "positionId": "1504208830", "state": 1, "isFinished": 0,
        "stopLossPrice": 0.12964, "takeProfitPrice": 0.19672, "symbol": "MARSCOIN_USDT"}
DONE = {"id": 566410963, "positionId": "1504208830", "state": 2, "isFinished": 1,
        "stopLossPrice": 0.11406, "takeProfitPrice": 0.19671, "symbol": "MARSCOIN_USDT"}


def _client(payload):
    c = object.__new__(MexcFuturesClient)
    c.private_get = MagicMock(return_value=payload)
    return c


def _rt(rows=None, *, raises=False, paper=False):
    rt = object.__new__(FuturesRuntime)
    rt.config = SimpleNamespace(paper_trade=paper)
    rt._flag = lambda name, default=False: default
    rt._env_float = lambda name, default=0.0: default
    rt.client = MagicMock()
    if raises:
        rt.client.get_stop_orders.side_effect = RuntimeError("timeout")
    else:
        rt.client.get_stop_orders.return_value = rows or []
    return rt


def _pos(md=None, sl=0.1141):
    return SimpleNamespace(symbol="MARSCOIN_USDT", side="LONG", position_id="1504208830",
                           entry_price=0.12939, sl_price=sl, tp_price=0.19672,
                           metadata={} if md is None else md)


def test_the_client_reads_both_payload_shapes():
    """The same endpoint returns a bare list here and {"data":{"resultList":[]}}
    elsewhere; handling one shape silently reads "no stop" on the other."""
    flat = _client({"data": [LIVE, DONE]})
    paged = _client({"data": {"resultList": [LIVE, DONE]}})
    assert [r["id"] for r in flat.get_stop_orders("MARSCOIN_USDT")] == [LIVE["id"]]
    assert [r["id"] for r in paged.get_stop_orders("MARSCOIN_USDT")] == [LIVE["id"]]


def test_superseded_orders_are_filtered_out():
    """Six rows came back for one live position: one current, five finished, one of
    them carrying the pre-breakeven stop. Taking the first match is a coin flip."""
    c = _client({"data": [DONE, LIVE]})
    live = c.get_stop_orders("MARSCOIN_USDT")
    assert len(live) == 1 and live[0]["stopLossPrice"] == pytest.approx(0.12964)
    assert len(c.get_stop_orders("MARSCOIN_USDT", live_only=False)) == 2


def test_a_string_zero_does_not_read_as_finished():
    c = _client({"data": [dict(LIVE, isFinished="0")]})
    assert len(c.get_stop_orders("MARSCOIN_USDT")) == 1


def test_a_row_with_no_state_field_is_treated_as_live():
    """A missing field must never read as "finished" - reporting a healthy position as
    having no stop is the false alarm this whole check exists to avoid."""
    c = _client({"data": [{"positionId": "p1", "stopLossPrice": 3900.0}]})
    assert len(c.get_stop_orders("ETH_USDT")) == 1


def test_junk_payloads_do_not_raise():
    for payload in ({}, {"data": None}, {"data": {"nothing": 1}}, "nonsense"):
        assert _client(payload).get_stop_orders("X_USDT") == []


def test_a_resting_stop_is_seen_and_priced():
    rt = _rt([LIVE])
    p = _pos()
    assert rt._verify_stop_on_book(p) == "SEEN"
    md = p.metadata
    assert md["stop_book_state"] == 1.0
    assert md["stop_book_price"] == pytest.approx(0.12964)
    assert md["stop_book_order_id"] == "566637126"
    assert md["stop_book_checks"] == 1.0
    assert md.get("stop_book_bare_seconds", 0.0) == 0.0


def test_the_gap_is_measured_against_the_stop_we_believe_in():
    """The exchange price is the truth; ours is the belief. A breakeven amend moves the
    exchange price and the gap must follow it, not flag it."""
    rt = _rt([LIVE])
    p = _pos(sl=0.12964)
    rt._verify_stop_on_book(p)
    assert p.metadata["stop_book_price_gap_bps"] == pytest.approx(0.0, abs=1.0)


def test_no_matching_order_is_absent_and_starts_the_bare_clock():
    rt = _rt([dict(LIVE, positionId="9999")])
    p = _pos()
    assert rt._verify_stop_on_book(p) == "ABSENT"
    assert p.metadata["stop_book_state"] == 0.0
    assert p.metadata["stop_book_absent_checks"] == 1.0
    assert "stop_book_bare_seconds" in p.metadata


def test_an_absent_reading_is_saved_at_once():
    """N1: kill rule K3 reads the bare readings, and state is otherwise saved only on
    events, so a restart before the next one erased them."""
    rt = _rt([dict(LIVE, positionId="9999")])
    rt._save_state = MagicMock()
    p = _pos()
    assert rt._verify_stop_on_book(p) == "ABSENT"
    rt._save_state.assert_called_once()
    rt._save_state.side_effect = OSError("disk full")          # a failed save never raises
    p.metadata["stop_book_due_ts"] = time.time() - 1
    assert rt._verify_stop_on_book(p) == "ABSENT"
    assert p.metadata["stop_book_absent_checks"] == 2.0


def test_a_seen_reading_does_not_save():
    rt = _rt([LIVE])
    rt._save_state = MagicMock()
    assert rt._verify_stop_on_book(_pos()) == "SEEN"
    rt._save_state.assert_not_called()


def test_an_unreadable_endpoint_is_not_called_bare():
    """ABSENT and UNREADABLE are different facts; collapsing them manufactures exactly
    the false alarm this exists to catch."""
    rt = _rt(raises=True)
    p = _pos()
    assert rt._verify_stop_on_book(p) == "UNREADABLE"
    assert p.metadata["stop_book_state"] == -1.0
    assert p.metadata["stop_book_unreadable_checks"] == 1.0
    assert "stop_book_bare_seconds" not in p.metadata


def test_it_is_throttled_and_the_due_stamp_forces_a_check():
    rt = _rt([LIVE])
    p = _pos()
    rt._verify_stop_on_book(p)
    assert rt._verify_stop_on_book(p) is None          # inside the interval
    p.metadata["stop_book_due_ts"] = time.time() - 1   # an amend asked for a recheck
    assert rt._verify_stop_on_book(p) == "SEEN"


def test_the_breakeven_amend_asks_for_a_recheck():
    """_move_exchange_stop cancels before it places, so the amend is the one moment a
    position is bare by construction - and the only one worth paying a read for."""
    src = inspect.getsource(FuturesRuntime._maybe_breakeven_stop)
    assert "stop_book_due_ts" in src


def test_paper_mode_writes_nothing():
    rt = _rt([LIVE], paper=True)
    p = _pos()
    assert rt._verify_stop_on_book(p) is None
    assert p.metadata == {}


def test_the_kill_switch():
    rt = _rt([LIVE])
    rt._flag = lambda name, default=False: False if name == "FUTURES_STOP_BOOK_VERIFY_ENABLED" else default
    p = _pos()
    assert rt._verify_stop_on_book(p) is None
    assert p.metadata == {}


def test_it_is_bounded_and_shadow_only():
    src = inspect.getsource(FuturesRuntime._verify_stop_on_book)
    assert "attempts=1, timeout=4.0" in src
    code = [l.split("#")[0] for l in src.split('"""')[2].split(chr(10))]
    body = chr(10).join(code)
    for forbidden in ("place_", "cancel_", "close_position", "_notify", "sleep("):
        assert forbidden not in body
    assert "sl_price =" not in src and "tp_price =" not in src


def test_it_runs_in_the_monitor_after_the_repair_and_reaches_the_record():
    mon = inspect.getsource(FuturesRuntime._monitor_open_positions_once)
    assert "_verify_stop_on_book(position)" in mon
    assert mon.index("_repair_bare_stop") < mon.index("_verify_stop_on_book")
    for key in ("stop_book_state", "stop_book_bare_seconds", "stop_book_price_gap_bps"):
        assert key in EXIT_TELEMETRY_KEYS


def test_the_adopted_position_reader_uses_the_same_normaliser():
    """/reconcile read every adopted position's stop as 0.0 on the paginated shape and
    then defaulted its R denominator to 20% margin, silently."""
    src = inspect.getsource(FuturesRuntime._resting_stop_for)
    assert "get_stop_orders" in src
    # a client without the helper takes the SAME normalisation, never a silent 0.0
    assert "normalise_stop_orders" in src
