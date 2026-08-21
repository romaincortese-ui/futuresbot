"""The reconcile history-lag race (fixed 2026-08-21).

MEXC removes a closed position from `open_positions` BEFORE it publishes the
closed row to `history_positions`. A reconcile poll landing inside that window
saw neither and cleared the position "without recording P&L" — permanently
erasing the trade.

PROVEN LIVE on ORDI_USDT: the stop filled at 09:06:11 and the drop branch fired
at 09:06:11.211, the same second. The history row was present moments later.
-$2.72 vanished from the ledger, and it was the sixth such loss. Every single
unrecorded close in the corpus is a LOSS, because winners exit through the bot's
own decision in-process while losers exit exchange-side and depend on this race.

The fix holds the position for a grace window and retries. These tests pin the
four cases that matter.
"""
import time
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from futuresbot.config import FuturesConfig
from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime


def _cfg(tmp_path):
    return replace(
        FuturesConfig.from_env(),
        symbol="BTC_USDT", symbols=("BTC_USDT",), paper_trade=False,
        runtime_state_file=str(tmp_path / "rt.json"),
        status_file=str(tmp_path / "st.json"),
        telegram_token="", telegram_chat_id="",
    )


class _Client:
    """Exchange stub: `open_rows` and `hist_rows` are swapped between polls to
    reproduce the lag."""

    def __init__(self, open_rows=None, hist_rows=None):
        self.open_rows = open_rows if open_rows is not None else []
        self.hist_rows = hist_rows if hist_rows is not None else []
        self.auth_error_hook = None
        self.hist_calls = 0

    def get_open_positions(self, symbol=None):
        return self.open_rows

    def get_historical_positions(self, symbol=None, page_num=1, page_size=20):
        self.hist_calls += 1
        return self.hist_rows

    def __getattr__(self, name):
        def _noop(*a, **k):
            return None
        return _noop


@pytest.fixture
def rt(tmp_path, monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    monkeypatch.delenv("FUTURES_RECONCILE_MISS_GRACE_SECONDS", raising=False)
    return FuturesRuntime(_cfg(tmp_path), _Client())


def _pos(pid="pid-1"):
    return FuturesPosition(
        symbol="ORDI_USDT", side="LONG", entry_price=4.576, contracts=150,
        contract_size=0.1, leverage=5, margin_usdt=13.78,
        tp_price=5.4, sl_price=4.40, position_id=pid, order_id="ord-1",
        opened_at=datetime(2026, 8, 21, 8, 29, tzinfo=timezone.utc),
        score=96.0, certainty=0.9, entry_signal="WILDCARD_LONG",
        metadata={"wildcard": 1.0, "sl_margin_pct": 19.0},
    )


def test_a_single_miss_does_not_drop_the_position(rt):
    """The ORDI case. Gone from open_positions, not yet in history — hold."""
    rt._register_position(_pos())
    rt._reconcile_closed_position()
    assert "ORDI_USDT" in rt.open_positions
    assert rt.trade_history == []
    assert rt.open_positions["ORDI_USDT"].metadata.get("reconcile_miss_since")


def test_the_trade_is_recorded_when_history_catches_up(rt):
    """The whole point: the P&L must land in the ledger, not be discarded."""
    rt._register_position(_pos())
    rt._reconcile_closed_position()                      # miss — held
    assert rt.trade_history == []

    rt.client.hist_rows = [{"positionId": "pid-1", "closeAvgPrice": 4.401}]
    rt._reconcile_closed_position()                      # history arrives

    assert "ORDI_USDT" not in rt.open_positions
    assert len(rt.trade_history) == 1, "the close must be recorded, not dropped"
    assert rt.trade_history[-1]["symbol"] == "ORDI_USDT"


def test_a_genuinely_vanished_position_still_clears_after_the_grace(rt):
    """The guard must not become a leak of its own — a position that really is
    gone has to be cleared eventually."""
    rt._register_position(_pos())
    rt._reconcile_closed_position()
    assert "ORDI_USDT" in rt.open_positions

    rt.open_positions["ORDI_USDT"].metadata["reconcile_miss_since"] = (
        time.time() - rt._reconcile_grace_seconds() - 1)
    rt._reconcile_closed_position()

    assert rt.open_positions == {}
    assert any("Cleared stale local position" in x for x in rt._recent_activity)


def test_a_position_still_open_on_the_exchange_resets_the_clock(rt):
    """A transient miss must never accumulate toward a drop across unrelated
    cycles — otherwise two isolated blips days apart would combine to kill a
    live position."""
    rt._register_position(_pos())
    rt._reconcile_closed_position()                      # miss 1
    assert rt.open_positions["ORDI_USDT"].metadata.get("reconcile_miss_since")

    rt.client.open_rows = [{"positionId": "pid-1"}]      # it's back
    rt._reconcile_closed_position()
    assert "reconcile_miss_since" not in rt.open_positions["ORDI_USDT"].metadata
    assert "ORDI_USDT" in rt.open_positions


def test_the_marker_survives_a_restart(rt, tmp_path):
    """Persisted, not in-memory: a restart mid-grace must not silently reset the
    clock and hand the race another free pass."""
    rt._register_position(_pos())
    rt._reconcile_closed_position()
    first = rt.open_positions["ORDI_USDT"].metadata["reconcile_miss_since"]

    revived = FuturesRuntime(_cfg(tmp_path), _Client())
    assert revived.open_positions["ORDI_USDT"].metadata["reconcile_miss_since"] == first


def test_grace_is_a_clock_not_a_poll_count(rt, monkeypatch):
    """The reconcile interval varies (~2s under the open-position guard, ~45s+
    from the cycle), so a fixed retry count would mean wildly different grace
    periods depending on whether a position happened to be open."""
    rt._register_position(_pos())
    for _ in range(50):                                  # 50 polls, no time passing
        rt._reconcile_closed_position()
    assert "ORDI_USDT" in rt.open_positions, "poll count alone must never drop it"

    monkeypatch.setenv("FUTURES_RECONCILE_MISS_GRACE_SECONDS", "10")
    assert rt._reconcile_grace_seconds() == 10.0
