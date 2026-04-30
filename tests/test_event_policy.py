from datetime import datetime, timedelta, timezone

from futuresbot.event_policy import evaluate_event_policy


BASE = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)


def test_event_policy_fails_open_when_state_is_missing():
    decision = evaluate_event_policy(symbol="BTC_USDT", side="LONG", state=None, now=BASE)

    assert decision.block_entry is False
    assert decision.size_multiplier == 1.0
    assert decision.leverage_multiplier == 1.0
    assert decision.reasons == ()


def test_event_policy_dampens_market_risk_for_longs():
    state = {
        "generated_at": BASE.isoformat(),
        "ttl_seconds": 1800,
        "market_risk_score": 0.70,
    }

    decision = evaluate_event_policy(symbol="BTC_USDT", side="LONG", state=state, now=BASE)

    assert decision.block_entry is False
    assert decision.size_multiplier == 0.65
    assert decision.leverage_multiplier == 0.70
    assert "crypto_event_risk:0.70" in decision.reasons


def test_event_policy_blocks_extreme_risk_windows():
    state = {
        "generated_at": BASE.isoformat(),
        "ttl_seconds": 1800,
        "events": [
            {"scope": "market", "direction": "risk_off", "severity": 0.95, "reason": "exchange_halt"}
        ],
    }

    decision = evaluate_event_policy(symbol="ETH_USDT", side="SHORT", state=state, now=BASE)

    assert decision.block_entry is True
    assert decision.size_multiplier == 0.40
    assert decision.leverage_multiplier == 0.50
    assert "exchange_halt" in decision.reasons


def test_event_policy_fails_open_when_stale():
    state = {
        "generated_at": (BASE - timedelta(hours=2)).isoformat(),
        "ttl_seconds": 1800,
        "market_risk_score": 0.95,
    }

    decision = evaluate_event_policy(symbol="BTC_USDT", side="LONG", state=state, now=BASE)

    assert decision.block_entry is False
    assert decision.size_multiplier == 1.0
    assert decision.reasons == ()
