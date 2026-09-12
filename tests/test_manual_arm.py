"""`/arm SYMBOL` — the manual arm of the retention trail.

The automatic gate (`peak_r < FUTURES_CONVEX_TRAIL_ARM_R`) refuses to trail at
all below 1.0R, so a trade at +0.6R has no floor: only the -1R stop, the TP and
the clock. `/arm` bypasses THAT GATE AND NOTHING ELSE — retain, the 3R ratchet,
the cost floor and the disable-if-floor-above-peak branch are untouched.

The invariant these pin: the floor is `retain(peak) x peak` floored at breakeven,
both factors only rise, and `convex_peak_r` only ever ratchets up — so a manual
arm can never lower a floor, widen a stop or un-arm anything. And the last test
in the file is the one that matters most: with the command never typed, the
automatic path is byte-identical to before.
"""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from futuresbot import commands as commands_module
from futuresbot.config import FuturesConfig
from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("FUTURES_CONVEX_TRAIL_RATCHET_R", "FUTURES_CONVEX_TRAIL_RATCHET_RETAIN",
                "FUTURES_CONVEX_TRAIL_RETAIN_FRAC", "FUTURES_CONVEX_RUNNER_TRAIL",
                "FUTURES_CONVEX_TRAIL_ARM_R", "FUTURES_CONVEX_COST_PCT",
                "FUTURES_CONVEX_COST_FLOOR_MULT", "FUTURES_WILDCARD_CONVEX_EXIT_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    # Mirror the live env: the code default for the retain fraction is 0.30, the
    # deployed value is 0.50. Pin it so these numbers mean what production means.
    monkeypatch.setenv("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", "0.50")


class _Client:
    """Minimal client: the only call `_manual_arm` makes is get_fair_price."""

    def __init__(self, price: float = 106.0) -> None:
        self.price = price

    def get_fair_price(self, symbol: str) -> float:
        return self.price

    def get_account_asset(self, currency: str = "USDT") -> dict[str, str]:
        return {"availableBalance": "200", "equity": "200"}

    def get_updates(self, *, offset=None, limit: int = 5, timeout: int = 0):
        return []


def _pos(entry: float = 100.0, sl: float = 90.0, side: str = "LONG",
         symbol: str = "ZEC_USDT", metadata: dict | None = None) -> FuturesPosition:
    """A 10% stop at 10x: 1R = $10, a +10% price move is exactly +1R, and the
    sleeve's own cost floor (0.190%/0.10 x 1.5 = 0.029R) is far below any peak
    used here - so these tests exercise the retention floor, not the cost floor."""
    return FuturesPosition(
        symbol=symbol, side=side, entry_price=entry, contracts=1,
        contract_size=1.0, leverage=10, margin_usdt=10.0,
        tp_price=entry * 1.5, sl_price=sl, position_id="1", order_id="1",
        opened_at=datetime.now(timezone.utc) - timedelta(hours=1),
        score=96.0, certainty=0.9, entry_signal="WILDCARD_LONG",
        metadata=metadata if metadata is not None else {"wildcard": 1.0, "sl_margin_pct": 100.0},
    )


def _runtime(tmp_path, client: _Client | None = None) -> FuturesRuntime:
    config = replace(
        FuturesConfig.from_env(),
        symbol="BTC_USDT", symbols=("BTC_USDT",),
        runtime_state_file=str(tmp_path / "state.json"),
        status_file=str(tmp_path / "status.json"),
        telegram_token="token", telegram_chat_id="1",
    )
    runtime = FuturesRuntime(config, client or _Client())
    runtime._notify = lambda message, parse_mode="HTML": runtime.__dict__.setdefault("_sent", []).append(message)
    return runtime


def _armed(runtime: FuturesRuntime, position: FuturesPosition) -> tuple[bool, str]:
    runtime.open_positions[position.symbol] = position
    return runtime._manual_arm(position.symbol)


# --- happy path ------------------------------------------------------------

def test_arms_below_the_gate_and_the_trail_then_fires(tmp_path, monkeypatch):
    """The owner's first example: in profit, below the automatic arm, nothing
    is armed — until a human types the command."""
    runtime = _runtime(tmp_path, _Client(price=106.0))   # +0.60R
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position

    # Before: the gate blocks the trail entirely, even after a big giveback.
    assert runtime._convex_runner_trail_exit(position, 106.0) is False
    assert runtime._convex_runner_trail_exit(position, 101.0) is False

    ok, message = runtime._manual_arm("ZEC")
    assert ok is True
    assert "ZEC_USDT" in message and "LONG" in message
    assert "+0.60R" in message                      # current R
    assert "+6.00" in message                       # current $ (1R = $10)
    assert "+0.30R" in message                      # resulting floor in R
    assert "+3.00" in message                       # resulting floor in $
    assert "CONVEX_RETENTION_TRAIL" in message
    assert "never falls" in message

    md = position.metadata
    assert md["manual_arm"] == 1.0
    assert md["manual_arm_at_r"] == pytest.approx(0.60, abs=0.01)
    assert md["manual_arm_peak_r"] == pytest.approx(0.60, abs=0.01)
    assert md["manual_arm_floor_r"] == pytest.approx(0.30, abs=0.01)
    assert md["manual_arm_arm_r"] == pytest.approx(1.0)
    assert md["convex_peak_r"] == pytest.approx(0.60, abs=0.01)

    # After: the floor is live at 0.50 x 0.60R = 0.30R -> price 103.
    closed = {}
    monkeypatch.setattr(runtime, "_close_position_for_exit",
                        lambda p, **kw: closed.update(reason=kw.get("reason")) or True)
    assert runtime._convex_runner_trail_exit(position, 104.0) is False   # +0.40R, above floor
    assert runtime._convex_runner_trail_exit(position, 102.0) is True    # +0.20R, below floor
    assert closed["reason"] == "CONVEX_RETENTION_TRAIL"


def test_arm_anchors_on_the_current_value_not_the_peak(tmp_path):
    """THE OWNER'S REQUIREMENT. Armed at +0.6R after a +0.8R peak, the floor derives
    from the CURRENT +0.6R (-> +0.30R), not the +0.8R peak (-> +0.40R). A floor off a
    peak the trade has fallen away from may never be reached again, so it secures
    nothing; the point is to lock in something reachable by construction."""
    runtime = _runtime(tmp_path, _Client(price=106.0))   # +0.60R, peak +0.80R
    position = _pos(metadata={"wildcard": 1.0, "sl_margin_pct": 100.0, "convex_peak_r": 0.80})
    ok, message = _armed(runtime, position)
    assert ok is True
    assert position.metadata["manual_arm_peak_r"] == pytest.approx(0.60)   # the anchor
    assert position.metadata["manual_arm_true_peak_r"] == pytest.approx(0.80)
    assert position.metadata["manual_arm_floor_r"] == pytest.approx(0.30)
    assert "+0.30R" in message


def test_a_deeply_retraced_position_is_armable_from_where_it_is(tmp_path):
    """Peak +0.80R, price back to +0.20R. Anchoring on the peak would put the floor
    at +0.40R - above the current value, an instant close. Anchoring on the current
    value gives +0.10R, which is reachable and better than the nothing in force
    below the gate."""
    runtime = _runtime(tmp_path, _Client(price=102.0))   # +0.20R
    position = _pos(metadata={"wildcard": 1.0, "sl_margin_pct": 100.0, "convex_peak_r": 0.80})
    ok, message = _armed(runtime, position)
    assert ok is True
    assert position.metadata["manual_arm_floor_r"] == pytest.approx(0.10)
    assert "+0.10R" in message


def test_cost_floor_above_the_current_level_still_refuses(tmp_path, monkeypatch):
    """The floor can only be below the current value by construction now (retain < 1),
    EXCEPT when the breakeven cost floor dominates. That case must still refuse."""
    monkeypatch.setenv("FUTURES_CONVEX_COST_PCT", "9.0")     # a punitive round trip
    runtime = _runtime(tmp_path, _Client(price=101.0))       # +0.10R
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    _refuses(runtime, position, "ZEC", "cannot be trailed profitably from here")


def test_refusal_11_legacy_giveback_mode_has_no_breakeven_floor(tmp_path, monkeypatch):
    """retain<=0 selects the legacy fixed-R giveback, which applies no cost floor:
    at +0.60R with the default 2.0R giveback the 'floor' is -1.40R. The automatic
    path never reaches it below the gate; /arm must refuse rather than arm into it."""
    monkeypatch.setenv("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", "0")
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    _refuses(runtime, position, "ZEC", "legacy giveback mode")
    assert "manual_arm" not in position.metadata


def test_success_reports_the_floor_as_a_price(tmp_path):
    """The only number that can be checked against a chart."""
    runtime = _runtime(tmp_path, _Client(price=106.0))   # +0.60R, floor +0.30R
    ok, message = _armed(runtime, _pos())
    assert ok is True
    assert "Exits at" in message
    # 10% stop at 10x -> sl_frac 0.10; floor 0.30R -> entry x (1 + 0.30 x 0.10) = 103.0
    assert "103" in message


def test_symbol_resolution_is_case_insensitive_and_suffix_optional(tmp_path):
    for argument in ("zec", "ZEC", "zec_usdt", "ZEC_USDT", " ZeC "):
        runtime = _runtime(tmp_path, _Client(price=106.0))
        runtime.open_positions["ZEC_USDT"] = _pos()
        ok, _ = runtime._manual_arm(argument)
        assert ok is True, argument
    runtime = _runtime(tmp_path, _Client(price=106.0))
    runtime.open_positions["ZEC_USDT"] = _pos()
    ok, message = runtime._manual_arm("ZE")
    assert ok is False and "No open position for ZE_USDT." in message


# --- refusals --------------------------------------------------------------

def _refuses(runtime: FuturesRuntime, position: FuturesPosition | None, argument: str,
             fragment: str) -> None:
    before = json.dumps(position.metadata, sort_keys=True, default=str) if position else None
    ok, message = runtime._manual_arm(argument)
    assert ok is False, message
    assert fragment in message, message
    if position is not None:
        assert json.dumps(position.metadata, sort_keys=True, default=str) == before


def test_refusal_1_no_argument(tmp_path):
    _refuses(_runtime(tmp_path), None, "", "Usage: /arm SYMBOL")


def test_refusal_2_no_such_position(tmp_path):
    _refuses(_runtime(tmp_path), None, "DOGE", "No open position for DOGE_USDT.")


def test_refusal_3_not_managed_by_the_trail(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_CONVEX_RUNNER_TRAIL", "0")
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    _refuses(runtime, position, "ZEC", "is not managed by the retention trail")


def test_refusal_4_already_manually_armed(tmp_path):
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    assert runtime._manual_arm("ZEC")[0] is True
    _refuses(runtime, position, "ZEC", "is already manually armed at +0.60R")


def test_refusal_5_no_usable_price(tmp_path):
    class _Dead(_Client):
        def get_fair_price(self, symbol: str) -> float:
            raise RuntimeError("feed down")

    runtime = _runtime(tmp_path, _Dead())
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    _refuses(runtime, position, "ZEC", "Could not read a price for ZEC_USDT")


def test_refusal_6_no_usable_stop_distance(tmp_path):
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos(sl=0.0, metadata={"wildcard": 1.0})
    runtime.open_positions["ZEC_USDT"] = position
    _refuses(runtime, position, "ZEC", "has no usable stop distance")


def test_refusal_7_not_in_profit(tmp_path):
    runtime = _runtime(tmp_path, _Client(price=97.0))       # -0.30R
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    _refuses(runtime, position, "ZEC", "only arms a trade that is in profit")


def test_refusal_8_already_armed_automatically(tmp_path):
    """The owner's SECOND example, at a new high. The live floor is already
    0.50 x 2.30R and arming from the same value reproduces it exactly, so there is
    nothing to gain — say so with the real numbers and point at the giveback form."""
    runtime = _runtime(tmp_path, _Client(price=123.0))      # +2.30R, at its peak
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    _refuses(runtime, position, "ZEC", "already has a floor at +1.15R")
    ok, message = runtime._manual_arm("ZEC")
    assert ok is False
    assert "+1.15R" in message and "50% of its +2.30R peak" in message
    assert "A giveback under 0.50 would beat it" in message


def test_refusal_9_floor_below_the_cost_floor(tmp_path, monkeypatch):
    """A floor under the sleeve's own round-trip cost banks a net loss, which is
    the `exit_level >= peak_r` branch the exit path already refuses to trail."""
    monkeypatch.setenv("FUTURES_CONVEX_COST_PCT", "4.0")    # cost floor 0.60R, at the peak
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    _refuses(runtime, position, "ZEC", "cannot be trailed profitably")


def test_refusals_never_write_state(tmp_path):
    runtime = _runtime(tmp_path, _Client(price=97.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    assert runtime._manual_arm("ZEC")[0] is False
    assert "manual_arm" not in position.metadata


# --- persistence -----------------------------------------------------------

def test_manual_arm_survives_a_restart(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    assert runtime._manual_arm("ZEC")[0] is True

    reloaded = _runtime(tmp_path, _Client(price=106.0))     # same state file
    restored = reloaded.open_positions["ZEC_USDT"]
    assert restored.metadata["manual_arm"] == 1.0
    assert restored.metadata["manual_arm_floor_r"] == pytest.approx(0.30, abs=0.01)
    assert restored.metadata["convex_peak_r"] == pytest.approx(0.60, abs=0.01)

    closed = {}
    monkeypatch.setattr(reloaded, "_close_position_for_exit",
                        lambda p, **kw: closed.update(reason=kw.get("reason")) or True)
    assert reloaded._convex_runner_trail_exit(restored, 102.0) is True
    assert closed["reason"] == "CONVEX_RETENTION_TRAIL"


# --- the invariant ---------------------------------------------------------

def test_the_floor_never_falls_after_a_manual_arm(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    assert runtime._manual_arm("ZEC")[0] is True
    monkeypatch.setattr(runtime, "_close_position_for_exit", lambda p, **kw: True)
    monkeypatch.setattr(runtime, "_maybe_record_peak_notify", lambda *a, **k: None)

    floors = []
    for price in (107.0, 114.0, 129.0, 131.0, 120.0, 145.0, 133.0):
        runtime._convex_runner_trail_exit(position, price)
        peak = position.metadata["convex_peak_r"]
        floors.append(runtime._trail_retain_for(peak, 0.50) * peak)
    assert all(b >= a - 1e-9 for a, b in zip(floors, floors[1:]))
    assert floors[-1] == pytest.approx(0.75 * position.metadata["convex_peak_r"])


def test_manual_arm_cannot_lower_an_existing_peak(tmp_path):
    runtime = _runtime(tmp_path, _Client(price=106.0))      # +0.60R now
    position = _pos(metadata={"wildcard": 1.0, "sl_margin_pct": 100.0, "convex_peak_r": 0.80})
    runtime.open_positions["ZEC_USDT"] = position
    assert runtime._manual_arm("ZEC")[0] is True
    assert position.metadata["convex_peak_r"] == pytest.approx(0.80)


def test_void_stamp_when_the_cost_floor_rises_above_the_peak(tmp_path, monkeypatch):
    """"Armed" must not silently stop meaning "trailing": cost_r moves with the
    LIVE stop distance, so an armed position can become un-trailable later."""
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    assert runtime._manual_arm("ZEC")[0] is True
    monkeypatch.setenv("FUTURES_CONVEX_COST_PCT", "4.0")
    assert runtime._convex_runner_trail_exit(position, 105.0) is False
    stamped = position.metadata["manual_arm_voided_ts"]
    assert stamped > 0
    assert runtime._convex_runner_trail_exit(position, 105.0) is False
    assert position.metadata["manual_arm_voided_ts"] == stamped


# --- telemetry -------------------------------------------------------------

def test_manual_arm_columns_reach_the_closed_trade(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    assert runtime._manual_arm("ZEC")[0] is True

    monkeypatch.setattr(runtime, "_notify", lambda *a, **k: None)
    runtime._close_history_trade(position, exit_price=103.0, reason="CONVEX_RETENTION_TRAIL")
    trade = runtime.trade_history[-1]
    assert trade["manual_arm"] == 1.0
    assert trade["manual_arm_at_r"] == pytest.approx(0.60, abs=0.01)
    assert trade["manual_arm_floor_r"] == pytest.approx(0.30, abs=0.01)
    assert trade["manual_arm_arm_r"] == pytest.approx(1.0)
    assert trade["manual_arm_ts"] > 0
    # Decisive: the peak never reached the automatic gate, so this exit happened
    # ONLY because a human armed it.
    assert trade["manual_arm_decisive"] == 1.0


def test_manual_arm_decisive_is_zero_when_the_auto_gate_would_have_armed(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    assert runtime._manual_arm("ZEC")[0] is True
    position.metadata["convex_peak_r"] = 2.4          # later ran past the 1.0R gate
    monkeypatch.setattr(runtime, "_notify", lambda *a, **k: None)
    runtime._close_history_trade(position, exit_price=112.0, reason="CONVEX_RETENTION_TRAIL")
    assert runtime.trade_history[-1]["manual_arm_decisive"] == 0.0


# --- the command surface ---------------------------------------------------

def test_telegram_command_arms_and_replies_with_numbers(tmp_path):
    runtime = _runtime(tmp_path, _Client(price=106.0))
    sent: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent.append(message)
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    runtime.telegram.get_updates = lambda **kwargs: [
        {"update_id": 1, "message": {"chat": {"id": "1"}, "text": "/arm zec"}},
    ]
    runtime._handle_telegram_commands()
    assert any("🔒 <b>Manual Arm</b>" in message for message in sent)
    assert any("+0.30R" in message for message in sent)
    assert position.metadata["manual_arm"] == 1.0
    assert any("/arm ZEC_USDT" in entry for entry in runtime._recent_activity)


def test_telegram_command_refusal_is_reported_not_silent(tmp_path):
    runtime = _runtime(tmp_path, _Client(price=106.0))
    sent: list[str] = []
    runtime._notify = lambda message, parse_mode="HTML": sent.append(message)
    runtime.telegram.get_updates = lambda **kwargs: [
        {"update_id": 1, "message": {"chat": {"id": "1"}, "text": "/arm doge"}},
    ]
    runtime._handle_telegram_commands()
    assert any("⚠️ <b>Manual Arm</b>" in message for message in sent)
    assert any("No open position for DOGE_USDT." in message for message in sent)


def test_arm_is_advertised_in_help(tmp_path):
    runtime = _runtime(tmp_path)
    assert "/arm" in runtime._build_help_message()
    assert "/arm" in runtime._commands_hint()


def test_channel_agnostic_dispatcher_knows_arm():
    assert commands_module.parse_command_text("/arm zec") == ("arm", {"target": "ZEC"})
    assert "arm" in commands_module.MUTATING
    assert "arm" in commands_module.VERBS


def test_status_line_reflects_a_manual_arm(tmp_path):
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    position.metadata["convex_peak_r"] = 0.60
    before = runtime._trail_line(position)
    assert before is not None and "arms at" in before
    assert runtime._manual_arm("ZEC")[0] is True
    after = runtime._trail_line(position)
    assert after is not None and "ARMED" in after and "exits at" in after


# --- THE ONE THAT MATTERS: inert unless typed ------------------------------

def test_automatic_path_is_unchanged_when_the_command_is_never_used(tmp_path, monkeypatch):
    """If /arm is never typed, the bot's behaviour must be bit-identical."""
    runtime = _runtime(tmp_path, _Client(price=106.0))
    monkeypatch.setattr(runtime, "_close_position_for_exit", lambda p, **kw: True)
    monkeypatch.setattr(runtime, "_maybe_record_peak_notify", lambda *a, **k: None)
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position

    # The gate still blocks everything below the automatic arm.
    assert runtime._convex_runner_trail_exit(position, 106.0) is False   # peak +0.60R
    assert runtime._convex_runner_trail_exit(position, 100.5) is False   # gave it all back
    assert "manual_arm" not in position.metadata

    # And above the arm it behaves exactly as before.
    assert runtime._convex_runner_trail_exit(position, 120.0) is False   # peak +2.00R
    assert runtime._convex_runner_trail_exit(position, 112.0) is False   # +1.20R > 1.00R floor
    assert runtime._convex_runner_trail_exit(position, 105.0) is True    # +0.50R < 1.00R floor


def test_polling_other_commands_does_not_touch_position_metadata(tmp_path):
    runtime = _runtime(tmp_path, _Client(price=106.0))
    runtime._notify = lambda message, parse_mode="HTML": None
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    before = json.dumps(position.metadata, sort_keys=True, default=str)
    runtime.telegram.get_updates = lambda **kwargs: [
        {"update_id": 1, "message": {"chat": {"id": "1"}, "text": "/status"}},
        {"update_id": 2, "message": {"chat": {"id": "1"}, "text": "/help"}},
    ]
    runtime._handle_telegram_commands()
    assert json.dumps(position.metadata, sort_keys=True, default=str) == before


# --- operator-chosen giveback ----------------------------------------------

def test_giveback_sets_the_floor_and_the_trail_uses_it(tmp_path, monkeypatch):
    """The owner's spec: /arm IOST 0.20 arms at the value now and floors at 0.8x it."""
    runtime = _runtime(tmp_path, _Client(price=106.0))        # +0.60R, 1R = $10
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    ok, message = runtime._manual_arm("ZEC", "0.20")
    assert ok is True
    # 0.20 giveback -> keep 0.80 of a +0.60R peak = +0.48R, not the config's 0.30R.
    assert position.metadata["manual_arm_retain"] == pytest.approx(0.80)
    assert position.metadata["manual_arm_floor_r"] == pytest.approx(0.48)
    assert "+0.48R" in message and "80%" in message and "your giveback" in message

    # And the EXIT PATH honours it, not the 0.50 in the environment.
    closed = {}
    monkeypatch.setattr(runtime, "_close_position_for_exit",
                        lambda p, **kw: closed.update(reason=kw.get("reason")) or True)
    assert runtime._convex_runner_trail_exit(position, 105.0) is False   # +0.50R, above
    assert runtime._convex_runner_trail_exit(position, 104.0) is True    # +0.40R, below
    assert closed["reason"] == "CONVEX_RETENTION_TRAIL"


def test_giveback_can_tighten_an_already_armed_trade(tmp_path):
    """His second example, now meaningful: above the gate a custom giveback RAISES
    the floor from the automatic 50% to 80% of the same peak."""
    runtime = _runtime(tmp_path, _Client(price=120.0))        # +2.00R
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    ok, message = runtime._manual_arm("ZEC", "0.20")
    assert ok is True
    assert position.metadata["manual_arm_floor_r"] == pytest.approx(1.60)   # vs 1.00 auto
    assert "+1.60R" in message


def test_giveback_that_would_lower_the_floor_is_refused(tmp_path):
    """THE INVARIANT. Above the gate the floor is already 0.50 x peak; a 0.70
    giveback would put it at 0.30 x peak. That lowers a live floor, so it refuses."""
    runtime = _runtime(tmp_path, _Client(price=120.0))        # +2.00R, auto floor +1.00R
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    before = json.dumps(position.metadata, sort_keys=True, default=str)
    ok, message = runtime._manual_arm("ZEC", "0.70")          # would floor at +0.60R
    assert ok is False
    assert "less protected than not arming it at all" in message, message
    assert "0.50 or less" in message, message
    assert json.dumps(position.metadata, sort_keys=True, default=str) == before

    # And the exact-equality case: at a new high, 0.50 reproduces the live floor
    # exactly, so there is nothing to gain and the command says so.
    ok, message = runtime._manual_arm("ZEC", "0.50")
    assert ok is False
    assert "no better" in message, message
    assert json.dumps(position.metadata, sort_keys=True, default=str) == before


def test_already_armed_without_a_giveback_still_reports_and_refuses(tmp_path):
    runtime = _runtime(tmp_path, _Client(price=120.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    ok, message = runtime._manual_arm("ZEC")
    assert ok is False
    # At a new high the bare command cannot beat the live floor: same anchor, same
    # retention, same number. The message names both and suggests the giveback form.
    assert "no better" in message or "would change nothing" in message, message
    assert "+1.00R" in message


@pytest.mark.parametrize("text,expected", [
    ("0.20", 0.20), ("0.2", 0.20), ("20", 0.20), ("20%", 0.20),
    (" 25 % ", 0.25), ("0,20", 0.20), ("0.05", 0.05), ("5", 0.05), ("99", 0.99),
])
def test_giveback_forms_are_accepted(text, expected):
    value, error = FuturesRuntime._parse_giveback(text)
    assert error is None, error
    assert value == pytest.approx(expected)


@pytest.mark.parametrize("text", ["0", "0%", "1", "4", "4%", "0.04", "100", "100%",
                                  "-0.2", "abc", "1.5e400"])
def test_giveback_out_of_range_or_unreadable_is_rejected(text):
    value, error = FuturesRuntime._parse_giveback(text)
    assert value is None
    assert error


def test_bracketed_symbol_is_accepted(tmp_path):
    """The owner writes the placeholder as /arm [IOST]."""
    runtime = _runtime(tmp_path, _Client(price=106.0))
    runtime.open_positions["ZEC_USDT"] = _pos()
    ok, _ = runtime._manual_arm("[ZEC]", "0.20")
    assert ok is True


def test_bad_giveback_changes_nothing(tmp_path):
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    ok, message = runtime._manual_arm("ZEC", "banana")
    assert ok is False
    assert "Could not read a giveback" in message
    assert "manual_arm" not in position.metadata


def test_no_giveback_still_uses_the_configured_retention(tmp_path):
    """Regression: the bare command must behave exactly as it did before."""
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    ok, message = runtime._manual_arm("ZEC")
    assert ok is True
    assert "manual_arm_retain" not in position.metadata
    assert position.metadata["manual_arm_floor_r"] == pytest.approx(0.30)
    assert "the automatic rule" in message


# --- the invariant below the gate ------------------------------------------

def test_a_looser_giveback_below_the_gate_is_refused(tmp_path):
    """THE BLOCKING DEFECT. The tighten-check used to sit inside `peak_r >= arm_r`,
    so below the gate - the only state /arm exists for - it never ran. A 0.70
    giveback stamped retain 0.30 PERMANENTLY, governing the trade even after the
    peak crossed 1.0R where the configured 0.50 would have taken over. Typing the
    command left the trade LESS protected than not typing it."""
    runtime = _runtime(tmp_path, _Client(price=106.0))     # +0.60R, below the 1.0R gate
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    before = json.dumps(position.metadata, sort_keys=True, default=str)
    ok, message = runtime._manual_arm("ZEC", "0.70")       # retain 0.30 < configured 0.50
    assert ok is False
    assert "less protected than not arming it at all" in message, message
    assert "0.50 or less" in message
    assert json.dumps(position.metadata, sort_keys=True, default=str) == before


def test_the_configured_giveback_below_the_gate_is_allowed(tmp_path):
    """Exactly the configured retention is the bare command's own behaviour, so it
    must be accepted - the refusal is for LOOSER, not for equal."""
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    ok, _ = runtime._manual_arm("ZEC", "0.50")
    assert ok is True
    assert position.metadata["manual_arm_floor_r"] == pytest.approx(0.30)


def test_armed_position_never_ends_up_looser_than_the_control(tmp_path, monkeypatch):
    """The end-to-end property the defect broke: for every accepted giveback, the
    armed position must exit at or above where an unarmed one would."""
    for giveback in ("0.05", "0.20", "0.35", "0.50"):
        armed_rt = _runtime(tmp_path, _Client(price=106.0))
        armed = _pos()
        armed_rt.open_positions["ZEC_USDT"] = armed
        assert armed_rt._manual_arm("ZEC", giveback)[0] is True
        control_rt = _runtime(tmp_path, _Client(price=106.0))
        control = _pos()
        control_rt.open_positions["ZEC_USDT"] = control
        for rt, pos in ((armed_rt, armed), (control_rt, control)):
            monkeypatch.setattr(rt, "_close_position_for_exit", lambda p, **kw: True)
            rt._convex_runner_trail_exit(pos, 129.0)        # run both to a +2.90R peak
        # Walk down together; the armed one must never survive past the control.
        for price in (125.0, 120.0, 115.0, 112.0, 110.0, 108.0, 106.0, 103.0, 101.0):
            a = armed_rt._convex_runner_trail_exit(armed, price)
            c = control_rt._convex_runner_trail_exit(control, price)
            assert not (c and not a), (
                f"giveback {giveback}: control exited at {price} and the armed "
                "position did not - /arm made it looser than doing nothing")
            if a or c:
                break


def test_status_line_shows_the_operator_floor_not_the_configured_one(tmp_path):
    """/status is the surface actually read at 3am. It used to print the CONFIGURED
    floor for a position governed by a different one."""
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    assert runtime._manual_arm("ZEC", "0.20")[0] is True    # floor +0.48R = $4.80
    line = runtime._trail_line(position)
    assert line is not None
    assert "4.80" in line, line
    assert "3.00" not in line, line                         # the configured-0.50 floor


def test_close_record_carries_the_operator_giveback(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, _Client(price=106.0))
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    assert runtime._manual_arm("ZEC", "0.20")[0] is True
    monkeypatch.setattr(runtime, "_notify", lambda *a, **k: None)
    runtime._close_history_trade(position, exit_price=104.8, reason="CONVEX_RETENTION_TRAIL")
    trade = runtime.trade_history[-1]
    assert trade["manual_arm_retain"] == pytest.approx(0.80)
    assert trade["manual_arm_giveback"] == pytest.approx(0.20)


def test_owner_scenario_peak_34_now_23_floors_at_18_40(tmp_path):
    """His exact scenario. 1R = $20. Peak was +$34 (1.70R), price is back at +$23
    (1.15R), the automatic trail already holds +$17. /arm ZEC 0.20 must floor at
    0.80 x $23 = $18.40 - derived from where the trade IS, not from a $34 peak it
    may never revisit - and then ratchet upward on any new high."""
    pos = FuturesPosition(
        symbol="ZEC_USDT", side="LONG", entry_price=100.0, contracts=2,
        contract_size=1.0, leverage=10, margin_usdt=20.0, tp_price=150.0, sl_price=90.0,
        position_id="1", order_id="1",
        opened_at=datetime.now(timezone.utc) - timedelta(hours=2),
        score=96.0, certainty=0.9, entry_signal="WILDCARD_LONG",
        metadata={"wildcard": 1.0, "sl_margin_pct": 100.0, "convex_peak_r": 1.70})
    runtime = _runtime(tmp_path, _Client(price=111.5))       # +1.15R = +$23
    runtime.open_positions["ZEC_USDT"] = pos
    one_r = runtime._position_stop_risk_usdt(pos)
    assert one_r == pytest.approx(20.0)

    ok, message = runtime._manual_arm("ZEC", "0.20")
    assert ok is True, message
    assert pos.metadata["manual_arm_floor_r"] * one_r == pytest.approx(18.40, abs=0.01)
    assert "+18.40" in message
    # Anchored on the current value; the true peak is kept only as telemetry.
    assert pos.metadata["manual_arm_peak_r"] == pytest.approx(1.15)
    assert pos.metadata["manual_arm_true_peak_r"] == pytest.approx(1.70)
    # Strictly better than the $17.00 the automatic rule was holding.
    assert pos.metadata["manual_arm_floor_r"] * one_r > 0.50 * 1.70 * one_r

    # It ratchets on the SAME poll that records a new high, not one cycle later.
    runtime._convex_runner_trail_exit(pos, 120.0)            # +2.00R = +$40
    assert pos.metadata["manual_arm_peak_r"] == pytest.approx(2.00)
    assert 0.80 * pos.metadata["manual_arm_peak_r"] * one_r == pytest.approx(32.00)


def test_the_anchor_never_falls_when_price_does(tmp_path):
    pos = _pos(metadata={"wildcard": 1.0, "sl_margin_pct": 100.0, "convex_peak_r": 0.80})
    runtime = _runtime(tmp_path, _Client(price=106.0))       # +0.60R
    runtime.open_positions["ZEC_USDT"] = pos
    assert runtime._manual_arm("ZEC", "0.20")[0] is True
    assert pos.metadata["manual_arm_peak_r"] == pytest.approx(0.60)
    for price in (105.0, 104.0, 103.0, 101.0, 100.5):
        runtime._convex_runner_trail_exit(pos, price)
        assert pos.metadata["manual_arm_peak_r"] >= 0.60 - 1e-9
