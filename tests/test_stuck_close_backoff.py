"""C04 (2026-09-24): a stuck close no longer cancels its own restored stop every second.

The software close cancels the resting stop, sends the close and, when the close is
rejected, puts the stop back and raises. The 1s monitor retried at once, so every retry
cancelled the stop the previous one had restored: during a stuck close the position had
no exchange stop 70-98% of the time. Owner-approved fix: after a failed close whose stop
was restored, leave that stop alone for 60s, then retry; alert once per episode.

Pinned here with a fake exchange and a fake clock: the stop is cancelled at most once per
60s, one alert per episode, the retry after the backoff closes normally, and the race and
restore-failed paths are exactly as before.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from futuresbot import runtime as runtime_module
from futuresbot.models import FuturesPosition
from futuresbot.runtime import (CLOSE_FAILED_REASON_KEY, CLOSE_FAILED_TS_KEY,
                                CLOSE_RETRY_BACKOFF_SECONDS, FuturesRuntime)
from tests.test_assessment_fixes import _pos, _runtime


class _Clock:
    def __init__(self, t: float = 1_800_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


class _Exchange:
    """Rejects closes until told otherwise; records when each call landed."""

    def __init__(self, clock: _Clock, *, open_rows=None, tpsl_raises: bool = False) -> None:
        self.clock = clock
        self.close_raises = True
        self.tpsl_raises = tpsl_raises
        self.open_rows = [{"positionType": 1, "holdVol": 5}] if open_rows is None else open_rows
        self.price = 95.0
        self.calls: list[tuple[str, float]] = []
        self.stops: list[float] = []

    def cancel_all_tpsl(self, *, position_id=None, symbol=None, **kw):
        self.calls.append(("cancel_all_tpsl", self.clock.t))
        return {"success": True}

    def close_position(self, **kwargs):
        self.calls.append(("close_position", self.clock.t))
        if self.close_raises:
            raise RuntimeError("MEXC futures private POST failed: 600 system busy")
        return {"orderId": "1"}

    def place_position_tpsl(self, **kwargs):
        self.calls.append(("place_position_tpsl", self.clock.t))
        self.stops.append(kwargs.get("stop_loss_price"))
        if self.tpsl_raises:
            raise RuntimeError("stop rejected")
        return {"success": True}

    def get_open_positions(self, symbol=None, **kw):
        return self.open_rows

    def get_order(self, order_id):
        return {"dealAvgPrice": 95.0}

    def get_fair_price(self, symbol):
        return self.price

    def get_account_asset(self, currency: str = "USDT"):
        return {"availableBalance": "1000", "equity": "1000"}

    def get_updates(self, *, offset=None, limit: int = 5, timeout: int = 0):
        return []

    def times(self, name: str) -> list[float]:
        return [t for n, t in self.calls if n == name]


@pytest.fixture()
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(runtime_module.time, "time", c)
    return c


def _setup(tmp_path, clock, **exchange_kw):
    exchange = _Exchange(clock, **exchange_kw)
    runtime = _runtime(tmp_path, exchange)
    alerts: list[tuple[str, str]] = []
    runtime._notify_once = lambda key, message, **kw: alerts.append((key, message))
    position = _pos()
    runtime.open_positions[position.symbol] = position
    return runtime, exchange, position, alerts


def _attempt(runtime, position) -> bool | None:
    """One software-exit attempt, as the monitor makes it: an exception is swallowed."""
    try:
        return runtime._close_position_for_exit(position, current_price=95.0,
                                                reason="CONVEX_RETENTION_TRAIL")
    except RuntimeError:
        return None


def test_the_backoff_is_a_named_60s_constant():
    assert CLOSE_RETRY_BACKOFF_SECONDS == 60.0


def test_repeated_rejections_cancel_the_stop_at_most_once_per_60s(tmp_path, clock):
    runtime, exchange, position, alerts = _setup(tmp_path, clock)
    start = clock.t
    for second in range(181):                        # a 3-minute stuck close, polled every 1s
        clock.t = start + second
        _attempt(runtime, position)
    cancels = exchange.times("cancel_all_tpsl")
    assert cancels == [start, start + 60, start + 120, start + 180]
    assert all(b - a >= CLOSE_RETRY_BACKOFF_SECONDS for a, b in zip(cancels, cancels[1:]))
    # every cancel was followed by a restore, so the stop is resting between attempts
    assert len(exchange.times("place_position_tpsl")) == len(cancels)
    assert exchange.calls[-1][0] == "place_position_tpsl"
    assert runtime.open_positions.get(position.symbol) is position


def test_a_deferred_retry_neither_raises_nor_touches_the_exchange(tmp_path, clock):
    runtime, exchange, position, _ = _setup(tmp_path, clock)
    with pytest.raises(RuntimeError):                # the first failure still raises, as today
        runtime._close_position_for_exit(position, current_price=95.0, reason="STOP_LOSS")
    assert position.metadata[CLOSE_FAILED_TS_KEY] == clock.t
    before = list(exchange.calls)
    clock.t += 59.0
    assert runtime._close_position_for_exit(position, current_price=95.0, reason="STOP_LOSS") is False
    assert exchange.calls == before


def test_exactly_one_alert_per_stuck_close_episode(tmp_path, clock):
    runtime, _, position, alerts = _setup(tmp_path, clock)
    start = clock.t
    for second in range(0, 1300, 1):                 # > 2 x the notify cooldown
        clock.t = start + second
        _attempt(runtime, position)
    assert len(alerts) == 1
    key, message = alerts[0]
    assert "Close Failed, Stop Restored" in message
    assert "ZEC_USDT" in message and "CONVEX_RETENTION_TRAIL" in message
    assert "600 system busy" in message


def test_after_the_backoff_a_successful_retry_closes_normally(tmp_path, clock):
    runtime, exchange, position, alerts = _setup(tmp_path, clock)
    start = clock.t
    assert _attempt(runtime, position) is None
    exchange.close_raises = False
    clock.t = start + 30.0
    assert _attempt(runtime, position) is False       # still inside the backoff
    clock.t = start + 60.0
    assert _attempt(runtime, position) is True
    assert position.symbol not in runtime.open_positions
    assert CLOSE_FAILED_TS_KEY not in position.metadata
    assert runtime.trade_history[-1]["exit_reason"] == "CONVEX_RETENTION_TRAIL"
    assert exchange.times("cancel_all_tpsl") == [start, start + 60.0]
    assert len(alerts) == 1


def test_the_monitor_retries_after_the_backoff_and_keeps_the_stop_between(tmp_path, clock, monkeypatch):
    monkeypatch.setenv("USE_FUTURES_FAIR_PRICE_WS", "0")
    runtime, exchange, position, alerts = _setup(tmp_path, clock)
    runtime._verify_stop_on_book = lambda p: None
    monkeypatch.setattr(FuturesRuntime, "_hourly_exit",
                        lambda self, p, price, now=None: self._close_position_for_exit(
                            p, current_price=price, reason="CONVEX_TIME_STOP"))
    start = clock.t
    for second in range(0, 125):
        clock.t = start + second
        runtime._monitor_open_positions_once()       # never raises: the monitor swallows it
    assert exchange.times("cancel_all_tpsl") == [start, start + 60, start + 120]
    exchange.close_raises = False
    clock.t = start + 180
    assert runtime._monitor_open_positions_once() is True
    assert position.symbol not in runtime.open_positions
    assert len(alerts) == 1


def test_the_stamp_is_persisted_and_a_stale_one_blocks_only_its_remaining_window(tmp_path, clock):
    runtime, exchange, position, _ = _setup(tmp_path, clock)
    stamped = clock.t
    _attempt(runtime, position)
    reloaded = FuturesRuntime(runtime.config, exchange)
    restored = reloaded.open_positions[position.symbol]
    assert restored.metadata[CLOSE_FAILED_TS_KEY] == pytest.approx(stamped)
    reloaded._notify_once = lambda *a, **k: None
    n = len(exchange.calls)
    clock.t = stamped + 20.0                         # restart 20s in: 40s of backoff left
    assert reloaded._close_position_for_exit(restored, current_price=95.0, reason="X") is False
    assert len(exchange.calls) == n
    clock.t = stamped + 60.0                         # never beyond 60s
    _attempt(reloaded, restored)
    assert len(exchange.calls) > n


def test_a_stamp_from_the_future_blocks_nothing(tmp_path, clock):
    runtime, exchange, position, _ = _setup(tmp_path, clock)
    position.metadata[CLOSE_FAILED_TS_KEY] = clock.t + 3600.0      # clock stepped back
    _attempt(runtime, position)
    assert exchange.times("cancel_all_tpsl") == [clock.t]


def test_race_path_is_unchanged_no_stamp_no_alert_no_delay(tmp_path, clock):
    """ZEC 09-19 / XRP 09-20: the exchange's own stop filled first, so the close and the
    restore both fail. Recognised as before - no stamp, no alert - and the next attempt
    is not delayed."""
    runtime, exchange, position, alerts = _setup(tmp_path, clock, open_rows=[], tpsl_raises=True)
    with pytest.raises(RuntimeError):
        runtime._close_position_for_exit(position, current_price=95.0, reason="CONVEX_HARD_STOP")
    assert CLOSE_FAILED_TS_KEY not in position.metadata
    assert alerts == []
    assert "be_stop_bare" not in position.metadata
    clock.t += 1.0
    _attempt(runtime, position)
    assert len(exchange.times("cancel_all_tpsl")) == 2


def test_restore_failed_path_is_unchanged(tmp_path, clock):
    runtime, exchange, position, alerts = _setup(tmp_path, clock, tpsl_raises=True)
    with pytest.raises(RuntimeError):
        runtime._close_position_for_exit(position, current_price=95.0, reason="STOP_LOSS")
    assert position.metadata.get("be_stop_bare") == 1.0
    assert CLOSE_FAILED_TS_KEY not in position.metadata
    assert len(alerts) == 1 and "Stop Not Restored" in alerts[0][1]
    clock.t += 1.0                                   # a bare position is not held back
    _attempt(runtime, position)
    assert len(exchange.times("cancel_all_tpsl")) == 2


def test_paper_trade_is_untouched_by_a_stamp(tmp_path, clock):
    runtime, exchange, position, _ = _setup(tmp_path, clock)
    runtime.config = replace(runtime.config, paper_trade=True)
    position.metadata[CLOSE_FAILED_TS_KEY] = clock.t
    assert runtime._close_position_for_exit(position, current_price=95.0, reason="X") is True
    assert exchange.calls == []


# --- FIX ROUND 1: the backoff DELAYS a decided exit, it never drops it ---------------

EARLY_STOP_ON = {"FUTURES_WILDCARD_CONVEX_EXIT_ENABLED": "1", "FUTURES_STRATEGY_MODE": "pmt_threshold",
                 "FUTURES_WILDCARD_EARLY_STOP_R": "0.5", "FUTURES_WILDCARD_EARLY_STOP_MINUTES": "30"}


def _wildcard(opened_at: datetime) -> FuturesPosition:
    """Entry 100, stop 90, 5x, 5 contracts: 1R = 50% of margin, so 94.8 is -0.52R and
    96.0 is -0.40R against the live WILDCARD early stop (0.5R inside 30 minutes)."""
    return FuturesPosition(
        symbol="ZEC_USDT", side="LONG", entry_price=100.0, contracts=5,
        contract_size=1.0, leverage=5, margin_usdt=100.0,
        tp_price=150.0, sl_price=90.0, position_id="777", order_id="1",
        opened_at=opened_at, score=96.0, certainty=0.9, entry_signal="WILDCARD_LONG",
        metadata={"wildcard": 1.0, "sl_margin_pct": 50.0},
    )


def _early_stop_setup(tmp_path, clock, monkeypatch, opened_at):
    for key, value in EARLY_STOP_ON.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("USE_FUTURES_FAIR_PRICE_WS", "0")
    runtime, exchange, _, alerts = _setup(tmp_path, clock)
    runtime.open_positions.clear()
    runtime._verify_stop_on_book = lambda p: None
    position = _wildcard(opened_at)
    runtime.open_positions[position.symbol] = position
    return runtime, exchange, position, alerts


def test_a_bounce_inside_the_backoff_does_not_drop_the_early_stop(tmp_path, clock, monkeypatch):
    """C04-1 (a), through the real monitor and _hourly_exit: ONE transient failure at
    -0.52R, then a bounce to -0.40R. The early stop was decided; it closes when the
    backoff ends, with its own reason, instead of riding on toward the -1R stop."""
    opened = datetime.now(timezone.utc) - timedelta(minutes=10)
    runtime, exchange, position, alerts = _early_stop_setup(tmp_path, clock, monkeypatch, opened)
    start = clock.t
    exchange.price = 94.8
    runtime._monitor_open_positions_once()           # fires, the close is rejected
    assert position.metadata["early_stop_fired"] == 1.0
    assert position.metadata[CLOSE_FAILED_REASON_KEY] == "CONVEX_EARLY_STOP"
    exchange.close_raises = False                    # the failure was transient
    exchange.price = 96.0                            # and the price bounced
    for second in range(1, 60):
        clock.t = start + second
        assert runtime._monitor_open_positions_once() is False
    clock.t = start + 60
    assert runtime._monitor_open_positions_once() is True
    assert position.symbol not in runtime.open_positions
    assert runtime.trade_history[-1]["exit_reason"] == "CONVEX_EARLY_STOP"
    assert exchange.times("cancel_all_tpsl") == [start, start + 60]
    assert len(alerts) == 1


def test_an_early_stop_whose_window_closes_during_the_backoff_still_closes(tmp_path, clock, monkeypatch):
    """C04-1 (b): the stop fires at minute 29.5 and price stays at -0.52R. At t+60 the
    rule's 30-minute window has ended; the latched close still goes through."""
    opened = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    runtime, exchange, position, _ = _early_stop_setup(tmp_path, clock, monkeypatch, opened)
    with pytest.raises(RuntimeError):
        runtime._hourly_exit(position, 94.8, now=opened + timedelta(minutes=29.5))
    exchange.close_raises = False
    clock.t += 30.0
    assert runtime._hourly_exit(position, 94.8, now=opened + timedelta(minutes=30.0)) is False
    clock.t += 30.0
    assert runtime._hourly_exit(position, 94.8, now=opened + timedelta(minutes=30.5)) is True
    assert runtime.trade_history[-1]["exit_reason"] == "CONVEX_EARLY_STOP"
    assert position.symbol not in runtime.open_positions


def test_the_retry_after_a_through_market_restore_puts_breakeven_back(tmp_path, clock):
    """C04-5: the exit fired with price already through the armed breakeven, so the
    restore fell back to the designed stop (90). Price then recovers above breakeven and
    the exit condition lapses; the latched retry re-places breakeven, not -1R."""
    runtime, exchange, position, _ = _setup(tmp_path, clock)
    position.metadata["be_stop_price"] = 100.19
    with pytest.raises(RuntimeError):
        runtime._close_position_for_exit(position, current_price=99.0, reason="CONVEX_RETENTION_TRAIL")
    clock.t += 60.0
    with pytest.raises(RuntimeError):                # the failure persists
        runtime._hourly_exit(position, 102.0)
    assert exchange.stops == [pytest.approx(90.0), pytest.approx(100.19)]


def test_a_failed_manual_close_puts_the_stop_back(tmp_path, clock):
    """C04-2: /close inside a stuck-close backoff cancelled the restored stop and, on a
    failure, left the position bare until the backoff ended."""
    runtime, exchange, position, _ = _setup(tmp_path, clock)
    _attempt(runtime, position)                      # a stuck close, stop restored
    clock.t += 5.0
    with pytest.raises(RuntimeError):
        runtime._force_close_position(reason="MANUAL_CLOSE", symbol=position.symbol)
    assert [name for name, t in exchange.calls if t == clock.t] == [
        "cancel_all_tpsl", "close_position", "place_position_tpsl"]
    assert exchange.stops[-1] == pytest.approx(90.0)


def test_a_latched_position_is_never_a_preemption_victim(tmp_path, clock, monkeypatch):
    """C04-3: a stuck WILDCARD position below +0.3R was an eligible victim, and a preempt
    after its backoff placed its stop twice (restore, then _rearm_stop)."""
    monkeypatch.setenv("FUTURES_WILDCARD_PREEMPT_ENABLED", "1")
    opened = datetime.now(timezone.utc) - timedelta(minutes=30)
    runtime, exchange, position, _ = _early_stop_setup(tmp_path, clock, monkeypatch, opened)
    incoming = SimpleNamespace(symbol="SOL_USDT", side="LONG")
    assert runtime._preemption_candidate(incoming)[0] is position     # eligible today
    with pytest.raises(RuntimeError):
        runtime._close_position_for_exit(position, current_price=95.0, reason="CONVEX_TIME_STOP")
    clock.t += 120.0                                 # even after its backoff
    assert runtime._preemption_candidate(incoming) is None


def test_a_failed_preemption_is_neither_stamped_nor_latched(tmp_path, clock, monkeypatch):
    """An eviction pairs only with the entry that just failed: it is not retried, so
    it is not latched, and the victim's own exits are not held back."""
    monkeypatch.setenv("FUTURES_WILDCARD_PREEMPT_ENABLED", "1")
    opened = datetime.now(timezone.utc) - timedelta(minutes=30)
    runtime, exchange, position, alerts = _early_stop_setup(tmp_path, clock, monkeypatch, opened)
    assert runtime._try_preempt_for(SimpleNamespace(symbol="SOL_USDT", side="LONG")) is None
    assert CLOSE_FAILED_TS_KEY not in position.metadata
    assert CLOSE_FAILED_REASON_KEY not in position.metadata
    assert [key for key, _ in alerts] == ["preempt_fail_ZEC_USDT"]


def test_a_new_episode_on_the_same_position_alerts_again(tmp_path, clock):
    """C04-4: one failure, then a new stuck episode 2h later (a restart, say) on the
    same position. The stale stamp starts a new episode, so it alerts again."""
    runtime, _, position, alerts = _setup(tmp_path, clock)
    _attempt(runtime, position)
    clock.t += 7200.0
    for second in range(0, 181):
        _attempt(runtime, position)
        clock.t += 1.0
    assert len(alerts) == 2


def test_a_manual_close_whose_cancel_failed_restores_nothing(tmp_path, clock):
    """N-1: when /close could not cancel the stop, the stop is still resting; restoring it on a
    failed close would duplicate it or record a false be_stop_bare (a K3 field)."""
    runtime, exchange, position, alerts = _setup(tmp_path, clock, tpsl_raises=True)

    def _cancel_fails(**kw):
        exchange.calls.append(("cancel_all_tpsl", clock.t))
        raise RuntimeError("cancel rejected")

    exchange.cancel_all_tpsl = _cancel_fails
    with pytest.raises(RuntimeError):
        runtime._force_close_position(reason="MANUAL_CLOSE", symbol=position.symbol)
    assert [name for name, _ in exchange.calls] == ["cancel_all_tpsl", "close_position"]
    assert not position.metadata.get("be_stop_bare")
