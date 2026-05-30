from __future__ import annotations

import argparse
import json
import math
import sys
import time
from urllib.error import HTTPError, URLError
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from futuresbot.prediction_market_classifier import classify_prediction_market


POLYMARKET_GAMMA_BASE = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB_BASE = "https://clob.polymarket.com"
KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"

@dataclass(slots=True)
class PublicPredictionMarket:
    provider: str
    event_id: str
    title: str
    symbol: str
    direction: str
    token_or_ticker: str
    series_ticker: str = ""
    history: tuple[tuple[datetime, float], ...] = ()


def parse_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, TypeError, ValueError):
            return None
    else:
        raw = str(value).strip()
        if not raw:
            return None
        if raw.isdigit():
            try:
                return datetime.fromtimestamp(float(raw), tz=timezone.utc)
            except (OSError, TypeError, ValueError):
                return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def export_public_prediction_history(
    *,
    start: datetime,
    end: datetime,
    symbols: Iterable[str],
    providers: Iterable[str] = ("polymarket",),
    grid_minutes: int = 15,
    max_observation_age_minutes: int = 1440,
    polymarket_limit: int = 500,
    polymarket_max_pages: int = 4,
    polymarket_tag_slug: str = "crypto",
    kalshi_series: Iterable[str] = ("KXBTC", "KXETH"),
    request_pause_seconds: float = 0.05,
) -> dict[str, Any]:
    allowed_symbols = tuple(symbol.upper() for symbol in symbols if symbol)
    provider_set = {provider.strip().lower() for provider in providers if provider.strip()}
    markets: list[PublicPredictionMarket] = []
    skipped: dict[str, int] = {}
    if "polymarket" in provider_set:
        polymarket_markets, polymarket_skipped = fetch_polymarket_markets(
            start=start,
            end=end,
            symbols=allowed_symbols,
            limit=polymarket_limit,
            max_pages=polymarket_max_pages,
            tag_slug=polymarket_tag_slug,
        )
        skipped.update({f"polymarket_{key}": value for key, value in polymarket_skipped.items()})
        markets.extend(_attach_polymarket_history(polymarket_markets, start, end, grid_minutes, request_pause_seconds))
    if "kalshi" in provider_set:
        kalshi_markets, kalshi_skipped = fetch_kalshi_markets(start=start, end=end, symbols=allowed_symbols, series=kalshi_series)
        skipped.update({f"kalshi_{key}": value for key, value in kalshi_skipped.items()})
        markets.extend(_attach_kalshi_history(kalshi_markets, start, end, grid_minutes, request_pause_seconds))
    return build_timeline_payload(
        markets,
        start=start,
        end=end,
        grid_minutes=grid_minutes,
        max_observation_age_minutes=max_observation_age_minutes,
        skipped=skipped,
    )


def fetch_polymarket_markets(
    *,
    start: datetime,
    end: datetime,
    symbols: Iterable[str],
    limit: int,
    max_pages: int,
    tag_slug: str,
) -> tuple[list[PublicPredictionMarket], dict[str, int]]:
    markets: list[PublicPredictionMarket] = []
    seen: set[str] = set()
    skipped = {"ambiguous": 0, "missing_token": 0, "outside_window": 0}
    for closed in (False, True):
        for page in range(max(1, max_pages)):
            params = {
                "limit": str(max(1, min(1000, limit))),
                "offset": str(page * max(1, min(1000, limit))),
                "closed": str(closed).lower(),
                "active": "true",
                "order": "volume",
                "ascending": "false",
            }
            if tag_slug:
                params["tag_slug"] = tag_slug
            raw = _http_json(f"{POLYMARKET_GAMMA_BASE}/markets", params)
            rows = raw.get("markets") if isinstance(raw, Mapping) else raw
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                identity = str(row.get("conditionId") or row.get("id") or row.get("slug") or "")
                if not identity or identity in seen:
                    continue
                seen.add(identity)
                if not _row_overlaps_window(row, start, end):
                    skipped["outside_window"] += 1
                    continue
                title = str(row.get("question") or row.get("title") or row.get("slug") or "")
                classified = classify_prediction_market(title, symbols)
                if classified is None:
                    skipped["ambiguous"] += 1
                    continue
                token = _polymarket_yes_token(row)
                if not token:
                    skipped["missing_token"] += 1
                    continue
                symbol, direction = classified
                markets.append(
                    PublicPredictionMarket(
                        provider="polymarket",
                        event_id=f"polymarket:{row.get('slug') or identity}",
                        title=title,
                        symbol=symbol,
                        direction=direction,
                        token_or_ticker=token,
                    )
                )
            if len(rows) < limit:
                break
    return markets, skipped


def fetch_kalshi_markets(
    *,
    start: datetime,
    end: datetime,
    symbols: Iterable[str],
    series: Iterable[str],
) -> tuple[list[PublicPredictionMarket], dict[str, int]]:
    markets: list[PublicPredictionMarket] = []
    skipped = {"ambiguous": 0, "outside_window": 0}
    for series_ticker in series:
        events = _paginated_kalshi_events(series_ticker)
        for event in events:
            if not isinstance(event, Mapping):
                continue
            if not _row_overlaps_window(event, start, end):
                skipped["outside_window"] += 1
                continue
            event_ticker = str(event.get("event_ticker") or "")
            if not event_ticker:
                continue
            raw_markets = _http_json(f"{KALSHI_BASE}/markets", {"event_ticker": event_ticker, "limit": "1000"})
            for row in raw_markets.get("markets") or []:
                if not isinstance(row, Mapping):
                    continue
                text = " ".join(str(row.get(key) or "") for key in ("title", "yes_sub_title", "subtitle"))
                classified = classify_prediction_market(text, symbols)
                if classified is None:
                    skipped["ambiguous"] += 1
                    continue
                symbol, direction = classified
                markets.append(
                    PublicPredictionMarket(
                        provider="kalshi",
                        event_id=f"kalshi:{row.get('ticker')}",
                        title=text.strip(),
                        symbol=symbol,
                        direction=direction,
                        token_or_ticker=str(row.get("ticker") or ""),
                        series_ticker=str(event.get("series_ticker") or series_ticker),
                    )
                )
    return markets, skipped


def build_timeline_payload(
    markets: list[PublicPredictionMarket],
    *,
    start: datetime,
    end: datetime,
    grid_minutes: int,
    max_observation_age_minutes: int,
    skipped: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    markets = [market for market in markets if market.history]
    if not markets:
        raise ValueError("No public prediction histories were found for unambiguous crypto directional markets.")
    grid = list(_iter_grid(start, end, grid_minutes))
    latest: dict[str, tuple[datetime, float]] = {}
    indices = {market.event_id: 0 for market in markets}
    max_age = timedelta(minutes=max(1, max_observation_age_minutes))
    timeline = []
    event_count = 0
    for timestamp in grid:
        events: list[dict[str, Any]] = []
        for market in markets:
            index = indices[market.event_id]
            while index < len(market.history) and market.history[index][0] <= timestamp:
                latest[market.event_id] = market.history[index]
                index += 1
            indices[market.event_id] = index
            observed = latest.get(market.event_id)
            if observed is None:
                continue
            observed_at, probability = observed
            if timestamp - observed_at > max_age:
                continue
            events.append(
                {
                    "event_id": market.event_id,
                    "title": market.title,
                    "source": market.provider,
                    "symbols": [market.symbol],
                    "direction": market.direction,
                    "probability": round(probability, 6),
                    "observed_at": observed_at.isoformat(),
                }
            )
        if not events:
            continue
        event_count += len(events)
        generated_at = timestamp.isoformat()
        timeline.append(
            {
                "timestamp": generated_at,
                "state": {
                    "generated_at": generated_at,
                    "ttl_seconds": max(60, int(grid_minutes) * 60 * 2),
                    "events": events,
                },
            }
        )
    if not timeline:
        raise ValueError("No timeline snapshots could be built from the fetched public prediction histories.")
    return {
        "metadata": {
            "format": "futures_prediction_overlay_v1",
            "source": "public_prediction_market_history",
            "built_at": datetime.now(timezone.utc).isoformat(),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "grid_minutes": int(grid_minutes),
            "max_observation_age_minutes": int(max_observation_age_minutes),
            "market_count": len(markets),
            "snapshot_count": len(timeline),
            "event_count": event_count,
            "skipped": dict(skipped or {}),
            "point_in_time_required": True,
        },
        "timeline": timeline,
    }


def _attach_polymarket_history(
    markets: list[PublicPredictionMarket],
    start: datetime,
    end: datetime,
    fidelity_minutes: int,
    request_pause_seconds: float,
) -> list[PublicPredictionMarket]:
    with_history: list[PublicPredictionMarket] = []
    for market in markets:
        try:
            raw = _http_json(
                f"{POLYMARKET_CLOB_BASE}/prices-history",
                {
                    "market": market.token_or_ticker,
                    "interval": "max",
                    "fidelity": str(max(1, int(fidelity_minutes))),
                },
            )
        except (HTTPError, URLError, TimeoutError):
            continue
        history = tuple(_history_points(raw.get("history") or [], start=start, end=end, time_key="t", price_key="p"))
        if history:
            with_history.append(replace(market, history=history))
        time.sleep(max(0.0, request_pause_seconds))
    return with_history


def _attach_kalshi_history(
    markets: list[PublicPredictionMarket],
    start: datetime,
    end: datetime,
    period_minutes: int,
    request_pause_seconds: float,
) -> list[PublicPredictionMarket]:
    with_history: list[PublicPredictionMarket] = []
    period = 1 if period_minutes <= 1 else 60 if period_minutes <= 60 else 1440
    for market in markets:
        if not market.series_ticker or not market.token_or_ticker:
            continue
        try:
            raw = _http_json(
                f"{KALSHI_BASE}/series/{market.series_ticker}/markets/{market.token_or_ticker}/candlesticks",
                {
                    "start_ts": str(int(start.timestamp())),
                    "end_ts": str(int(end.timestamp())),
                    "period_interval": str(period),
                },
            )
        except (HTTPError, URLError, TimeoutError):
            continue
        history = tuple(_kalshi_history_points(raw.get("candlesticks") or [], start=start, end=end))
        if history:
            with_history.append(replace(market, history=history))
        time.sleep(max(0.0, request_pause_seconds))
    return with_history


def _history_points(rows: Iterable[Any], *, start: datetime, end: datetime, time_key: str, price_key: str) -> Iterable[tuple[datetime, float]]:
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        timestamp = parse_timestamp(row.get(time_key))
        probability = _probability(row.get(price_key))
        if timestamp is None or probability is None:
            continue
        if start <= timestamp <= end:
            yield timestamp, probability


def _kalshi_history_points(rows: Iterable[Any], *, start: datetime, end: datetime) -> Iterable[tuple[datetime, float]]:
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        timestamp = parse_timestamp(row.get("end_period_ts"))
        price = row.get("price") if isinstance(row.get("price"), Mapping) else {}
        probability = _probability(
            price.get("close_dollars")
            or price.get("close")
            or price.get("mean_dollars")
            or price.get("mean")
            or row.get("close")
        )
        if timestamp is None or probability is None:
            continue
        if start <= timestamp <= end:
            yield timestamp, probability


def _polymarket_yes_token(row: Mapping[str, Any]) -> str:
    token_ids = _json_list(row.get("clobTokenIds"))
    outcomes = [str(item).strip().lower() for item in _json_list(row.get("outcomes"))]
    if not token_ids:
        return ""
    if outcomes:
        for index, outcome in enumerate(outcomes):
            if outcome == "yes" and index < len(token_ids):
                return str(token_ids[index])
    return str(token_ids[0])


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _row_overlaps_window(row: Mapping[str, Any], start: datetime, end: datetime) -> bool:
    opens = parse_timestamp(row.get("startDate") or row.get("createdAt") or row.get("created_time") or row.get("open_time"))
    closes = parse_timestamp(row.get("closedTime") or row.get("close_time") or row.get("endDate") or row.get("end_date"))
    if opens is not None and opens > end:
        return False
    if closes is not None and closes < start:
        return False
    return True


def _paginated_kalshi_events(series_ticker: str) -> list[Mapping[str, Any]]:
    events: list[Mapping[str, Any]] = []
    cursor = ""
    while True:
        params = {"series_ticker": series_ticker, "limit": "200"}
        if cursor:
            params["cursor"] = cursor
        raw = _http_json(f"{KALSHI_BASE}/events", params)
        events.extend(item for item in raw.get("events") or [] if isinstance(item, Mapping))
        cursor = str(raw.get("cursor") or "")
        if not cursor:
            break
    return events


def _http_json(url: str, params: Mapping[str, str]) -> Any:
    full_url = f"{url}?{urlencode(params)}" if params else url
    request = Request(full_url, headers={"User-Agent": "futuresbot-public-prediction-export/1.0"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _probability(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if probability > 1.0 and probability <= 100.0:
        probability /= 100.0
    if not math.isfinite(probability) or probability < 0.0 or probability > 1.0:
        return None
    return probability


def _iter_grid(start: datetime, end: datetime, grid_minutes: int) -> Iterable[datetime]:
    current = start
    step = timedelta(minutes=max(1, int(grid_minutes)))
    while current <= end:
        yield current
        current += step


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export public Polymarket/Kalshi history into FUTURES_BACKTEST_PREDICTION_STATE_FILE.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--symbols", default="BTC_USDT,ETH_USDT,SOL_USDT,BNB_USDT,SEI_USDT,ZEC_USDT")
    parser.add_argument("--providers", default="polymarket", help="Comma-separated providers: polymarket,kalshi")
    parser.add_argument("--grid-minutes", type=int, default=15)
    parser.add_argument("--max-observation-age-minutes", type=int, default=1440)
    parser.add_argument("--polymarket-tag-slug", default="crypto")
    parser.add_argument("--polymarket-limit", type=int, default=500)
    parser.add_argument("--polymarket-max-pages", type=int, default=4)
    parser.add_argument("--kalshi-series", default="KXBTC,KXETH")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    start = parse_timestamp(args.start)
    end = parse_timestamp(args.end)
    if start is None or end is None or start >= end:
        raise SystemExit("--start and --end must be valid UTC timestamps with start before end")
    payload = export_public_prediction_history(
        start=start,
        end=end,
        symbols=[item.strip() for item in args.symbols.split(",") if item.strip()],
        providers=[item.strip() for item in args.providers.split(",") if item.strip()],
        grid_minutes=max(1, int(args.grid_minutes)),
        max_observation_age_minutes=max(1, int(args.max_observation_age_minutes)),
        polymarket_limit=max(1, int(args.polymarket_limit)),
        polymarket_max_pages=max(1, int(args.polymarket_max_pages)),
        polymarket_tag_slug=str(args.polymarket_tag_slug or ""),
        kalshi_series=[item.strip() for item in args.kalshi_series.split(",") if item.strip()],
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    metadata = payload["metadata"]
    print(
        f"Wrote {output} with {metadata['snapshot_count']} snapshots, "
        f"{metadata['market_count']} markets, and {metadata['event_count']} snapshot-events."
    )
    if metadata.get("skipped"):
        print(json.dumps(metadata["skipped"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
