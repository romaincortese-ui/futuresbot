from __future__ import annotations

from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient


def _client() -> MexcFuturesClient:
    return MexcFuturesClient(FuturesConfig.from_env())


def test_get_historical_positions_accepts_documented_list_payload(monkeypatch):
    client = _client()
    row = {"positionId": 1, "symbol": "BTC_USDT", "realised": 0.25}
    monkeypatch.setattr(client, "private_get", lambda path, params: {"success": True, "data": [row]})

    assert client.get_historical_positions("BTC_USDT") == [row]


def test_get_historical_positions_accepts_paginated_result_list(monkeypatch):
    client = _client()
    row = {"positionId": 2, "symbol": "ETH_USDT", "realised": -0.1}
    monkeypatch.setattr(
        client,
        "private_get",
        lambda path, params: {"success": True, "data": {"resultList": [row]}},
    )

    assert client.get_historical_positions("ETH_USDT") == [row]
