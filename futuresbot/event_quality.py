from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AdverseEventQualityDecision:
    allowed: bool
    reason: str = ""
    net_rr: float | None = None
    min_net_rr: float | None = None
    score: float | None = None
    min_score: float | None = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _float_or_none(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def evaluate_adverse_event_quality(signal: Any, *, min_confidence_score: float) -> AdverseEventQualityDecision:
    if not _env_bool("FUTURES_CRYPTO_EVENT_ADVERSE_QUALITY_GATE_ENABLED", True):
        return AdverseEventQualityDecision(True)
    metadata = getattr(signal, "metadata", None) or {}
    reason = str(metadata.get("crypto_event_reason") or "")
    alignment = _float_or_none(metadata.get("crypto_event_alignment"))
    min_alignment = abs(_env_float("FUTURES_CRYPTO_EVENT_ADVERSE_QUALITY_MIN_ALIGNMENT", 0.35))
    adverse = reason == "crypto_event_adverse_reduce" or (alignment is not None and alignment <= -min_alignment)
    if not adverse:
        return AdverseEventQualityDecision(True)

    net_rr = _float_or_none(metadata.get("net_rr"))
    min_net_rr = _float_or_none(metadata.get("min_net_rr"))
    score = _float_or_none(getattr(signal, "score", None))
    min_score = max(0.0, float(min_confidence_score or 0.0))
    rr_buffer = max(0.0, _env_float("FUTURES_CRYPTO_EVENT_ADVERSE_MIN_NET_RR_BUFFER", 0.25))
    score_gate_enabled = _env_bool("FUTURES_CRYPTO_EVENT_ADVERSE_SCORE_GATE_ENABLED", False)
    score_buffer = max(0.0, _env_float("FUTURES_CRYPTO_EVENT_ADVERSE_SCORE_BUFFER", 8.0))

    if net_rr is not None and min_net_rr is not None and net_rr < min_net_rr + rr_buffer:
        return AdverseEventQualityDecision(False, "adverse_event_marginal_net_rr", net_rr, min_net_rr, score, min_score)
    if score_gate_enabled and score is not None and score < min_score + score_buffer:
        return AdverseEventQualityDecision(False, "adverse_event_marginal_score", net_rr, min_net_rr, score, min_score)
    return AdverseEventQualityDecision(True, "adverse_event_quality_pass", net_rr, min_net_rr, score, min_score)
