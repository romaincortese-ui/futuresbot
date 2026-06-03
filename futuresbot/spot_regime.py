"""Market regime classification ported from mexc-bot-v2 (the spot bot).

Computes a multiplier from ATR expansion vs its 40-bar baseline plus the
gap between current price and 50-EMA, then maps the multiplier to a
discrete label:

    mult > 1.30           -> CRASH
    1.10 < mult <= 1.30   -> BEAR
    0.95 < mult <= 1.10   -> SIDEWAYS
    0.80 < mult <= 0.95   -> BULL
    mult <= 0.80          -> STRONG_BULL

The futures bot uses this label to decide whether to enable the early
``ADVERSE_PEAK_TRAIL`` exit (SIDEWAYS only) or let the position run to
its stop-loss (any trending regime).
"""

from __future__ import annotations

import os

import pandas as pd

# mexc-bot-v2 LiveConfig defaults — see mexcbot/runtime.py
# compute_market_regime_multiplier.
_HIGH_VOL_ATR_RATIO = 1.50
_LOW_VOL_ATR_RATIO = 0.70
_TIGHTEN_MULT = 1.20
_LOOSEN_MULT = 0.85
_STRONG_UPTREND_GAP = 0.05
_STRONG_DOWNTREND_GAP = -0.05
_TREND_MULT = 0.90


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
        return int(raw)
    except (TypeError, ValueError):
        return default


def _ema_gap(frame: pd.DataFrame | None) -> float | None:
    if frame is None or len(frame) < 50 or "close" not in frame.columns:
        return None
    try:
        close = frame["close"].astype(float)
        ema50 = close.ewm(span=50, adjust=False).mean()
        ema_value = float(ema50.iloc[-1])
        return float(close.iloc[-1]) / ema_value - 1.0 if ema_value > 0 else None
    except Exception:
        return None


def _ema_gap_delta(frame: pd.DataFrame | None, lookback_bars: int) -> float | None:
    if lookback_bars <= 0:
        return None
    if frame is None or len(frame) <= lookback_bars or "close" not in frame.columns:
        return None
    try:
        close = frame["close"].astype(float)
        ema50 = close.ewm(span=50, adjust=False).mean()
        gaps = close / ema50 - 1.0
        return float(gaps.iloc[-1] - gaps.iloc[-1 - lookback_bars])
    except Exception:
        return None


def compute_market_regime_multiplier(frame: pd.DataFrame | None) -> float:
    try:
        if (
            frame is None
            or len(frame) < 50
            or not {"high", "low", "close"}.issubset(frame.columns)
        ):
            return 1.0
        close = frame["close"].astype(float)
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        prev_close = close.shift(1)
        true_range = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr = true_range.ewm(alpha=1.0 / 14.0, adjust=False).mean()
        if len(atr) > 40 and float(atr.iloc[-41:-1].mean()) > 0:
            atr_ratio = float(atr.iloc[-1] / atr.iloc[-41:-1].mean())
        else:
            atr_ratio = 1.0
        ema50 = close.ewm(span=50, adjust=False).mean()
        ema_value = float(ema50.iloc[-1])
        ema_gap = float(close.iloc[-1]) / ema_value - 1.0 if ema_value > 0 else 0.0

        mult = 1.0
        if atr_ratio > _HIGH_VOL_ATR_RATIO:
            mult *= _TIGHTEN_MULT
        elif atr_ratio < _LOW_VOL_ATR_RATIO:
            mult *= _LOOSEN_MULT
        if ema_gap > _STRONG_UPTREND_GAP:
            mult *= _TREND_MULT
        elif ema_gap < _STRONG_DOWNTREND_GAP:
            mult *= _TIGHTEN_MULT
        return max(0.7, min(2.0, mult))
    except Exception:
        return 1.0


def classify_regime_label(mult: float) -> str:
    if mult > 1.30:
        return "CRASH"
    if mult > 1.10:
        return "BEAR"
    if mult > 0.95:
        return "SIDEWAYS"
    if mult > 0.80:
        return "BULL"
    return "STRONG_BULL"


def spot_regime_label(frame: pd.DataFrame | None) -> str:
    label = classify_regime_label(compute_market_regime_multiplier(frame))
    trend_gap = max(0.0, _env_float("FUTURES_REGIME_TREND_GAP", 0.015))
    lookback_bars = max(0, _env_int("FUTURES_REGIME_TREND_GAP_LOOKBACK_BARS", 1))
    gap = _ema_gap(frame)
    gap_delta = _ema_gap_delta(frame, lookback_bars)
    if label == "SIDEWAYS" and trend_gap > 0 and gap is not None:
        bullish_persistent = lookback_bars == 0 or (gap_delta is not None and gap_delta > 0)
        bearish_persistent = lookback_bars == 0 or (gap_delta is not None and gap_delta < 0)
        if gap >= trend_gap and bullish_persistent:
            return "BULL"
        if gap <= -trend_gap and bearish_persistent:
            return "BEAR"
    return label


def is_sideways(frame: pd.DataFrame | None) -> bool:
    return spot_regime_label(frame) == "SIDEWAYS"
