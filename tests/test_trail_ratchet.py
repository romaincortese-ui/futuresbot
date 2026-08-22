"""The conditional trail ratchet: tighten only once a trade is EXCEPTIONAL.

The flat 0.30 retention floor is right while a runner is still growing and wrong
once it has already made its money. From a 3R peak only 13.2% of trades exit
within 20% of their high and 40.4% hand the whole run back to the floor, while
the mean peak at that point is 5.95R against a 5R target (208 days, 1380
candidates, tools/peak_fate_ab.py).

A BLANKET higher retention was tested first and lost -$4.09 over 188 days,
because it also tightened trades peaking 1-2R and taxed winners during the phase
that pays for everything. Conditioning on the peak is what makes it work.

These pin the behaviour, the ratchet-only invariant, and the two ways it must
stay inert: below the trigger, and when disabled.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from futuresbot.config import FuturesConfig
from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("FUTURES_CONVEX_TRAIL_RATCHET_R", "FUTURES_CONVEX_TRAIL_RATCHET_RETAIN",
              "FUTURES_CONVEX_TRAIL_RETAIN_FRAC", "FUTURES_CONVEX_RUNNER_TRAIL",
              "FUTURES_WILDCARD_CONVEX_EXIT_ENABLED"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def rt(tmp_path, monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "rt.json"),
                  status_file=str(tmp_path / "st.json"),
                  telegram_token="", telegram_chat_id="")
    r = object.__new__(FuturesRuntime)
    r.config = cfg
    return r


def _pos(entry=100.0, sl=90.0):
    """leverage 2, sl_margin_pct 20 -> price +10% == +1R."""
    return FuturesPosition(
        symbol="FOO_USDT", side="LONG", entry_price=entry, contracts=100,
        contract_size=1.0, leverage=2, margin_usdt=50.0,
        tp_price=entry * 1.5, sl_price=sl, position_id="1", order_id="1",
        opened_at=datetime.now(timezone.utc) - timedelta(hours=1),
        score=96.0, certainty=0.9, entry_signal="WILDCARD_LONG",
        metadata={"wildcard": 1.0, "sl_margin_pct": 20.0},
    )


# --- the fraction itself ---------------------------------------------------

def test_base_retention_below_the_trigger(rt):
    assert rt._trail_retain_for(1.0, 0.30) == pytest.approx(0.30)
    assert rt._trail_retain_for(2.99, 0.30) == pytest.approx(0.30)


def test_ratchets_at_and_above_the_trigger(rt):
    assert rt._trail_retain_for(3.0, 0.30) == pytest.approx(0.75)
    assert rt._trail_retain_for(9.0, 0.30) == pytest.approx(0.75)


def test_thresholds_are_configurable(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_CONVEX_TRAIL_RATCHET_R", "2.5")
    monkeypatch.setenv("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", "0.60")
    assert rt._trail_retain_for(2.49, 0.30) == pytest.approx(0.30)
    assert rt._trail_retain_for(2.5, 0.30) == pytest.approx(0.60)


def test_disabled_by_zero_trigger(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_CONVEX_TRAIL_RATCHET_R", "0")
    assert rt._trail_retain_for(9.0, 0.30) == pytest.approx(0.30)


def test_never_lowers_the_floor(rt, monkeypatch):
    """A ratchet that could reduce retention would break the design invariant
    that a built profit is never fully given back."""
    monkeypatch.setenv("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", "0.10")
    assert rt._trail_retain_for(9.0, 0.30) == pytest.approx(0.30)


def test_floor_is_monotonic_in_peak(rt):
    """floor = retain(peak) x peak. Both factors only rise, so the floor can
    never fall — including across the step at the trigger."""
    floors = [rt._trail_retain_for(p / 10.0, 0.30) * (p / 10.0) for p in range(10, 120)]
    assert all(b >= a - 1e-9 for a, b in zip(floors, floors[1:]))
    # and the step is a genuine jump up, not a dip
    assert rt._trail_retain_for(3.0, 0.30) * 3.0 > rt._trail_retain_for(2.99, 0.30) * 2.99


# --- the trail using it ----------------------------------------------------

def test_an_exceptional_trade_keeps_three_quarters_of_its_peak(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    seen = {}
    monkeypatch.setattr(rt, "_close_position_for_exit",
                        lambda p, **k: seen.update(reason=k.get("reason")) or True)
    monkeypatch.setattr(rt, "_save_state", lambda *a, **k: None)
    monkeypatch.setattr(rt, "_maybe_record_peak_notify", lambda *a, **k: None)
    p = _pos()
    # peak +3.5R -> ratcheted floor 0.75 x 3.5 = 2.625R -> price 126.25
    assert rt._convex_runner_trail_exit(p, 135.0) is False
    assert p.metadata["convex_peak_r"] == pytest.approx(3.5, abs=0.05)
    assert rt._convex_runner_trail_exit(p, 127.0) is False      # +2.7R, above floor
    assert rt._convex_runner_trail_exit(p, 125.0) is True       # +2.5R, below floor
    assert seen["reason"] == "CONVEX_RETENTION_TRAIL"


def test_the_same_trade_under_the_old_flat_rule_would_have_held(rt, monkeypatch):
    """The point of the change, stated as a test: at +2.5R off a 3.5R peak the
    flat 0.30 floor (1.05R) holds on and can still give everything back."""
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setenv("FUTURES_CONVEX_TRAIL_RATCHET_R", "0")     # ratchet off
    monkeypatch.setattr(rt, "_close_position_for_exit", lambda p, **k: True)
    monkeypatch.setattr(rt, "_save_state", lambda *a, **k: None)
    monkeypatch.setattr(rt, "_maybe_record_peak_notify", lambda *a, **k: None)
    p = _pos()
    assert rt._convex_runner_trail_exit(p, 135.0) is False
    assert rt._convex_runner_trail_exit(p, 125.0) is False        # still holding


def test_a_modest_winner_is_untouched(rt, monkeypatch):
    """Below the trigger nothing changes — this is what the blanket rule got
    wrong, and the reason it lost money."""
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setattr(rt, "_close_position_for_exit", lambda p, **k: True)
    monkeypatch.setattr(rt, "_save_state", lambda *a, **k: None)
    monkeypatch.setattr(rt, "_maybe_record_peak_notify", lambda *a, **k: None)
    p = _pos()
    assert rt._convex_runner_trail_exit(p, 120.0) is False        # peak +2.0R
    # flat floor 0.30 x 2.0 = 0.60R -> price 106. Above it, holds.
    assert rt._convex_runner_trail_exit(p, 110.0) is False        # +1.0R
    assert rt._convex_runner_trail_exit(p, 105.0) is True         # +0.5R < 0.60R
