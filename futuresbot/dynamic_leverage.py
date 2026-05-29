from __future__ import annotations

import math
import os
from dataclasses import dataclass

from futuresbot.opportunity_score import opportunity_score_10


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _env_token(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


_DEFAULT_SYMBOL_CAPS: dict[str, int] = {
    "BTC_USDT": 20,
    "ETH_USDT": 18,
    "SOL_USDT": 16,
    "BCH_USDT": 12,
    "BNB_USDT": 12,
    "LINK_USDT": 12,
    "TAO_USDT": 10,
    "ZEC_USDT": 5,
    "DASH_USDT": 8,
    "SEI_USDT": 8,
    "PEPE_USDT": 6,
}


_DEFAULT_SIGNAL_CAPS: tuple[tuple[str, int], ...] = (
    ("SHARP_EVENT", 8),
    ("EVENT_CATALYST", 8),
    ("IMPULSE_EVENT", 10),
    ("MOMENTUM_BREAKAWAY", 10),
    ("RANGE_EXPANSION", 10),
    ("BREAKOUT_HOLD", 12),
    ("LEVEL_BREAK", 12),
    ("BTC_ROUND_LEVEL", 12),
    ("BTC_REVERSAL", 12),
    ("MAJOR_THRESHOLD", 14),
    # New shorter-timeframe trend signals target x15-x20 leverage.
    ("DOWNTREND_MOMENTUM", 20),
    ("UPTREND_MOMENTUM", 20),
)


@dataclass(frozen=True, slots=True)
class DynamicLeverageDecision:
    leverage: int | None
    enabled: bool
    min_leverage: int
    max_leverage: int
    score_cap: int
    stop_cap: int
    symbol_cap: int
    signal_cap: int
    final_cap: int
    stop_margin_loss_pct: float


def dynamic_leverage_enabled() -> bool:
    return _env_bool("FUTURES_DYNAMIC_LEVERAGE_ENABLED", True)


def dynamic_leverage_min() -> int:
    return max(1, _env_int("FUTURES_DYNAMIC_LEVERAGE_MIN", 5))


def dynamic_leverage_max() -> int:
    return max(dynamic_leverage_min(), _env_int("FUTURES_DYNAMIC_LEVERAGE_MAX", 20))


def _score_cap(raw_score: float | int | None, certainty: float) -> int:
    score_10 = opportunity_score_10(raw_score)
    if score_10 <= 0:
        score_10 = max(1, min(10, int(round(max(0.0, min(0.99, certainty)) * 10.0))))
    defaults = {1: 5, 2: 5, 3: 5, 4: 5, 5: 5, 6: 5, 7: 5, 8: 8, 9: 12, 10: 20}
    cap = defaults.get(score_10, 5)
    return max(1, _env_int(f"FUTURES_DYNAMIC_LEVERAGE_SCORE{score_10}_MAX", cap))


def _symbol_cap(symbol: str, fallback: int) -> int:
    normalized = str(symbol or "").upper()
    default = _DEFAULT_SYMBOL_CAPS.get(normalized, fallback)
    token = _env_token(normalized)
    return max(1, _env_int(f"FUTURES_{token}_DYNAMIC_LEVERAGE_MAX", default)) if token else max(1, default)


def _signal_cap(entry_signal: str, fallback: int) -> int:
    signal = str(entry_signal or "").upper()
    default = fallback
    for marker, cap in _DEFAULT_SIGNAL_CAPS:
        if marker in signal:
            default = cap
            break
    token = _env_token(signal)
    return max(1, _env_int(f"FUTURES_{token}_DYNAMIC_LEVERAGE_MAX", default)) if token else max(1, default)


def _static_leverage(
    *,
    certainty: float,
    sl_distance_pct: float,
    hard_loss_cap_pct: float,
    leverage_min: int,
    leverage_max: int,
) -> DynamicLeverageDecision:
    min_bound = max(1, min(int(leverage_min), int(leverage_max)))
    max_bound = max(min_bound, int(leverage_max))
    if sl_distance_pct <= 0:
        leverage = None
        risk_cap = 0
    else:
        target = min_bound + max(0.0, min(0.99, certainty)) * (max_bound - min_bound)
        risk_cap = int(math.floor(hard_loss_cap_pct / sl_distance_pct))
        leverage = None if risk_cap < min_bound else max(min_bound, min(max_bound, int(round(target)), risk_cap))
    return DynamicLeverageDecision(
        leverage=leverage,
        enabled=False,
        min_leverage=min_bound,
        max_leverage=max_bound,
        score_cap=max_bound,
        stop_cap=risk_cap,
        symbol_cap=max_bound,
        signal_cap=max_bound,
        final_cap=min(max_bound, risk_cap) if risk_cap > 0 else 0,
        stop_margin_loss_pct=float(sl_distance_pct) * float(leverage or 0),
    )


def resolve_dynamic_leverage(
    *,
    certainty: float,
    sl_distance_pct: float,
    hard_loss_cap_pct: float,
    leverage_min: int,
    leverage_max: int,
    raw_score: float | int | None = None,
    symbol: str = "",
    entry_signal: str = "",
) -> DynamicLeverageDecision:
    if sl_distance_pct <= 0:
        return DynamicLeverageDecision(None, dynamic_leverage_enabled(), 1, 1, 0, 0, 0, 0, 0, 0.0)
    if not dynamic_leverage_enabled():
        return _static_leverage(
            certainty=certainty,
            sl_distance_pct=sl_distance_pct,
            hard_loss_cap_pct=hard_loss_cap_pct,
            leverage_min=leverage_min,
            leverage_max=leverage_max,
        )

    configured_max = max(1, min(int(leverage_max), dynamic_leverage_max()))
    min_bound = max(1, min(configured_max, dynamic_leverage_min()))
    score_cap = _score_cap(raw_score, certainty)
    symbol_cap = _symbol_cap(symbol, configured_max)
    signal_cap = _signal_cap(entry_signal, configured_max)
    max_margin_loss = max(
        0.0,
        min(
            float(hard_loss_cap_pct),
            _env_float("FUTURES_DYNAMIC_LEVERAGE_MAX_MARGIN_LOSS_PCT", float(hard_loss_cap_pct)),
        ),
    )
    stop_cap = int(math.floor(max_margin_loss / sl_distance_pct)) if max_margin_loss > 0 else 0
    final_cap = min(configured_max, score_cap, stop_cap, symbol_cap, signal_cap)
    leverage = None if final_cap < min_bound else max(min_bound, final_cap)
    return DynamicLeverageDecision(
        leverage=leverage,
        enabled=True,
        min_leverage=min_bound,
        max_leverage=configured_max,
        score_cap=score_cap,
        stop_cap=stop_cap,
        symbol_cap=symbol_cap,
        signal_cap=signal_cap,
        final_cap=final_cap,
        stop_margin_loss_pct=float(sl_distance_pct) * float(leverage or 0),
    )