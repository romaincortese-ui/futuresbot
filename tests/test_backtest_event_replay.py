from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from futuresbot.backtest import FuturesBacktestEngine, _crypto_event_margin_multiplier
from futuresbot.models import FuturesSignal


def _engine(config: SimpleNamespace) -> FuturesBacktestEngine:
    engine = FuturesBacktestEngine.__new__(FuturesBacktestEngine)
    engine.config = config
    engine._crypto_event_replay_loaded = False
    engine._crypto_event_replay_payload = None
    return engine


def _config(**overrides) -> SimpleNamespace:
    defaults = {
        "crypto_event_overlay_enabled": True,
        "crypto_event_state_file": "",
        "crypto_event_stale_seconds": 1800,
        "crypto_event_min_abs_bias": 0.35,
        "crypto_event_threshold_relief": 4.0,
        "crypto_event_score_boost": 5.0,
        "crypto_event_adverse_score_penalty": 4.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_backtest_replays_timeline_event_state(tmp_path):
    event_file = tmp_path / "events.json"
    event_file.write_text(
        json.dumps(
            {
                "timeline": [
                    {
                        "from": "2026-05-17T10:00:00Z",
                        "until": "2026-05-17T11:00:00Z",
                        "state": {"ttl_seconds": 3600, "market_risk_score": 0.70},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    engine = _engine(_config(crypto_event_state_file=str(event_file)))

    state = engine._crypto_event_state_for(datetime(2026, 5, 17, 10, 15, tzinfo=timezone.utc))

    assert state is not None
    assert state["market_risk_score"] == 0.70
    assert state["generated_at"] == "2026-05-17T10:00:00+00:00"


def test_backtest_crypto_event_policy_reduces_leverage_and_margin():
    engine = _engine(_config())
    now = datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc)
    signal = FuturesSignal(
        symbol="BTC_USDT",
        side="LONG",
        score=90.0,
        certainty=0.9,
        entry_price=90000.0,
        tp_price=93000.0,
        sl_price=88500.0,
        leverage=10,
        entry_signal="BREAKOUT_HOLD_LONG",
        metadata={},
    )
    state = {
        "generated_at": now.isoformat(),
        "ttl_seconds": 1800,
        "market_risk_score": 0.70,
    }

    adjusted = engine._apply_crypto_event_overlay(signal, state, now)

    assert adjusted is not None
    assert adjusted.leverage == 7
    assert adjusted.metadata["crypto_event_size_multiplier"] == 0.65
    assert _crypto_event_margin_multiplier(adjusted.metadata) == 0.65
