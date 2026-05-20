from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import threading
import time

log = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


WS_URL = os.environ.get("FUTURES_FAIR_PRICE_WS_URL", "wss://contract.mexc.com/edge")
WS_PING_SECS = 20


class FuturesFairPriceMonitor:
    def __init__(self) -> None:
        self._prices: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._wanted: set[str] = set()
        self._wanted_lock = threading.Lock()
        self._running = False

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="futures-fair-price-ws")
        self._thread.start()
        log.info("Futures fair-price WebSocket monitor starting")

    def stop(self) -> None:
        self._running = False

    def set_symbols(self, symbols: set[str]) -> None:
        with self._wanted_lock:
            self._wanted = {str(symbol).upper() for symbol in symbols if str(symbol or "").strip()}

    def get_price(self, symbol: str) -> float | None:
        with self._lock:
            entry = self._prices.get(str(symbol or "").upper())
        if entry is None:
            return None
        price, updated_at = entry
        stale_seconds = max(1.0, _env_float("FUTURES_FAIR_PRICE_WS_STALE_SECONDS", 5.0))
        if time.time() - updated_at > stale_seconds:
            return None
        return price

    @staticmethod
    def _is_clean_close(exc: Exception) -> bool:
        return type(exc).__name__ == "ConnectionClosedOK"

    @classmethod
    def _reconnect_delay(cls, exc: Exception, backoff: int) -> int:
        return 2 if cls._is_clean_close(exc) else backoff

    @classmethod
    def _next_backoff(cls, exc: Exception, backoff: int) -> int:
        return 2 if cls._is_clean_close(exc) else min(backoff * 2, 60)

    @classmethod
    def _log_reconnect(cls, exc: Exception, delay: int) -> None:
        if cls._is_clean_close(exc):
            log.debug("Futures fair-price WS closed cleanly (%s: %s); reconnect in %ss", type(exc).__name__, exc, delay)
            return
        log.warning("Futures fair-price WS error (%s: %s); reconnect in %ss", type(exc).__name__, exc, delay)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._ws_loop())
        except Exception as exc:
            log.error("Futures fair-price WS monitor thread crashed: %s", exc)
        finally:
            loop.close()

    async def _ws_loop(self) -> None:
        try:
            import websockets  # type: ignore[import-untyped]
        except ImportError:
            log.error("'websockets' library not installed; futures fair-price WS monitor disabled")
            return

        backoff = 2
        while self._running:
            with self._wanted_lock:
                wanted = set(self._wanted)
            if not wanted:
                await asyncio.sleep(2)
                continue
            try:
                async with websockets.connect(WS_URL, ping_interval=None, close_timeout=5, open_timeout=10) as ws:
                    log.debug("Futures fair-price WS connected")
                    backoff = 2
                    subscribed: set[str] = set()
                    last_ping = time.time()
                    while self._running:
                        with self._wanted_lock:
                            wanted = set(self._wanted)
                        new_subs = wanted - subscribed
                        for symbol in sorted(new_subs):
                            await ws.send(json.dumps({"method": "sub.fair.price", "param": {"symbol": symbol}, "gzip": False}))
                        if new_subs:
                            subscribed |= new_subs
                            log.info("Futures fair-price WS subscribed: %s", sorted(new_subs))
                        old_subs = subscribed - wanted
                        for symbol in sorted(old_subs):
                            await ws.send(json.dumps({"method": "unsub.fair.price", "param": {"symbol": symbol}}))
                        if old_subs:
                            subscribed -= old_subs
                            log.debug("Futures fair-price WS unsubscribed: %s", sorted(old_subs))
                        if time.time() - last_ping >= WS_PING_SECS:
                            await ws.send(json.dumps({"method": "ping"}))
                            last_ping = time.time()
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        except asyncio.TimeoutError:
                            continue
                        msg = self._decode_message(raw)
                        if not msg or msg.get("channel") == "pong":
                            continue
                        data = msg.get("data") if isinstance(msg.get("data"), dict) else {}
                        symbol = str(msg.get("symbol") or data.get("symbol") or "").upper()
                        price_raw = data.get("price") or data.get("fairPrice")
                        try:
                            price = float(price_raw)
                        except (TypeError, ValueError):
                            continue
                        if symbol and price > 0:
                            with self._lock:
                                self._prices[symbol] = (price, time.time())
            except Exception as exc:
                if not self._running:
                    break
                delay = self._reconnect_delay(exc, backoff)
                self._log_reconnect(exc, delay)
                await asyncio.sleep(delay)
                backoff = self._next_backoff(exc, backoff)

    @staticmethod
    def _decode_message(raw: str | bytes) -> dict[str, object] | None:
        if isinstance(raw, bytes):
            try:
                raw = gzip.decompress(raw).decode("utf-8")
            except Exception:
                try:
                    raw = raw.decode("utf-8")
                except Exception:
                    return None
        try:
            payload = json.loads(raw)
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None