from __future__ import annotations

import math
import os
from typing import Any, Mapping


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name)
        if raw is None or raw.strip() == "":
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def opportunity_score_10(raw_score: float | int | None) -> int:
    try:
        score = float(raw_score or 0.0)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(score) or score <= 0:
        return 0
    return max(0, min(10, int(math.floor(score / 10.0 + 0.5))))


def opportunity_balance_fraction(raw_score: float | int | None) -> float:
    score_10 = opportunity_score_10(raw_score)
    if score_10 <= 5:
        return 0.0
    if score_10 <= 7:
        return 0.50
    if score_10 <= 9:
        return 0.75
    return 1.0


def opportunity_nav_risk_pct(raw_score: float | int | None, *, default: float = 0.04) -> float:
    score_10 = opportunity_score_10(raw_score)
    if score_10 <= 5:
        return 0.0
    base = max(0.0, _env_float("FUTURES_OPPORTUNITY_NAV_RISK_PCT", default))
    if not _env_bool("FUTURES_SCORE_BUCKET_NAV_RISK_ENABLED", True):
        return base
    if score_10 == 6:
        return max(
            0.0,
            _env_float(
                "FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE6",
                _env_float("FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE6_7", base * 0.375),
            ),
        )
    if score_10 == 7:
        return max(
            0.0,
            _env_float(
                "FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE7",
                _env_float("FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE6_7", base),
            ),
        )
    if score_10 == 8:
        return max(0.0, _env_float("FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE8", base))
    if score_10 == 9:
        return max(0.0, _env_float("FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE9", base))
    return max(0.0, _env_float("FUTURES_OPPORTUNITY_NAV_RISK_PCT_SCORE10", base * 1.125))


def opportunity_metadata(metadata: Mapping[str, Any] | None, raw_score: float | int | None) -> dict[str, Any]:
    score_10 = opportunity_score_10(raw_score)
    return {
        **(dict(metadata or {})),
        "opportunity_score_10": score_10,
        "opportunity_balance_fraction": opportunity_balance_fraction(raw_score),
        "opportunity_nav_risk_pct": opportunity_nav_risk_pct(raw_score),
    }
