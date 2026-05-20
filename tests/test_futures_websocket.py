from __future__ import annotations

import gzip
import json
import time

from futuresbot.websocket import FuturesFairPriceMonitor


def test_fair_price_monitor_returns_fresh_prices(monkeypatch):
    monkeypatch.setenv("FUTURES_FAIR_PRICE_WS_STALE_SECONDS", "5")
    monitor = FuturesFairPriceMonitor()
    monitor.set_symbols({"btc_usdt"})
    monitor._prices["BTC_USDT"] = (100.5, time.time())

    assert monitor.get_price("BTC_USDT") == 100.5


def test_fair_price_monitor_rejects_stale_prices(monkeypatch):
    monkeypatch.setenv("FUTURES_FAIR_PRICE_WS_STALE_SECONDS", "1")
    monitor = FuturesFairPriceMonitor()
    monitor._prices["BTC_USDT"] = (100.5, time.time() - 10)

    assert monitor.get_price("BTC_USDT") is None


def test_decode_gzipped_futures_ws_payload():
    payload = {"channel": "push.fair.price", "data": {"symbol": "BTC_USDT", "price": 100.5}}
    raw = gzip.compress(json.dumps(payload).encode("utf-8"))

    assert FuturesFairPriceMonitor._decode_message(raw) == payload