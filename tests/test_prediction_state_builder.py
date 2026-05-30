from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from futuresbot.prediction_overlay import select_point_in_time_prediction_state
from tools.build_prediction_state_file import PredictionStateBuildError, build_prediction_state_file


def test_builder_converts_csv_rows_to_point_in_time_timeline(tmp_path):
    source = tmp_path / "prediction_rows.csv"
    source.write_text(
        "timestamp,event_id,source,symbol,direction,probability,title\n"
        "2026-05-30T10:00:00Z,btc-flow,prophet,BTCUSDT,bullish,72%,BTC risk-on flow\n"
        "2026-05-30T10:15:00Z,btc-flow,prophet,BTC_USDT,bullish,0.68,BTC risk-on flow\n"
        "2026-05-30T10:30:00Z,eth-flow,prophet,ETH_USDT,bearish,64,ETH risk-off flow\n",
        encoding="utf-8",
    )

    payload = build_prediction_state_file([source], ttl_seconds=900, symbols=["BTC_USDT"])

    assert payload["metadata"]["snapshot_count"] == 2
    assert payload["metadata"]["event_count"] == 2
    first_event = payload["timeline"][0]["state"]["events"][0]
    assert first_event["symbols"] == ["BTC_USDT"]
    assert first_event["probability"] == 0.72

    state = select_point_in_time_prediction_state(payload, datetime(2026, 5, 30, 10, 20, tzinfo=timezone.utc))

    assert state is not None
    assert state["generated_at"] == "2026-05-30T10:15:00+00:00"
    assert state["events"][0]["probability"] == 0.68


def test_builder_accepts_jsonl_snapshots(tmp_path):
    source = tmp_path / "prediction_snapshots.jsonl"
    rows = [
        {
            "generated_at": "2026-05-30T10:00:00Z",
            "events": [
                {
                    "event_id": "btc-flow",
                    "source": "prophet",
                    "symbols": ["BTC_USDT"],
                    "direction": "bullish",
                    "probability": 0.71,
                }
            ],
        },
        {
            "generated_at": "2026-05-30T10:15:00Z",
            "events": [
                {
                    "event_id": "btc-flow",
                    "source": "polymarket",
                    "symbols": ["BTC_USDT"],
                    "direction": "bullish",
                    "yes_price": 0.69,
                }
            ],
        },
    ]
    source.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    payload = build_prediction_state_file([source], ttl_seconds=900)

    assert payload["metadata"]["snapshot_count"] == 2
    assert payload["timeline"][1]["state"]["events"][0]["yes_price"] == 0.69


def test_builder_rejects_outcome_columns_by_default(tmp_path):
    source = tmp_path / "leaky_rows.csv"
    source.write_text(
        "timestamp,event_id,source,symbol,direction,probability,outcome\n"
        "2026-05-30T10:00:00Z,btc-flow,prophet,BTC_USDT,bullish,0.72,win\n",
        encoding="utf-8",
    )

    with pytest.raises(PredictionStateBuildError, match="future information"):
        build_prediction_state_file([source])
