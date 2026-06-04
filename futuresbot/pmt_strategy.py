from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

import pandas as pd

from futuresbot.models import FuturesSignal


PMT_STRATEGY_MODE = "pmt_threshold"

ELIGIBLE_PMT_SYMBOLS: tuple[str, ...] = (
    "BTC_USDT",
    "ETH_USDT",
    "SOL_USDT",
    "BNB_USDT",
    "SEI_USDT",
    "ZEC_USDT",
)

PMT_WIN_COOLDOWN_EXIT_REASONS = frozenset({"TAKE_PROFIT", "PEAK_PROFIT_LOCK"})


def pmt_win_cooldown_exit_reason(reason: object) -> bool:
    return str(reason or "").upper() in PMT_WIN_COOLDOWN_EXIT_REASONS


@dataclass(frozen=True, slots=True)
class PairPMTProfile:
    symbol: str
    threshold_step: float
    flat_24h_pct: float
    flash_6h_pct: float
    mega_12h_pct: float
    mega_24h_pct: float


DEFAULT_PMT_PROFILES: dict[str, PairPMTProfile] = {
    "BTC_USDT": PairPMTProfile("BTC_USDT", 1000.0, 0.008, 0.010, 0.030, 0.050),
    "ETH_USDT": PairPMTProfile("ETH_USDT", 50.0, 0.010, 0.013, 0.040, 0.060),
    "SOL_USDT": PairPMTProfile("SOL_USDT", 10.0, 0.012, 0.016, 0.050, 0.075),
    "BNB_USDT": PairPMTProfile("BNB_USDT", 75.0, 0.011, 0.015, 0.048, 0.080),
    "SEI_USDT": PairPMTProfile("SEI_USDT", 0.01, 0.020, 0.030, 0.080, 0.120),
    "ZEC_USDT": PairPMTProfile("ZEC_USDT", 100.0, 0.030, 0.045, 0.110, 0.170),
}


@dataclass(frozen=True, slots=True)
class PairMarketTrend:
    symbol: str
    label: str
    move_24h_pct: float
    move_12h_pct: float
    move_6h_pct: float


@dataclass(frozen=True, slots=True)
class MentalThresholdCross:
    side: str
    level: float
    previous_close: float
    current_close: float
    move_1bar_pct: float
    distance_beyond_level_pct: float
    cross_previous_close: float | None = None
    cross_close: float | None = None
    confirmation_bars: int = 0


def pmt_strategy_enabled() -> bool:
    mode = os.environ.get("FUTURES_STRATEGY_MODE", "").strip().lower()
    if mode == PMT_STRATEGY_MODE:
        return True
    return os.environ.get("FUTURES_PMT_STRATEGY_ENABLED", "0").strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_symbol_set(raw: str) -> set[str]:
    return {item.strip().upper() for item in raw.replace(";", ",").replace(" ", ",").split(",") if item.strip()}


def pmt_symbol_allowed(symbol: str) -> bool:
    symbol = symbol.upper()
    if symbol not in DEFAULT_PMT_PROFILES:
        return False
    tokens = _parse_symbol_set(os.environ.get("FUTURES_PMT_SYMBOLS", ",".join(ELIGIBLE_PMT_SYMBOLS)))
    if not tokens or "*" in tokens or "ALL" in tokens:
        tokens = set(ELIGIBLE_PMT_SYMBOLS)
    return symbol in tokens


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


def _env_pct_fraction(name: str, default: float) -> float:
    value = _env_float(name, default)
    return value / 100.0 if value > 1.0 else value


def _signed_for_side(value: float, side: str) -> float:
    return value if side.upper() == "LONG" else -value


def _symbol_env_prefix(symbol: str) -> str:
    cleaned = "".join(ch for ch in symbol.upper() if ch.isalnum())
    return f"FUTURES_{cleaned}"


def pair_pmt_profile(symbol: str) -> PairPMTProfile | None:
    symbol = symbol.upper()
    base = DEFAULT_PMT_PROFILES.get(symbol)
    if base is None:
        return None
    prefix = _symbol_env_prefix(symbol)
    return PairPMTProfile(
        symbol=symbol,
        threshold_step=mental_threshold_step(symbol, _base_profile=base),
        flat_24h_pct=max(0.0, _env_pct_fraction(f"{prefix}_PMT_FLAT_24H_PCT", base.flat_24h_pct)),
        flash_6h_pct=max(0.0, _env_pct_fraction(f"{prefix}_PMT_FLASH_6H_PCT", base.flash_6h_pct)),
        mega_12h_pct=max(0.0, _env_pct_fraction(f"{prefix}_PMT_MEGA_12H_PCT", base.mega_12h_pct)),
        mega_24h_pct=max(0.0, _env_pct_fraction(f"{prefix}_PMT_MEGA_24H_PCT", base.mega_24h_pct)),
    )


def mental_threshold_step(symbol: str, *, _base_profile: PairPMTProfile | None = None) -> float:
    symbol = symbol.upper()
    per_symbol = _env_float(f"{_symbol_env_prefix(symbol)}_PMT_THRESHOLD_STEP", 0.0)
    if per_symbol > 0:
        return per_symbol
    raw = os.environ.get("FUTURES_PMT_MENTAL_THRESHOLD_STEPS", "")
    for item in raw.split(","):
        if ":" not in item:
            continue
        key, value = item.split(":", 1)
        if key.strip().upper() != symbol:
            continue
        try:
            parsed = float(value.strip())
        except ValueError:
            parsed = 0.0
        if parsed > 0:
            return parsed
    base = _base_profile or DEFAULT_PMT_PROFILES.get(symbol)
    if base is not None:
        return base.threshold_step
    return max(0.000001, _env_float("FUTURES_PMT_DEFAULT_THRESHOLD_STEP", 1.0))


def _close_hours_ago(frame: pd.DataFrame, hours: float) -> float | None:
    if frame is None or len(frame) < 2 or "close" not in frame:
        return None
    close = frame["close"].astype(float)
    index = frame.index
    if isinstance(index, pd.DatetimeIndex) and len(index) == len(frame):
        end = index[-1]
        if end.tzinfo is None:
            end = end.tz_localize("UTC")
            index = index.tz_localize("UTC") if index.tz is None else index
        cutoff = end - pd.Timedelta(hours=hours)
        eligible = index[index <= cutoff]
        if len(eligible) > 0:
            return float(close.loc[eligible[-1]])
    fallback_bars = max(1, int(round(hours * 4)))
    if len(close) <= fallback_bars:
        return None
    return float(close.iloc[-fallback_bars - 1])


def _pct_change(current: float, previous: float | None) -> float | None:
    if previous is None or previous <= 0 or current <= 0:
        return None
    return current / previous - 1.0


def classify_pair_market_trend(frame: pd.DataFrame, symbol: str) -> PairMarketTrend | None:
    if frame is None or len(frame) < 100 or "close" not in frame:
        return None
    profile = pair_pmt_profile(symbol)
    if profile is None:
        return None
    current = float(frame["close"].astype(float).iloc[-1])
    move_24h = _pct_change(current, _close_hours_ago(frame, 24.0))
    move_12h = _pct_change(current, _close_hours_ago(frame, 12.0))
    move_6h = _pct_change(current, _close_hours_ago(frame, 6.0))
    if move_24h is None or move_12h is None or move_6h is None:
        return None

    if move_12h <= -profile.mega_12h_pct or move_24h <= -profile.mega_24h_pct:
        label = "MEGA_BEARISH"
    elif move_12h >= profile.mega_12h_pct or move_24h >= profile.mega_24h_pct:
        label = "MEGA_BULLISH"
    elif move_6h <= -profile.flash_6h_pct:
        label = "FLASH_BEARISH"
    elif move_6h >= profile.flash_6h_pct:
        label = "FLASH_BULLISH"
    elif abs(move_24h) < profile.flat_24h_pct:
        label = "FLAT"
    elif move_24h <= -profile.flat_24h_pct:
        label = "BEARISH"
    else:
        label = "BULLISH"

    return PairMarketTrend(
        symbol=symbol.upper(),
        label=label,
        move_24h_pct=move_24h,
        move_12h_pct=move_12h,
        move_6h_pct=move_6h,
    )


def _detect_threshold_cross(previous: float, current: float, symbol: str) -> MentalThresholdCross | None:
    step = mental_threshold_step(symbol)
    if previous <= 0 or current <= 0 or step <= 0:
        return None

    down_level = math.floor(previous / step) * step
    if down_level > 0 and current < down_level <= previous:
        return MentalThresholdCross(
            side="SHORT",
            level=down_level,
            previous_close=previous,
            current_close=current,
            move_1bar_pct=current / previous - 1.0,
            distance_beyond_level_pct=abs(current - down_level) / current,
            cross_previous_close=previous,
            cross_close=current,
        )

    up_level = math.ceil(previous / step) * step
    if up_level > 0 and current > up_level >= previous:
        return MentalThresholdCross(
            side="LONG",
            level=up_level,
            previous_close=previous,
            current_close=current,
            move_1bar_pct=current / previous - 1.0,
            distance_beyond_level_pct=abs(current - up_level) / current,
            cross_previous_close=previous,
            cross_close=current,
        )
    return None


def _pmt_confirmation_bars() -> int:
    return max(0, _env_int("FUTURES_PMT_CONFIRMATION_BARS", 1))


def detect_mental_threshold_cross(frame: pd.DataFrame, symbol: str) -> MentalThresholdCross | None:
    if frame is None or len(frame) < 2 or "close" not in frame:
        return None
    closes = frame["close"].astype(float)
    confirmation_bars = _pmt_confirmation_bars()
    if confirmation_bars <= 0:
        return _detect_threshold_cross(float(closes.iloc[-2]), float(closes.iloc[-1]), symbol)
    if len(closes) < confirmation_bars + 2:
        return None
    cross_position = len(closes) - 1 - confirmation_bars
    cross = _detect_threshold_cross(float(closes.iloc[cross_position - 1]), float(closes.iloc[cross_position]), symbol)
    if cross is None:
        return None
    confirmation = closes.iloc[cross_position + 1 :].astype(float)
    if cross.side == "SHORT" and any(float(close) >= cross.level for close in confirmation):
        return None
    if cross.side == "LONG" and any(float(close) <= cross.level for close in confirmation):
        return None
    previous = float(closes.iloc[-2])
    current = float(closes.iloc[-1])
    return MentalThresholdCross(
        side=cross.side,
        level=cross.level,
        previous_close=previous,
        current_close=current,
        move_1bar_pct=current / previous - 1.0 if previous > 0 else 0.0,
        distance_beyond_level_pct=abs(current - cross.level) / current if current > 0 else 0.0,
        cross_previous_close=cross.previous_close,
        cross_close=cross.current_close,
        confirmation_bars=confirmation_bars,
    )


def _aligned_with_pmt(side: str, label: str) -> bool | None:
    side = side.upper()
    label = label.upper()
    if label == "FLAT":
        return None
    bullish = label in {"BULLISH", "FLASH_BULLISH", "MEGA_BULLISH"}
    bearish = label in {"BEARISH", "FLASH_BEARISH", "MEGA_BEARISH"}
    if bullish:
        return side == "LONG"
    if bearish:
        return side == "SHORT"
    return None


def _pmt_blocks_side(side: str, label: str) -> bool:
    side = side.upper()
    label = label.upper()
    if label == "MEGA_BEARISH" and side == "LONG":
        return True
    if label == "MEGA_BULLISH" and side == "SHORT":
        return True
    if label == "FLASH_BEARISH" and side == "LONG":
        return _env_float("FUTURES_PMT_FLASH_COUNTERTREND_MIN_SCORE", 999.0) >= 999.0
    if label == "FLASH_BULLISH" and side == "SHORT":
        return _env_float("FUTURES_PMT_FLASH_COUNTERTREND_MIN_SCORE", 999.0) >= 999.0
    return False


def _volume_ratio(frame: pd.DataFrame, lookback: int = 20) -> float:
    if "volume" not in frame or len(frame) < lookback + 1:
        return 1.0
    volume = frame["volume"].astype(float)
    baseline = float(volume.iloc[-lookback - 1 : -1].mean())
    if baseline <= 0:
        return 1.0
    return max(0.0, float(volume.iloc[-1]) / baseline)


def _recent_move_pct(frame: pd.DataFrame, bars: int) -> float:
    close = frame["close"].astype(float)
    if len(close) <= bars or float(close.iloc[-bars - 1]) <= 0:
        return 0.0
    return float(close.iloc[-1]) / float(close.iloc[-bars - 1]) - 1.0


def _recent_failed_level_reclaim(frame: pd.DataFrame, cross: MentalThresholdCross) -> bool:
    lookback = max(0, _env_int("FUTURES_PMT_RECENT_RECLAIM_LOOKBACK_BARS", 16))
    if lookback <= 0 or "close" not in frame:
        return False
    closes = frame["close"].astype(float).tolist()
    cross_position = len(closes) - 1 - max(0, int(cross.confirmation_bars or 0))
    start = max(1, cross_position - lookback)
    prior = closes[start:cross_position]
    if len(prior) < 2:
        return False
    failed_break_seen = False
    if cross.side == "SHORT":
        for close in prior:
            if close < cross.level:
                failed_break_seen = True
            elif failed_break_seen and close >= cross.level:
                return True
    else:
        for close in prior:
            if close > cross.level:
                failed_break_seen = True
            elif failed_break_seen and close <= cross.level:
                return True
    return False


def _broader_trend_conflict(pmt: PairMarketTrend, side: str) -> bool:
    if not _env_bool("FUTURES_PMT_BLOCK_BROADER_TREND_CONFLICT", True):
        return False
    profile = pair_pmt_profile(pmt.symbol)
    if profile is None:
        return False
    side = side.upper()
    if side == "LONG" and pmt.move_24h_pct <= -profile.flat_24h_pct:
        return True
    if side == "SHORT" and pmt.move_24h_pct >= profile.flat_24h_pct:
        return True
    return False


def _confirmation_followthrough_failed(cross: MentalThresholdCross) -> bool:
    min_followthrough = max(0.0, _env_pct_fraction("FUTURES_PMT_CONFIRMATION_MIN_FOLLOWTHROUGH_PCT", 0.0005))
    if min_followthrough <= 0 or int(cross.confirmation_bars or 0) <= 0:
        return False
    cross_close = float(cross.cross_close if cross.cross_close is not None else cross.current_close)
    if cross_close <= 0:
        return False
    if cross.side == "SHORT":
        return cross.current_close > cross_close * (1.0 - min_followthrough)
    return cross.current_close < cross_close * (1.0 + min_followthrough)


def _pmt_safety_rejection(frame: pd.DataFrame, pmt: PairMarketTrend, cross: MentalThresholdCross) -> str | None:
    if _confirmation_followthrough_failed(cross):
        return "confirmation_no_followthrough"
    if _env_bool("FUTURES_PMT_BLOCK_RECENT_FAILED_RECLAIM", True) and _recent_failed_level_reclaim(frame, cross):
        return "recent_failed_reclaim"
    if _broader_trend_conflict(pmt, cross.side):
        return "broader_trend_conflict"
    return None


def pmt_balance_fraction_for_score(score: float | int | None) -> float:
    try:
        value = float(score or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(value) or value < 85.0:
        return 0.0
    if value < 92.0:
        return max(0.0, min(1.0, _env_float("FUTURES_PMT_SCORE_BAND_SIZE_85_91", 0.25)))
    if value < 97.0:
        return max(0.0, min(1.0, _env_float("FUTURES_PMT_SCORE_BAND_SIZE_92_96", 0.50)))
    return max(0.0, min(1.0, _env_float("FUTURES_PMT_SCORE_BAND_SIZE_97_100", 1.00)))


def _score_cap(caps: dict[str, float], reason: str, cap: float) -> None:
    cap = max(0.0, min(100.0, float(cap)))
    current = caps.get(reason)
    caps[reason] = cap if current is None else min(current, cap)


def _trend_ratio(value: float, threshold: float) -> float:
    if threshold <= 0:
        return 0.0
    return max(0.0, value / threshold)


def _edge_score_threshold_cross(
    pmt: PairMarketTrend,
    cross: MentalThresholdCross,
    aligned: bool | None,
    *,
    signed_1bar: float,
    signed_1h: float,
    signed_6h: float,
    volume_ratio: float,
    penalties: dict[str, float],
) -> tuple[float, dict[str, float], dict[str, float]]:
    profile = pair_pmt_profile(pmt.symbol)
    signed_12h = _signed_for_side(pmt.move_12h_pct, cross.side)
    signed_24h = _signed_for_side(pmt.move_24h_pct, cross.side)
    level_distance = max(0.0, float(cross.distance_beyond_level_pct or 0.0))

    score = 58.0
    if aligned is True:
        score += {
            "BEARISH": 6.0,
            "BULLISH": 6.0,
            "FLASH_BEARISH": 10.0,
            "FLASH_BULLISH": 10.0,
            "MEGA_BEARISH": 14.0,
            "MEGA_BULLISH": 14.0,
        }.get(pmt.label, 0.0)
    elif aligned is False:
        score -= 20.0
    else:
        score += 5.0

    if profile is not None:
        score += min(10.0, _trend_ratio(signed_24h, profile.flat_24h_pct) * 3.0)
        score += min(9.0, _trend_ratio(signed_12h, profile.mega_12h_pct) * 9.0)
        score += min(8.0, _trend_ratio(signed_6h, profile.flash_6h_pct) * 5.0)
    else:
        score += min(10.0, max(0.0, signed_24h * 100.0 * 1.2))
        score += min(9.0, max(0.0, signed_12h * 100.0 * 1.0))
        score += min(8.0, max(0.0, signed_6h * 100.0 * 1.0))

    score += min(4.0, max(0.0, signed_1h * 100.0 * 1.5))
    score += min(4.0, max(0.0, signed_1bar * 100.0 * 2.0))

    if 0.0005 <= level_distance <= 0.0080:
        score += 5.0
    elif level_distance < 0.0005:
        score -= 4.0
    else:
        score -= min(10.0, (level_distance - 0.0080) * 100.0 * 8.0)

    if 1.05 <= volume_ratio <= 2.25:
        score += min(4.0, (volume_ratio - 1.0) * 3.0)
    elif volume_ratio > 2.25:
        score -= min(8.0, (volume_ratio - 2.25) * 5.0)
    elif volume_ratio < 0.80:
        score -= 4.0

    caps: dict[str, float] = {}
    late_distance = max(0.0, _env_pct_fraction("FUTURES_PMT_LATE_ENTRY_DISTANCE_PCT", 0.0100))
    extreme_late_distance = max(late_distance, _env_pct_fraction("FUTURES_PMT_EXTREME_LATE_ENTRY_DISTANCE_PCT", 0.0180))
    if late_distance > 0 and level_distance >= late_distance:
        _score_cap(caps, "late_entry_distance", _env_float("FUTURES_PMT_LATE_ENTRY_SCORE_CAP", 82.0))
    if extreme_late_distance > 0 and level_distance >= extreme_late_distance:
        _score_cap(caps, "extreme_late_entry_distance", _env_float("FUTURES_PMT_EXTREME_LATE_ENTRY_SCORE_CAP", 72.0))

    volume_climax = max(0.0, _env_float("FUTURES_PMT_VOLUME_CLIMAX_RATIO", 1.50))
    exhausted = "one_bar_exhaustion" in penalties or "one_hour_exhaustion" in penalties
    if exhausted and volume_climax > 0 and volume_ratio >= volume_climax:
        _score_cap(caps, "exhausted_volume_climax", _env_float("FUTURES_PMT_EXHAUSTED_CLIMAX_SCORE_CAP", 75.0))
    elif "one_hour_exhaustion" in penalties:
        _score_cap(caps, "one_hour_exhaustion", _env_float("FUTURES_PMT_ONE_HOUR_EXHAUSTION_SCORE_CAP", 94.0))
    elif len(penalties) >= 2:
        _score_cap(caps, "stacked_exhaustion", _env_float("FUTURES_PMT_STACKED_EXHAUSTION_SCORE_CAP", 82.0))

    if pmt.label.startswith("FLASH_"):
        _score_cap(caps, "flash_trend_unproven", _env_float("FUTURES_PMT_FLASH_SCORE_CAP", 94.0))

    if profile is not None and signed_24h < profile.flat_24h_pct:
        _score_cap(caps, "weak_broader_trend", _env_float("FUTURES_PMT_WEAK_BROADER_TREND_SCORE_CAP", 90.0))

    weak_followthrough = max(0.0, _env_pct_fraction("FUTURES_PMT_WEAK_FOLLOWTHROUGH_1BAR_PCT", 0.0020))
    if not pmt.label.startswith("MEGA_") and weak_followthrough > 0 and signed_1bar < weak_followthrough and volume_ratio >= 1.50:
        _score_cap(caps, "weak_followthrough_on_volume", _env_float("FUTURES_PMT_WEAK_FOLLOWTHROUGH_SCORE_CAP", 90.0))

    raw_edge_score = max(0.0, score)
    capped_edge_score = min(raw_edge_score, min(caps.values()) if caps else 100.0)
    features = {
        "pmt_edge_raw_score": round(raw_edge_score, 4),
        "pmt_edge_score_cap": round(min(caps.values()) if caps else 100.0, 4),
        "signed_1bar_pct": round(signed_1bar, 6),
        "signed_1h_pct": round(signed_1h, 6),
        "signed_6h_pct": round(signed_6h, 6),
        "signed_12h_pct": round(signed_12h, 6),
        "signed_24h_pct": round(signed_24h, 6),
    }
    return max(0.0, min(100.0, capped_edge_score)), caps, features


def _score_threshold_cross(frame: pd.DataFrame, pmt: PairMarketTrend, cross: MentalThresholdCross) -> tuple[float, dict[str, Any]]:
    profile = pair_pmt_profile(pmt.symbol)
    aligned = _aligned_with_pmt(cross.side, pmt.label)
    score = 58.0
    if aligned is True:
        score += {
            "BEARISH": 14.0,
            "BULLISH": 14.0,
            "FLASH_BEARISH": 20.0,
            "FLASH_BULLISH": 20.0,
            "MEGA_BEARISH": 28.0,
            "MEGA_BULLISH": 28.0,
        }.get(pmt.label, 0.0)
    elif aligned is False:
        score -= 24.0
    else:
        score += 8.0

    signed_1bar = _signed_for_side(cross.move_1bar_pct, cross.side)
    signed_1h = _recent_move_pct(frame, 4)
    signed_1h = _signed_for_side(signed_1h, cross.side)
    signed_6h = _signed_for_side(pmt.move_6h_pct, cross.side)
    volume_ratio = _volume_ratio(frame)

    score += min(10.0, max(0.0, signed_1bar * 100.0 * 18.0))
    score += min(8.0, max(0.0, signed_1h * 100.0 * 4.0))
    score += min(8.0, max(0.0, signed_6h * 100.0 * 1.4))
    score += min(6.0, max(0.0, cross.distance_beyond_level_pct * 100.0 * 12.0))
    if volume_ratio >= 1.05:
        score += min(8.0, (volume_ratio - 1.0) * 10.0)
    elif volume_ratio < 0.75:
        score -= 4.0

    raw_score = score
    penalties: dict[str, float] = {}
    exhaustion_1bar = max(0.0, _env_pct_fraction("FUTURES_PMT_EXHAUSTION_1BAR_PCT", 0.0060))
    if exhaustion_1bar > 0 and signed_1bar >= exhaustion_1bar:
        penalties["one_bar_exhaustion"] = max(0.0, _env_float("FUTURES_PMT_EXHAUSTION_1BAR_PENALTY", 10.0))
    exhaustion_1h = max(0.0, _env_pct_fraction("FUTURES_PMT_EXHAUSTION_1H_PCT", 0.0120))
    if exhaustion_1h > 0 and signed_1h >= exhaustion_1h:
        penalties["one_hour_exhaustion"] = max(0.0, _env_float("FUTURES_PMT_EXHAUSTION_1H_PENALTY", 8.0))
    volume_climax = max(0.0, _env_float("FUTURES_PMT_VOLUME_CLIMAX_RATIO", 1.50))
    if volume_climax > 0 and volume_ratio >= volume_climax and signed_1bar >= max(0.0, exhaustion_1bar * 0.75):
        penalties["volume_climax"] = max(0.0, _env_float("FUTURES_PMT_VOLUME_CLIMAX_PENALTY", 6.0))
    score -= sum(penalties.values())
    setup_score = max(0.0, min(100.0, score))
    edge_score, caps, edge_features = _edge_score_threshold_cross(
        pmt,
        cross,
        aligned,
        signed_1bar=signed_1bar,
        signed_1h=signed_1h,
        signed_6h=signed_6h,
        volume_ratio=volume_ratio,
        penalties=penalties,
    )
    final_score = min(setup_score, edge_score) if _env_bool("FUTURES_PMT_EDGE_SCORING_ENABLED", True) else setup_score

    metadata = {
        "strategy": PMT_STRATEGY_MODE,
        "pmt_score_model": "setup_edge_v1" if _env_bool("FUTURES_PMT_EDGE_SCORING_ENABLED", True) else "setup_only_v1",
        "pmt_label": pmt.label,
        "pmt_move_24h_pct": round(pmt.move_24h_pct, 6),
        "pmt_move_12h_pct": round(pmt.move_12h_pct, 6),
        "pmt_move_6h_pct": round(pmt.move_6h_pct, 6),
        "mental_threshold_level": round(cross.level, 10),
        "mental_threshold_step": mental_threshold_step(pmt.symbol),
        "pmt_flat_24h_pct_threshold": round(profile.flat_24h_pct, 6) if profile else None,
        "pmt_flash_6h_pct_threshold": round(profile.flash_6h_pct, 6) if profile else None,
        "pmt_mega_12h_pct_threshold": round(profile.mega_12h_pct, 6) if profile else None,
        "pmt_mega_24h_pct_threshold": round(profile.mega_24h_pct, 6) if profile else None,
        "mental_threshold_previous_close": round(cross.previous_close, 10),
        "mental_threshold_current_close": round(cross.current_close, 10),
        "mental_threshold_cross_previous_close": round(cross.cross_previous_close if cross.cross_previous_close is not None else cross.previous_close, 10),
        "mental_threshold_cross_close": round(cross.cross_close if cross.cross_close is not None else cross.current_close, 10),
        "mental_threshold_confirmation_bars": int(cross.confirmation_bars or 0),
        "mental_threshold_distance_beyond_pct": round(cross.distance_beyond_level_pct, 6),
        "move_1bar_pct": round(cross.move_1bar_pct, 6),
        "move_1h_pct": round(_recent_move_pct(frame, 4), 6),
        "volume_ratio_20": round(volume_ratio, 4),
        "pmt_aligned": aligned if aligned is not None else "flat",
        "pmt_raw_score": round(raw_score, 4),
        "pmt_setup_score": round(setup_score, 4),
        "pmt_edge_score": round(edge_score, 4),
        "pmt_score_caps": {key: round(value, 4) for key, value in caps.items()},
        "pmt_score_penalty": round(sum(penalties.values()), 4),
        "pmt_score_penalties": {key: round(value, 4) for key, value in penalties.items()},
        **edge_features,
    }
    return max(0.0, min(100.0, final_score)), metadata


def _leverage_for_score(score: float, pmt_label: str) -> int:
    min_lev = max(1, int(_env_float("FUTURES_PMT_MIN_LEVERAGE", _env_float("FUTURES_LEVERAGE_MIN", 15.0))))
    max_lev = max(min_lev, int(_env_float("FUTURES_PMT_MAX_LEVERAGE", _env_float("FUTURES_LEVERAGE_MAX", 25.0))))
    if not _env_bool("FUTURES_PMT_EDGE_SCORING_ENABLED", True):
        if score >= 92.0 or pmt_label.startswith("MEGA_"):
            target = max_lev
        elif score >= 84.0:
            target = min(max_lev, 35)
        else:
            target = min(max_lev, 25)
        return max(min_lev, min(max_lev, int(target)))
    if score >= 97.0:
        target = max_lev
    elif score >= 92.0:
        target = min(max_lev, min_lev + round((max_lev - min_lev) * 0.70))
    elif score >= 85.0:
        target = min(max_lev, min_lev + round((max_lev - min_lev) * 0.40))
    else:
        target = min_lev
    return max(min_lev, min(max_lev, int(target)))


def _tp_margin_pct(score: float) -> float:
    cap = max(0.0, _env_float("FUTURES_PMT_TP_MARGIN_CAP_PCT", 200.0))
    floor = max(0.0, _env_float("FUTURES_PMT_TP_MARGIN_FLOOR_PCT", 100.0))
    value = floor + max(0.0, score - 70.0) * 5.0
    return min(cap, value)


def _sl_margin_pct(score: float, *, leverage: int, taker_fee_rate: float) -> float:
    cap = max(0.0, _env_float("FUTURES_PMT_SL_MARGIN_CAP_PCT", 20.0))
    fee_margin_pct = max(0.0, taker_fee_rate) * 2.0 * max(1, leverage) * 100.0
    cap = max(0.0, cap - fee_margin_pct)
    floor = max(0.0, _env_float("FUTURES_PMT_SL_MARGIN_FLOOR_PCT", 10.0))
    floor = min(floor, cap)
    value = floor + max(0.0, score - 70.0) * 0.7
    return min(cap, value)


def _target_prices(entry_price: float, side: str, leverage: int, tp_margin_pct: float, sl_margin_pct: float) -> tuple[float, float]:
    tp_move = (tp_margin_pct / 100.0) / max(1, leverage)
    sl_move = (sl_margin_pct / 100.0) / max(1, leverage)
    if side == "LONG":
        return entry_price * (1.0 + tp_move), entry_price * (1.0 - sl_move)
    return entry_price * (1.0 - tp_move), entry_price * (1.0 + sl_move)


def score_pmt_threshold_signal(frame: pd.DataFrame, config: Any) -> FuturesSignal | None:
    symbol = str(getattr(config, "symbol", "BTC_USDT") or "BTC_USDT").upper()
    if not pmt_symbol_allowed(symbol):
        return None
    pmt = classify_pair_market_trend(frame, symbol)
    cross = detect_mental_threshold_cross(frame, symbol)
    if pmt is None or cross is None:
        return None
    if _pmt_blocks_side(cross.side, pmt.label):
        return None
    if _pmt_safety_rejection(frame, pmt, cross) is not None:
        return None

    score, metadata = _score_threshold_cross(frame, pmt, cross)
    min_score = max(0.0, _env_float("FUTURES_PMT_MIN_SCORE", float(getattr(config, "min_confidence_score", 70.0) or 70.0)))
    metadata["pmt_min_score"] = round(min_score, 4)
    if score < min_score:
        return None

    leverage = _leverage_for_score(score, pmt.label)
    entry_price = cross.current_close
    tp_margin_pct = _tp_margin_pct(score)
    taker_fee_rate = float(getattr(config, "taker_fee_rate", _env_float("MEXC_PERP_DEFAULT_TAKER_FEE_RATE", 0.0008)) or 0.0008)
    sl_margin_pct = _sl_margin_pct(score, leverage=leverage, taker_fee_rate=taker_fee_rate)
    tp_price, sl_price = _target_prices(entry_price, cross.side, leverage, tp_margin_pct, sl_margin_pct)
    metadata.update(
        {
            "tp_margin_pct": round(tp_margin_pct, 4),
            "sl_margin_pct": round(sl_margin_pct, 4),
            "tp_price_move_pct": round(abs(tp_price - entry_price) / entry_price, 6),
            "sl_price_move_pct": round(abs(entry_price - sl_price) / entry_price, 6),
            "opportunity_score_10": int(max(1, min(10, round(score / 10.0)))),
            "opportunity_balance_fraction": pmt_balance_fraction_for_score(score),
            "pmt_balance_fraction": pmt_balance_fraction_for_score(score),
            "opportunity_nav_risk_pct": 1.0,
            "profit_lock_trigger_pct_override": max(0.0, _env_float("FUTURES_PMT_PROFIT_LOCK_TRIGGER_PCT", 20.0)),
            "profit_lock_giveback_pct_override": max(0.0, _env_float("FUTURES_PMT_PROFIT_LOCK_GIVEBACK_PCT", 0.0)),
            "profit_lock_pullback_fraction_override": min(0.95, max(0.0, _env_float("FUTURES_PMT_PROFIT_LOCK_PULLBACK_FRACTION", 0.70))),
            "profit_lock_min_tp_progress_override": max(0.0, _env_float("FUTURES_PMT_PROFIT_LOCK_MIN_TP_PROGRESS", 0.0)),
            "profit_lock_floor_pct_override": 0.0,
            "profit_lock_exit_min_net_pct_override": max(0.0, _env_float("FUTURES_PMT_PROFIT_LOCK_EXIT_MIN_NET_PCT", 20.0)),
        }
    )
    return FuturesSignal(
        symbol=symbol,
        side=cross.side,
        score=round(score, 2),
        certainty=round(max(0.50, min(0.99, score / 100.0)), 4),
        entry_price=round(entry_price, 10),
        tp_price=round(tp_price, 10),
        sl_price=round(sl_price, 10),
        leverage=leverage,
        entry_signal=f"PMT_THRESHOLD_{cross.side}",
        metadata=metadata,
    )


def diagnose_pmt_threshold_rejection(frame: pd.DataFrame, config: Any) -> str:
    symbol = str(getattr(config, "symbol", "BTC_USDT") or "BTC_USDT").upper()
    if not pmt_symbol_allowed(symbol):
        return "symbol_not_enabled_for_pmt"
    pmt = classify_pair_market_trend(frame, symbol)
    if pmt is None:
        return "pmt_unavailable"
    cross = detect_mental_threshold_cross(frame, symbol)
    if cross is None:
        if _pmt_confirmation_bars() > 0 and len(frame) >= 2:
            immediate = _detect_threshold_cross(float(frame["close"].astype(float).iloc[-2]), float(frame["close"].astype(float).iloc[-1]), symbol)
            if immediate is not None:
                return f"confirmation_pending side={immediate.side} pmt={pmt.label} level={immediate.level:g}"
        return f"no_mental_threshold_cross pmt={pmt.label} move_24h={pmt.move_24h_pct:+.4f} move_12h={pmt.move_12h_pct:+.4f} move_6h={pmt.move_6h_pct:+.4f}"
    if _pmt_blocks_side(cross.side, pmt.label):
        return f"countertrend_block side={cross.side} pmt={pmt.label} level={cross.level:g}"
    safety_rejection = _pmt_safety_rejection(frame, pmt, cross)
    if safety_rejection is not None:
        return f"{safety_rejection} side={cross.side} pmt={pmt.label} level={cross.level:g}"
    score, metadata = _score_threshold_cross(frame, pmt, cross)
    min_score = max(0.0, _env_float("FUTURES_PMT_MIN_SCORE", float(getattr(config, "min_confidence_score", 70.0) or 70.0)))
    if score < min_score:
        return f"score_below_threshold score={score:.2f} min={min_score:.2f} side={cross.side} pmt={pmt.label} level={cross.level:g} penalties={metadata.get('pmt_score_penalties') or {}} caps={metadata.get('pmt_score_caps') or {}}"
    return "accepted"