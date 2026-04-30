from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


DEFAULT_STALE_SECONDS = 1_800
DEFAULT_SIZE_MULTIPLIER = 0.65
DEFAULT_LEVERAGE_MULTIPLIER = 0.70
DEFAULT_SEVERE_SIZE_MULTIPLIER = 0.40
DEFAULT_SEVERE_LEVERAGE_MULTIPLIER = 0.50
DEFAULT_BLOCK_THRESHOLD = 0.92


@dataclass(frozen=True, slots=True)
class EventPolicyDecision:
    symbol: str
    side: str
    block_entry: bool
    size_multiplier: float
    leverage_multiplier: float
    reasons: tuple[str, ...]
    state_age_seconds: float | None = None


def parse_event_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def is_event_state_fresh(
    state: dict[str, Any] | None,
    *,
    now: datetime,
    stale_after_seconds: int = DEFAULT_STALE_SECONDS,
) -> tuple[bool, float | None]:
    if not isinstance(state, dict):
        return False, None
    generated_at = parse_event_timestamp(state.get("generated_at") or state.get("updated_at") or state.get("timestamp"))
    if generated_at is None:
        return False, None
    current = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    age = max(0.0, (current - generated_at).total_seconds())
    ttl = state.get("ttl_seconds") or state.get("stale_after_seconds") or stale_after_seconds
    try:
        max_age = max(1.0, float(ttl))
    except (TypeError, ValueError):
        max_age = float(stale_after_seconds)
    return age <= max_age, age


def evaluate_event_policy(
    *,
    symbol: str,
    side: str,
    state: dict[str, Any] | None,
    now: datetime,
    stale_after_seconds: int = DEFAULT_STALE_SECONDS,
    size_multiplier: float = DEFAULT_SIZE_MULTIPLIER,
    leverage_multiplier: float = DEFAULT_LEVERAGE_MULTIPLIER,
    severe_size_multiplier: float = DEFAULT_SEVERE_SIZE_MULTIPLIER,
    severe_leverage_multiplier: float = DEFAULT_SEVERE_LEVERAGE_MULTIPLIER,
    block_threshold: float = DEFAULT_BLOCK_THRESHOLD,
) -> EventPolicyDecision:
    sym = (symbol or "").strip().upper()
    trade_side = (side or "").strip().upper()
    fresh, age = is_event_state_fresh(state, now=now, stale_after_seconds=stale_after_seconds)
    if not fresh or not isinstance(state, dict):
        return EventPolicyDecision(sym, trade_side, False, 1.0, 1.0, (), age)

    risk_score, risk_reasons = _risk_score_for_symbol(state, sym)
    if risk_score <= 0:
        return EventPolicyDecision(sym, trade_side, False, 1.0, 1.0, (), age)

    reasons = [f"crypto_event_risk:{risk_score:.2f}", *risk_reasons]
    block = risk_score >= float(block_threshold)
    if risk_score >= 0.80:
        size_mult = severe_size_multiplier
        leverage_mult = severe_leverage_multiplier
    else:
        size_mult = size_multiplier
        leverage_mult = leverage_multiplier

    if trade_side == "SHORT" and not block:
        size_mult = max(size_mult, 0.75)
        leverage_mult = max(leverage_mult, 0.80)

    return EventPolicyDecision(
        symbol=sym,
        side=trade_side,
        block_entry=block,
        size_multiplier=max(0.0, min(1.0, float(size_mult))),
        leverage_multiplier=max(0.0, min(1.0, float(leverage_mult))),
        reasons=tuple(dict.fromkeys(reason for reason in reasons if reason)),
        state_age_seconds=age,
    )


def _risk_score_for_symbol(state: dict[str, Any], symbol: str) -> tuple[float, list[str]]:
    score = _safe_float(state.get("market_risk_score"), 0.0)
    reasons: list[str] = []
    if score > 0:
        reasons.append("market")

    stable = _safe_float(state.get("stablecoin_supply_change_24h_frac"), 0.0)
    if stable <= -0.01:
        score = max(score, 0.65)
        reasons.append("stable_supply_shrinking")

    inflow = _safe_float(state.get("btc_exchange_inflow_1h"), 0.0)
    if inflow >= 5_000.0:
        score = max(score, 0.80)
        reasons.append("exchange_inflow_spike")

    for raw in state.get("events") or state.get("headlines") or ():
        if not isinstance(raw, dict):
            continue
        direction = str(raw.get("direction") or raw.get("bias") or "").strip().lower()
        if direction and direction not in {"risk_off", "bearish", "negative"}:
            continue
        scope = str(raw.get("scope") or "").strip().lower()
        symbols = {str(item).strip().upper() for item in raw.get("symbols") or () if str(item).strip()}
        applies = scope in {"", "market", "global", "crypto", "market_wide"} or symbol in symbols
        if not applies:
            continue
        event_score = _safe_float(raw.get("severity") or raw.get("score"), 0.0)
        if event_score > score:
            score = event_score
        reason = str(raw.get("reason") or raw.get("category") or "headline").strip().lower()
        if reason:
            reasons.append(reason)
    return max(0.0, min(1.0, score)), reasons


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)
