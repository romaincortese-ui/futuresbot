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


def test_place_order_normalizes_primitive_order_id(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "private_post", lambda path, body: {"success": True, "data": 123456})

    order = client.place_order(symbol="BTC_USDT", side=1, vol=1, leverage=5)

    assert order == {"orderId": "123456"}


def test_place_order_sets_long_trigger_directions(monkeypatch):
    client = _client()
    captured: dict[str, object] = {}

    def fake_post(path, body):
        captured.update(body)
        return {"success": True, "data": 123456}

    monkeypatch.setattr(client, "private_post", fake_post)

    client.place_order(
        symbol="BTC_USDT",
        side=1,
        vol=1,
        leverage=20,
        take_profit_price=105.0,
        stop_loss_price=98.0,
    )

    assert captured["profitTrend"] == 1
    assert captured["lossTrend"] == 2


def test_place_order_sets_short_trigger_directions(monkeypatch):
    client = _client()
    captured: dict[str, object] = {}

    def fake_post(path, body):
        captured.update(body)
        return {"success": True, "data": 123456}

    monkeypatch.setattr(client, "private_post", fake_post)

    client.place_order(
        symbol="BTC_USDT",
        side=3,
        vol=1,
        leverage=20,
        take_profit_price=95.0,
        stop_loss_price=102.0,
    )

    assert captured["profitTrend"] == 2
    assert captured["lossTrend"] == 1
