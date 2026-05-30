from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


TIMESTAMP_KEYS = (
    "generated_at",
    "as_of",
    "updated_at",
    "timestamp",
    "time",
    "created_at",
    "observed_at",
    "block_time",
    "published_at",
)
EVENT_LIST_KEYS = ("events", "predictions", "markets")
PROBABILITY_KEYS = (
    "primary_probability",
    "probability",
    "implied_probability",
    "yes_probability",
    "yes_price",
    "price",
    "last_price",
    "prophet_probability",
    "polymarket_probability",
    "kalshi_probability",
    "secondary_probability",
    "consensus_probability",
    "no_probability",
    "no_price",
)
OUTCOME_KEYS = (
    "outcome",
    "resolved",
    "resolution",
    "result",
    "future_return",
    "future_pnl",
    "target",
    "label",
    "winner",
    "winning",
    "final_price",
)


class PredictionStateBuildError(ValueError):
    pass


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


def build_prediction_state_file(
    input_paths: Iterable[Path],
    *,
    ttl_seconds: int = 60,
    source_name: str = "",
    symbols: Iterable[str] = (),
    start: datetime | None = None,
    end: datetime | None = None,
    allow_outcome_columns: bool = False,
) -> dict[str, Any]:
    snapshots: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    source_files: list[str] = []
    rejected_rows = 0
    for path in input_paths:
        source_files.append(str(path))
        for raw in _load_records(path):
            try:
                for timestamp, events in _normalise_record(
                    raw,
                    ttl_seconds=ttl_seconds,
                    source_name=source_name,
                    symbols=set(_normalise_symbol(symbol) for symbol in symbols if symbol),
                    allow_outcome_columns=allow_outcome_columns,
                ):
                    if start is not None and timestamp < start:
                        continue
                    if end is not None and timestamp > end:
                        continue
                    snapshots[timestamp].extend(events)
            except PredictionStateBuildError:
                rejected_rows += 1
                raise

    timeline = []
    event_count = 0
    for timestamp in sorted(snapshots):
        events = snapshots[timestamp]
        if not events:
            continue
        event_count += len(events)
        generated_at = timestamp.isoformat()
        timeline.append(
            {
                "timestamp": generated_at,
                "state": {
                    "generated_at": generated_at,
                    "ttl_seconds": int(ttl_seconds),
                    "events": events,
                },
            }
        )

    if not timeline:
        raise PredictionStateBuildError("No usable point-in-time prediction snapshots were found.")

    return {
        "metadata": {
            "format": "futures_prediction_overlay_v1",
            "built_at": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": int(ttl_seconds),
            "source_files": source_files,
            "snapshot_count": len(timeline),
            "event_count": event_count,
            "rejected_rows": rejected_rows,
            "point_in_time_required": True,
        },
        "timeline": timeline,
    }


def _load_records(path: Path) -> list[Mapping[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if suffix == ".jsonl":
        records: list[Mapping[str, Any]] = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            raw = line.strip()
            if not raw:
                continue
            parsed = json.loads(raw)
            if not isinstance(parsed, Mapping):
                raise PredictionStateBuildError(f"{path}:{line_no} must contain a JSON object")
            records.append(parsed)
        return records
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(parsed, Mapping):
        if any(key in parsed for key in ("timeline", "states", "events_by_time")):
            items = parsed.get("timeline") or parsed.get("states") or parsed.get("events_by_time") or []
            if not isinstance(items, list):
                raise PredictionStateBuildError(f"{path} timeline/states must be a list")
            return [item for item in items if isinstance(item, Mapping)]
        return [parsed]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, Mapping)]
    raise PredictionStateBuildError(f"{path} must contain a JSON object, JSON list, JSONL, or CSV rows")


def _normalise_record(
    raw: Mapping[str, Any],
    *,
    ttl_seconds: int,
    source_name: str,
    symbols: set[str],
    allow_outcome_columns: bool,
) -> list[tuple[datetime, list[dict[str, Any]]]]:
    _reject_hindsight_columns(raw, allow_outcome_columns=allow_outcome_columns)
    timestamp = _record_timestamp(raw)
    state = raw.get("state") if isinstance(raw.get("state"), Mapping) else raw
    if timestamp is None:
        timestamp = _record_timestamp(state)
    if timestamp is None:
        raise PredictionStateBuildError(f"Prediction row is missing a point-in-time timestamp: {raw}")

    event_items = _event_items(state)
    if not event_items and any(key in state for key in PROBABILITY_KEYS):
        event_items = [state]
    events = [
        event
        for item in event_items
        for event in [_normalise_event(item, timestamp=timestamp, source_name=source_name, symbols=symbols, allow_outcome_columns=allow_outcome_columns)]
        if event is not None
    ]
    if not events:
        return []
    return [(timestamp, events)]


def _event_items(state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in EVENT_LIST_KEYS:
        raw_events = state.get(key)
        if isinstance(raw_events, Mapping):
            return [item for item in raw_events.values() if isinstance(item, Mapping)]
        if isinstance(raw_events, list):
            return [item for item in raw_events if isinstance(item, Mapping)]
    return []


def _normalise_event(
    raw: Mapping[str, Any],
    *,
    timestamp: datetime,
    source_name: str,
    symbols: set[str],
    allow_outcome_columns: bool,
) -> dict[str, Any] | None:
    _reject_hindsight_columns(raw, allow_outcome_columns=allow_outcome_columns)
    event_symbols = _split_symbols(raw.get("symbols") or raw.get("symbol") or raw.get("asset") or raw.get("ticker") or "")
    if symbols and not {_normalise_symbol(symbol) for symbol in event_symbols}.intersection(symbols):
        return None

    probability_keys = [key for key in PROBABILITY_KEYS if raw.get(key) not in (None, "")]
    if not probability_keys:
        raise PredictionStateBuildError(f"Prediction event is missing a probability at {timestamp.isoformat()}: {raw}")

    event: dict[str, Any] = {}
    event_id = _first_present(raw, "event_id", "id", "slug", "market_id", "condition_id", "question", "title", "name")
    if event_id is not None:
        event["event_id"] = str(event_id).strip()
    title = _first_present(raw, "title", "question", "name")
    if title is not None:
        event["title"] = str(title).strip()
    source = _first_present(raw, "source", "provider", "market", "exchange") or source_name
    if source:
        event["source"] = str(source).strip().lower()
    if event_symbols:
        event["symbols"] = event_symbols
    scope = _first_present(raw, "scope", "category")
    if scope:
        event["scope"] = str(scope).strip().lower()
    direction = _first_present(raw, "direction", "bias", "favourable_side", "favorable_side", "trade_side", "side")
    if direction:
        event["direction"] = _normalise_direction(str(direction))

    for key in PROBABILITY_KEYS:
        value = raw.get(key)
        if value in (None, ""):
            continue
        event[key] = _parse_probability(value, key=key)
    event_given_success = raw.get("event_given_success")
    if event_given_success not in (None, ""):
        event["event_given_success"] = _parse_probability(event_given_success, key="event_given_success")
    return event


def _record_timestamp(raw: Mapping[str, Any]) -> datetime | None:
    for key in TIMESTAMP_KEYS:
        parsed = parse_timestamp(raw.get(key))
        if parsed is not None:
            return parsed
    return None


def _reject_hindsight_columns(raw: Mapping[str, Any], *, allow_outcome_columns: bool) -> None:
    if allow_outcome_columns:
        return
    present = sorted(key for key in raw if str(key).strip().lower() in OUTCOME_KEYS and raw.get(key) not in (None, ""))
    if present:
        raise PredictionStateBuildError(
            "Input contains outcome/resolution columns that can leak future information: " + ", ".join(present)
        )


def _parse_probability(value: Any, *, key: str) -> float:
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith("%"):
            raw = raw[:-1].strip()
            scale = 100.0
        else:
            scale = 1.0
        try:
            parsed = float(raw)
        except ValueError as exc:
            raise PredictionStateBuildError(f"Invalid probability for {key}: {value!r}") from exc
        parsed = parsed / scale
    else:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise PredictionStateBuildError(f"Invalid probability for {key}: {value!r}") from exc
    if parsed > 1.0 and parsed <= 100.0:
        parsed = parsed / 100.0
    if not 0.0 <= parsed <= 1.0:
        raise PredictionStateBuildError(f"Probability for {key} must be between 0 and 1, got {value!r}")
    return round(parsed, 6)


def _split_symbols(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw = str(value or "")
        raw_items = raw.replace(";", ",").replace("|", ",").split(",")
    symbols: list[str] = []
    for item in raw_items:
        text = str(item).strip().upper().replace("-", "_").replace("/", "_")
        if not text:
            continue
        if "_" not in text and text.endswith("USDT") and len(text) > 4:
            text = f"{text[:-4]}_USDT"
        if text not in symbols:
            symbols.append(text)
    return symbols


def _normalise_symbol(value: str) -> str:
    return "".join(ch for ch in str(value).upper() if ch.isalnum())


def _normalise_direction(value: str) -> str:
    lowered = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if lowered in {"long", "buy", "bull", "bullish", "risk_on", "positive", "up", "yes"}:
        return "bullish"
    if lowered in {"short", "sell", "bear", "bearish", "risk_off", "negative", "down", "no"}:
        return "bearish"
    return lowered


def _first_present(raw: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a point-in-time FUTURES_BACKTEST_PREDICTION_STATE_FILE from historical prediction snapshots."
    )
    parser.add_argument("--input", nargs="+", required=True, help="CSV, JSON, or JSONL exports from Prophet/0G/Polymarket/Kalshi snapshots.")
    parser.add_argument("--output", required=True, help="Destination JSON file for FUTURES_BACKTEST_PREDICTION_STATE_FILE.")
    parser.add_argument("--ttl-seconds", type=int, default=60, help="How long each snapshot is valid in backtest time.")
    parser.add_argument("--source-name", default="", help="Fallback source name when rows do not include source/provider.")
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbol filter, e.g. BTC_USDT,ETH_USDT.")
    parser.add_argument("--start", default="", help="Optional inclusive UTC start timestamp.")
    parser.add_argument("--end", default="", help="Optional inclusive UTC end timestamp.")
    parser.add_argument("--allow-outcome-columns", action="store_true", help="Allow outcome/result columns. Use only for trusted exports where they are ignored.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    start = parse_timestamp(args.start) if args.start else None
    end = parse_timestamp(args.end) if args.end else None
    symbols = [symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()]
    output = build_prediction_state_file(
        [Path(path) for path in args.input],
        ttl_seconds=max(1, int(args.ttl_seconds)),
        source_name=args.source_name,
        symbols=symbols,
        start=start,
        end=end,
        allow_outcome_columns=bool(args.allow_outcome_columns),
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    metadata = output["metadata"]
    print(
        "Built prediction state file "
        f"{output_path} with {metadata['snapshot_count']} snapshots and {metadata['event_count']} events."
    )


if __name__ == "__main__":
    main()
