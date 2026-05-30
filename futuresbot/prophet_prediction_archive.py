from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.request import Request, urlopen

from futuresbot.prediction_market_classifier import classify_prediction_market


PROPHET_GRAPHQL_URL = "https://app.prophetmarket.ai/api/graphql"
PROPHET_CRYPTO_MARKETS_QUERY = """
query ProphetCryptoMarkets($first: Int!, $after: String) {
  markets(input: { first: $first, after: $after, filter: { categorySlug: "crypto" }, sort: VOLUME_DESC }) {
    edges {
      node {
        id
        slug
        title
        question
        resolutionDate
        status
        yesPriceBps
        noPriceBps
        volumeCents
        category { slug name }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()


class ProphetArchiveError(RuntimeError):
    pass


@dataclass(slots=True)
class ProphetArchiveResult:
    state: dict[str, Any]
    raw_market_count: int
    event_count: int
    skipped: dict[str, int]
    archive_path: str = ""
    latest_path: str = ""
    published_redis: bool = False


def fetch_prophet_crypto_markets(
    *,
    endpoint: str = PROPHET_GRAPHQL_URL,
    page_size: int = 50,
    max_pages: int = 2,
    timeout_seconds: float = 10.0,
) -> list[dict[str, Any]]:
    markets: list[dict[str, Any]] = []
    after: str | None = None
    for _page in range(max(1, int(max_pages))):
        payload = _graphql_post(
            endpoint,
            PROPHET_CRYPTO_MARKETS_QUERY,
            {"first": max(1, min(100, int(page_size))), "after": after},
            timeout_seconds=timeout_seconds,
        )
        connection = payload.get("data", {}).get("markets") if isinstance(payload, Mapping) else None
        nodes = _extract_market_nodes(connection)
        if not nodes:
            break
        markets.extend(nodes)
        page_info = connection.get("pageInfo") if isinstance(connection, Mapping) else {}
        if not isinstance(page_info, Mapping) or not page_info.get("hasNextPage"):
            break
        after = str(page_info.get("endCursor") or "") or None
        if after is None:
            break
    return markets


def build_prophet_prediction_state(
    markets: Iterable[Mapping[str, Any]],
    *,
    generated_at: datetime | None = None,
    symbols: Iterable[str] = (),
    ttl_seconds: int = 900,
    include_resolved: bool = False,
) -> ProphetArchiveResult:
    observed_at = _normalise_datetime(generated_at or datetime.now(timezone.utc))
    allowed_symbols = tuple(symbol.upper() for symbol in symbols if symbol)
    skipped = {"ambiguous_or_unsupported": 0, "missing_probability": 0, "non_open": 0}
    raw_market_count = 0
    events: list[dict[str, Any]] = []

    for market in markets:
        raw_market_count += 1
        status = str(market.get("status") or "").strip().upper()
        if status and status != "OPEN" and not include_resolved:
            skipped["non_open"] += 1
            continue
        text = " ".join(str(market.get(key) or "") for key in ("title", "question", "slug")).strip()
        classified = classify_prediction_market(text, allowed_symbols)
        if classified is None:
            skipped["ambiguous_or_unsupported"] += 1
            continue
        probability = _probability_from_bps(market.get("yesPriceBps") or market.get("yes_price_bps"))
        if probability is None:
            skipped["missing_probability"] += 1
            continue
        symbol, direction = classified
        slug = str(market.get("slug") or "").strip()
        market_id = str(market.get("id") or slug or text).strip()
        event_id = f"prophet:{slug or market_id}"
        event = {
            "event_id": event_id,
            "title": str(market.get("title") or market.get("question") or slug or market_id).strip(),
            "question": str(market.get("question") or market.get("title") or "").strip(),
            "source": "prophet",
            "provider": "prophet",
            "symbols": [symbol],
            "direction": direction,
            "probability": round(probability, 6),
            "primary_probability": round(probability, 6),
            "observed_at": observed_at.isoformat(),
            "status": status or "UNKNOWN",
        }
        resolution_date = str(market.get("resolutionDate") or market.get("resolution_date") or "").strip()
        if resolution_date:
            event["resolution_date"] = resolution_date
        yes_bps = _int_or_none(market.get("yesPriceBps") or market.get("yes_price_bps"))
        no_bps = _int_or_none(market.get("noPriceBps") or market.get("no_price_bps"))
        if yes_bps is not None:
            event["yes_price_bps"] = yes_bps
        if no_bps is not None:
            event["no_price_bps"] = no_bps
        events.append(event)

    state = {
        "generated_at": observed_at.isoformat(),
        "ttl_seconds": max(1, int(ttl_seconds)),
        "events": events,
        "metadata": {
            "source": "prophet_market_current_odds",
            "raw_market_count": raw_market_count,
            "event_count": len(events),
            "skipped": skipped,
            "point_in_time_required": True,
        },
    }
    return ProphetArchiveResult(state=state, raw_market_count=raw_market_count, event_count=len(events), skipped=skipped)


def archive_current_prophet_odds(
    *,
    archive_path: Path | str | None = None,
    latest_path: Path | str | None = None,
    symbols: Iterable[str] = (),
    endpoint: str = PROPHET_GRAPHQL_URL,
    page_size: int = 50,
    max_pages: int = 2,
    ttl_seconds: int = 900,
    timeout_seconds: float = 10.0,
    include_resolved: bool = False,
    redis_url: str = "",
    redis_key: str = "",
    redis_ttl_seconds: int | None = None,
    generated_at: datetime | None = None,
) -> ProphetArchiveResult:
    markets = fetch_prophet_crypto_markets(
        endpoint=endpoint,
        page_size=page_size,
        max_pages=max_pages,
        timeout_seconds=timeout_seconds,
    )
    result = build_prophet_prediction_state(
        markets,
        generated_at=generated_at,
        symbols=symbols,
        ttl_seconds=ttl_seconds,
        include_resolved=include_resolved,
    )
    if archive_path:
        path = Path(archive_path)
        _append_timeline_jsonl(path, result.state)
        result.archive_path = str(path)
    if latest_path:
        path = Path(latest_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.state, indent=2, sort_keys=True), encoding="utf-8")
        result.latest_path = str(path)
    if redis_url and redis_key:
        result.published_redis = _publish_redis_state(
            redis_url=redis_url,
            redis_key=redis_key,
            state=result.state,
            ttl_seconds=redis_ttl_seconds or max(int(ttl_seconds), int(ttl_seconds) * 2),
        )
    return result


def _graphql_post(endpoint: str, query: str, variables: Mapping[str, Any], *, timeout_seconds: float) -> Mapping[str, Any]:
    body = json.dumps({"query": query, "variables": dict(variables)}).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "futuresbot-prophet-archive/1.0"},
        method="POST",
    )
    with urlopen(request, timeout=max(1.0, float(timeout_seconds))) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise ProphetArchiveError("Prophet GraphQL returned a non-object response")
    errors = payload.get("errors")
    if errors:
        raise ProphetArchiveError(f"Prophet GraphQL returned errors: {errors}")
    return payload


def _extract_market_nodes(connection: Any) -> list[dict[str, Any]]:
    if isinstance(connection, list):
        return [dict(item) for item in connection if isinstance(item, Mapping)]
    if not isinstance(connection, Mapping):
        return []
    nodes = connection.get("nodes")
    if isinstance(nodes, list):
        return [dict(item) for item in nodes if isinstance(item, Mapping)]
    edges = connection.get("edges")
    if isinstance(edges, list):
        extracted = []
        for edge in edges:
            if isinstance(edge, Mapping) and isinstance(edge.get("node"), Mapping):
                extracted.append(dict(edge["node"]))
        return extracted
    return []


def _append_timeline_jsonl(path: Path, state: Mapping[str, Any]) -> None:
    timestamp = str(state.get("generated_at") or datetime.now(timezone.utc).isoformat())
    row = {"timestamp": timestamp, "state": dict(state)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True))
        handle.write("\n")


def _publish_redis_state(*, redis_url: str, redis_key: str, state: Mapping[str, Any], ttl_seconds: int) -> bool:
    try:
        import redis

        client = redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)
        client.set(redis_key, json.dumps(dict(state), sort_keys=True), ex=max(1, int(ttl_seconds)))
        return True
    except Exception:
        return False


def _probability_from_bps(value: Any) -> float | None:
    parsed = _float_or_none(value)
    if parsed is None:
        return None
    probability = parsed / 10_000.0 if parsed > 1.0 else parsed
    if 0.0 <= probability <= 1.0:
        return probability
    return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    parsed = _float_or_none(value)
    if parsed is None:
        return None
    return int(round(parsed))


def _normalise_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)