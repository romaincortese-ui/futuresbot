from __future__ import annotations

import math
from typing import Any, Mapping


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


def opportunity_metadata(metadata: Mapping[str, Any] | None, raw_score: float | int | None) -> dict[str, Any]:
    score_10 = opportunity_score_10(raw_score)
    return {
        **(dict(metadata or {})),
        "opportunity_score_10": score_10,
        "opportunity_balance_fraction": opportunity_balance_fraction(raw_score),
    }
