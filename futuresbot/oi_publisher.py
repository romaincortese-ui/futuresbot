"""Open-interest timeseries publisher — shadow study for the OI-vs-price signal.

Records (timestamp, open_interest, price) snapshots per symbol to a Redis
sorted set (`oi_ts:{symbol}`, score = epoch-ms) so a later lift study can ask,
for each closed trade, whether OI was rising at entry. OBSERVATION-ONLY:
best-effort, swallows every error, and is never read by the trading path — it
cannot affect entries, sizing, or risk. Mirrors funding_publisher's no-dep,
no-op-without-Redis design.
"""
from __future__ import annotations

import json
import logging
from typing import Sequence

log = logging.getLogger(__name__)

OI_TS_KEY_PREFIX = "oi_ts:"
DEFAULT_MAX_AGE_SECONDS = 7 * 86400  # retain ~7 days for the OI lift study


def _client(redis_url: str):
    if not redis_url:
        return None
    try:
        import redis  # type: ignore
    except ImportError:
        log.debug("OI publisher: redis package not installed; skipped")
        return None
    try:
        return redis.Redis.from_url(redis_url, socket_timeout=2.0, socket_connect_timeout=2.0)
    except Exception as exc:  # pragma: no cover — defensive
        log.debug("OI publisher: client construction failed: %s", exc)
        return None


def record_oi_snapshots(
    redis_url: str,
    snapshots: Sequence[tuple[str, int, float, float]],
    *,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    client=None,
) -> int:
    """Append (symbol, ts_ms, oi, price) snapshots; trim entries older than
    max_age. Returns the count written. Best-effort — never raises."""
    if not snapshots:
        return 0
    client = client or _client(redis_url)
    if client is None:
        return 0
    newest = max(int(s[1]) for s in snapshots)
    cutoff = newest - max_age_seconds * 1000
    written = 0
    for symbol, ts_ms, oi, price in snapshots:
        key = OI_TS_KEY_PREFIX + symbol
        member = json.dumps({"t": int(ts_ms), "oi": float(oi), "p": float(price)}, separators=(",", ":"))
        try:
            client.zadd(key, {member: int(ts_ms)})
            client.zremrangebyscore(key, 0, cutoff)
            written += 1
        except Exception as exc:  # pragma: no cover — defensive
            log.debug("OI publisher: zadd %s failed: %s", key, exc)
    return written


def read_oi_series(
    redis_url: str,
    symbol: str,
    since_ms: int,
    until_ms: int,
    *,
    client=None,
) -> list[dict]:
    """Read OI snapshots for a symbol in [since_ms, until_ms] (for the lift
    analyzer). Returns a time-sorted list of {t, oi, p}. Best-effort."""
    client = client or _client(redis_url)
    if client is None:
        return []
    try:
        raw = client.zrangebyscore(OI_TS_KEY_PREFIX + symbol, since_ms, until_ms)
    except Exception as exc:  # pragma: no cover — defensive
        log.debug("OI publisher: zrangebyscore failed: %s", exc)
        return []
    out = []
    for m in raw:
        try:
            out.append(json.loads(m))
        except (TypeError, ValueError):
            continue
    return sorted(out, key=lambda d: d.get("t", 0))
