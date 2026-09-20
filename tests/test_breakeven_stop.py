"""Breakeven stop after a proved peak (trial 21F, owner decision 2026-09-20).

Once the fair peak reaches FUTURES_CONVEX_BREAKEVEN_ARM_R the resting exchange stop
moves ONCE to entry +/- costs. position.sl_price must not move: r_now divides by the
live stop distance, so moving it would rescale every R the position reports.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from futuresbot.config import FuturesConfig
from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime


class _Client:
    def __init__(self, *, place_raises: bool = False) -> None:
        self.place_raises = place_raises
        self.calls: list[tuple[str, dict]] = []

    def cancel_all_tpsl(self, *, position_id=None, symbol=None, **kw):
        self.calls.append(("cancel", {"position_id": position_id, "symbol": symbol, **kw}))
        return {"success": True}

    def place_position_tpsl(self, **kw):
        self.calls.append(("place", kw))
        if self.place_raises:
            raise RuntimeError("stop rejected")
        return {"success": True}

    def get_open_positions(self, symbol=None):
        return [{"positionType": 1, "holdVol": 10}]

    def get_account_asset(self, currency: str = "USDT"):
        return {"availableBalance": "1000", "equity": "1000"}

    def get_updates(self, *, offset=None, limit: int = 5, timeout: int = 0):
        return []


def _runtime(tmp_path, client, monkeypatch, *, arm="0.90", paper=False):
    monkeypatch.setenv("FUTURES_CONVEX_BREAKEVEN_ARM_R", arm)
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "s.json"), status_file=str(tmp_path / "st.json"),
                  telegram_token="t", telegram_chat_id="1", paper_trade=paper)
    rt = FuturesRuntime(cfg, client)
    rt._notify = lambda *a, **k: None
    rt._notify_once = lambda *a, **k: None
    rt._save_state = lambda: None
    return rt


def _pos(side: str = "LONG") -> FuturesPosition:
    sl = 98.0 if side == "LONG" else 102.0
    tp = 110.0 if side == "LONG" else 90.0
    return FuturesPosition(symbol="ZEC_USDT", side=side, entry_price=100.0, contracts=10,
                           contract_size=1.0, leverage=5, margin_usdt=200.0, tp_price=tp,
                           sl_price=sl, position_id="7", order_id="1",
                           opened_at=datetime.now(timezone.utc) - timedelta(minutes=20),
                           score=96.0, certainty=0.9, entry_signal="TREND_LONG",
                           metadata={"wildcard": 1.0, "trend": 1.0, "sl_margin_pct": 10.0})


def _placed(client):
    return [c[1] for c in client.calls if c[0] == "place"]


def test_a_proved_long_moves_the_resting_stop_once(tmp_path, monkeypatch):
    client = _Client()
    rt = _runtime(tmp_path, client, monkeypatch)
    pos = _pos()
    rt._maybe_breakeven_stop(pos, 101.9, r_now=0.95, peak_r=0.95)
    assert _placed(client)[0]["stop_loss_price"] == pytest.approx(100.19)
    assert _placed(client)[0]["take_profit_price"] == pytest.approx(110.0)
    assert pos.metadata["be_stop_price"] == pytest.approx(100.19)
    assert pos.sl_price == 98.0, "the R denominator must not move"

    rt._maybe_breakeven_stop(pos, 101.0, r_now=0.92, peak_r=1.40)   # never a second time
    assert len(_placed(client)) == 1


def test_a_short_moves_below_entry(tmp_path, monkeypatch):
    client = _Client()
    rt = _runtime(tmp_path, client, monkeypatch)
    pos = _pos("SHORT")
    rt._maybe_breakeven_stop(pos, 98.1, r_now=0.95, peak_r=0.95)
    assert _placed(client)[0]["stop_loss_price"] == pytest.approx(99.81)


def test_below_the_arm_nothing_is_sent(tmp_path, monkeypatch):
    client = _Client()
    rt = _runtime(tmp_path, client, monkeypatch)
    pos = _pos()
    rt._maybe_breakeven_stop(pos, 100.8, r_now=0.89, peak_r=0.89)
    assert client.calls == [] and "be_stop_price" not in pos.metadata


def test_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("FUTURES_CONVEX_BREAKEVEN_ARM_R", raising=False)
    client = _Client()
    rt = _runtime(tmp_path, client, monkeypatch, arm="0")
    pos = _pos()
    rt._maybe_breakeven_stop(pos, 103.0, r_now=1.5, peak_r=1.5)
    assert client.calls == []


def test_a_failed_move_flags_the_position_bare_and_stops_re_amending(tmp_path, monkeypatch):
    """Cancel landed, place failed, restore failed: no resting stop. The amend stands
    down (the repair loop owns it from here) and the position is flagged."""
    client = _Client(place_raises=True)
    rt = _runtime(tmp_path, client, monkeypatch)
    pos = _pos()
    for _ in range(5):
        pos.metadata.pop("be_stop_last_try_ts", None)        # a minute has passed each time
        rt._maybe_breakeven_stop(pos, 101.9, r_now=0.95, peak_r=0.95)
    assert "be_stop_price" not in pos.metadata
    assert pos.metadata["be_stop_attempts"] == 1.0
    assert pos.metadata["be_stop_bare"] == 1.0
    assert [p["stop_loss_price"] for p in _placed(client)].count(98.0) >= 1   # tried to restore


def test_paper_trading_sends_no_orders_and_does_not_claim_an_armed_stop(tmp_path, monkeypatch):
    """Nothing enforces the level in paper, so the live key would make a paper row
    look like an armed live one in the corpus."""
    client = _Client()
    rt = _runtime(tmp_path, client, monkeypatch, paper=True)
    pos = _pos()
    rt._maybe_breakeven_stop(pos, 101.9, r_now=0.95, peak_r=0.95)
    assert client.calls == []
    assert "be_stop_price" not in pos.metadata
    assert pos.metadata["be_stop_paper_price"] == pytest.approx(100.19)


def test_the_shadow_threshold_records_and_never_orders(tmp_path, monkeypatch):
    client = _Client()
    rt = _runtime(tmp_path, client, monkeypatch, arm="0")            # rule off, shadow on
    pos = _pos()
    rt._maybe_breakeven_stop(pos, 100.8, r_now=0.80, peak_r=0.80)
    assert pos.metadata["be_shadow_arm_r"] == pytest.approx(0.80)
    assert "be_shadow_touch_ts" not in pos.metadata
    rt._maybe_breakeven_stop(pos, 100.1, r_now=0.05, peak_r=0.80)   # through entry+costs
    assert pos.metadata["be_shadow_touch_r"] == pytest.approx(0.05)
    first = pos.metadata["be_shadow_touch_ts"]
    rt._maybe_breakeven_stop(pos, 99.0, r_now=-0.5, peak_r=0.80)
    assert pos.metadata["be_shadow_touch_ts"] == first              # first touch only
    assert client.calls == []


def test_the_trail_calls_it_and_the_telemetry_reaches_the_records():
    import inspect
    from futuresbot.runtime import EXIT_TELEMETRY_KEYS
    trail = inspect.getsource(FuturesRuntime._convex_runner_trail_exit)
    assert "_maybe_breakeven_stop" in trail
    assert trail.index("_maybe_breakeven_stop") < trail.index("if r_now > peak_r:")
    assert "be_stop_price" in EXIT_TELEMETRY_KEYS and "be_shadow_touch_r" in EXIT_TELEMETRY_KEYS
    for fn in (FuturesRuntime._close_history_trade, FuturesRuntime._append_feature_store):
        assert "EXIT_TELEMETRY_KEYS" in inspect.getsource(fn)


def test_a_faded_trade_never_gets_a_stop_on_the_wrong_side(tmp_path, monkeypatch):
    """The population this rule targets peaks and fades. With a persisted peak (a
    restart, or the deploy that enables it) the market can already be below entry."""
    client = _Client()
    rt = _runtime(tmp_path, client, monkeypatch)
    pos = _pos()
    rt._maybe_breakeven_stop(pos, 99.0, r_now=-0.5, peak_r=1.40)     # long, price under entry
    assert client.calls == [] and "be_stop_price" not in pos.metadata
    assert pos.metadata["be_stop_wrong_side"] == pytest.approx(-0.5)

    short = _pos("SHORT")
    rt._maybe_breakeven_stop(short, 101.0, r_now=-0.5, peak_r=1.40)
    assert client.calls == [] and "be_stop_price" not in short.metadata


def test_without_a_position_id_nothing_is_cancelled(tmp_path, monkeypatch):
    """cancel_all_tpsl with a falsy id cancels the whole symbol and the restore path
    refuses without an id: the position would be left bare."""
    client = _Client()
    rt = _runtime(tmp_path, client, monkeypatch)
    pos = _pos()
    pos.position_id = ""
    rt._maybe_breakeven_stop(pos, 101.9, r_now=0.95, peak_r=0.95)
    assert client.calls == [] and pos.metadata["be_stop_no_position_id"] == 1.0


def test_retries_are_rate_limited_to_one_a_minute(tmp_path, monkeypatch):
    client = _Client(place_raises=True)
    rt = _runtime(tmp_path, client, monkeypatch)
    pos = _pos()
    for _ in range(4):
        rt._maybe_breakeven_stop(pos, 101.9, r_now=0.95, peak_r=0.95)
    assert pos.metadata["be_stop_attempts"] == 1.0


def test_a_restore_keeps_the_breakeven_floor(tmp_path, monkeypatch):
    """Every path that re-places the bracket must read the breakeven price, or a
    failed close silently reverts the floor to -1R."""
    pos = _pos()
    assert FuturesRuntime._effective_stop_price(pos) == 98.0
    pos.metadata["be_stop_price"] = 100.19
    assert FuturesRuntime._effective_stop_price(pos) == pytest.approx(100.19)
    import inspect
    for fn in (FuturesRuntime._restore_exchange_tpsl, FuturesRuntime._rearm_stop):
        assert "_effective_stop_price" in inspect.getsource(fn)


def test_a_failed_move_cancels_before_restoring_and_stays_inside_its_budget(tmp_path, monkeypatch):
    """An ambiguous place may already rest on the exchange: restoring without
    cancelling would leave two live stops. And the failure path must stay bounded -
    it runs in the synchronous position monitor."""
    client = _Client(place_raises=True)
    rt = _runtime(tmp_path, client, monkeypatch)
    pos = _pos()
    rt._maybe_breakeven_stop(pos, 101.9, r_now=0.95, peak_r=0.95)
    kinds = [c[0] for c in client.calls]
    assert kinds == ["cancel", "place", "cancel", "place"]          # cancel before the restore
    for name, kw in client.calls:
        assert kw.get("attempts") == 1 and kw.get("timeout") == 4.0, (name, kw)


def test_guard_counters_reach_the_records():
    from futuresbot.runtime import EXIT_TELEMETRY_KEYS
    for k in ("be_stop_wrong_side", "be_stop_no_position_id", "be_stop_attempts", "be_stop_paper_price"):
        assert k in EXIT_TELEMETRY_KEYS


def test_a_bare_position_is_repaired_and_the_flag_clears(tmp_path, monkeypatch):
    """Cancel landed, both places failed: no resting stop. That state is retried until
    it is repaired, because the in-process stop dies with the process."""
    client = _Client(place_raises=True)
    rt = _runtime(tmp_path, client, monkeypatch)
    pos = _pos()
    rt._maybe_breakeven_stop(pos, 101.9, r_now=0.95, peak_r=0.95)
    assert pos.metadata["be_stop_bare"] == 1.0

    client.place_raises = False                                  # exchange comes back
    pos.metadata.pop("be_stop_bare_last_try_ts", None)
    assert rt._repair_bare_stop(pos, 101.9) is True
    assert "be_stop_bare" not in pos.metadata
    assert _placed(client)[-1]["stop_loss_price"] == 98.0         # the designed stop, restored


def test_a_sub_dollar_short_keeps_its_breakeven_on_the_right_side(tmp_path, monkeypatch):
    """The 0.01 fallback tick used to round a 0.008 entry's stop to 0.01 - a -12R stop
    instead of breakeven. No snapping, and anything not on the profit side is refused."""
    client = _Client()
    rt = _runtime(tmp_path, client, monkeypatch)
    pos = _pos("SHORT")
    pos.entry_price = 0.0080
    pos.sl_price = 0.00816
    pos.tp_price = 0.0076
    rt._maybe_breakeven_stop(pos, 0.00785, r_now=0.95, peak_r=0.95)
    placed = _placed(client)[0]["stop_loss_price"]
    assert placed == pytest.approx(0.0080 * (1 - 0.0019))
    assert placed < pos.entry_price                               # a short's floor sits below entry


def test_bounded_calls_make_exactly_one_request_with_no_retry_sleep():
    """attempts=1 must mean one call and no sleep: these run inside the position monitor."""
    import time as _time
    from futuresbot import marketdata as md
    calls = {"n": 0}

    class _Sess:
        def post(self, *a, **kw):
            calls["n"] += 1
            raise RuntimeError("stall")
        get = post

    client = object.__new__(md.MexcFuturesClient)
    client.session = _Sess()
    client.config = type("C", (), {"futures_base_url": "https://x"})()
    client._headers = lambda **kw: {}
    t0 = _time.time()
    with pytest.raises(Exception):
        client.private_post("/x", {"a": 1}, attempts=1, timeout=1.0)
    assert calls["n"] == 1 and _time.time() - t0 < 0.5          # no phantom backoff sleep


def test_the_repair_runs_from_the_monitor_not_from_the_trail():
    """FUTURES_CONVEX_RUNNER_TRAIL=0 is the first thing an owner reaches for after a
    "Stop Not Restored" alert: the repair must not die with it."""
    import inspect
    monitor = inspect.getsource(FuturesRuntime._monitor_open_positions_once)
    assert "_repair_bare_stop" in monitor
    trail = inspect.getsource(FuturesRuntime._convex_runner_trail_exit)
    assert "_repair_bare_stop" not in trail


def test_a_restore_falls_back_when_the_breakeven_floor_is_through_the_market(tmp_path, monkeypatch):
    """A breakeven floor sits ~50x closer to market than the designed stop, so a failed
    close can find the market already past it. Re-placing it there would be rejected."""
    client = _Client()
    rt = _runtime(tmp_path, client, monkeypatch)
    pos = _pos()
    pos.metadata["be_stop_price"] = 100.19
    assert rt._restore_exchange_tpsl(pos, current_price=100.05) is True
    assert _placed(client)[-1]["stop_loss_price"] == 98.0          # the designed stop
    assert rt._restore_exchange_tpsl(pos, current_price=101.50) is True
    assert _placed(client)[-1]["stop_loss_price"] == pytest.approx(100.19)


def test_a_failed_restore_on_an_open_position_raises_the_bare_flag(tmp_path, monkeypatch):
    client = _Client(place_raises=True)
    rt = _runtime(tmp_path, client, monkeypatch)
    pos = _pos()
    assert rt._restore_exchange_tpsl(pos) is False
    assert pos.metadata["be_stop_bare"] == 1.0                     # the close path too


def test_the_preempt_rearm_gets_the_same_guard_and_flag(tmp_path, monkeypatch):
    """A preempted position is below its breakeven floor by construction, so re-placing
    the floor there would be rejected or fill at once."""
    client = _Client()
    rt = _runtime(tmp_path, client, monkeypatch)
    pos = _pos()
    pos.metadata["be_stop_price"] = 100.19
    assert rt._rearm_stop(pos, 99.40) is True
    assert _placed(client)[-1]["stop_loss_price"] == 98.0          # designed stop, not the floor

    failing = _Client(place_raises=True)
    rt2 = _runtime(tmp_path, failing, monkeypatch)
    pos2 = _pos()
    assert rt2._rearm_stop(pos2, 99.40) is False
    assert pos2.metadata["be_stop_bare"] == 1.0                    # the repair loop takes over
