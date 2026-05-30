from __future__ import annotations

import json
from datetime import datetime, timezone

from futuresbot.prophet_prediction_archive import archive_current_prophet_odds, build_prophet_prediction_state


def test_build_prophet_prediction_state_filters_directional_open_markets():
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    result = build_prophet_prediction_state(
        [
            {
                "id": "btc-1",
                "slug": "btc-above-79k-by-june-12",
                "title": "BTC Above $79K by June 12?",
                "question": "Will Bitcoin go above 79k by June 12?",
                "status": "OPEN",
                "yesPriceBps": 3977,
                "noPriceBps": 6135,
            },
            {
                "id": "eth-1",
                "slug": "eth-below-2000",
                "title": "Will Ethereum fall below $2,000 this month?",
                "status": "OPEN",
                "yesPriceBps": 2500,
            },
            {"id": "xrp-1", "title": "XRP above $1.30?", "status": "OPEN", "yesPriceBps": 4310},
            {"id": "btc-old", "title": "BTC Closes > $90K By May 22?", "status": "RESOLVED_NO", "yesPriceBps": 0},
        ],
        generated_at=now,
        symbols=["BTC_USDT", "ETH_USDT"],
        ttl_seconds=900,
    )

    assert result.raw_market_count == 4
    assert result.event_count == 2
    assert result.skipped["ambiguous_or_unsupported"] == 1
    assert result.skipped["non_open"] == 1
    btc_event = result.state["events"][0]
    eth_event = result.state["events"][1]
    assert btc_event["event_id"] == "prophet:btc-above-79k-by-june-12"
    assert btc_event["symbols"] == ["BTC_USDT"]
    assert btc_event["direction"] == "bullish"
    assert btc_event["primary_probability"] == 0.3977
    assert eth_event["symbols"] == ["ETH_USDT"]
    assert eth_event["direction"] == "bearish"


def test_archive_current_prophet_odds_writes_replay_and_latest_files(tmp_path, monkeypatch):
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    archive_path = tmp_path / "prophet.jsonl"
    latest_path = tmp_path / "latest.json"
    markets = [
        {
            "id": "btc-1",
            "slug": "btc-above-79k-by-june-12",
            "title": "BTC Above $79K by June 12?",
            "status": "OPEN",
            "yesPriceBps": 3977,
        }
    ]
    monkeypatch.setattr("futuresbot.prophet_prediction_archive.fetch_prophet_crypto_markets", lambda **kwargs: markets)

    result = archive_current_prophet_odds(
        archive_path=archive_path,
        latest_path=latest_path,
        symbols=["BTC_USDT"],
        generated_at=now,
    )

    assert result.event_count == 1
    replay_row = json.loads(archive_path.read_text(encoding="utf-8").strip())
    latest_state = json.loads(latest_path.read_text(encoding="utf-8"))
    assert replay_row["timestamp"] == now.isoformat()
    assert replay_row["state"]["events"][0]["source"] == "prophet"
    assert latest_state["generated_at"] == now.isoformat()