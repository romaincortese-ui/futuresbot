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


def test_arm_uses_the_running_peak_not_the_current_r(tmp_path):
    """Armed at +0.6R after a +0.8R peak: the floor is off the PEAK, exactly as
    the automatic rule would compute it, and it still sits below the current level."""
    runtime = _runtime(tmp_path, _Client(price=106.0))   # +0.60R
    position = _pos(metadata={"wildcard": 1.0, "sl_margin_pct": 100.0, "convex_peak_r": 0.80})
    ok, message = _armed(runtime, position)
    assert ok is True
    assert position.metadata["manual_arm_peak_r"] == pytest.approx(0.80)
    assert position.metadata["manual_arm_floor_r"] == pytest.approx(0.40)
    assert "+0.40R" in message


def test_refusal_10_retraced_past_the_floor_would_close_immediately(tmp_path):
    """THE DEFECT THIS GUARD EXISTS FOR. Peak +0.80R puts the floor at +0.40R, but
    price has already fallen back to +0.20R. The old check only compared the floor
    to the PEAK, so this armed successfully and the next one-second poll closed the
    trade - /arm banking a giveback it was written to prevent."""
    runtime = _runtime(tmp_path, _Client(price=102.0))   # +0.20R, below the 0.40R floor
    position = _pos(metadata={"wildcard": 1.0, "sl_margin_pct": 100.0, "convex_peak_r": 0.80})
    runtime.open_positions["ZEC_USDT"] = position
    _refuses(runtime, position, "ZEC", "already given back past that floor")
    assert "manual_arm" not in position.metadata


def test_refusal_10_boundary_floor_equal_to_current_is_refused(tmp_path):
    """At r_now == exit_level the exit path closes (it holds only while
    r_now > exit_level), so the boundary must refuse, not arm."""
    runtime = _runtime(tmp_path, _Client(price=104.0))   # +0.40R == the 0.40R floor
    position = _pos(metadata={"wildcard": 1.0, "sl_margin_pct": 100.0, "convex_peak_r": 0.80})
    runtime.open_positions["ZEC_USDT"] = position
    _refuses(runtime, position, "ZEC", "already given back past that floor")


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
    """The owner's SECOND example. The floor already tracks the running peak, so
    /arm would change nothing — say so with the real numbers instead of acting."""
    runtime = _runtime(tmp_path, _Client(price=123.0))      # +2.30R
    position = _pos()
    runtime.open_positions["ZEC_USDT"] = position
    _refuses(runtime, position, "ZEC", "is already armed: peak +2.30R")
    ok, message = runtime._manual_arm("ZEC")
    assert "floor +1.15R" in message and "keeps 50%" in message


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
