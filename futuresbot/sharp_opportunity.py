from __future__ import annotations

import dataclasses
import math
import os
from dataclasses import dataclass, field
from typing import Any, Iterable

import pandas as pd

from futuresbot.indicators import calc_atr, calc_ema, resample_ohlcv
from futuresbot.models import FuturesSignal


SHARP_EVENT_ALLOWED_ENTRY_SIGNALS: frozenset[str] = frozenset(
    {
        "SHARP_EVENT_BREAKOUT_LONG",
        "SHARP_EVENT_BREAKOUT_SHORT",
        "IMPULSE_EVENT_CONTINUATION_LONG",
        "IMPULSE_EVENT_CONTINUATION_SHORT",
        "MOMENTUM_BREAKAWAY_LONG",
        "MOMENTUM_BREAKAWAY_SHORT",
        "LEVEL_BREAK_LONG",
        "LEVEL_BREAK_SHORT",
        "RANGE_EXPANSION_CONTINUATION_LONG",
        "RANGE_EXPANSION_CONTINUATION_SHORT",
        "BREAKOUT_HOLD_LONG",
    }
)


@dataclass(frozen=True, slots=True)
class SharpOpportunityDecision:
    allowed: bool
    reason: str
    side: str | None = None
    score: float = 0.0
    risk_multiplier: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


def evaluate_sharp_opportunity_overlay(
    frame_15m: pd.DataFrame,
    *,
    symbol: str,
    core_symbols: Iterable[str] = (),
    enabled: bool = True,
    risk_multiplier: float = 0.35,
) -> SharpOpportunityDecision:
    """Return whether a non-core symbol has a temporary sharp-event permit.

    This is intentionally a permit, not an entry signal. Runtime/backtest code
    still calls the normal futures strategy and accepts only event-style entry
    signals that agree with the permit direction.
    """

    symbol_name = symbol.upper()
    if symbol_name in {item.upper() for item in core_symbols}:
        return SharpOpportunityDecision(True, "core_symbol", risk_multiplier=1.0)
    if not enabled:
        return SharpOpportunityDecision(False, "sharp_event_overlay_disabled")
    if frame_15m is None or frame_15m.empty:
        return SharpOpportunityDecision(False, "no_15m_frame")
    frame = frame_15m.copy().dropna()
    lookback_bars = max(24, _env_int("FUTURES_SHARP_EVENT_LOOKBACK_BARS", 96))
    confirm_bars = max(1, _env_int("FUTURES_SHARP_EVENT_CONFIRM_BARS", 2))
    required_bars = max(220, lookback_bars + confirm_bars + 32)
    if len(frame) < required_bars:
        return SharpOpportunityDecision(False, f"insufficient_15m_bars={len(frame)}<{required_bars}")

    try:
        close = frame["close"].astype(float)
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        volume = frame["volume"].astype(float)
        current_price = float(close.iloc[-1])
        if current_price <= 0 or not math.isfinite(current_price):
            return SharpOpportunityDecision(False, "invalid_current_price")

        atr_15_series = calc_atr(frame, 14)
        current_atr_15 = float(atr_15_series.iloc[-1]) if len(atr_15_series) else 0.0
        frame_1h = resample_ohlcv(frame, "1h")
        close_1h = frame_1h["close"].astype(float) if not frame_1h.empty else pd.Series(dtype=float)
        atr_1h_series = calc_atr(frame_1h, 14) if not frame_1h.empty else pd.Series(dtype=float)
        ema20_1h = calc_ema(close_1h, 20) if not close_1h.empty else pd.Series(dtype=float)
        current_atr_1h = float(atr_1h_series.iloc[-1]) if len(atr_1h_series) else current_atr_15
        current_ema20 = float(ema20_1h.iloc[-1]) if len(ema20_1h) else current_price
        if current_atr_15 <= 0 or current_atr_1h <= 0:
            return SharpOpportunityDecision(False, "indicator_not_ready")

        move_3h = _pct_change(close, 12)
        move_6h = _pct_change(close, 24)
        move_24h = _pct_change(close, 96)
        side_move = move_6h if abs(move_6h) >= abs(move_3h) * 0.75 else move_3h
        side = "LONG" if side_move >= 0 else "SHORT"
        reference_bars = 24 if abs(move_6h) >= abs(move_3h) * 0.75 else 12
        reference_price = float(close.iloc[-(reference_bars + 1)])
        move_pct = abs((current_price / reference_price) - 1.0) if reference_price > 0 else 0.0
        move_atr = abs(current_price - reference_price) / current_atr_15

        prior = frame.iloc[-(lookback_bars + confirm_bars):-confirm_bars]
        confirmation = frame.iloc[-confirm_bars:]
        if prior.empty or confirmation.empty:
            return SharpOpportunityDecision(False, "empty_breakout_window")
        prior_high = float(prior["high"].astype(float).max())
        prior_low = float(prior["low"].astype(float).min())
        confirm_close = confirmation["close"].astype(float)
        breakout_buffer = current_atr_15 * _env_float("FUTURES_SHARP_EVENT_BREAKOUT_BUFFER_ATR", 0.05)
        long_close_ratio = float((confirm_close >= prior_high + breakout_buffer).mean()) if prior_high > 0 else 0.0
        short_close_ratio = float((confirm_close <= prior_low - breakout_buffer).mean()) if prior_low > 0 else 0.0
        broke_high = current_price >= prior_high + breakout_buffer and long_close_ratio > 0
        broke_low = current_price <= prior_low - breakout_buffer and short_close_ratio > 0

        trigger_volume = max(1e-9, float(volume.iloc[-4:].mean()))
        prior_volume = volume.iloc[-36:-4]
        prior_volume_mean = max(1e-9, float(prior_volume.mean()) if not prior_volume.empty else float(volume.mean()))
        volume_ratio = trigger_volume / prior_volume_mean
        window_volume = float(volume.iloc[-8:].sum())
        window_volume_ratio = window_volume / max(1e-9, prior_volume_mean * min(8, len(volume)))

        recent_high = float(high.iloc[-8:].max())
        recent_low = float(low.iloc[-8:].min())
        close_buffer = current_atr_15 * _env_float("FUTURES_SHARP_EVENT_CLOSE_BUFFER_ATR", 0.35)
        close_near_high = current_price >= recent_high - close_buffer
        close_near_low = current_price <= recent_low + close_buffer
        ema_extension_atr = abs(current_price - current_ema20) / current_atr_1h
        trend_1h = _pct_change(close, 4)
        trend_6h = move_6h

        min_move_pct = _env_float("FUTURES_SHARP_EVENT_MIN_MOVE_PCT", 0.006)
        min_move_atr = _env_float("FUTURES_SHARP_EVENT_MIN_MOVE_ATR", 1.10)
        min_volume_ratio = _env_float("FUTURES_SHARP_EVENT_MIN_VOLUME_RATIO", 1.05)
        min_window_volume_ratio = _env_float("FUTURES_SHARP_EVENT_MIN_WINDOW_VOLUME_RATIO", 1.05)
        min_close_ratio = _env_float("FUTURES_SHARP_EVENT_MIN_CLOSE_RATIO", 0.50)
        max_ema_extension_atr = _env_float("FUTURES_SHARP_EVENT_MAX_EMA_EXTENSION_ATR", 4.50)
        max_move_atr = _env_float("FUTURES_SHARP_EVENT_MAX_MOVE_ATR", 7.50)
        max_counter_trend = _env_float("FUTURES_SHARP_EVENT_MAX_COUNTER_TREND_1H", 0.004)
        min_score = _env_float("FUTURES_SHARP_EVENT_MIN_SCORE", 72.0)

        volume_ok = volume_ratio >= min_volume_ratio or window_volume_ratio >= min_window_volume_ratio
        long_ok = (
            side == "LONG"
            and broke_high
            and long_close_ratio >= min_close_ratio
            and move_pct >= min_move_pct
            and move_atr >= min_move_atr
            and volume_ok
            and close_near_high
            and ema_extension_atr <= max_ema_extension_atr
            and move_atr <= max_move_atr
            and trend_1h >= -max_counter_trend
        )
        short_ok = (
            side == "SHORT"
            and broke_low
            and short_close_ratio >= min_close_ratio
            and move_pct >= min_move_pct
            and move_atr >= min_move_atr
            and volume_ok
            and close_near_low
            and ema_extension_atr <= max_ema_extension_atr
            and move_atr <= max_move_atr
            and trend_1h <= max_counter_trend
        )
        score = 45.0
        score += min(20.0, move_pct * 900.0)
        score += min(16.0, move_atr * 3.0)
        score += min(12.0, max(volume_ratio, window_volume_ratio) * 4.0)
        score += 8.0 if (broke_high or broke_low) else 0.0
        score += 5.0 if (close_near_high if side == "LONG" else close_near_low) else 0.0
        score += min(6.0, abs(trend_6h) * 300.0)
        if ema_extension_atr > max_ema_extension_atr * 0.80:
            score -= min(8.0, (ema_extension_atr - max_ema_extension_atr * 0.80) * 3.0)
        score = round(max(0.0, score), 2)
        metadata = {
            "sharp_event_score": score,
            "sharp_event_side": side,
            "sharp_event_price": round(current_price, 10),
            "sharp_event_move_3h_pct": round(move_3h, 6),
            "sharp_event_move_6h_pct": round(move_6h, 6),
            "sharp_event_move_24h_pct": round(move_24h, 6),
            "sharp_event_move_pct": round(move_pct, 6),
            "sharp_event_move_atr": round(move_atr, 4),
            "sharp_event_volume_ratio": round(volume_ratio, 4),
            "sharp_event_window_volume_ratio": round(window_volume_ratio, 4),
            "sharp_event_close_ratio": round(long_close_ratio if side == "LONG" else short_close_ratio, 4),
            "sharp_event_ema_extension_atr": round(ema_extension_atr, 4),
            "sharp_event_prior_high": round(prior_high, 10),
            "sharp_event_prior_low": round(prior_low, 10),
        }
        if not (long_ok or short_ok):
            return SharpOpportunityDecision(False, _blocked_reason(locals()), side=side, score=score, metadata=metadata)
        if score < min_score:
            return SharpOpportunityDecision(False, f"sharp_event_score={score:.2f}<{min_score:.2f}", side=side, score=score, metadata=metadata)
        return SharpOpportunityDecision(
            True,
            "sharp_event_permit",
            side=side,
            score=score,
            risk_multiplier=max(0.0, min(1.0, float(risk_multiplier or 0.0))),
            metadata=metadata,
        )
    except Exception as exc:
        return SharpOpportunityDecision(False, f"sharp_event_error={type(exc).__name__}")


def sharp_event_signal_allowed(signal: FuturesSignal, decision: SharpOpportunityDecision) -> bool:
    if not decision.allowed or decision.side is None:
        return bool(decision.allowed)
    if signal.side.upper() != decision.side.upper():
        return False
    if signal.entry_signal.upper() not in SHARP_EVENT_ALLOWED_ENTRY_SIGNALS:
        return False
    return _sharp_event_trade_filters_pass(decision)


def build_sharp_event_signal(
    frame_15m: pd.DataFrame,
    config: Any,
    decision: SharpOpportunityDecision,
    *,
    bypass_symbol_calibration: bool,
) -> FuturesSignal | None:
    if not _sharp_event_trade_filters_pass(decision):
        return None
    if frame_15m is None or frame_15m.empty or decision.side is None:
        return None
    frame = frame_15m.copy().dropna()
    if len(frame) < 220:
        return None
    try:
        close = frame["close"].astype(float)
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        current_price = float(close.iloc[-1])
        if current_price <= 0 or not math.isfinite(current_price):
            return None
        atr_series = calc_atr(frame, 14)
        current_atr = float(atr_series.iloc[-1]) if len(atr_series) else 0.0
        if current_atr <= 0 or not math.isfinite(current_atr):
            return None
        stop_lookback = max(4, _env_int("FUTURES_SHARP_EVENT_STOP_LOOKBACK_BARS", 12))
        recent_high = float(high.iloc[-stop_lookback:].max())
        recent_low = float(low.iloc[-stop_lookback:].min())
        min_stop_pct = max(0.001, _env_float("FUTURES_SHARP_EVENT_MIN_STOP_PCT", 0.022))
        max_stop_pct = max(min_stop_pct, _env_float("FUTURES_SHARP_EVENT_MAX_STOP_PCT", 0.032))
        swing_buffer_atr = max(0.0, _env_float("FUTURES_SHARP_EVENT_SWING_SL_BUFFER_ATR", 0.25))
        tp_move = max(
            current_atr * max(1.0, _env_float("FUTURES_SHARP_EVENT_TP_ATR_MULT", 9.0)),
            current_price * max(0.01, _env_float("FUTURES_SHARP_EVENT_TP_FLOOR_PCT", 0.075)),
        )
        side = decision.side.upper()
        if side == "LONG":
            swing_stop = recent_low - current_atr * swing_buffer_atr
            sl_price = max(current_price * (1.0 - max_stop_pct), min(swing_stop, current_price * (1.0 - min_stop_pct)))
            tp_price = current_price + tp_move
            entry_signal = "SHARP_EVENT_BREAKOUT_LONG"
            risk = current_price - sl_price
        elif side == "SHORT":
            swing_stop = recent_high + current_atr * swing_buffer_atr
            sl_price = min(current_price * (1.0 + max_stop_pct), max(swing_stop, current_price * (1.0 + min_stop_pct)))
            tp_price = current_price - tp_move
            entry_signal = "SHARP_EVENT_BREAKOUT_SHORT"
            risk = sl_price - current_price
        else:
            return None
        if risk <= 0 or tp_move / risk < float(getattr(config, "min_reward_risk", 1.0) or 1.0):
            return None
        metadata = {
            **decision.metadata,
            "sharp_event_overlay": 1.0,
            "sharp_event_reason": decision.reason,
            "sharp_event_risk_multiplier": float(decision.risk_multiplier),
            "sharp_event_bypass_symbol_calibration": 1.0 if bypass_symbol_calibration else 0.0,
            "sharp_event_synthetic_signal": 1.0,
            "sharp_event_stop_pct": round(risk / current_price, 6),
            "trailing_exit_activation_progress": _env_float("FUTURES_SHARP_EVENT_TRAILING_ACTIVATION_PROGRESS", 0.28),
            "trailing_exit_drawdown_pct": _env_float("FUTURES_SHARP_EVENT_TRAILING_DRAWDOWN_PCT", 0.02),
            "early_exit_min_profit_pct": _env_float("FUTURES_SHARP_EVENT_TRAILING_MIN_PROFIT_PCT", 0.018),
        }
        from futuresbot.strategy import _build_signal

        return _build_signal(
            side=side,
            score=max(float(decision.score), float(getattr(config, "min_confidence_score", 0.0) or 0.0)),
            entry_price=current_price,
            tp_price=tp_price,
            sl_price=sl_price,
            entry_signal=entry_signal,
            config=config,
            metadata=metadata,
        )
    except Exception:
        return None


def annotate_sharp_event_signal(
    signal: FuturesSignal,
    decision: SharpOpportunityDecision,
    *,
    bypass_symbol_calibration: bool,
) -> FuturesSignal:
    metadata = {
        **(signal.metadata or {}),
        **decision.metadata,
        "sharp_event_overlay": 1.0,
        "sharp_event_reason": decision.reason,
        "sharp_event_risk_multiplier": float(decision.risk_multiplier),
        "sharp_event_bypass_symbol_calibration": 1.0 if bypass_symbol_calibration else 0.0,
    }
    return dataclasses.replace(signal, metadata=metadata)


def _sharp_event_trade_filters_pass(decision: SharpOpportunityDecision) -> bool:
    if not decision.allowed or decision.side is None:
        return False
    if decision.side.upper() == "SHORT" and not _env_bool("FUTURES_SHARP_EVENT_ALLOW_SHORTS", False):
        return False
    metadata = decision.metadata or {}
    min_score = _env_float("FUTURES_SHARP_EVENT_SIGNAL_MIN_SCORE", 100.0)
    min_move_atr = _env_float("FUTURES_SHARP_EVENT_SIGNAL_MIN_MOVE_ATR", 4.75)
    min_ema_extension = _env_float("FUTURES_SHARP_EVENT_SIGNAL_MIN_EMA_EXTENSION_ATR", 2.85)
    min_directional_24h = _env_float("FUTURES_SHARP_EVENT_SIGNAL_MIN_24H_MOVE_PCT", 0.025)
    max_volume_ratio = _env_float("FUTURES_SHARP_EVENT_SIGNAL_MAX_VOLUME_RATIO", 3.0)
    max_window_volume_ratio = _env_float("FUTURES_SHARP_EVENT_SIGNAL_MAX_WINDOW_VOLUME_RATIO", 3.0)
    min_price = _env_float("FUTURES_SHARP_EVENT_SIGNAL_MIN_PRICE", 1.0)
    try:
        current_price = float(metadata.get("sharp_event_price") or 0.0)
        move_atr = float(metadata.get("sharp_event_move_atr") or 0.0)
        ema_extension = float(metadata.get("sharp_event_ema_extension_atr") or 0.0)
        move_24h = float(metadata.get("sharp_event_move_24h_pct") or 0.0)
        volume_ratio = float(metadata.get("sharp_event_volume_ratio") or 0.0)
        window_volume_ratio = float(metadata.get("sharp_event_window_volume_ratio") or 0.0)
    except (TypeError, ValueError):
        return False
    if float(decision.score or 0.0) < min_score:
        return False
    if current_price < min_price:
        return False
    if move_atr < min_move_atr:
        return False
    if ema_extension < min_ema_extension:
        return False
    if volume_ratio > max_volume_ratio or window_volume_ratio > max_window_volume_ratio:
        return False
    if decision.side.upper() == "LONG" and move_24h < min_directional_24h:
        return False
    if decision.side.upper() == "SHORT" and move_24h > -min_directional_24h:
        return False
    return True


def sharp_event_margin_multiplier(metadata: dict[str, Any] | None, default: float = 1.0) -> float:
    if not isinstance(metadata, dict) or float(metadata.get("sharp_event_overlay") or 0.0) < 1.0:
        return default
    try:
        value = float(metadata.get("sharp_event_risk_multiplier", default))
    except (TypeError, ValueError):
        value = default
    return max(0.0, min(1.0, value))


def _pct_change(close: pd.Series, bars: int) -> float:
    if len(close) <= bars:
        return 0.0
    previous = float(close.iloc[-(bars + 1)])
    current = float(close.iloc[-1])
    if previous <= 0:
        return 0.0
    return (current / previous) - 1.0


def _blocked_reason(values: dict[str, Any]) -> str:
    side = str(values.get("side") or "?")
    if side == "LONG" and not values.get("broke_high"):
        return "no_upside_breakout"
    if side == "SHORT" and not values.get("broke_low"):
        return "no_downside_breakout"
    if float(values.get("move_pct") or 0.0) < float(values.get("min_move_pct") or 0.0):
        return "move_pct_below_floor"
    if float(values.get("move_atr") or 0.0) < float(values.get("min_move_atr") or 0.0):
        return "move_atr_below_floor"
    if not values.get("volume_ok"):
        return "volume_ratio_below_floor"
    if float(values.get("ema_extension_atr") or 0.0) > float(values.get("max_ema_extension_atr") or 0.0):
        return "late_chase_ema_extension"
    if float(values.get("move_atr") or 0.0) > float(values.get("max_move_atr") or 0.0):
        return "late_chase_move_atr"
    return "sharp_event_conditions_not_met"


def _env_float(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name)
        if raw is None or raw.strip() == "":
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        raw = os.environ.get(name)
        if raw is None or raw.strip() == "":
            return default
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
