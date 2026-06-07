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


def test_place_position_tpsl_uses_stop_loss_direction_for_long_profit_lock(monkeypatch):
    client = _client()
    captured: dict[str, object] = {}

    def fake_post(path, body):
        captured.update(body)
        return {"success": True, "data": {"orderId": "stop-1"}}

    monkeypatch.setattr(client, "private_post", fake_post)

    client.place_position_tpsl(
        position_id="12345",
        vol=3,
        take_profit_price=None,
        stop_loss_price=100.26,
        side="LONG",
    )

    assert captured["takeProfitPrice"] is None
    assert captured["stopLossPrice"] == 100.26
    assert captured["profitTrend"] is None
    assert captured["lossTrend"] == 2


def test_close_position_includes_position_id_and_omits_open_leverage(monkeypatch):
    client = _client()
    captured: dict[str, object] = {}

    def fake_post(path, body):
        captured.update(body)
        return {"success": True, "data": {"orderId": "close-1"}}

    monkeypatch.setattr(client, "private_post", fake_post)

    client.close_position(
        symbol="BNB_USDT",
        side=4,
        vol=3,
        leverage=5,
        position_mode=2,
        position_id="12345",
    )

    assert captured["positionId"] == 12345
    assert captured["leverage"] is None
    assert captured["reduceOnly"] is True


def test_close_position_omits_reduce_only_for_dual_side_mode(monkeypatch):
    client = _client()
    captured: dict[str, object] = {}

    def fake_post(path, body):
        captured.update(body)
        return {"success": True, "data": {"orderId": "close-1"}}

    monkeypatch.setattr(client, "private_post", fake_post)

    client.close_position(symbol="BNB_USDT", side=4, vol=3, leverage=5, position_mode=1, position_id="12345")

    assert captured["positionMode"] == 1
    assert captured["reduceOnly"] is None


def test_get_all_tickers_normalizes_list_payload(monkeypatch):
    client = _client()
    rows = [{"symbol": "BTC_USDT"}, {"symbol": "ETH_USDT"}]
    monkeypatch.setattr(client, "public_get", lambda path, params=None: {"success": True, "data": rows})

    assert client.get_all_tickers() == rows


def test_get_all_contract_details_normalizes_single_dict_payload(monkeypatch):
    client = _client()
    row = {"symbol": "BTC_USDT"}
    monkeypatch.setattr(client, "public_get", lambda path, params=None: {"success": True, "data": row})

    assert client.get_all_contract_details() == [row]
