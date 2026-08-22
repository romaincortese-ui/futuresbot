"""The PMT hard-exit hijack of recovered positions (fixed 2026-08-22).

`_refresh_live_positions` adopted untracked exchange positions with
tp_price=0.0 / sl_price=0.0, and `_pmt_hard_exit` compared the live price
against those zeros:

    LONG  -> `current_price >= tp_price` with tp_price 0.0 is ALWAYS true
             -> force-closed as TAKE_PROFIT, at price 0.0
    SHORT -> `current_price >= sl_price` with sl_price 0.0 is ALWAYS true
             -> force-closed as STOP_LOSS

So any recovered position on an active PMT symbol died on the very next tick,
deterministically, on both sides. ETH and SOL are inside the six PMT symbols,
which meant every convex position on a major was exposed the moment its local
tracking was lost — a restart before the state save is enough.

Two fixes, pinned separately: an unset level is never a breached one, and the
recovery path now reads the position's real resting stop the way /reconcile
always has.
"""
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from futuresbot.config import FuturesConfig
from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime


def _cfg(tmp_path):
    return replace(
        FuturesConfig.from_env(),
        symbol="ETH_USDT", symbols=("ETH_USDT",), paper_trade=False,
        runtime_state_file=str(tmp_path / "rt.json"),
        status_file=str(tmp_path / "st.json"),
        telegram_token="", telegram_chat_id="",
    )


def _pos(side="LONG", *, tp=0.0, sl=0.0):
    return FuturesPosition(
        symbol="ETH_USDT", side=side, entry_price=4000.0, contracts=10,
        contract_size=0.01, leverage=9, margin_usdt=7.0,
        tp_price=tp, sl_price=sl, position_id="p1", order_id="",
        opened_at=datetime.now(timezone.utc), score=0.0, certainty=0.0,
        entry_signal="RECOVERED",
    )


class _Client:
    def __init__(self, rows=None, stops=None):
        self.rows = rows or []
        self.stops = stops or []
        self.closed = []

    def get_open_positions(self, symbol=None):
        return self.rows

    def get_contract_detail(self, symbol):
        return {"contractSize": 0.01}

    def private_get(self, path, params=None):
        if "stoporder" in path:
            return {"data": self.stops}
        return {}

    def cancel_all_tpsl(self, **kw):
        return {}

    def close_position(self, **kw):
        self.closed.append(kw)
        return {"orderId": ""}

    def get_order(self, order_id):
        return {}


def _rt(tmp_path, client):
    rt = object.__new__(FuturesRuntime)
    rt.config = _cfg(tmp_path)
    rt.client = client
    return rt


# --- the hijack itself -----------------------------------------------------

@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_unset_levels_never_trigger_an_exit(tmp_path, side):
    client = _Client()
    rt = _rt(tmp_path, client)
    assert rt._pmt_hard_exit(_pos(side), current_price=4000.0) is False
    assert client.closed == [], "a recovered position was force-closed on zeros"


def test_a_real_stop_still_fires_with_no_target_set(tmp_path):
    """The guard must not disarm genuine stops — that would be the opposite bug."""
    client = _Client()
    rt = _rt(tmp_path, client)
    rt._close_position_for_exit = lambda position, *, current_price, reason: (
        client.closed.append((reason, current_price)) or True)
    assert rt._pmt_hard_exit(_pos("LONG", sl=3900.0), current_price=3899.0) is True
    assert client.closed == [("STOP_LOSS", 3900.0)]


def test_a_real_target_still_fires_with_no_stop_set(tmp_path):
    client = _Client()
    rt = _rt(tmp_path, client)
    rt._close_position_for_exit = lambda position, *, current_price, reason: (
        client.closed.append((reason, current_price)) or True)
    assert rt._pmt_hard_exit(_pos("SHORT", tp=3800.0), current_price=3799.0) is True
    assert client.closed == [("TAKE_PROFIT", 3800.0)]


def test_untouched_position_between_its_levels_is_left_alone(tmp_path):
    client = _Client()
    rt = _rt(tmp_path, client)
    assert rt._pmt_hard_exit(_pos("LONG", sl=3900.0, tp=4200.0), current_price=4000.0) is False
    assert client.closed == []


# --- the recovery path that created the zeros ------------------------------

def test_recovery_reads_the_real_resting_stop(tmp_path):
    client = _Client(
        rows=[{"positionId": "p1", "positionType": 1, "holdAvgPrice": 4000.0,
               "holdVol": 10, "leverage": 9, "im": 7.0}],
        stops=[{"positionId": "p1", "stopLossPrice": 3900.0, "takeProfitPrice": 4300.0}],
    )
    rt = _rt(tmp_path, client)
    rt._active_symbols = ("ETH_USDT",)
    rt.open_positions = {}
    registered = []
    rt._register_position = registered.append
    rt._refresh_live_positions()
    assert len(registered) == 1
    assert registered[0].sl_price == 3900.0
    assert registered[0].tp_price == 4300.0
    # ...and so it survives the very tick that used to kill it
    assert rt._pmt_hard_exit(registered[0], current_price=4000.0) is False


def test_recovery_without_a_resting_stop_adopts_unmanaged_but_does_not_die(tmp_path):
    client = _Client(
        rows=[{"positionId": "p9", "positionType": 1, "holdAvgPrice": 4000.0,
               "holdVol": 10, "leverage": 9, "im": 7.0}],
        stops=[],
    )
    rt = _rt(tmp_path, client)
    rt._active_symbols = ("ETH_USDT",)
    rt.open_positions = {}
    registered = []
    rt._register_position = registered.append
    rt._refresh_live_positions()
    assert registered[0].sl_price == 0.0 and registered[0].tp_price == 0.0
    assert rt._pmt_hard_exit(registered[0], current_price=4000.0) is False
    assert client.closed == []
