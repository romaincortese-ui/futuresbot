from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Mapping

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


# Trend thresholds recalibrated to real crypto move sizes (2026-06-08).
# Rationale: the prior MEGA bands were too wide — a 4% BTC day scored as an
# ordinary "BULLISH" move and rarely cleared the 92.5 conviction floor, so the
# bot sat out real trends. MEGA (12h/24h) thresholds scaled ~0.6x so a strong
# 3-4% day registers as MEGA and earns a high-conviction score; FLASH (6h)
# normalised to ~1.5% for majors (a genuine 6h flash move). High-volatility
# alts (SEI, ZEC) scaled proportionally so they stay appropriately higher.
# threshold_step (mental-threshold level) and flat_24h are intentionally
# unchanged. Fields: (symbol, threshold_step, flat_24h, flash_6h, mega_12h, mega_24h).
DEFAULT_PMT_PROFILES: dict[str, PairPMTProfile] = {
    "BTC_USDT": PairPMTProfile("BTC_USDT", 1000.0, 0.008, 0.015, 0.018, 0.030),
    "ETH_USDT": PairPMTProfile("ETH_USDT", 50.0, 0.010, 0.015, 0.024, 0.031),
    "SOL_USDT": PairPMTProfile("SOL_USDT", 2.5, 0.012, 0.016, 0.025, 0.037),
    "BNB_USDT": PairPMTProfile("BNB_USDT", 20.0, 0.011, 0.015, 0.019, 0.030),
    "SEI_USDT": PairPMTProfile("SEI_USDT", 0.01, 0.020, 0.022, 0.048, 0.072),
    "ZEC_USDT": PairPMTProfile("ZEC_USDT", 25.0, 0.030, 0.032, 0.060, 0.096),
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


def _pmt_simple_scoring_enabled() -> bool:
    return _env_bool("FUTURES_PMT_SIMPLE_SCORING_ENABLED", False)


def _pmt_simple_core_weight() -> float:
    return max(0.0, min(1.0, _env_float("FUTURES_PMT_SIMPLE_CORE_WEIGHT", 0.90)))


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
    default = 0 if _pmt_simple_scoring_enabled() else 1
    return max(0, _env_int("FUTURES_PMT_CONFIRMATION_BARS", default))


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
    if _pmt_simple_scoring_enabled():
        if _env_bool("FUTURES_PMT_SIMPLE_BLOCK_CONFIRMATION_NO_FOLLOWTHROUGH", False) and _confirmation_followthrough_failed(cross):
            return "confirmation_no_followthrough"
        if _env_bool("FUTURES_PMT_SIMPLE_BLOCK_RECENT_FAILED_RECLAIM", False) and _recent_failed_level_reclaim(frame, cross):
            return "recent_failed_reclaim"
        if _broader_trend_conflict(pmt, cross.side):
            return "broader_trend_conflict"
        return None
    if _confirmation_followthrough_failed(cross):
        return "confirmation_no_followthrough"
    if _env_bool("FUTURES_PMT_BLOCK_RECENT_FAILED_RECLAIM", True) and _recent_failed_level_reclaim(frame, cross):
        return "recent_failed_reclaim"
    if _broader_trend_conflict(pmt, cross.side):
        return "broader_trend_conflict"
    return None


_REDUCED_ENTRY_BLOCKING_CAPS = {
    "late_entry_distance",
    "extreme_late_entry_distance",
    "exhausted_volume_climax",
    "one_hour_exhaustion",
    "stacked_exhaustion",
    "weak_followthrough_on_volume",
}
_REDUCED_ENTRY_BLOCKING_PENALTIES = {
    "one_bar_exhaustion",
    "one_hour_exhaustion",
    "volume_climax",
}


def _pmt_full_score_min(config: Any) -> float:
    return max(0.0, _env_float("FUTURES_PMT_MIN_SCORE", float(getattr(config, "min_confidence_score", 70.0) or 70.0)))


def _pmt_reduced_entry_min_score(full_score_min: float) -> float:
    if not _env_bool("FUTURES_PMT_REDUCED_SCORE_ENTRIES_ENABLED", True):
        return full_score_min
    default = min(full_score_min, 90.0) if full_score_min > 90.0 else full_score_min
    return max(0.0, min(full_score_min, _env_float("FUTURES_PMT_REDUCED_ENTRY_MIN_SCORE", default)))


def _pmt_full_balance_min_score() -> float:
    return max(0.0, _env_float("FUTURES_PMT_FULL_BALANCE_MIN_SCORE", 95.0))


def _pmt_reduced_entry_blockers(metadata: Mapping[str, Any]) -> list[str]:
    pmt_label = str(metadata.get("pmt_label") or "")
    allowed_prefixes = tuple(
        item.strip()
        for item in os.environ.get("FUTURES_PMT_REDUCED_ENTRY_LABEL_PREFIXES", "FLASH_,MEGA_").split(",")
        if item.strip()
    )
    if allowed_prefixes and not pmt_label.startswith(allowed_prefixes):
        return [f"pmt_label={pmt_label or 'UNKNOWN'}"]
    raw_caps = metadata.get("pmt_score_caps") or {}
    caps = raw_caps if isinstance(raw_caps, Mapping) else {}
    raw_penalties = metadata.get("pmt_score_penalties") or {}
    penalties = raw_penalties if isinstance(raw_penalties, Mapping) else {}
    blockers = set(caps).intersection(_REDUCED_ENTRY_BLOCKING_CAPS)
    blockers.update(set(penalties).intersection(_REDUCED_ENTRY_BLOCKING_PENALTIES))
    return sorted(blockers)


def _pmt_reduced_score_entry_allowed(score: float, metadata: Mapping[str, Any]) -> tuple[bool, str]:
    blockers = _pmt_reduced_entry_blockers(metadata)
    if blockers:
        return False, "blockers=" + ";".join(blockers)
    min_edge_score = max(0.0, _env_float("FUTURES_PMT_REDUCED_ENTRY_MIN_EDGE_SCORE", 90.0))
    try:
        edge_score = float(metadata.get("pmt_edge_score") or 0.0)
    except (TypeError, ValueError):
        edge_score = 0.0
    if edge_score < min_edge_score:
        return False, f"edge_score={edge_score:.2f}<min={min_edge_score:.2f}"
    return True, "clean_reduced_score"


def pmt_balance_fraction_for_score(score: float | int | None) -> float:
    try:
        value = float(score or 0.0)
    except (TypeError, ValueError):
        return 0.0
    full_balance_min = _pmt_full_balance_min_score()
    if _env_bool("FUTURES_PMT_REDUCED_SCORE_ENTRIES_ENABLED", True):
        default_entry_min = min(full_balance_min, 90.0) if full_balance_min > 90.0 else full_balance_min
        entry_min = max(0.0, min(full_balance_min, _env_float("FUTURES_PMT_REDUCED_ENTRY_MIN_SCORE", default_entry_min)))
    else:
        entry_min = full_balance_min
    if not math.isfinite(value) or value < entry_min:
        return 0.0
    if value < min(92.0, full_balance_min):
        return max(0.0, min(1.0, _env_float("FUTURES_PMT_SCORE_BAND_SIZE_90_91", _env_float("FUTURES_PMT_SCORE_BAND_SIZE_85_91", 0.25))))
    if value < full_balance_min:
        return max(0.0, min(1.0, _env_float("FUTURES_PMT_SCORE_BAND_SIZE_92_94", _env_float("FUTURES_PMT_SCORE_BAND_SIZE_92_96", 0.50))))
    return max(0.0, min(1.0, _env_float("FUTURES_PMT_SCORE_BAND_SIZE_95_100", _env_float("FUTURES_PMT_SCORE_BAND_SIZE_97_100", 1.00))))


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
    if _pmt_simple_scoring_enabled():
        return _score_simple_threshold_cross(frame, pmt, cross)

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


def _simple_core_score(label: str, aligned: bool | None) -> float:
    if aligned is False:
        return _env_float("FUTURES_PMT_SIMPLE_COUNTERTREND_SCORE", 0.0)
    label = label.upper()
    if label.startswith("MEGA_"):
        return _env_float("FUTURES_PMT_SIMPLE_MEGA_SCORE", 96.0)
    if label.startswith("FLASH_"):
        return _env_float("FUTURES_PMT_SIMPLE_FLASH_SCORE", 93.0)
    if label in {"BULLISH", "BEARISH"}:
        return _env_float("FUTURES_PMT_SIMPLE_TREND_SCORE", 90.0)
    return _env_float("FUTURES_PMT_SIMPLE_FLAT_SCORE", 86.0)


def _side_receives_funding(side: str, funding_rate: float) -> bool:
    side = side.upper()
    if side == "LONG":
        return funding_rate < 0.0
    if side == "SHORT":
        return funding_rate > 0.0
    return False


def _apply_funding_score_adjustment(
    score: float,
    metadata: dict[str, Any],
    *,
    side: str,
    funding_rate: float | None = None,
    funding_cap: float | None = None,
) -> tuple[float, dict[str, Any]]:
    if not _env_bool("FUTURES_PMT_FUNDING_SCORE_ENABLED", True) or funding_rate is None:
        return score, metadata
    try:
        rate = float(funding_rate)
    except (TypeError, ValueError):
        return score, metadata
    try:
        cap = abs(float(funding_cap or 0.0))
    except (TypeError, ValueError):
        cap = 0.0

    receives = _side_receives_funding(side, rate)
    adverse = abs(rate) > 0.0 and not receives
    penalty = 0.0
    bonus = 0.0
    if adverse:
        if cap > 0.0:
            excess_ratio = max(0.0, abs(rate) / cap - 1.0)
        else:
            fallback_cap = max(0.000001, _env_float("FUTURES_PMT_FUNDING_SCORE_FALLBACK_CAP", 0.0002))
            excess_ratio = abs(rate) / fallback_cap
        penalty = min(
            max(0.0, _env_float("FUTURES_PMT_FUNDING_ADVERSE_MAX_PENALTY", 2.0)),
            excess_ratio * max(0.0, _env_float("FUTURES_PMT_FUNDING_ADVERSE_EXCESS_PENALTY_PER_CAP", 1.0)),
        )
    elif receives:
        if cap > 0.0:
            favorable_ratio = abs(rate) / cap
        else:
            favorable_ratio = 0.0
        bonus = min(
            max(0.0, _env_float("FUTURES_PMT_FUNDING_FAVORABLE_MAX_BONUS", 0.5)),
            favorable_ratio * max(0.0, _env_float("FUTURES_PMT_FUNDING_FAVORABLE_BONUS_PER_CAP", 0.25)),
        )

    adjusted = max(0.0, min(100.0, score - penalty + bonus))
    funding_score_cap: float | None = None
    if adverse and _env_bool("FUTURES_PMT_FUNDING_ADVERSE_REDUCED_SIZE_CAP_ENABLED", True):
        funding_score_cap = max(0.0, min(100.0, _env_float("FUTURES_PMT_FUNDING_ADVERSE_SCORE_CAP", 91.99)))
        adjusted = min(adjusted, funding_score_cap)
    out = dict(metadata)
    out["pmt_funding_score_enabled"] = True
    out["pmt_funding_rate_8h"] = round(rate, 8)
    out["pmt_funding_abs_cap"] = round(cap, 8)
    out["pmt_funding_receives"] = bool(receives)
    out["pmt_funding_adverse"] = bool(adverse)
    out["pmt_score_before_funding"] = round(score, 4)
    out["pmt_funding_score_penalty"] = round(penalty, 4)
    out["pmt_funding_score_bonus"] = round(bonus, 4)
    if funding_score_cap is not None:
        caps = dict(out.get("pmt_score_caps") or {})
        caps["funding_adverse_reduced_size"] = round(funding_score_cap, 4)
        out["pmt_score_caps"] = caps
        out["pmt_funding_score_cap"] = round(funding_score_cap, 4)
    out["pmt_edge_score"] = round(adjusted, 4)
    out["pmt_edge_raw_score"] = round(float(out.get("pmt_edge_raw_score", score)), 4)
    if penalty > 0.0:
        penalties = dict(out.get("pmt_score_penalties") or {})
        penalties["funding_adverse"] = round(penalty, 4)
        out["pmt_score_penalties"] = penalties
        out["pmt_score_penalty"] = round(float(out.get("pmt_score_penalty") or 0.0) + penalty, 4)
    if bonus > 0.0:
        out["pmt_score_bonus_funding"] = round(bonus, 4)
    return adjusted, out


def _score_simple_threshold_cross(frame: pd.DataFrame, pmt: PairMarketTrend, cross: MentalThresholdCross) -> tuple[float, dict[str, Any]]:
    profile = pair_pmt_profile(pmt.symbol)
    aligned = _aligned_with_pmt(cross.side, pmt.label)
    signed_1bar = _signed_for_side(cross.move_1bar_pct, cross.side)
    signed_1h = _signed_for_side(_recent_move_pct(frame, 4), cross.side)
    signed_6h = _signed_for_side(pmt.move_6h_pct, cross.side)
    signed_12h = _signed_for_side(pmt.move_12h_pct, cross.side)
    signed_24h = _signed_for_side(pmt.move_24h_pct, cross.side)
    volume_ratio = _volume_ratio(frame)
    level_distance = max(0.0, float(cross.distance_beyond_level_pct or 0.0))

    core_score = _simple_core_score(pmt.label, aligned)
    core_weight = _pmt_simple_core_weight()
    bonus_cap = max(0.0, _env_float("FUTURES_PMT_SIMPLE_CONTEXT_BONUS_CAP", 4.0))
    bonus = 0.0
    bonus += min(1.5, max(0.0, signed_1bar * 100.0 * 4.0))
    bonus += min(1.0, max(0.0, signed_1h * 100.0 * 1.5))
    bonus += min(1.0, max(0.0, signed_6h * 100.0 * 0.4))
    if volume_ratio >= 1.05:
        bonus += min(0.5, (volume_ratio - 1.0) * 0.5)
    context_scale = max(0.0, (1.0 - core_weight) / 0.10)
    context_bonus = min(bonus_cap * context_scale, bonus * context_scale)
    score = max(0.0, min(100.0, core_score + context_bonus))

    caps: dict[str, float] = {}
    penalties: dict[str, float] = {}
    late_distance = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_LATE_ENTRY_DISTANCE_PCT", 0.0250))
    extreme_late_distance = max(late_distance, _env_pct_fraction("FUTURES_PMT_SIMPLE_EXTREME_LATE_ENTRY_DISTANCE_PCT", 0.0400))
    if late_distance > 0 and cross.distance_beyond_level_pct >= late_distance:
        _score_cap(caps, "simple_late_entry_distance", _env_float("FUTURES_PMT_SIMPLE_LATE_ENTRY_SCORE_CAP", 88.0))
    if extreme_late_distance > 0 and cross.distance_beyond_level_pct >= extreme_late_distance:
        _score_cap(caps, "simple_extreme_late_entry_distance", _env_float("FUTURES_PMT_SIMPLE_EXTREME_LATE_ENTRY_SCORE_CAP", 82.0))

    weak_followthrough_1bar = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_WEAK_FOLLOWTHROUGH_1BAR_PCT", 0.0010))
    weak_followthrough_1h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_WEAK_FOLLOWTHROUGH_1H_PCT", 0.0020))
    weak_followthrough_volume = max(0.0, _env_float("FUTURES_PMT_SIMPLE_WEAK_FOLLOWTHROUGH_MIN_VOLUME_RATIO", 1.50))
    weak_followthrough_enabled = _env_bool("FUTURES_PMT_SIMPLE_BLOCK_WEAK_FOLLOWTHROUGH", True)
    if (
        weak_followthrough_enabled
        and not pmt.label.upper().startswith("MEGA_")
        and weak_followthrough_1bar > 0.0
        and weak_followthrough_1h > 0.0
        and volume_ratio >= weak_followthrough_volume
        and signed_1bar < weak_followthrough_1bar
        and signed_1h < weak_followthrough_1h
    ):
        penalties["simple_weak_followthrough"] = max(0.0, _env_float("FUTURES_PMT_SIMPLE_WEAK_FOLLOWTHROUGH_PENALTY", 6.0))
        _score_cap(caps, "simple_weak_followthrough", _env_float("FUTURES_PMT_SIMPLE_WEAK_FOLLOWTHROUGH_SCORE_CAP", 89.0))

    exhaustion_1bar = max(0.0, _env_pct_fraction("FUTURES_PMT_EXHAUSTION_1BAR_PCT", 0.0060))
    exhaustion_1h = max(0.0, _env_pct_fraction("FUTURES_PMT_EXHAUSTION_1H_PCT", 0.0120))
    volume_climax = max(0.0, _env_float("FUTURES_PMT_VOLUME_CLIMAX_RATIO", 1.50))
    one_bar_exhausted = exhaustion_1bar > 0 and signed_1bar >= exhaustion_1bar
    one_hour_exhausted = exhaustion_1h > 0 and signed_1h >= exhaustion_1h
    if one_bar_exhausted:
        penalties["one_bar_exhaustion"] = max(0.0, _env_float("FUTURES_PMT_SIMPLE_EXHAUSTION_1BAR_PENALTY", 6.0))
    if one_hour_exhausted:
        penalties["one_hour_exhaustion"] = max(0.0, _env_float("FUTURES_PMT_SIMPLE_EXHAUSTION_1H_PENALTY", 6.0))
    if volume_climax > 0 and volume_ratio >= volume_climax and (one_bar_exhausted or one_hour_exhausted):
        penalties["volume_climax"] = max(0.0, _env_float("FUTURES_PMT_SIMPLE_VOLUME_CLIMAX_PENALTY", 6.0))
        _score_cap(caps, "simple_exhausted_volume_climax", _env_float("FUTURES_PMT_SIMPLE_EXHAUSTED_CLIMAX_SCORE_CAP", 92.0))
    if one_bar_exhausted and one_hour_exhausted:
        _score_cap(caps, "simple_stacked_exhaustion", _env_float("FUTURES_PMT_SIMPLE_STACKED_EXHAUSTION_SCORE_CAP", 92.0))
    elif one_hour_exhausted:
        _score_cap(caps, "simple_one_hour_exhaustion", _env_float("FUTURES_PMT_SIMPLE_ONE_HOUR_EXHAUSTION_SCORE_CAP", 94.0))

    high_score_exhaustion_min = max(0.0, _env_float("FUTURES_PMT_SIMPLE_HIGH_SCORE_EXHAUSTION_MIN_SCORE", 94.5))
    severe_1bar = max(exhaustion_1bar, _env_pct_fraction("FUTURES_PMT_SIMPLE_SEVERE_EXHAUSTION_1BAR_PCT", 0.0090))
    severe_1h = max(exhaustion_1h, _env_pct_fraction("FUTURES_PMT_SIMPLE_SEVERE_EXHAUSTION_1H_PCT", 0.0180))
    if score >= high_score_exhaustion_min and (one_bar_exhausted or one_hour_exhausted):
        _score_cap(caps, "simple_high_score_exhaustion", _env_float("FUTURES_PMT_SIMPLE_HIGH_SCORE_EXHAUSTION_SCORE_CAP", 94.0))
        if signed_1bar >= severe_1bar or signed_1h >= severe_1h:
            _score_cap(caps, "simple_severe_high_score_exhaustion", _env_float("FUTURES_PMT_SIMPLE_SEVERE_HIGH_SCORE_EXHAUSTION_SCORE_CAP", 92.0))
    if score >= high_score_exhaustion_min:
        stretch_6h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_HIGH_SCORE_STRETCHED_6H_PCT", 0.0180))
        stretch_12h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_HIGH_SCORE_STRETCHED_12H_PCT", 0.0240))
        volume_chase_ratio = max(0.0, _env_float("FUTURES_PMT_SIMPLE_HIGH_SCORE_VOLUME_CHASE_RATIO", 1.75))
        volume_chase_1h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_HIGH_SCORE_VOLUME_CHASE_1H_PCT", 0.0040))
        blowoff_volume_ratio = max(0.0, _env_float("FUTURES_PMT_SIMPLE_HIGH_SCORE_BLOWOFF_VOLUME_RATIO", 2.0))
        blowoff_1bar = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_HIGH_SCORE_BLOWOFF_1BAR_PCT", 0.0180))
        blowoff_1h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_HIGH_SCORE_BLOWOFF_1H_PCT", 0.0180))
        broader_overstretch_24h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_HIGH_SCORE_BROADER_OVERSTRETCH_24H_PCT", 0.0800))
        broader_overstretch_max_1h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_HIGH_SCORE_BROADER_OVERSTRETCH_MAX_1H_PCT", 0.0250))
        if (stretch_6h > 0.0 and signed_6h >= stretch_6h) or (stretch_12h > 0.0 and signed_12h >= stretch_12h):
            penalties["simple_high_score_trend_stretch"] = max(0.0, _env_float("FUTURES_PMT_SIMPLE_HIGH_SCORE_TREND_STRETCH_PENALTY", 8.0))
            _score_cap(caps, "simple_high_score_trend_stretch", _env_float("FUTURES_PMT_SIMPLE_HIGH_SCORE_TREND_STRETCH_SCORE_CAP", 92.0))
        if volume_chase_ratio > 0.0 and volume_ratio >= volume_chase_ratio and signed_1h >= volume_chase_1h:
            penalties["simple_high_score_volume_chase"] = max(0.0, _env_float("FUTURES_PMT_SIMPLE_HIGH_SCORE_VOLUME_CHASE_PENALTY", 8.0))
            _score_cap(caps, "simple_high_score_volume_chase", _env_float("FUTURES_PMT_SIMPLE_HIGH_SCORE_VOLUME_CHASE_SCORE_CAP", 92.0))
        if blowoff_volume_ratio > 0.0 and volume_ratio >= blowoff_volume_ratio and (
            (blowoff_1bar > 0.0 and signed_1bar >= blowoff_1bar) or (blowoff_1h > 0.0 and signed_1h >= blowoff_1h)
        ):
            penalties["simple_high_score_blowoff_chase"] = max(0.0, _env_float("FUTURES_PMT_SIMPLE_HIGH_SCORE_BLOWOFF_PENALTY", 9.0))
            _score_cap(caps, "simple_high_score_blowoff_chase", _env_float("FUTURES_PMT_SIMPLE_HIGH_SCORE_BLOWOFF_SCORE_CAP", 89.0))
        if broader_overstretch_24h > 0.0 and signed_24h >= broader_overstretch_24h and signed_1h <= broader_overstretch_max_1h:
            penalties["simple_high_score_broader_overstretch"] = max(0.0, _env_float("FUTURES_PMT_SIMPLE_HIGH_SCORE_BROADER_OVERSTRETCH_PENALTY", 9.0))
            _score_cap(caps, "simple_high_score_broader_overstretch", _env_float("FUTURES_PMT_SIMPLE_HIGH_SCORE_BROADER_OVERSTRETCH_SCORE_CAP", 89.0))
    elif _env_bool("FUTURES_PMT_SIMPLE_BLOCK_SCORE9_FATIGUE", True):
        fatigue_6h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_SCORE9_FATIGUE_6H_PCT", 0.0150))
        fatigue_12h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_SCORE9_FATIGUE_12H_PCT", 0.0200))
        late_stretch_12h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_SCORE9_LATE_STRETCH_12H_PCT", 0.0250))
        late_stretch_24h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_SCORE9_LATE_STRETCH_24H_PCT", 0.0500))
        late_distance = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_SCORE9_LATE_STRETCH_DISTANCE_PCT", 0.0045))
        fatigue_sequence = fatigue_6h > 0.0 and fatigue_12h > 0.0 and signed_6h >= fatigue_6h and signed_12h >= fatigue_12h
        late_stretch = level_distance >= late_distance and (
            (late_stretch_12h > 0.0 and signed_12h >= late_stretch_12h)
            or (late_stretch_24h > 0.0 and signed_24h >= late_stretch_24h and signed_12h > 0.0)
        )
        if fatigue_sequence or late_stretch:
            penalties["simple_score9_trend_fatigue"] = max(0.0, _env_float("FUTURES_PMT_SIMPLE_SCORE9_FATIGUE_PENALTY", 7.0))
            _score_cap(caps, "simple_score9_trend_fatigue", _env_float("FUTURES_PMT_SIMPLE_SCORE9_FATIGUE_SCORE_CAP", 91.0))
        overstretch_24h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_SCORE9_OVERSTRETCHED_24H_PCT", 0.0800))
        if overstretch_24h > 0.0 and signed_24h >= overstretch_24h and signed_1bar <= 0.0:
            penalties["simple_score9_broader_overstretch"] = max(0.0, _env_float("FUTURES_PMT_SIMPLE_SCORE9_BROADER_OVERSTRETCH_PENALTY", 7.0))
            _score_cap(caps, "simple_score9_broader_overstretch", _env_float("FUTURES_PMT_SIMPLE_SCORE9_BROADER_OVERSTRETCH_SCORE_CAP", 91.0))
        conflict_6h = _env_pct_fraction("FUTURES_PMT_SIMPLE_SCORE9_CONFLICT_6H_PCT", 0.0)
        conflict_max_1h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_SCORE9_CONFLICT_MAX_1H_PCT", 0.0030))
        late_flat_distance = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_SCORE9_LATE_FLAT_DISTANCE_PCT", 0.0045))
        late_flat_6h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_SCORE9_LATE_FLAT_6H_PCT", 0.0050))
        late_flat_12h = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_SCORE9_LATE_FLAT_12H_PCT", 0.0050))
        low_volume_pullback = max(0.0, _env_float("FUTURES_PMT_SIMPLE_SCORE9_LOW_VOLUME_PULLBACK_RATIO", 0.50))
        weak_trend_conflict = signed_6h < conflict_6h and signed_1h < conflict_max_1h
        weak_late_flat = level_distance >= late_flat_distance and signed_6h < late_flat_6h and signed_12h < late_flat_12h
        weak_low_volume_pullback = low_volume_pullback > 0.0 and volume_ratio <= low_volume_pullback and signed_1h < 0.0
        if weak_trend_conflict or weak_late_flat or weak_low_volume_pullback:
            penalties["simple_score9_weak_followthrough_quality"] = max(0.0, _env_float("FUTURES_PMT_SIMPLE_SCORE9_WEAK_QUALITY_PENALTY", 7.0))
            _score_cap(caps, "simple_score9_weak_followthrough_quality", _env_float("FUTURES_PMT_SIMPLE_SCORE9_WEAK_QUALITY_SCORE_CAP", 91.0))
        failed_volume_ratio = max(0.0, _env_float("FUTURES_PMT_SIMPLE_SCORE9_FAILED_VOLUME_RATIO", 2.0))
        failed_volume_distance = max(0.0, _env_pct_fraction("FUTURES_PMT_SIMPLE_SCORE9_FAILED_VOLUME_MAX_DISTANCE_PCT", 0.0010))
        if failed_volume_ratio > 0.0 and volume_ratio >= failed_volume_ratio and signed_1bar <= 0.0 and level_distance <= failed_volume_distance:
            penalties["simple_score9_failed_volume_cross"] = max(0.0, _env_float("FUTURES_PMT_SIMPLE_SCORE9_FAILED_VOLUME_PENALTY", 7.0))
            _score_cap(caps, "simple_score9_failed_volume_cross", _env_float("FUTURES_PMT_SIMPLE_SCORE9_FAILED_VOLUME_SCORE_CAP", 91.0))

    if _env_bool("FUTURES_PMT_SIMPLE_BLOCK_FAILED_RECLAIM_BY_CAP", False) and _recent_failed_level_reclaim(frame, cross):
        _score_cap(caps, "simple_recent_failed_reclaim", _env_float("FUTURES_PMT_SIMPLE_FAILED_RECLAIM_SCORE_CAP", 88.0))

    final_score = min(score, min(caps.values()) if caps else 100.0)
    edge_cap = min(caps.values()) if caps else 100.0
    metadata = {
        "strategy": PMT_STRATEGY_MODE,
        "pmt_score_model": "simple_trend_threshold_v1",
        "pmt_simple_core_score": round(core_score, 4),
        "pmt_simple_context_bonus": round(max(0.0, score - core_score), 4),
        "pmt_simple_context_raw_bonus": round(min(bonus_cap, bonus), 4),
        "pmt_simple_context_bonus_scale": round(context_scale, 4),
        "pmt_simple_core_weight": round(core_weight, 4),
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
        "pmt_raw_score": round(core_score, 4),
        "pmt_setup_score": round(score, 4),
        "pmt_edge_score": round(final_score, 4),
        "pmt_score_caps": {key: round(value, 4) for key, value in caps.items()},
        "pmt_score_penalty": round(sum(penalties.values()), 4),
        "pmt_score_penalties": {key: round(value, 4) for key, value in penalties.items()},
        "pmt_edge_raw_score": round(score, 4),
        "pmt_edge_score_cap": round(edge_cap, 4),
        "signed_1bar_pct": round(signed_1bar, 6),
        "signed_1h_pct": round(signed_1h, 6),
        "signed_6h_pct": round(signed_6h, 6),
        "signed_12h_pct": round(signed_12h, 6),
        "signed_24h_pct": round(signed_24h, 6),
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


def pmt_stop_first_sizing_enabled() -> bool:
    """Stop-first R-multiple sizing: stop = k x ATR placed outside noise first,
    leverage derived as floor(risk budget / stop distance) instead of
    back-solving the stop from a leverage choice."""
    return _env_bool("FUTURES_PMT_STOP_FIRST_SIZING_ENABLED", False)


def _atr_from_frame(frame: pd.DataFrame, period: int) -> float | None:
    if frame is None or len(frame) < max(2, period + 1):
        return None
    try:
        highs = frame["high"].astype(float)
        lows = frame["low"].astype(float)
        closes = frame["close"].astype(float)
    except (KeyError, TypeError, ValueError):
        return None
    prev_close = closes.shift(1)
    tr = pd.concat([(highs - lows), (highs - prev_close).abs(), (lows - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / max(1, period), adjust=False).mean()
    value = float(atr.iloc[-1])
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def _resolve_stop_first_geometry(frame: pd.DataFrame, *, entry_price: float) -> tuple[int, float, float, dict[str, float]] | None:
    """Return (leverage, tp_margin_pct, sl_margin_pct, metadata) for the
    stop-first R-design, or None when ATR is unavailable (caller falls back
    to legacy score-based geometry).

    Replay-calibrated defaults (229 real fills, 2026-03-12..2026-06-08):
    stop 3.0xATR(14, 15m) = 1R = 20% margin budget, TP at +5R, no
    breakeven/scale-out. Net-of-fee expectancy +0.68R/trade overall and
    +1.37R/trade on PMT-era entries.
    """
    if entry_price <= 0:
        return None
    atr_period = max(2, _env_int("FUTURES_PMT_STOP_FIRST_ATR_PERIOD", 14))
    atr_value = _atr_from_frame(frame, atr_period)
    if atr_value is None:
        return None
    stop_mult = max(0.1, _env_float("FUTURES_PMT_STOP_FIRST_ATR_MULT", 3.0))
    risk_budget_pct = max(1.0, _env_float("FUTURES_PMT_STOP_FIRST_RISK_BUDGET_MARGIN_PCT", 20.0))
    target_r = max(0.5, _env_float("FUTURES_PMT_STOP_FIRST_TARGET_R", 5.0))
    min_lev = max(1, _env_int("FUTURES_PMT_STOP_FIRST_MIN_LEVERAGE", 1))
    max_lev = max(min_lev, int(_env_float("FUTURES_PMT_MAX_LEVERAGE", _env_float("FUTURES_LEVERAGE_MAX", 25.0))))
    stop_frac = stop_mult * atr_value / entry_price
    if stop_frac <= 0 or not math.isfinite(stop_frac):
        return None
    leverage = int((risk_budget_pct / 100.0) / stop_frac)
    leverage = max(min_lev, min(max_lev, leverage))
    sl_margin_pct = stop_frac * leverage * 100.0
    tp_margin_pct = sl_margin_pct * target_r
    metadata = {
        "pmt_stop_first": 1.0,
        "pmt_stop_first_atr": round(atr_value, 10),
        "pmt_stop_first_atr_period": float(atr_period),
        "pmt_stop_first_atr_mult": round(stop_mult, 4),
        "pmt_stop_first_target_r": round(target_r, 4),
        "pmt_stop_first_risk_budget_pct": round(risk_budget_pct, 4),
        "pmt_stop_first_stop_price_frac": round(stop_frac, 8),
    }
    return leverage, tp_margin_pct, sl_margin_pct, metadata


def score_pmt_threshold_signal(
    frame: pd.DataFrame,
    config: Any,
    *,
    funding_rate: float | None = None,
    funding_cap: float | None = None,
) -> FuturesSignal | None:
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
    score, metadata = _apply_funding_score_adjustment(
        score,
        metadata,
        side=cross.side,
        funding_rate=funding_rate,
        funding_cap=funding_cap,
    )
    full_score_min = _pmt_full_score_min(config)
    entry_score_min = _pmt_reduced_entry_min_score(full_score_min)
    metadata["pmt_min_score"] = round(full_score_min, 4)
    metadata["pmt_entry_min_score"] = round(entry_score_min, 4)
    # Float-boundary tolerance: penalties produce scores like 92.4999.. that
    # display as 92.50 yet fail a strict floor check (three documented knife-
    # edge kills incl. ZEC 425-short 2026-06-10, score 92.50 vs floor 92.50,
    # -4% follow-through missed). This is NOT a floor loosening (that failed
    # the gate at 17% win); it only admits the float-equal class.
    score_floor_epsilon = max(0.0, _env_float("FUTURES_PMT_SCORE_FLOOR_EPSILON", 0.05))
    if score <= entry_score_min - score_floor_epsilon:
        return None
    if score < full_score_min - score_floor_epsilon:
        allowed, reason = _pmt_reduced_score_entry_allowed(score, metadata)
        metadata["pmt_reduced_score_entry"] = bool(allowed)
        metadata["pmt_reduced_score_reason"] = reason
        if not allowed:
            return None
    else:
        metadata["pmt_reduced_score_entry"] = False

    leverage = _leverage_for_score(score, pmt.label)
    entry_price = cross.current_close
    tp_margin_pct = _tp_margin_pct(score)
    taker_fee_rate = float(getattr(config, "taker_fee_rate", _env_float("MEXC_PERP_DEFAULT_TAKER_FEE_RATE", 0.0008)) or 0.0008)
    sl_margin_pct = _sl_margin_pct(score, leverage=leverage, taker_fee_rate=taker_fee_rate)
    stop_first = pmt_stop_first_sizing_enabled()
    stop_first_metadata: dict[str, float] = {}
    if stop_first:
        resolved = _resolve_stop_first_geometry(frame, entry_price=entry_price)
        if resolved is not None:
            leverage, tp_margin_pct, sl_margin_pct, stop_first_metadata = resolved
        else:
            stop_first = False
    tp_price, sl_price = _target_prices(entry_price, cross.side, leverage, tp_margin_pct, sl_margin_pct)
    if stop_first:
        # Replay-validated R-design uses a pure stop/TP exit pair; the peak
        # lock stays available but armed far out so runners are not clipped.
        profit_lock_trigger_pct = max(0.0, _env_float("FUTURES_PMT_STOP_FIRST_PROFIT_LOCK_TRIGGER_PCT", tp_margin_pct * 0.80))
        profit_lock_giveback_pct = max(0.0, _env_float("FUTURES_PMT_STOP_FIRST_PROFIT_LOCK_GIVEBACK_PCT", 0.0))
        profit_lock_pullback_fraction = min(0.95, max(0.0, _env_float("FUTURES_PMT_STOP_FIRST_PROFIT_LOCK_PULLBACK_FRACTION", 0.25)))
        profit_lock_min_tp_progress = max(0.0, _env_float("FUTURES_PMT_STOP_FIRST_PROFIT_LOCK_MIN_TP_PROGRESS", 0.0))
        profit_lock_floor_pct = max(0.0, _env_float("FUTURES_PMT_STOP_FIRST_PROFIT_LOCK_FLOOR_PCT", tp_margin_pct * 0.50))
        profit_lock_exit_min_net_pct = max(0.0, _env_float("FUTURES_PMT_STOP_FIRST_PROFIT_LOCK_EXIT_MIN_NET_PCT", 0.0))
    elif _env_bool("FUTURES_PMT_QUICK_PROFIT_PROTECTION_ENABLED", False):
        profit_lock_trigger_pct = max(0.0, _env_float("FUTURES_PMT_QUICK_PROFIT_TRIGGER_PCT", 18.0))
        profit_lock_giveback_pct = max(0.0, _env_float("FUTURES_PMT_QUICK_PROFIT_GIVEBACK_PCT", 0.0))
        profit_lock_pullback_fraction = min(0.95, max(0.0, _env_float("FUTURES_PMT_QUICK_PROFIT_PULLBACK_FRACTION", 0.95)))
        profit_lock_min_tp_progress = max(0.0, _env_float("FUTURES_PMT_QUICK_PROFIT_MIN_TP_PROGRESS", 0.0))
        profit_lock_floor_pct = max(0.0, _env_float("FUTURES_PMT_QUICK_PROFIT_FLOOR_PCT", 5.0))
        profit_lock_exit_min_net_pct = max(0.0, _env_float("FUTURES_PMT_QUICK_PROFIT_EXIT_MIN_NET_PCT", 0.0))
    else:
        profit_lock_trigger_pct = max(0.0, _env_float("FUTURES_PMT_PROFIT_LOCK_TRIGGER_PCT", 5.5))
        profit_lock_giveback_pct = max(0.0, _env_float("FUTURES_PMT_PROFIT_LOCK_GIVEBACK_PCT", 0.0))
        profit_lock_pullback_fraction = min(0.95, max(0.0, _env_float("FUTURES_PMT_PROFIT_LOCK_PULLBACK_FRACTION", 0.15)))
        profit_lock_min_tp_progress = max(0.0, _env_float("FUTURES_PMT_PROFIT_LOCK_MIN_TP_PROGRESS", 0.0))
        profit_lock_floor_pct = max(0.0, _env_float("FUTURES_PMT_PROFIT_LOCK_FLOOR_PCT", 5.0))
        profit_lock_exit_min_net_pct = max(0.0, _env_float("FUTURES_PMT_PROFIT_LOCK_EXIT_MIN_NET_PCT", 0.0))
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
            "pmt_quick_profit_protection_enabled": _env_bool("FUTURES_PMT_QUICK_PROFIT_PROTECTION_ENABLED", False),
            "profit_lock_trigger_pct_override": profit_lock_trigger_pct,
            "profit_lock_giveback_pct_override": profit_lock_giveback_pct,
            "profit_lock_pullback_fraction_override": profit_lock_pullback_fraction,
            "profit_lock_min_tp_progress_override": profit_lock_min_tp_progress,
            "profit_lock_floor_pct_override": profit_lock_floor_pct,
            "profit_lock_exit_min_net_pct_override": profit_lock_exit_min_net_pct,
        }
    )
    if stop_first_metadata:
        metadata.update(stop_first_metadata)
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


def diagnose_pmt_threshold_rejection(
    frame: pd.DataFrame,
    config: Any,
    *,
    funding_rate: float | None = None,
    funding_cap: float | None = None,
) -> str:
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
    score, metadata = _apply_funding_score_adjustment(
        score,
        metadata,
        side=cross.side,
        funding_rate=funding_rate,
        funding_cap=funding_cap,
    )
    full_score_min = _pmt_full_score_min(config)
    entry_score_min = _pmt_reduced_entry_min_score(full_score_min)
    if score <= entry_score_min:
        return f"score_below_threshold score={score:.2f} min={entry_score_min:.2f} full_min={full_score_min:.2f} side={cross.side} pmt={pmt.label} level={cross.level:g} penalties={metadata.get('pmt_score_penalties') or {}} caps={metadata.get('pmt_score_caps') or {}}"
    if score < full_score_min:
        allowed, reason = _pmt_reduced_score_entry_allowed(score, metadata)
        if not allowed:
            return f"reduced_score_blocked score={score:.2f} min={entry_score_min:.2f} full_min={full_score_min:.2f} reason={reason} side={cross.side} pmt={pmt.label} level={cross.level:g} penalties={metadata.get('pmt_score_penalties') or {}} caps={metadata.get('pmt_score_caps') or {}}"
    return "accepted"