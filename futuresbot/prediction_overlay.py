from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


DEFAULT_STALE_SECONDS = 60
DEFAULT_DIVERGENCE_THRESHOLD = 0.15
DEFAULT_MIN_FAVOURABLE_PROBABILITY = 0.50
DEFAULT_MIN_POSTERIOR = 0.50
DEFAULT_EVENT_GIVEN_SUCCESS = 0.60
DEFAULT_KELLY_BASE_FRACTION = 0.04
DEFAULT_MAX_SIZE_MULTIPLIER = 1.0
DEFAULT_SCORE_SCALE = 20.0


@dataclass(frozen=True, slots=True)
class PredictionOverlayDecision:
    allowed: bool
    reason: str
    fresh: bool = False
    event_id: str = ""
    event_title: str = ""
    source_names: tuple[str, ...] = ()
    primary_probability: float | None = None
    secondary_probability: float | None = None
    favourable_probability: float = 0.50
    base_success_probability: float = 0.50
    bayesian_success_probability: float = 0.50
    kelly_fraction: float = 0.0
    size_multiplier: float = 1.0
    score_offset: float = 0.0
    divergence: float | None = None
    state_age_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def parse_prediction_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_prediction_state_fresh(
    state: Mapping[str, Any] | None,
    now: datetime,
    *,
    stale_seconds: int = DEFAULT_STALE_SECONDS,
) -> tuple[bool, float | None]:
    if not isinstance(state, Mapping):
        return False, None
    generated_at = parse_prediction_timestamp(
        state.get("generated_at") or state.get("as_of") or state.get("updated_at") or state.get("timestamp")
    )
    if generated_at is None:
        return False, None
    current = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    age = (current - generated_at).total_seconds()
    ttl_raw = state.get("ttl_seconds") or state.get("stale_after_seconds") or stale_seconds
    try:
        ttl = max(1.0, float(ttl_raw))
    except (TypeError, ValueError):
        ttl = float(stale_seconds)
    return 0.0 <= age <= ttl, max(0.0, age)


def select_point_in_time_prediction_state(payload: Any, now: datetime) -> dict[str, Any] | None:
    if not isinstance(payload, (Mapping, list)):
        return None
    if isinstance(payload, Mapping) and not any(key in payload for key in ("timeline", "states", "events_by_time")):
        return dict(payload)
    items = payload if isinstance(payload, list) else payload.get("timeline") or payload.get("states") or payload.get("events_by_time") or []
    if not isinstance(items, list):
        return None
    current = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    selected: dict[str, Any] | None = None
    for item in items:
        if not isinstance(item, Mapping):
            continue
        start = parse_prediction_timestamp(item.get("from") or item.get("start") or item.get("generated_at") or item.get("timestamp"))
        if start is None or start > current:
            continue
        end = parse_prediction_timestamp(item.get("until") or item.get("end") or item.get("expires_at"))
        if end is not None and current >= end:
            continue
        raw_state = item.get("state") if isinstance(item.get("state"), Mapping) else item
        state = dict(raw_state)
        state.setdefault("generated_at", start.isoformat())
        selected = state
    return selected


def merge_prediction_states(primary: Any, secondary_states: Sequence[Any] = ()) -> dict[str, Any] | None:
    if not isinstance(primary, Mapping):
        return None
    merged = dict(primary)
    events = _raw_events(primary)
    for state in secondary_states:
        if isinstance(state, Mapping):
            events.extend(_raw_events(state))
    if events:
        merged["events"] = events
    return merged


def apply_prediction_overlay(
    signal: Any,
    state: Mapping[str, Any] | None,
    now: datetime,
    *,
    enabled: bool = False,
    stale_seconds: int = DEFAULT_STALE_SECONDS,
    fallback_mode: str = "neutral",
    divergence_threshold: float = DEFAULT_DIVERGENCE_THRESHOLD,
    min_favourable_probability: float = DEFAULT_MIN_FAVOURABLE_PROBABILITY,
    min_posterior: float = DEFAULT_MIN_POSTERIOR,
    event_given_success: float = DEFAULT_EVENT_GIVEN_SUCCESS,
    kelly_base_fraction: float = DEFAULT_KELLY_BASE_FRACTION,
    max_size_multiplier: float = DEFAULT_MAX_SIZE_MULTIPLIER,
    score_scale: float = DEFAULT_SCORE_SCALE,
) -> Any | None:
    decision = evaluate_prediction_overlay(
        signal,
        state,
        now,
        enabled=enabled,
        stale_seconds=stale_seconds,
        fallback_mode=fallback_mode,
        divergence_threshold=divergence_threshold,
        min_favourable_probability=min_favourable_probability,
        min_posterior=min_posterior,
        event_given_success=event_given_success,
        kelly_base_fraction=kelly_base_fraction,
        max_size_multiplier=max_size_multiplier,
        score_scale=score_scale,
    )
    if not decision.allowed:
        return None
    if not decision.fresh or decision.reason in {"disabled", "no_relevant_prediction_event", "neutral_fallback"}:
        return signal
    metadata = {
        **(getattr(signal, "metadata", None) or {}),
        **decision.metadata,
    }
    score = max(0.0, float(getattr(signal, "score", 0.0) or 0.0) + decision.score_offset)
    certainty = max(0.0, min(1.0, decision.bayesian_success_probability))
    return dataclasses.replace(
        signal,
        score=round(score, 2),
        certainty=round(certainty, 4),
        metadata=metadata,
    )


def evaluate_prediction_overlay(
    signal: Any,
    state: Mapping[str, Any] | None,
    now: datetime,
    *,
    enabled: bool = False,
    stale_seconds: int = DEFAULT_STALE_SECONDS,
    fallback_mode: str = "neutral",
    divergence_threshold: float = DEFAULT_DIVERGENCE_THRESHOLD,
    min_favourable_probability: float = DEFAULT_MIN_FAVOURABLE_PROBABILITY,
    min_posterior: float = DEFAULT_MIN_POSTERIOR,
    event_given_success: float = DEFAULT_EVENT_GIVEN_SUCCESS,
    kelly_base_fraction: float = DEFAULT_KELLY_BASE_FRACTION,
    max_size_multiplier: float = DEFAULT_MAX_SIZE_MULTIPLIER,
    score_scale: float = DEFAULT_SCORE_SCALE,
) -> PredictionOverlayDecision:
    if not enabled:
        return PredictionOverlayDecision(True, "disabled")
    fresh, age = is_prediction_state_fresh(state, now, stale_seconds=stale_seconds)
    fallback = str(fallback_mode or "neutral").strip().lower()
    if not fresh or not isinstance(state, Mapping):
        if fallback in {"abort", "block", "halt"}:
            return PredictionOverlayDecision(False, "stale_prediction_state", state_age_seconds=age)
        return PredictionOverlayDecision(True, "neutral_fallback", state_age_seconds=age)

    event = _select_relevant_event(state, str(getattr(signal, "symbol", "") or ""), str(getattr(signal, "side", "") or ""))
    if event is None:
        return PredictionOverlayDecision(True, "no_relevant_prediction_event", fresh=True, state_age_seconds=age)

    primary_probability = _optional_float(event.get("primary_probability"))
    if primary_probability is None:
        primary_probability = _optional_float(event.get("probability"))
    if primary_probability is None:
        return PredictionOverlayDecision(True, "prediction_event_missing_probability", fresh=True, state_age_seconds=age)
    primary_probability = _clamp_probability(primary_probability)

    secondary_probability = _optional_float(event.get("secondary_probability"))
    if secondary_probability is not None:
        secondary_probability = _clamp_probability(secondary_probability)
    divergence = abs(primary_probability - secondary_probability) if secondary_probability is not None else None
    source_names = tuple(str(item) for item in event.get("source_names") or () if str(item))
    event_id = str(event.get("event_id") or event.get("id") or event.get("slug") or "")
    event_title = str(event.get("title") or event.get("question") or event.get("name") or event_id)
    if divergence is not None and divergence > max(0.0, float(divergence_threshold)):
        metadata = _decision_metadata(
            event_id=event_id,
            event_title=event_title,
            reason="prediction_oracle_divergence",
            primary_probability=primary_probability,
            secondary_probability=secondary_probability,
            favourable_probability=0.5,
            base_success=0.5,
            posterior=0.5,
            kelly=0.0,
            size_multiplier=0.0,
            divergence=divergence,
            source_names=source_names,
            state_age_seconds=age,
        )
        return PredictionOverlayDecision(
            False,
            "prediction_oracle_divergence",
            fresh=True,
            event_id=event_id,
            event_title=event_title,
            source_names=source_names,
            primary_probability=primary_probability,
            secondary_probability=secondary_probability,
            divergence=divergence,
            state_age_seconds=age,
            metadata=metadata,
        )

    favourable_probability = _favourable_probability(primary_probability, str(event.get("favourable_side") or ""), str(getattr(signal, "side", "") or ""))
    base_success = _base_success_probability(signal)
    event_given_success_value = _clamp_probability(_optional_float(event.get("event_given_success")) or event_given_success)
    posterior = _bayesian_success_probability(
        base_success=base_success,
        event_probability=max(0.01, favourable_probability),
        event_given_success=event_given_success_value,
    )
    reward_risk = _reward_risk(signal)
    kelly = _kelly_fraction(favourable_probability, reward_risk)
    size_multiplier = _size_multiplier_from_kelly(
        kelly,
        base_fraction=kelly_base_fraction,
        max_size_multiplier=max_size_multiplier,
    )
    score_offset = (posterior - base_success) * max(0.0, float(score_scale))
    reason = "prediction_overlay_pass"
    allowed = True
    if favourable_probability < max(0.0, min(1.0, float(min_favourable_probability))):
        reason = "prediction_unfavourable_probability"
        allowed = False
    elif posterior < max(0.0, min(1.0, float(min_posterior))):
        reason = "prediction_low_bayesian_success"
        allowed = False
    elif kelly <= 0.0 or size_multiplier <= 0.0:
        reason = "prediction_nonpositive_kelly"
        allowed = False

    metadata = _decision_metadata(
        event_id=event_id,
        event_title=event_title,
        reason=reason,
        primary_probability=primary_probability,
        secondary_probability=secondary_probability,
        favourable_probability=favourable_probability,
        base_success=base_success,
        posterior=posterior,
        kelly=kelly,
        size_multiplier=size_multiplier if allowed else 0.0,
        divergence=divergence,
        source_names=source_names,
        state_age_seconds=age,
        reward_risk=reward_risk,
    )
    return PredictionOverlayDecision(
        allowed,
        reason,
        fresh=True,
        event_id=event_id,
        event_title=event_title,
        source_names=source_names,
        primary_probability=primary_probability,
        secondary_probability=secondary_probability,
        favourable_probability=favourable_probability,
        base_success_probability=base_success,
        bayesian_success_probability=posterior,
        kelly_fraction=kelly,
        size_multiplier=size_multiplier if allowed else 0.0,
        score_offset=score_offset if allowed else 0.0,
        divergence=divergence,
        state_age_seconds=age,
        metadata=metadata,
    )


def _raw_events(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = state.get("events") or state.get("predictions") or state.get("markets") or []
    if isinstance(raw, Mapping):
        raw = list(raw.values())
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, Mapping)]
    if any(key in state for key in ("probability", "yes_price", "price", "primary_probability")):
        return [dict(state)]
    return []


def _select_relevant_event(state: Mapping[str, Any], symbol: str, side: str) -> dict[str, Any] | None:
    candidates: list[tuple[float, dict[str, Any]]] = []
    trade_side = _canonical_side(side)
    for event in _group_prediction_events(state):
        relevance = _event_relevance(event, symbol)
        if relevance <= 0:
            continue
        favourable_side = _event_favourable_side(event)
        if not favourable_side:
            continue
        primary = _optional_float(event.get("primary_probability") or event.get("probability"))
        if primary is None:
            continue
        favourable = _favourable_probability(_clamp_probability(primary), favourable_side, trade_side)
        edge = abs(favourable - 0.5) * relevance
        candidates.append((edge, {**event, "favourable_side": favourable_side}))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _group_prediction_events(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for event in _raw_events(state):
        event_id = str(event.get("event_id") or event.get("id") or event.get("slug") or event.get("title") or event.get("question") or "event").strip()
        direction = str(event.get("direction") or event.get("bias") or event.get("favourable_side") or event.get("side") or "").strip().lower()
        symbols = event.get("symbols") or event.get("symbol") or ""
        if isinstance(symbols, list):
            symbol_key = ",".join(sorted(str(item).upper() for item in symbols))
        else:
            symbol_key = str(symbols).upper()
        key = f"{event_id}|{direction}|{symbol_key}"
        group = grouped.setdefault(key, dict(event))
        source = str(event.get("source") or event.get("provider") or event.get("market") or "").strip().lower()
        probability = _extract_probability(event)
        source_names = set(str(item) for item in group.get("source_names") or () if str(item))
        if source:
            source_names.add(source)
        probabilities = event.get("probabilities") if isinstance(event.get("probabilities"), Mapping) else {}
        primary = _first_probability(
            probabilities,
            event,
            ("prophet", "0g", "primary", "primary_probability", "prophet_probability"),
        )
        secondaries = _secondary_probabilities(probabilities, event)
        if probability is not None:
            if source and not any(token in source for token in ("prophet", "0g", "primary")):
                secondaries.append(probability)
            elif primary is None:
                primary = probability
        if primary is not None and group.get("primary_probability") is None:
            group["primary_probability"] = _clamp_probability(primary)
        existing_secondaries = list(group.get("_secondary_probabilities") or [])
        existing_secondaries.extend(_clamp_probability(item) for item in secondaries)
        if existing_secondaries:
            group["_secondary_probabilities"] = existing_secondaries
            group["secondary_probability"] = sum(existing_secondaries) / len(existing_secondaries)
        group["source_names"] = tuple(sorted(source_names))
    return [group for group in grouped.values()]


def _first_probability(probabilities: Mapping[str, Any], event: Mapping[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = probabilities.get(name)
        if value is not None:
            return _optional_float(value)
    for name in names:
        value = event.get(name)
        if value is not None:
            return _optional_float(value)
    return None


def _secondary_probabilities(probabilities: Mapping[str, Any], event: Mapping[str, Any]) -> list[float]:
    values: list[float] = []
    for key, value in probabilities.items():
        lowered = str(key).lower()
        if lowered in {"prophet", "0g", "primary", "primary_probability", "prophet_probability"}:
            continue
        parsed = _optional_float(value)
        if parsed is not None:
            values.append(parsed)
    for key in ("secondary_probability", "consensus_probability", "polymarket_probability", "kalshi_probability"):
        parsed = _optional_float(event.get(key))
        if parsed is not None:
            values.append(parsed)
    return values


def _extract_probability(event: Mapping[str, Any]) -> float | None:
    for key in ("probability", "implied_probability", "yes_probability", "yes_price", "price", "last_price"):
        value = _optional_float(event.get(key))
        if value is not None:
            return _clamp_probability(value)
    no_price = _optional_float(event.get("no_price") or event.get("no_probability"))
    if no_price is not None:
        return 1.0 - _clamp_probability(no_price)
    return None


def _event_relevance(event: Mapping[str, Any], symbol: str) -> float:
    symbol_norm = _normalize_symbol(symbol)
    raw_symbols = event.get("symbols") or event.get("symbol") or []
    if isinstance(raw_symbols, str):
        raw_symbols = [raw_symbols]
    symbols = {_normalize_symbol(str(item)) for item in raw_symbols if str(item).strip()}
    if symbols:
        return 1.2 if symbol_norm in symbols else 0.0
    scope = str(event.get("scope") or "").strip().lower()
    if not scope or scope in {"market", "global", "crypto", "all", "sector", "macro"}:
        return 1.0
    return 0.0


def _event_favourable_side(event: Mapping[str, Any]) -> str:
    raw = str(
        event.get("favourable_side")
        or event.get("favorable_side")
        or event.get("trade_side")
        or event.get("side")
        or event.get("direction")
        or event.get("bias")
        or ""
    ).strip().lower()
    if raw in {"long", "buy", "bullish", "risk_on", "positive", "up"}:
        return "LONG"
    if raw in {"short", "sell", "bearish", "risk_off", "negative", "down"}:
        return "SHORT"
    return ""


def _favourable_probability(probability: float, favourable_side: str, trade_side: str) -> float:
    p = _clamp_probability(probability)
    event_side = _canonical_side(favourable_side)
    side = _canonical_side(trade_side)
    if not event_side or not side or event_side == side:
        return p
    return 1.0 - p


def _base_success_probability(signal: Any) -> float:
    metadata = getattr(signal, "metadata", None) or {}
    for key in ("prediction_base_win_rate", "historical_win_rate", "calibration_win_rate", "win_rate"):
        value = _optional_float(metadata.get(key))
        if value is not None:
            return _clamp_probability(value)
    certainty = _optional_float(getattr(signal, "certainty", None))
    if certainty is not None:
        return _clamp_probability(certainty)
    return 0.50


def _bayesian_success_probability(*, base_success: float, event_probability: float, event_given_success: float) -> float:
    numerator = _clamp_probability(event_given_success) * _clamp_probability(base_success)
    denominator = max(0.01, _clamp_probability(event_probability))
    return _clamp_probability(numerator / denominator)


def _kelly_fraction(probability: float, reward_risk: float) -> float:
    p = _clamp_probability(probability)
    q = 1.0 - p
    b = max(0.01, float(reward_risk))
    return max(0.0, p - (q / b))


def _reward_risk(signal: Any) -> float:
    entry = _optional_float(getattr(signal, "entry_price", None)) or 0.0
    tp = _optional_float(getattr(signal, "tp_price", None)) or 0.0
    sl = _optional_float(getattr(signal, "sl_price", None)) or 0.0
    if entry <= 0 or tp <= 0 or sl <= 0:
        return 1.0
    reward = abs(tp - entry)
    risk = abs(entry - sl)
    if risk <= 0:
        return 1.0
    return max(0.01, reward / risk)


def _size_multiplier_from_kelly(kelly: float, *, base_fraction: float, max_size_multiplier: float) -> float:
    base = max(0.001, float(base_fraction))
    cap = max(0.0, float(max_size_multiplier))
    return max(0.0, min(cap, float(kelly) / base))


def _decision_metadata(
    *,
    event_id: str,
    event_title: str,
    reason: str,
    primary_probability: float | None,
    secondary_probability: float | None,
    favourable_probability: float,
    base_success: float,
    posterior: float,
    kelly: float,
    size_multiplier: float,
    divergence: float | None,
    source_names: tuple[str, ...],
    state_age_seconds: float | None,
    reward_risk: float | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "prediction_overlay": 1.0,
        "prediction_reason": reason,
        "prediction_event_id": event_id,
        "prediction_event_title": event_title,
        "prediction_primary_probability": round(float(primary_probability), 4) if primary_probability is not None else None,
        "prediction_secondary_probability": round(float(secondary_probability), 4) if secondary_probability is not None else None,
        "prediction_favourable_probability": round(float(favourable_probability), 4),
        "prediction_base_success_probability": round(float(base_success), 4),
        "prediction_bayesian_success_probability": round(float(posterior), 4),
        "prediction_kelly_fraction": round(float(kelly), 6),
        "prediction_size_multiplier": round(float(size_multiplier), 4),
        "prediction_sources": list(source_names),
    }
    if divergence is not None:
        metadata["prediction_oracle_divergence"] = round(float(divergence), 4)
    if state_age_seconds is not None:
        metadata["prediction_state_age_seconds"] = round(float(state_age_seconds), 1)
    if reward_risk is not None:
        metadata["prediction_reward_risk"] = round(float(reward_risk), 4)
    return metadata


def _canonical_side(value: str) -> str:
    lowered = str(value or "").strip().lower()
    if lowered in {"long", "buy", "bid"}:
        return "LONG"
    if lowered in {"short", "sell", "ask"}:
        return "SHORT"
    return ""


def _normalize_symbol(symbol: str) -> str:
    return "".join(ch for ch in str(symbol).upper() if ch.isalnum())


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _clamp_probability(value: float) -> float:
    parsed = float(value)
    if parsed > 1.0 and parsed <= 100.0:
        parsed /= 100.0
    return max(0.0, min(1.0, parsed))
