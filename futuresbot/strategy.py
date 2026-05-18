from __future__ import annotations

import math
import os
from typing import Protocol

import pandas as pd

from futuresbot.indicators import calc_adx, calc_atr, calc_ema, calc_rsi, resample_ohlcv
from futuresbot.models import FuturesSignal
from futuresbot.opportunity_score import opportunity_metadata


_DEFAULT_SYMBOL_DISABLED_ENTRY_SIGNALS: dict[str, tuple[str, ...]] = {
    "BTC_USDT": ("MOMENTUM_BREAKAWAY_SHORT", "BTC_ROUND_LEVEL_LONG"),
    "ETH_USDT": ("COIL_BREAKOUT_LONG", "MOMENTUM_BREAKAWAY_SHORT", "IMPULSE_EVENT_CONTINUATION_SHORT"),
    "SOL_USDT": ("TREND_CONTINUATION_SHORT",),
    "BNB_USDT": ("LEVEL_BREAK_LONG", "IMPULSE_EVENT_CONTINUATION_SHORT"),
    "TAO_USDT": (
        "COIL_BREAKOUT_LONG",
        "IMPULSE_EVENT_CONTINUATION_LONG",
        "IMPULSE_EVENT_CONTINUATION_SHORT",
        "MOMENTUM_BREAKAWAY_SHORT",
    ),
    "SEI_USDT": ("COIL_BREAKOUT_LONG", "COIL_BREAKDOWN_SHORT", "MOMENTUM_BREAKAWAY_SHORT"),
    "ZEC_USDT": ("IMPULSE_EVENT_CONTINUATION_SHORT",),
}


_LEVEL_BREAK_DEFAULT_SYMBOLS: str = (
    "BTC_USDT,ETH_USDT,SOL_USDT,PEPE_USDT,TAO_USDT,"
    "BNB_USDT,BCH_USDT,SEI_USDT,LINK_USDT,ZEC_USDT"
)


_LEVEL_BREAK_SYMBOL_DEFAULTS: dict[str, dict[str, float]] = {
    "BTC_USDT": {"MIN_BREAK_PCT": 0.0030, "MIN_BREAK_ATR": 0.40, "SCORE_BONUS": 7.0, "LEVERAGE_MAX": 12.0},
    "ETH_USDT": {"MIN_BREAK_PCT": 0.0200, "MIN_BREAK_ATR": 0.45, "SCORE_BONUS": 4.0, "LEVERAGE_MAX": 10.0},
    "SOL_USDT": {"MIN_BREAK_PCT": 0.0200, "MIN_BREAK_ATR": 0.55, "SCORE_BONUS": 2.0, "LEVERAGE_MAX": 8.0},
    "PEPE_USDT": {"LOOKBACK_BARS": 72.0, "MIN_BREAK_PCT": 0.0300, "MIN_BREAK_ATR": 0.55, "SCORE_BONUS": 3.0, "LEVERAGE_MAX": 7.0},
    "TAO_USDT": {"LOOKBACK_BARS": 72.0, "MIN_BREAK_PCT": 0.0070, "MIN_BREAK_ATR": 0.50, "SCORE_BONUS": 3.0, "LEVERAGE_MAX": 8.0},
    "BNB_USDT": {"MIN_BREAK_PCT": 0.0025, "MIN_BREAK_ATR": 0.35, "SCORE_BONUS": 4.0, "LEVERAGE_MAX": 8.0},
    "BCH_USDT": {"MIN_BREAK_PCT": 0.0150, "MIN_BREAK_ATR": 0.40, "SCORE_BONUS": 4.0, "LEVERAGE_MAX": 10.0},
    "SEI_USDT": {"LOOKBACK_BARS": 72.0, "MIN_BREAK_PCT": 0.0300, "MIN_BREAK_ATR": 0.55, "SCORE_BONUS": 3.0, "LEVERAGE_MAX": 6.0},
    "LINK_USDT": {"MIN_BREAK_PCT": 0.0180, "MIN_BREAK_ATR": 0.45, "SCORE_BONUS": 4.0, "LEVERAGE_MAX": 8.0},
    "ZEC_USDT": {"LOOKBACK_BARS": 72.0, "MIN_BREAK_PCT": 0.0080, "MIN_BREAK_ATR": 0.55, "SCORE_BONUS": 3.0, "LEVERAGE_MAX": 8.0},
}


_BTC_ROUND_LEVEL_SYMBOLS = "BTC_USDT"


_MAJOR_THRESHOLD_DEFAULT_SYMBOLS = "BTC_USDT,SOL_USDT,ETH_USDT"


_MAJOR_THRESHOLD_SYMBOL_DEFAULTS: dict[str, dict[str, float]] = {
    "BTC_USDT": {
        "GRID": 1000.0,
        "LOOKBACK_BARS": 288.0,
        "STOP_PCT": 0.0070,
        "MIN_STOP_PCT": 0.0045,
        "MAX_STOP_PCT": 0.0120,
        "TP_GRID_MULT": 6.0,
        "TP_FLOOR_PCT": 0.055,
        "LEVERAGE_MAX": 8.0,
    },
    "ETH_USDT": {
        "GRID": 100.0,
        "LOOKBACK_BARS": 288.0,
        "STOP_PCT": 0.0090,
        "MIN_STOP_PCT": 0.0055,
        "MAX_STOP_PCT": 0.0140,
        "TP_GRID_MULT": 4.0,
        "TP_FLOOR_PCT": 0.045,
        "LEVERAGE_MAX": 8.0,
    },
    "SOL_USDT": {
        "GRID": 5.0,
        "LOOKBACK_BARS": 288.0,
        "STOP_PCT": 0.0100,
        "MIN_STOP_PCT": 0.0060,
        "MAX_STOP_PCT": 0.0160,
        "TP_GRID_MULT": 4.0,
        "TP_FLOOR_PCT": 0.045,
        "LEVERAGE_MAX": 8.0,
    },
}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _symbol_enabled(name: str, symbol: str, default: str = "") -> bool:
    raw = os.environ.get(name, default)
    normalized_raw = raw.replace(";", " ").replace(",", " ").replace("\n", " ")
    tokens = {"".join(ch for ch in item.upper() if ch.isalnum()) for item in normalized_raw.split() if item.strip()}
    normalized = "".join(ch for ch in symbol.upper() if ch.isalnum())
    return "*" in tokens or normalized in tokens


def _symbol_env_prefix(symbol: str) -> str:
    return "".join(ch for ch in symbol.upper() if ch.isalnum())


def _level_break_float(symbol: str, suffix: str, default: float) -> float:
    symbol_defaults = _LEVEL_BREAK_SYMBOL_DEFAULTS.get(symbol.upper(), {})
    value = float(symbol_defaults.get(suffix, default))
    value = _env_float(f"FUTURES_LEVEL_BREAK_{suffix}", value)
    return _env_float(f"FUTURES_{_symbol_env_prefix(symbol)}_LEVEL_BREAK_{suffix}", value)


def _level_break_int(symbol: str, suffix: str, default: int) -> int:
    return int(max(1.0, round(_level_break_float(symbol, suffix, float(default)))))


def _major_threshold_float(symbol: str, suffix: str, default: float) -> float:
    symbol_defaults = _MAJOR_THRESHOLD_SYMBOL_DEFAULTS.get(symbol.upper(), {})
    value = float(symbol_defaults.get(suffix, default))
    value = _env_float(f"FUTURES_MAJOR_THRESHOLD_{suffix}", value)
    return _env_float(f"FUTURES_{_symbol_env_prefix(symbol)}_MAJOR_THRESHOLD_{suffix}", value)


def _major_threshold_int(symbol: str, suffix: str, default: int) -> int:
    return int(max(1.0, round(_major_threshold_float(symbol, suffix, float(default)))))


def _parse_entry_signal_list(raw: str | None) -> set[str]:
    if raw is None:
        return set()
    normalized = raw.replace(";", ",").replace("\n", ",").replace(" ", ",")
    return {item.strip().upper() for item in normalized.split(",") if item.strip()}


# Canonical "simplified" strategy whitelist — based on 30d baseline backtest
# evidence (Apr14–May14 2026). The signals kept here are EMA trend-pullback,
# Donchian-style consolidation breakouts, and ATR-impulse continuation — the
# three patterns that produced positive PnL in the baseline run. All other
# signals are switched off when FUTURES_SIMPLIFIED_STRATEGY_ENABLED=true.
_SIMPLIFIED_STRATEGY_KEEP = frozenset({
    "TREND_CONTINUATION_LONG",
    "TREND_CONTINUATION_SHORT",
    "COIL_BREAKOUT_LONG",
    "COIL_BREAKDOWN_SHORT",
    "PRESSURE_BREAK_LONG",
    "PRESSURE_BREAK_SHORT",
    "IMPULSE_EVENT_CONTINUATION_LONG",
    "IMPULSE_EVENT_CONTINUATION_SHORT",
})
_SIMPLIFIED_STRATEGY_DISABLE = frozenset({
    "MAJOR_THRESHOLD_LONG",
    "MAJOR_THRESHOLD_SHORT",
    "BTC_ROUND_LEVEL_LONG",
    "BTC_REVERSAL_BREAKDOWN_SHORT",
    "BREAKOUT_HOLD_LONG",
    "BREAKOUT_HOLD_SHORT",
    "LEVEL_BREAK_LONG",
    "LEVEL_BREAK_SHORT",
    "MOMENTUM_BREAKAWAY_LONG",
    "MOMENTUM_BREAKAWAY_SHORT",
    "RANGE_EXPANSION_CONTINUATION_LONG",
    "RANGE_EXPANSION_CONTINUATION_SHORT",
    "EVENT_CATALYST_LONG",
    "EVENT_CATALYST_SHORT",
})


def _entry_signal_disabled(config: "StrategyConfig", entry_signal: str) -> bool:
    symbol = getattr(config, "symbol", "").upper()
    disabled = set(_DEFAULT_SYMBOL_DISABLED_ENTRY_SIGNALS.get(symbol, ()))
    if _env_bool("FUTURES_SIMPLIFIED_STRATEGY_ENABLED", False):
        disabled.update(_SIMPLIFIED_STRATEGY_DISABLE)
    global_raw = os.environ.get("FUTURES_DISABLED_ENTRY_SIGNALS")
    disabled.update(_parse_entry_signal_list(global_raw))
    symbol_key = f"FUTURES_{_symbol_env_prefix(symbol)}_DISABLED_ENTRY_SIGNALS"
    symbol_raw = os.environ.get(symbol_key)
    if symbol_raw is not None:
        symbol_tokens = _parse_entry_signal_list(symbol_raw)
        if symbol_tokens & {"NONE", "OFF", "0", "FALSE"}:
            disabled.clear()
        else:
            disabled.update(symbol_tokens)
    return entry_signal.upper() in disabled


def _side_threshold(config: "StrategyConfig", side: str, offset: float) -> float:
    env_offset = _env_float(f"FUTURES_{side.upper()}_THRESHOLD_OFFSET", 0.0)
    return max(1.0, float(config.min_confidence_score) + env_offset + float(offset or 0.0))


def _cost_budget_mode() -> str:
    raw = os.environ.get("FUTURES_COST_BUDGET_MODE", "shadow")
    mode = str(raw or "shadow").strip().lower()
    if mode in {"0", "false", "no", "off", "disabled"}:
        return "off"
    if mode in {"1", "true", "yes", "on", "enforce", "binding", "live"}:
        return "enforce"
    return "shadow"


def _cost_budget_enforced() -> bool:
    legacy = str(os.environ.get("USE_COST_BUDGET_RR", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
    return legacy or _cost_budget_mode() == "enforce"


def _cost_budget_projection(
    *,
    entry_price: float,
    tp_price: float,
    sl_price: float,
    leverage: int,
    symbol: str | None = None,
) -> dict[str, float | str] | None:
    if _cost_budget_mode() == "off" and not _cost_budget_enforced():
        return None
    try:
        from futuresbot.cost_budget import compute_cost_bps

        if entry_price <= 0:
            return None
        tp_distance_pct = abs(tp_price - entry_price) / entry_price
        sl_distance_pct = abs(entry_price - sl_price) / entry_price
        if tp_distance_pct <= 0 or sl_distance_pct <= 0:
            return None
        hold_hours = _env_float("COST_BUDGET_HOLD_HOURS", 4.0)
        funding_rate = _env_float("COST_BUDGET_FUNDING_RATE_8H", 0.0001)
        taker_fee = _env_float("COST_BUDGET_TAKER_FEE_RATE", 0.0006)
        if symbol:
            normalized = "".join(ch if ch.isalnum() else "_" for ch in symbol.upper())
            override = os.environ.get(f"COST_BUDGET_TAKER_FEE_RATE_{normalized}")
            if override is not None:
                try:
                    taker_fee = float(override)
                except (TypeError, ValueError):
                    pass
        cost = compute_cost_bps(
            leverage=leverage,
            hold_hours=hold_hours,
            funding_rate_8h=funding_rate,
            taker_fee_rate=taker_fee,
        )
        cost_pct = max(0.0, cost.total_bps) / 10_000.0
        gross_rr = tp_distance_pct / sl_distance_pct if sl_distance_pct > 0 else 0.0
        net_rr = tp_distance_pct / (sl_distance_pct + cost_pct) if sl_distance_pct + cost_pct > 0 else 0.0
        min_rr = _env_float("MIN_NET_RR", 1.8)
        return {
            "cost_budget_mode": "enforce" if _cost_budget_enforced() else _cost_budget_mode(),
            "gross_rr": round(gross_rr, 4),
            "net_rr": round(net_rr, 4),
            "min_net_rr": round(max(0.0, min_rr), 4),
            "fee_bps": round(cost.fees_bps, 4),
            "slippage_bps": round(cost.slippage_bps, 4),
            "funding_bps": round(cost.funding_bps, 4),
            "total_cost_bps": round(cost.total_bps, 4),
            "cost_budget_pass": 1.0 if net_rr >= max(0.0, min_rr) else 0.0,
        }
    except Exception:
        return None


class StrategyConfig(Protocol):
    symbol: str
    min_confidence_score: float
    long_threshold_offset: float
    short_threshold_offset: float
    leverage_min: int
    leverage_max: int
    hard_loss_cap_pct: float
    adx_floor: float
    trend_24h_floor: float
    trend_6h_floor: float
    breakout_buffer_atr: float
    consolidation_window_bars: int
    consolidation_max_range_pct: float
    consolidation_atr_mult: float
    volume_ratio_floor: float
    tp_atr_mult: float
    tp_range_mult: float
    tp_floor_pct: float
    sl_buffer_atr_mult: float
    sl_trend_atr_mult: float
    min_reward_risk: float
    early_exit_tp_progress: float
    early_exit_min_profit_pct: float
    early_exit_buffer_pct: float


def _safe_float(value: float | int | None) -> float:
    if value is None:
        return float("nan")
    return float(value)


def _round_price_precision(price: float) -> float:
    """Round prices to a scale-appropriate precision.

    Fixes sub-cent-coin pricing (PEPE, SHIB, etc.): rounding to 2 decimals
    flattens them to 0.00 and silently corrupts every downstream calc that
    reads ``signal.entry_price`` / ``tp_price`` / ``sl_price``.
    """

    try:
        px = float(price)
    except (TypeError, ValueError):
        return 0.0
    ax = abs(px)
    if ax <= 0:
        return 0.0
    if ax < 0.001:
        return round(px, 10)
    if ax < 0.1:
        return round(px, 6)
    if ax < 100:
        return round(px, 4)
    return round(px, 2)


def _confidence(score: float, threshold: float) -> float:
    return max(0.35, min(0.99, 0.35 + max(0.0, score - threshold) / 40.0))


def _leverage_for_signal(certainty: float, sl_distance_pct: float, config: StrategyConfig) -> int | None:
    return _leverage_for_signal_with_bounds(certainty, sl_distance_pct, config, config.leverage_min, config.leverage_max)


def _leverage_for_signal_with_bounds(
    certainty: float,
    sl_distance_pct: float,
    config: StrategyConfig,
    leverage_min: int,
    leverage_max: int,
) -> int | None:
    if sl_distance_pct <= 0:
        return None
    leverage_min = max(1, min(int(leverage_min), int(leverage_max)))
    leverage_max = max(leverage_min, int(leverage_max))
    target = leverage_min + certainty * (leverage_max - leverage_min)
    risk_cap = int(math.floor(config.hard_loss_cap_pct / sl_distance_pct))
    if risk_cap < leverage_min:
        return None
    return max(leverage_min, min(leverage_max, int(round(target)), risk_cap))


def _passes_cost_budget_gate(
    *,
    entry_price: float,
    tp_price: float,
    sl_price: float,
    leverage: int,
    symbol: str | None = None,
) -> bool:
    """Sprint 1 §2.2 — cost-adjusted reward/risk gate.

    Off by default. When ``USE_COST_BUDGET_RR=1`` is set, require that
    ``tp_distance / (sl_distance + expected_cost)`` clears ``MIN_NET_RR``
    (default 1.8). Expected cost uses a conservative funding + slippage
    estimate scaled by leverage.

    Never raises — any import or arithmetic failure falls open (legacy gate
    behaviour) so live trading is not interrupted by a Sprint 1 plumbing bug.
    """

    if not _cost_budget_enforced():
        return True
    try:
        projection = _cost_budget_projection(
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
            leverage=leverage,
            symbol=symbol,
        )
        return True if projection is None else float(projection.get("cost_budget_pass", 1.0)) >= 1.0
    except Exception:
        return True


def _cost_budget_required_tp_distance_pct(
    *,
    entry_price: float,
    sl_price: float,
    leverage: int,
    symbol: str | None = None,
) -> float | None:
    if not _cost_budget_enforced() or entry_price <= 0:
        return None
    dummy_tp = entry_price * 1.01 if sl_price < entry_price else entry_price * 0.99
    projection = _cost_budget_projection(
        entry_price=entry_price,
        tp_price=dummy_tp,
        sl_price=sl_price,
        leverage=leverage,
        symbol=symbol,
    )
    if projection is None:
        return None
    sl_distance_pct = abs(entry_price - sl_price) / entry_price
    cost_pct = max(0.0, float(projection.get("total_cost_bps") or 0.0)) / 10_000.0
    min_net_rr = max(0.0, float(projection.get("min_net_rr") or _env_float("MIN_NET_RR", 1.8)))
    buffer_pct = max(0.0, _env_float("FUTURES_COST_BUDGET_TP_EXTENSION_BUFFER_PCT", 0.0005))
    return (sl_distance_pct + cost_pct) * min_net_rr + buffer_pct


def _cost_budget_tp_extension_enabled(entry_signal: str) -> bool:
    if not _cost_budget_enforced():
        return False
    if not _env_bool("FUTURES_EXTEND_TP_FOR_COST_BUDGET", True):
        return False
    signal = str(entry_signal or "").upper()
    if signal.startswith("MAJOR_THRESHOLD"):
        return _env_bool("FUTURES_MAJOR_THRESHOLD_EXTEND_TP_FOR_COST_BUDGET", True)
    if signal.startswith("BREAKOUT_HOLD"):
        return _env_bool("FUTURES_BREAKOUT_HOLD_EXTEND_TP_FOR_COST_BUDGET", True)
    if signal.startswith("LEVEL_BREAK"):
        return _env_bool("FUTURES_LEVEL_BREAK_EXTEND_TP_FOR_COST_BUDGET", True)
    if signal.startswith("BTC_ROUND_LEVEL"):
        return _env_bool("FUTURES_BTC_ROUND_LEVEL_EXTEND_TP_FOR_COST_BUDGET", True)
    if signal.startswith("BTC_REVERSAL"):
        return _env_bool("FUTURES_BTC_REVERSAL_SHORT_EXTEND_TP_FOR_COST_BUDGET", True)
    if signal.startswith("IMPULSE") or signal.startswith("MOMENTUM_BREAKAWAY") or signal.startswith("RANGE_EXPANSION"):
        return _env_bool("FUTURES_IMPULSE_EXTEND_TP_FOR_COST_BUDGET", True)
    if signal.startswith("EVENT_CATALYST"):
        return _env_bool("FUTURES_EVENT_CATALYST_EXTEND_TP_FOR_COST_BUDGET", True)
    return True


def _extend_tp_for_cost_budget(
    *,
    side: str,
    entry_signal: str,
    entry_price: float,
    tp_price: float,
    sl_price: float,
    leverage: int,
    symbol: str | None = None,
) -> tuple[float, dict[str, float]] | None:
    if not _cost_budget_tp_extension_enabled(entry_signal):
        return tp_price, {}
    required_tp_distance_pct = _cost_budget_required_tp_distance_pct(
        entry_price=entry_price,
        sl_price=sl_price,
        leverage=leverage,
        symbol=symbol,
    )
    if required_tp_distance_pct is None or entry_price <= 0:
        return tp_price, {}
    current_tp_distance_pct = abs(tp_price - entry_price) / entry_price
    if required_tp_distance_pct <= current_tp_distance_pct:
        return tp_price, {
            "cost_budget_required_tp_distance_pct": round(required_tp_distance_pct, 6),
            "cost_budget_tp_extended": 0.0,
        }
    if side.upper() == "LONG":
        adjusted_tp_price = entry_price * (1.0 + required_tp_distance_pct)
    else:
        adjusted_tp_price = entry_price * (1.0 - required_tp_distance_pct)
    if adjusted_tp_price <= 0:
        return None
    return adjusted_tp_price, {
        "cost_budget_required_tp_distance_pct": round(required_tp_distance_pct, 6),
        "cost_budget_original_tp_distance_pct": round(current_tp_distance_pct, 6),
        "cost_budget_tp_extended": 1.0,
    }


def _build_signal(
    *,
    side: str,
    score: float,
    entry_price: float,
    tp_price: float,
    sl_price: float,
    entry_signal: str,
    config: StrategyConfig,
    metadata: dict[str, float | str],
    leverage_min_override: int | None = None,
    leverage_max_override: int | None = None,
) -> FuturesSignal | None:
    sl_distance_pct = abs(entry_price - sl_price) / entry_price if entry_price > 0 else 0.0
    certainty = _confidence(score, config.min_confidence_score)
    leverage_min_bound = leverage_min_override if leverage_min_override is not None else config.leverage_min
    leverage_max_bound = leverage_max_override if leverage_max_override is not None else config.leverage_max
    leverage = _leverage_for_signal_with_bounds(
        certainty,
        sl_distance_pct,
        config,
        leverage_min_bound,
        leverage_max_bound,
    )
    if leverage is None:
        return None
    extension = _extend_tp_for_cost_budget(
        side=side,
        entry_signal=entry_signal,
        entry_price=entry_price,
        tp_price=tp_price,
        sl_price=sl_price,
        leverage=leverage,
        symbol=getattr(config, "symbol", None),
    )
    if extension is None:
        return None
    tp_price, cost_extension_metadata = extension
    cost_projection = _cost_budget_projection(
        entry_price=entry_price,
        tp_price=tp_price,
        sl_price=sl_price,
        leverage=leverage,
        symbol=getattr(config, "symbol", None),
    )
    if not _passes_cost_budget_gate(
        entry_price=entry_price,
        tp_price=tp_price,
        sl_price=sl_price,
        leverage=leverage,
        symbol=getattr(config, "symbol", None),
    ):
        return None
    signal_metadata = {
        **metadata,
        "sl_distance_pct": round(sl_distance_pct, 6),
        "tp_distance_pct": round(abs(tp_price - entry_price) / entry_price if entry_price > 0 else 0.0, 6),
        "leverage_min_bound": float(leverage_min_bound),
        "leverage_max_bound": float(leverage_max_bound),
        "hourly_exit_progress": config.early_exit_tp_progress,
        **cost_extension_metadata,
        **(cost_projection or {}),
    }
    return FuturesSignal(
        symbol=config.symbol,
        side=side,
        score=round(score, 2),
        certainty=round(certainty, 4),
        entry_price=_round_price_precision(entry_price),
        tp_price=_round_price_precision(tp_price),
        sl_price=_round_price_precision(sl_price),
        leverage=leverage,
        entry_signal=entry_signal,
        metadata=opportunity_metadata(signal_metadata, score),
    )


def score_btc_futures_setup(
    frame_15m: pd.DataFrame,
    config: StrategyConfig,
    *,
    long_threshold_offset: float = 0.0,
    short_threshold_offset: float = 0.0,
    event_bias_score: float = 0.0,
    event_max_severity: float = 0.0,
    event_count: int = 0,
    sharp_event_overlay_active: bool = False,
) -> FuturesSignal | None:
    if frame_15m is None or len(frame_15m) < 220:
        return None
    frame_15m = frame_15m.copy()
    frame_1h = resample_ohlcv(frame_15m, "1h")
    if len(frame_1h) < 120:
        return None

    close_15 = frame_15m["close"].astype(float)
    open_15 = frame_15m["open"].astype(float)
    high_15 = frame_15m["high"].astype(float)
    low_15 = frame_15m["low"].astype(float)
    volume_15 = frame_15m["volume"].astype(float)
    close_1h = frame_1h["close"].astype(float)
    high_1h = frame_1h["high"].astype(float)
    low_1h = frame_1h["low"].astype(float)

    ema20 = calc_ema(close_1h, 20)
    ema50 = calc_ema(close_1h, 50)
    ema100 = calc_ema(close_1h, 100)
    rsi_1h = calc_rsi(close_1h, 14)
    rsi_15 = calc_rsi(close_15, 14)
    adx_1h = calc_adx(frame_1h, 14)
    atr_1h = calc_atr(frame_1h, 14)
    atr_15 = calc_atr(frame_15m, 14)

    current_price = float(close_15.iloc[-1])
    current_ema20 = _safe_float(ema20.iloc[-1])
    current_ema50 = _safe_float(ema50.iloc[-1])
    current_ema100 = _safe_float(ema100.iloc[-1])
    current_rsi_1h = _safe_float(rsi_1h.iloc[-1])
    current_rsi_15 = _safe_float(rsi_15.iloc[-1])
    current_adx = _safe_float(adx_1h.iloc[-1])
    current_atr_1h = _safe_float(atr_1h.iloc[-1])
    current_atr_15 = _safe_float(atr_15.iloc[-1])
    if not all(math.isfinite(value) and value > 0 for value in [current_price, current_ema20, current_ema50, current_ema100, current_adx, current_atr_1h, current_atr_15]):
        return None

    consolidation = frame_15m.iloc[-(config.consolidation_window_bars + 1):-1]
    if consolidation.empty:
        return None
    consolidation_high = float(consolidation["high"].max())
    consolidation_low = float(consolidation["low"].min())
    consolidation_range = consolidation_high - consolidation_low
    consolidation_cap = max(config.consolidation_max_range_pct, (current_atr_15 / current_price) * config.consolidation_atr_mult)
    consolidation_range_pct = consolidation_range / current_price if current_price > 0 else 0.0
    consolidation_ok = consolidation_range_pct <= consolidation_cap
    volume_baseline = max(1e-9, float(volume_15.iloc[-(config.consolidation_window_bars + 1):-1].mean()))
    volume_ratio = float(volume_15.iloc[-1]) / volume_baseline

    trend_24h = (float(close_1h.iloc[-1]) / float(close_1h.iloc[-25])) - 1.0 if len(close_1h) >= 25 else 0.0
    trend_6h = (float(close_1h.iloc[-1]) / float(close_1h.iloc[-7])) - 1.0 if len(close_1h) >= 7 else 0.0
    ema_gap = (current_ema20 / current_ema50) - 1.0 if current_ema50 > 0 else 0.0
    ema_slope = (current_ema20 / float(ema20.iloc[-6])) - 1.0 if len(ema20) >= 6 and float(ema20.iloc[-6]) > 0 else 0.0
    breakout_buffer = current_atr_15 * config.breakout_buffer_atr

    breakout_long = current_price > consolidation_high + breakout_buffer
    pressure_long = current_price > consolidation_high - breakout_buffer * 0.35
    breakout_short = current_price < consolidation_low - breakout_buffer
    pressure_short = current_price < consolidation_low + breakout_buffer * 0.35

    # Trend-continuation path: in a confirmed uptrend/downtrend, accept entries
    # on pullbacks to EMA20 without requiring a fresh coil breakout. This
    # captures continuation setups that classic coil-breakout logic misses
    # once the trend is already underway.
    continuation_enabled = os.environ.get("FUTURES_CONTINUATION_ENABLED", "true").lower() == "true"
    continuation_ema_pullback_upper = _env_float("FUTURES_CONTINUATION_PULLBACK_UPPER_ATR", 1.0)
    continuation_ema_pullback_lower = _env_float("FUTURES_CONTINUATION_PULLBACK_LOWER_ATR", 0.4)
    continuation_trend_24h_mult = _env_float("FUTURES_CONTINUATION_TREND_24H_MULT", 1.2)
    continuation_trend_6h_min = _env_float("FUTURES_CONTINUATION_TREND_6H_MIN", 0.0015)
    continuation_adx_min = _env_float("FUTURES_CONTINUATION_ADX_MIN", config.adx_floor + 4.0)
    # Pullback zone: price within [-lower*ATR, +upper*ATR] of EMA20. Allows
    # both shallow dips below EMA20 and ride-above-EMA20 during strong trends,
    # while excluding extended/parabolic conditions far above EMA20.
    ema_offset_long = (current_price - current_ema20) / current_atr_1h if current_atr_1h > 0 else 999.0
    ema_offset_short = (current_ema20 - current_price) / current_atr_1h if current_atr_1h > 0 else 999.0
    long_pullback_zone = -continuation_ema_pullback_lower <= ema_offset_long <= continuation_ema_pullback_upper
    short_pullback_zone = -continuation_ema_pullback_lower <= ema_offset_short <= continuation_ema_pullback_upper
    continuation_long = (
        continuation_enabled
        and current_ema20 > current_ema50 > current_ema100
        and ema_slope > 0
        and current_adx >= continuation_adx_min
        and trend_24h >= config.trend_24h_floor * continuation_trend_24h_mult
        and trend_6h >= continuation_trend_6h_min
        and long_pullback_zone
    )
    continuation_short = (
        continuation_enabled
        and current_ema20 < current_ema50 < current_ema100
        and ema_slope < 0
        and current_adx >= continuation_adx_min
        and trend_24h <= -config.trend_24h_floor * continuation_trend_24h_mult
        and trend_6h <= -continuation_trend_6h_min
        and short_pullback_zone
    )

    rsi_1h_long_min = _env_float("FUTURES_RSI_1H_LONG_MIN", 56.0)
    rsi_15_long_min = _env_float("FUTURES_RSI_15_LONG_MIN", 54.0)
    rsi_1h_short_max = _env_float("FUTURES_RSI_1H_SHORT_MAX", 44.0)
    rsi_15_short_max = _env_float("FUTURES_RSI_15_SHORT_MAX", 46.0)
    volume_floor_cfg = _env_float("FUTURES_VOLUME_RATIO_FLOOR", config.volume_ratio_floor)
    # Continuation entries relax RSI to mid-range (natural pullback levels)
    rsi_1h_long_cont = _env_float("FUTURES_RSI_1H_LONG_CONT_MIN", 50.0)
    rsi_15_long_cont = _env_float("FUTURES_RSI_15_LONG_CONT_MIN", 48.0)
    rsi_1h_short_cont = _env_float("FUTURES_RSI_1H_SHORT_CONT_MAX", 50.0)
    rsi_15_short_cont = _env_float("FUTURES_RSI_15_SHORT_CONT_MAX", 52.0)

    impulse_enabled = _env_bool("FUTURES_IMPULSE_CONTINUATION_ENABLED", True)
    impulse_lookback_bars = max(3, int(_env_float("FUTURES_IMPULSE_LOOKBACK_BARS", 8.0)))
    impulse_min_move_pct = _env_float("FUTURES_IMPULSE_MIN_MOVE_PCT", 0.006)
    impulse_min_move_atr = _env_float("FUTURES_IMPULSE_MIN_MOVE_ATR", 1.10)
    impulse_volume_floor = _env_float("FUTURES_IMPULSE_VOLUME_FLOOR", 1.15)
    impulse_adx_min = _env_float("FUTURES_IMPULSE_ADX_MIN", 12.0)
    impulse_trend_6h_min = _env_float("FUTURES_IMPULSE_TREND_6H_MIN", 0.0005)
    impulse_rsi_1h_long_min = _env_float("FUTURES_IMPULSE_RSI_1H_LONG_MIN", 48.0)
    impulse_rsi_15_long_min = _env_float("FUTURES_IMPULSE_RSI_15_LONG_MIN", 50.0)
    impulse_rsi_15_long_max = _env_float("FUTURES_IMPULSE_RSI_15_LONG_MAX", 82.0)
    impulse_rsi_1h_short_max = _env_float("FUTURES_IMPULSE_RSI_1H_SHORT_MAX", 52.0)
    impulse_rsi_15_short_max = _env_float("FUTURES_IMPULSE_RSI_15_SHORT_MAX", 50.0)
    impulse_rsi_15_short_min = _env_float("FUTURES_IMPULSE_RSI_15_SHORT_MIN", 18.0)
    impulse_close_buffer_atr = _env_float("FUTURES_IMPULSE_CLOSE_BUFFER_ATR", 0.35)
    impulse_max_ema_extension_atr = _env_float("FUTURES_IMPULSE_MAX_EMA_EXTENSION_ATR", 2.75)
    impulse_reference = current_price
    if len(close_15) > impulse_lookback_bars:
        impulse_reference = float(close_15.iloc[-(impulse_lookback_bars + 1)])
    impulse_move_pct = (current_price / impulse_reference) - 1.0 if impulse_reference > 0 else 0.0
    impulse_move_atr = abs(current_price - impulse_reference) / current_atr_15 if current_atr_15 > 0 else 0.0
    impulse_recent_high = float(high_15.iloc[-impulse_lookback_bars:].max())
    impulse_recent_low = float(low_15.iloc[-impulse_lookback_bars:].min())
    impulse_recent_close_high = float(close_15.iloc[-impulse_lookback_bars:].max())
    impulse_recent_close_low = float(close_15.iloc[-impulse_lookback_bars:].min())
    impulse_prior_close_window = close_15.iloc[-impulse_lookback_bars:-1]
    if impulse_prior_close_window.empty:
        impulse_prior_close_window = close_15.iloc[-impulse_lookback_bars:]
    impulse_prior_close_high = float(impulse_prior_close_window.max())
    impulse_prior_close_low = float(impulse_prior_close_window.min())
    impulse_close_near_high = current_price >= impulse_recent_close_high - current_atr_15 * impulse_close_buffer_atr
    impulse_close_near_low = current_price <= impulse_recent_close_low + current_atr_15 * impulse_close_buffer_atr
    impulse_ema_extension = abs(current_price - current_ema20) / current_atr_1h if current_atr_1h > 0 else 999.0
    event_anti_chase_enabled = _env_bool("FUTURES_EVENT_ANTI_CHASE_ENABLED", True)
    event_anti_chase_near_extreme_pct = max(0.0, _env_float("FUTURES_EVENT_ANTI_CHASE_NEAR_EXTREME_PCT", 0.0025))
    event_anti_chase_near_extreme_atr = max(0.0, _env_float("FUTURES_EVENT_ANTI_CHASE_NEAR_EXTREME_ATR", 0.30))
    event_anti_chase_min_move_atr = max(0.0, _env_float("FUTURES_EVENT_ANTI_CHASE_MIN_MOVE_ATR", 0.90))
    event_anti_chase_break_buffer_atr = max(0.0, _env_float("FUTURES_EVENT_ANTI_CHASE_BREAK_BUFFER_ATR", 0.10))
    event_anti_chase_volume_floor = max(0.0, _env_float("FUTURES_EVENT_ANTI_CHASE_VOLUME_FLOOR", 0.75))
    distance_to_recent_low = max(0.0, current_price - impulse_recent_low)
    distance_to_recent_high = max(0.0, impulse_recent_high - current_price)
    distance_to_recent_low_pct = distance_to_recent_low / current_price if current_price > 0 else 999.0
    distance_to_recent_high_pct = distance_to_recent_high / current_price if current_price > 0 else 999.0
    distance_to_recent_low_atr = distance_to_recent_low / current_atr_15 if current_atr_15 > 0 else 999.0
    distance_to_recent_high_atr = distance_to_recent_high / current_atr_15 if current_atr_15 > 0 else 999.0
    event_short_near_low = distance_to_recent_low_pct <= event_anti_chase_near_extreme_pct or distance_to_recent_low_atr <= event_anti_chase_near_extreme_atr
    event_long_near_high = distance_to_recent_high_pct <= event_anti_chase_near_extreme_pct or distance_to_recent_high_atr <= event_anti_chase_near_extreme_atr
    event_short_fresh_break = (
        current_price <= impulse_prior_close_low - current_atr_15 * event_anti_chase_break_buffer_atr
        and volume_ratio >= event_anti_chase_volume_floor
    )
    event_long_fresh_break = (
        current_price >= impulse_prior_close_high + current_atr_15 * event_anti_chase_break_buffer_atr
        and volume_ratio >= event_anti_chase_volume_floor
    )
    event_short_anti_chase_block = (
        event_anti_chase_enabled
        and event_bias_score < 0
        and impulse_move_atr >= event_anti_chase_min_move_atr
        and event_short_near_low
        and not event_short_fresh_break
    )
    event_long_anti_chase_block = (
        event_anti_chase_enabled
        and event_bias_score > 0
        and impulse_move_atr >= event_anti_chase_min_move_atr
        and event_long_near_high
        and not event_long_fresh_break
    )
    impulse_volume_ok = volume_ratio >= impulse_volume_floor
    prior_volume_end = max(0, len(volume_15) - impulse_lookback_bars)
    prior_volume_start = max(0, prior_volume_end - config.consolidation_window_bars)
    prior_volume = volume_15.iloc[prior_volume_start:prior_volume_end]
    if prior_volume.empty:
        prior_volume = volume_15.iloc[-(config.consolidation_window_bars + 1):-1]
    impulse_window_volume_baseline = max(1e-9, float(prior_volume.mean()))
    impulse_window_volume_ratio = float(volume_15.iloc[-impulse_lookback_bars:].sum()) / (
        impulse_window_volume_baseline * impulse_lookback_bars
    )
    impulse_body = abs(float(close_15.iloc[-1]) - float(open_15.iloc[-1])) / current_atr_15 if current_atr_15 > 0 else 0.0
    long_stack = current_ema20 > current_ema50 > current_ema100
    short_stack = current_ema20 < current_ema50 < current_ema100

    # FUTURES_AGGRESSIVE_EMA_BYPASS_ENABLED — relax full EMA-stack requirement during
    # high-conviction regime transitions: when ADX is strong AND RSI(1h) is at an
    # extreme (oversold for shorts target / overbought for longs target), allow a
    # weaker 2-EMA alignment to qualify. Captures impulse setups where EMA100 is
    # straddling EMA20/EMA50 (the BTC 5/12 5/13 production miss case).
    if _env_bool("FUTURES_AGGRESSIVE_EMA_BYPASS_ENABLED", False):
        bypass_adx = _env_float("FUTURES_AGGRESSIVE_EMA_BYPASS_ADX_MIN", 40.0)
        bypass_rsi_overbought = _env_float("FUTURES_AGGRESSIVE_EMA_BYPASS_RSI_OB", 75.0)
        bypass_rsi_oversold = _env_float("FUTURES_AGGRESSIVE_EMA_BYPASS_RSI_OS", 25.0)
        if current_adx >= bypass_adx:
            if not long_stack and current_ema20 > current_ema50 and current_rsi_1h >= bypass_rsi_overbought:
                long_stack = True
            if not short_stack and current_ema20 < current_ema50 and current_rsi_1h <= bypass_rsi_oversold:
                short_stack = True

    def directional_market_penalty(side: str) -> float:
        penalty = 0.0
        if consolidation_range_pct > consolidation_cap:
            over = (consolidation_range_pct - consolidation_cap) / max(consolidation_cap, 1e-9)
            penalty += min(8.0, max(0.0, over * 4.0))
        if side == "LONG":
            if trend_24h < config.trend_24h_floor:
                miss = (config.trend_24h_floor - trend_24h) / max(config.trend_24h_floor, 1e-9)
                penalty += min(8.0, max(0.0, miss * 3.0))
            if trend_6h < config.trend_6h_floor:
                miss = (config.trend_6h_floor - trend_6h) / max(config.trend_6h_floor, 1e-9)
                penalty += min(6.0, max(0.0, miss * 2.5))
            if not long_stack:
                penalty += 5.0
            if ema_slope <= 0:
                penalty += 3.0
        else:
            if trend_24h > -config.trend_24h_floor:
                miss = (config.trend_24h_floor + trend_24h) / max(config.trend_24h_floor, 1e-9)
                penalty += min(8.0, max(0.0, miss * 3.0))
            if trend_6h > -config.trend_6h_floor:
                miss = (config.trend_6h_floor + trend_6h) / max(config.trend_6h_floor, 1e-9)
                penalty += min(6.0, max(0.0, miss * 2.5))
            if not short_stack:
                penalty += 5.0
            if ema_slope >= 0:
                penalty += 3.0
        return round(penalty, 4)

    impulse_soft_market_gates = _env_bool("FUTURES_IMPULSE_SOFT_MARKET_GATES", True)
    impulse_long_market_ok = (trend_6h >= impulse_trend_6h_min or ema_slope > 0) and current_price > current_ema20
    impulse_short_market_ok = (trend_6h <= -impulse_trend_6h_min or ema_slope < 0) and current_price < current_ema20
    impulse_long_penalty = directional_market_penalty("LONG") if impulse_soft_market_gates else 0.0
    impulse_short_penalty = directional_market_penalty("SHORT") if impulse_soft_market_gates else 0.0

    event_catalyst_enabled = _env_bool("FUTURES_EVENT_CATALYST_ENABLED", True)
    event_min_abs_bias = _env_float("FUTURES_EVENT_CATALYST_MIN_ABS_BIAS", 0.55)
    event_min_severity = _env_float("FUTURES_EVENT_CATALYST_MIN_SEVERITY", 0.70)
    event_min_move_pct = _env_float("FUTURES_EVENT_CATALYST_MIN_MOVE_PCT", 0.002)
    event_min_move_atr = _env_float("FUTURES_EVENT_CATALYST_MIN_MOVE_ATR", 0.35)
    event_volume_floor = _env_float("FUTURES_EVENT_CATALYST_VOLUME_FLOOR", 0.95)
    event_adx_min = _env_float("FUTURES_EVENT_CATALYST_ADX_MIN", 10.0)
    event_max_ema_extension_atr = _env_float("FUTURES_EVENT_CATALYST_MAX_EMA_EXTENSION_ATR", 3.75)
    event_rsi_15_long_min = _env_float("FUTURES_EVENT_CATALYST_RSI_15_LONG_MIN", 47.0)
    event_rsi_15_long_max = _env_float("FUTURES_EVENT_CATALYST_RSI_15_LONG_MAX", 86.0)
    event_rsi_15_short_max = _env_float("FUTURES_EVENT_CATALYST_RSI_15_SHORT_MAX", 53.0)
    event_rsi_15_short_min = _env_float("FUTURES_EVENT_CATALYST_RSI_15_SHORT_MIN", 14.0)
    event_abs_bias = abs(float(event_bias_score or 0.0))
    event_active = (
        event_catalyst_enabled
        and int(event_count or 0) > 0
        and event_abs_bias >= event_min_abs_bias
        and float(event_max_severity or 0.0) >= event_min_severity
    )

    range_expansion_enabled = _env_bool("FUTURES_RANGE_EXPANSION_ENABLED", True)
    range_expansion_symbol_ok = _symbol_enabled(
        "FUTURES_RANGE_EXPANSION_SYMBOLS",
        getattr(config, "symbol", ""),
        "TAO_USDT",
    ) or bool(sharp_event_overlay_active)
    range_min_range_pct = _env_float("FUTURES_RANGE_EXPANSION_MIN_RANGE_PCT", 0.018)
    range_max_range_pct = _env_float("FUTURES_RANGE_EXPANSION_MAX_RANGE_PCT", 0.055)
    range_min_trend_24h = _env_float("FUTURES_RANGE_EXPANSION_MIN_TREND_24H", 0.018)
    range_min_trend_6h = _env_float("FUTURES_RANGE_EXPANSION_MIN_TREND_6H", -0.002)
    range_volume_floor = _env_float("FUTURES_RANGE_EXPANSION_VOLUME_FLOOR", 1.05)
    range_adx_min = _env_float("FUTURES_RANGE_EXPANSION_ADX_MIN", 12.0)
    range_rsi_15_long_max = _env_float("FUTURES_RANGE_EXPANSION_RSI_15_LONG_MAX", 84.0)
    range_rsi_15_short_min = _env_float("FUTURES_RANGE_EXPANSION_RSI_15_SHORT_MIN", 16.0)
    range_max_ema_extension_atr = _env_float("FUTURES_RANGE_EXPANSION_MAX_EMA_EXTENSION_ATR", 3.5)
    range_is_wide_but_tradeable = (
        consolidation_range_pct > max(consolidation_cap, range_min_range_pct)
        and consolidation_range_pct <= range_max_range_pct
    )

    breakout_hold_enabled = _env_bool("FUTURES_BREAKOUT_HOLD_ENABLED", True)
    breakout_hold_symbol_ok = _symbol_enabled(
        "FUTURES_BREAKOUT_HOLD_SYMBOLS",
        getattr(config, "symbol", ""),
        "BTC_USDT",
    )
    breakout_hold_bars = max(2, int(_env_float("FUTURES_BREAKOUT_HOLD_BARS", 4.0)))
    breakout_hold_lookback = max(
        breakout_hold_bars + 4,
        int(_env_float("FUTURES_BREAKOUT_HOLD_LOOKBACK_BARS", 48.0)),
    )
    breakout_hold_level = 0.0
    breakout_hold_low = 0.0
    breakout_hold_high = 0.0
    breakout_hold_close_ratio = 0.0
    breakout_hold_support_buffer = 0.0
    breakout_hold_support_margin_atr = 0.0
    breakout_hold_reclaim_score = 0.0
    breakout_hold_shelf_volume_ratio = 0.0
    breakout_hold_confirmation_volume_ratio = max(volume_ratio, impulse_window_volume_ratio)
    breakout_hold_prior_ok = False
    breakout_hold_shelf_ok = False
    if len(frame_15m) > breakout_hold_lookback:
        breakout_hold_prior = high_15.iloc[-breakout_hold_lookback:-breakout_hold_bars]
        breakout_hold_window_lows = low_15.iloc[-breakout_hold_bars:]
        breakout_hold_window_highs = high_15.iloc[-breakout_hold_bars:]
        breakout_hold_window_closes = close_15.iloc[-breakout_hold_bars:]
        if not breakout_hold_prior.empty and not breakout_hold_window_closes.empty:
            breakout_hold_level = float(breakout_hold_prior.max())
            breakout_hold_low = float(breakout_hold_window_lows.min())
            breakout_hold_high = float(breakout_hold_window_highs.max())
            breakout_hold_support_buffer = max(
                current_atr_15 * _env_float("FUTURES_BREAKOUT_HOLD_SUPPORT_BUFFER_ATR", 0.35),
                current_price * _env_float("FUTURES_BREAKOUT_HOLD_SUPPORT_BUFFER_PCT", 0.0015),
            )
            close_floor = breakout_hold_level - breakout_hold_support_buffer * 0.25
            breakout_hold_close_ratio = float((breakout_hold_window_closes >= close_floor).mean())
            breakout_hold_support_margin_atr = (
                (breakout_hold_low - (breakout_hold_level - breakout_hold_support_buffer)) / current_atr_15
                if current_atr_15 > 0
                else 0.0
            )

    breakout_hold_trigger_buffer = current_atr_15 * _env_float(
        "FUTURES_BREAKOUT_HOLD_TRIGGER_BUFFER_ATR",
        config.breakout_buffer_atr,
    )
    breakout_hold_min_close_ratio = _env_float("FUTURES_BREAKOUT_HOLD_MIN_CLOSE_RATIO", 0.75)
    breakout_hold_volume_floor = _env_float("FUTURES_BREAKOUT_HOLD_VOLUME_FLOOR", 0.65)
    breakout_hold_adx_min = _env_float("FUTURES_BREAKOUT_HOLD_ADX_MIN", max(10.0, config.adx_floor - 4.0))
    breakout_hold_trend_24h_min = _env_float("FUTURES_BREAKOUT_HOLD_TREND_24H_MIN", 0.002)
    breakout_hold_trend_6h_min = _env_float("FUTURES_BREAKOUT_HOLD_TREND_6H_MIN", 0.001)
    breakout_hold_rsi_1h_min = _env_float("FUTURES_BREAKOUT_HOLD_RSI_1H_MIN", 48.0)
    breakout_hold_rsi_15_min = _env_float("FUTURES_BREAKOUT_HOLD_RSI_15_MIN", 46.0)
    breakout_hold_rsi_15_max = _env_float("FUTURES_BREAKOUT_HOLD_RSI_15_MAX", 90.0)
    breakout_hold_max_ema_extension_atr = _env_float("FUTURES_BREAKOUT_HOLD_MAX_EMA_EXTENSION_ATR", 4.0)
    breakout_hold_shelf_bars = max(
        breakout_hold_bars,
        int(_env_float("FUTURES_BREAKOUT_HOLD_SHELF_BARS", 16.0)),
    )
    breakout_hold_max_shelf_pullback_pct = _env_float("FUTURES_BREAKOUT_HOLD_MAX_SHELF_PULLBACK_PCT", 0.030)
    breakout_hold_reclaim_atr = _env_float("FUTURES_BREAKOUT_HOLD_RECLAIM_ATR", 1.20)
    breakout_hold_reclaim_pct = _env_float("FUTURES_BREAKOUT_HOLD_RECLAIM_PCT", 0.006)
    if breakout_hold_level > 0:
        breakout_hold_prior_ok = (
            breakout_hold_high >= breakout_hold_level + breakout_hold_trigger_buffer
            and breakout_hold_low >= breakout_hold_level - breakout_hold_support_buffer
            and breakout_hold_close_ratio >= breakout_hold_min_close_ratio
            and current_price >= breakout_hold_level - breakout_hold_support_buffer * 0.25
        )
    if len(frame_15m) > breakout_hold_shelf_bars:
        shelf_high = float(high_15.iloc[-breakout_hold_shelf_bars:].max())
        shelf_low = float(low_15.iloc[-breakout_hold_shelf_bars:].min())
        shelf_volume = float(volume_15.iloc[-breakout_hold_shelf_bars:].sum())
        shelf_volume_baseline_window = volume_15.iloc[-(breakout_hold_shelf_bars * 3):-breakout_hold_shelf_bars]
        shelf_volume_baseline = max(
            1e-9,
            float(shelf_volume_baseline_window.mean()) * breakout_hold_shelf_bars
            if not shelf_volume_baseline_window.empty
            else volume_baseline * breakout_hold_shelf_bars,
        )
        breakout_hold_shelf_volume_ratio = shelf_volume / shelf_volume_baseline
        breakout_hold_confirmation_volume_ratio = max(
            breakout_hold_confirmation_volume_ratio,
            breakout_hold_shelf_volume_ratio,
        )
        shelf_pullback_pct = (shelf_high - shelf_low) / shelf_high if shelf_high > 0 else 0.0
        reclaim_distance = max(current_atr_15 * breakout_hold_reclaim_atr, current_price * breakout_hold_reclaim_pct)
        breakout_hold_shelf_ok = (
            shelf_high > 0
            and shelf_low > 0
            and shelf_pullback_pct <= breakout_hold_max_shelf_pullback_pct
            and current_price >= shelf_high - reclaim_distance
            and trend_24h >= breakout_hold_trend_24h_min * 2.0
            and trend_6h >= breakout_hold_trend_6h_min * 2.0
        )
        if breakout_hold_shelf_ok and not breakout_hold_prior_ok:
            breakout_hold_level = shelf_low
            breakout_hold_low = shelf_low
            breakout_hold_high = shelf_high
            breakout_hold_support_buffer = max(
                current_atr_15 * _env_float("FUTURES_BREAKOUT_HOLD_SUPPORT_BUFFER_ATR", 0.35),
                current_price * _env_float("FUTURES_BREAKOUT_HOLD_SUPPORT_BUFFER_PCT", 0.0015),
            )
            breakout_hold_close_ratio = float((close_15.iloc[-breakout_hold_shelf_bars:] >= shelf_low).mean())
            breakout_hold_support_margin_atr = (
                breakout_hold_support_buffer / current_atr_15 if current_atr_15 > 0 else 0.0
            )
        if shelf_high > 0 and current_atr_15 > 0:
            breakout_hold_reclaim_score = max(
                0.0,
                min(1.0, (current_price - (shelf_high - current_atr_15 * breakout_hold_reclaim_atr)) / (current_atr_15 * breakout_hold_reclaim_atr)),
            )
    breakout_hold_long_ok = (
        breakout_hold_enabled
        and breakout_hold_symbol_ok
        and breakout_hold_level > 0
        and (breakout_hold_prior_ok or breakout_hold_shelf_ok)
        and current_adx >= breakout_hold_adx_min
        and trend_24h >= breakout_hold_trend_24h_min
        and trend_6h >= breakout_hold_trend_6h_min
        and breakout_hold_confirmation_volume_ratio >= breakout_hold_volume_floor
        and current_rsi_1h >= breakout_hold_rsi_1h_min
        and current_rsi_15 >= breakout_hold_rsi_15_min
        and current_rsi_15 <= breakout_hold_rsi_15_max
        and (long_stack or current_price > current_ema20 or ema_slope > 0)
        and impulse_ema_extension <= breakout_hold_max_ema_extension_atr
    )

    symbol_name = getattr(config, "symbol", "").upper()
    btc_short_uptrend_guard_active = (
        symbol_name == "BTC_USDT"
        and _env_bool("FUTURES_BTC_SHORT_UPTREND_GUARD", True)
        and (current_price >= current_ema20 or (long_stack and current_price >= current_ema50))
        and ema_slope > 0
        and (trend_24h > 0 or trend_6h > 0)
    )

    major_threshold_enabled = _env_bool("FUTURES_MAJOR_THRESHOLD_ENABLED", True)
    major_threshold_symbol_ok = _symbol_enabled(
        "FUTURES_MAJOR_THRESHOLD_SYMBOLS",
        symbol_name,
        _MAJOR_THRESHOLD_DEFAULT_SYMBOLS,
    )
    major_threshold_grid = max(1e-9, _major_threshold_float(symbol_name, "GRID", 1000.0))
    major_threshold_long_level = math.floor(current_price / major_threshold_grid) * major_threshold_grid if current_price > 0 else 0.0
    major_threshold_short_level = math.ceil(current_price / major_threshold_grid) * major_threshold_grid if current_price > 0 else 0.0
    major_threshold_lookback = max(24, _major_threshold_int(symbol_name, "LOOKBACK_BARS", 288))
    major_threshold_confirm_bars = max(1, _major_threshold_int(symbol_name, "CONFIRM_BARS", 2))
    major_threshold_buffer = max(
        current_atr_15 * _major_threshold_float(symbol_name, "BUFFER_ATR", 0.08),
        current_price * _major_threshold_float(symbol_name, "BUFFER_PCT", 0.00035),
    )
    major_threshold_recent_low = 0.0
    major_threshold_recent_high = 0.0
    major_threshold_long_close_ratio = 0.0
    major_threshold_short_close_ratio = 0.0
    major_threshold_long_recently_crossed = False
    major_threshold_short_recently_crossed = False
    major_threshold_long_move_pct = 0.0
    major_threshold_short_move_pct = 0.0
    major_threshold_long_move_atr = 0.0
    major_threshold_short_move_atr = 0.0
    major_threshold_volume_ratio = max(volume_ratio, impulse_window_volume_ratio)
    if len(frame_15m) > major_threshold_lookback + major_threshold_confirm_bars:
        threshold_prior = frame_15m.iloc[-(major_threshold_lookback + major_threshold_confirm_bars):-major_threshold_confirm_bars]
        threshold_confirmation = frame_15m.iloc[-major_threshold_confirm_bars:]
        if not threshold_prior.empty and not threshold_confirmation.empty:
            confirmation_close = threshold_confirmation["close"].astype(float)
            confirmation_high = threshold_confirmation["high"].astype(float)
            confirmation_low = threshold_confirmation["low"].astype(float)
            prior_close = threshold_prior["close"].astype(float)
            major_threshold_recent_low = float(confirmation_low.min())
            major_threshold_recent_high = float(confirmation_high.max())
            major_threshold_long_close_ratio = float(
                (confirmation_close >= major_threshold_long_level + major_threshold_buffer * 0.25).mean()
            ) if major_threshold_long_level > 0 else 0.0
            major_threshold_short_close_ratio = float(
                (confirmation_close <= major_threshold_short_level - major_threshold_buffer * 0.25).mean()
            ) if major_threshold_short_level > 0 else 0.0
            prior_close_max = float(prior_close.max())
            prior_close_min = float(prior_close.min())
            major_threshold_long_recently_crossed = (
                major_threshold_long_level > 0
                and prior_close_max <= major_threshold_long_level - major_threshold_buffer * 0.10
            )
            major_threshold_short_recently_crossed = (
                major_threshold_short_level > 0
                and prior_close_min >= major_threshold_short_level + major_threshold_buffer * 0.10
            )
            prior_volume = threshold_prior["volume"].astype(float)
            prior_volume_mean = float(prior_volume.mean()) if not prior_volume.empty else volume_baseline
            confirmation_volume = float(threshold_confirmation["volume"].astype(float).sum())
            threshold_volume_ratio = confirmation_volume / max(1e-9, prior_volume_mean * len(threshold_confirmation))
            major_threshold_volume_ratio = max(major_threshold_volume_ratio, threshold_volume_ratio)
    if major_threshold_long_level > 0:
        major_threshold_long_move_pct = (current_price / major_threshold_long_level) - 1.0
        major_threshold_long_move_atr = (current_price - major_threshold_long_level) / current_atr_15 if current_atr_15 > 0 else 0.0
    if major_threshold_short_level > 0:
        major_threshold_short_move_pct = (major_threshold_short_level / current_price) - 1.0 if current_price > 0 else 0.0
        major_threshold_short_move_atr = (major_threshold_short_level - current_price) / current_atr_15 if current_atr_15 > 0 else 0.0

    major_threshold_min_close_ratio = _major_threshold_float(symbol_name, "MIN_CLOSE_RATIO", 1.00)
    major_threshold_min_price = _major_threshold_float(symbol_name, "MIN_PRICE", 0.0)
    major_threshold_volume_floor = _major_threshold_float(symbol_name, "VOLUME_FLOOR", 0.35)
    major_threshold_adx_min = _major_threshold_float(symbol_name, "ADX_MIN", 10.0)
    major_threshold_trend_24h_min = _major_threshold_float(symbol_name, "TREND_24H_MIN", 0.002)
    major_threshold_trend_6h_min = _major_threshold_float(symbol_name, "TREND_6H_MIN", 0.0005)
    major_threshold_rsi_1h_long_min = _major_threshold_float(symbol_name, "RSI_1H_LONG_MIN", 48.0)
    major_threshold_rsi_1h_long_max = _major_threshold_float(symbol_name, "RSI_1H_LONG_MAX", 88.0)
    major_threshold_rsi_1h_short_min = _major_threshold_float(symbol_name, "RSI_1H_SHORT_MIN", 12.0)
    major_threshold_rsi_1h_short_max = _major_threshold_float(symbol_name, "RSI_1H_SHORT_MAX", 52.0)
    major_threshold_rsi_15_long_min = _major_threshold_float(symbol_name, "RSI_15_LONG_MIN", 43.0)
    major_threshold_rsi_15_long_max = _major_threshold_float(symbol_name, "RSI_15_LONG_MAX", 92.0)
    major_threshold_rsi_15_short_min = _major_threshold_float(symbol_name, "RSI_15_SHORT_MIN", 8.0)
    major_threshold_rsi_15_short_max = _major_threshold_float(symbol_name, "RSI_15_SHORT_MAX", 57.0)
    major_threshold_max_extension_atr = _major_threshold_float(symbol_name, "MAX_EMA_EXTENSION_ATR", 6.0)
    major_threshold_max_move_atr = _major_threshold_float(symbol_name, "MAX_MOVE_ATR", 6.5)
    major_threshold_min_move_atr = _major_threshold_float(symbol_name, "MIN_MOVE_ATR", 0.10)
    major_threshold_min_move_pct = _major_threshold_float(symbol_name, "MIN_MOVE_PCT", 0.0008)
    major_threshold_long_ok = (
        major_threshold_enabled
        and major_threshold_symbol_ok
        and major_threshold_long_level > 0
        and major_threshold_long_level >= major_threshold_min_price
        and current_price >= major_threshold_long_level + major_threshold_buffer
        and major_threshold_long_recently_crossed
        and major_threshold_long_close_ratio >= major_threshold_min_close_ratio
        and major_threshold_long_move_pct >= major_threshold_min_move_pct
        and major_threshold_long_move_atr >= major_threshold_min_move_atr
        and major_threshold_long_move_atr <= major_threshold_max_move_atr
        and major_threshold_volume_ratio >= major_threshold_volume_floor
        and current_adx >= major_threshold_adx_min
        and trend_24h >= major_threshold_trend_24h_min
        and trend_6h >= major_threshold_trend_6h_min
        and current_rsi_1h >= major_threshold_rsi_1h_long_min
        and current_rsi_1h <= major_threshold_rsi_1h_long_max
        and current_rsi_15 >= major_threshold_rsi_15_long_min
        and current_rsi_15 <= major_threshold_rsi_15_long_max
        and (current_price > current_ema20 or ema_slope > 0)
        and impulse_ema_extension <= major_threshold_max_extension_atr
    )
    major_threshold_short_ok = (
        major_threshold_enabled
        and major_threshold_symbol_ok
        and major_threshold_short_level > 0
        and major_threshold_short_level >= major_threshold_min_price
        and current_price <= major_threshold_short_level - major_threshold_buffer
        and major_threshold_short_recently_crossed
        and major_threshold_short_close_ratio >= major_threshold_min_close_ratio
        and major_threshold_short_move_pct >= major_threshold_min_move_pct
        and major_threshold_short_move_atr >= major_threshold_min_move_atr
        and major_threshold_short_move_atr <= major_threshold_max_move_atr
        and major_threshold_volume_ratio >= major_threshold_volume_floor
        and current_adx >= major_threshold_adx_min
        and trend_24h <= -major_threshold_trend_24h_min
        and trend_6h <= -major_threshold_trend_6h_min
        and current_rsi_1h >= major_threshold_rsi_1h_short_min
        and current_rsi_1h <= major_threshold_rsi_1h_short_max
        and current_rsi_15 >= major_threshold_rsi_15_short_min
        and current_rsi_15 <= major_threshold_rsi_15_short_max
        and (current_price < current_ema20 or ema_slope < 0)
        and impulse_ema_extension <= major_threshold_max_extension_atr
        and not btc_short_uptrend_guard_active
    )

    btc_round_level_enabled = _env_bool("FUTURES_BTC_ROUND_LEVEL_LONG_ENABLED", True)
    btc_round_level_symbol_ok = _symbol_enabled(
        "FUTURES_BTC_ROUND_LEVEL_SYMBOLS",
        symbol_name,
        _BTC_ROUND_LEVEL_SYMBOLS,
    )
    btc_round_level_grid = max(100.0, _env_float("FUTURES_BTC_ROUND_LEVEL_GRID", 1000.0))
    btc_round_level = math.floor(current_price / btc_round_level_grid) * btc_round_level_grid if current_price > 0 else 0.0
    btc_round_level_lookback = max(12, int(_env_float("FUTURES_BTC_ROUND_LEVEL_LOOKBACK_BARS", 48.0)))
    btc_round_level_confirm_bars = max(1, int(_env_float("FUTURES_BTC_ROUND_LEVEL_CONFIRM_BARS", 3.0)))
    btc_round_level_buffer = max(
        current_atr_15 * _env_float("FUTURES_BTC_ROUND_LEVEL_BUFFER_ATR", 0.10),
        current_price * _env_float("FUTURES_BTC_ROUND_LEVEL_BUFFER_PCT", 0.00045),
    )
    btc_round_level_close_ratio = 0.0
    btc_round_level_recently_crossed = False
    btc_round_level_move_pct = 0.0
    btc_round_level_move_atr = 0.0
    btc_round_level_recent_low = 0.0
    btc_round_level_volume_ratio = max(volume_ratio, impulse_window_volume_ratio)
    if btc_round_level > 0 and len(frame_15m) > btc_round_level_lookback + btc_round_level_confirm_bars:
        btc_round_prior = frame_15m.iloc[-(btc_round_level_lookback + btc_round_level_confirm_bars):-btc_round_level_confirm_bars]
        btc_round_confirmation = frame_15m.iloc[-btc_round_level_confirm_bars:]
        if not btc_round_prior.empty and not btc_round_confirmation.empty:
            btc_round_level_recent_low = float(btc_round_confirmation["low"].astype(float).min())
            btc_round_level_close_ratio = float(
                (btc_round_confirmation["close"].astype(float) >= btc_round_level + btc_round_level_buffer * 0.25).mean()
            )
            prior_low = float(btc_round_prior["low"].astype(float).min())
            prior_close_min = float(btc_round_prior["close"].astype(float).min())
            btc_round_level_recently_crossed = (
                prior_low <= btc_round_level - btc_round_level_buffer
                or prior_close_min < btc_round_level
            )
            prior_volume = frame_15m["volume"].astype(float).iloc[-(btc_round_level_lookback + btc_round_level_confirm_bars):-btc_round_level_confirm_bars]
            prior_volume_mean = float(prior_volume.mean()) if not prior_volume.empty else volume_baseline
            confirmation_volume = float(btc_round_confirmation["volume"].astype(float).sum())
            confirmation_volume_ratio = confirmation_volume / max(1e-9, prior_volume_mean * len(btc_round_confirmation))
            btc_round_level_volume_ratio = max(btc_round_level_volume_ratio, confirmation_volume_ratio)
    if btc_round_level > 0:
        btc_round_level_move_pct = (current_price / btc_round_level) - 1.0
        btc_round_level_move_atr = (current_price - btc_round_level) / current_atr_15 if current_atr_15 > 0 else 0.0

    btc_round_level_min_close_ratio = _env_float("FUTURES_BTC_ROUND_LEVEL_MIN_CLOSE_RATIO", 0.67)
    btc_round_level_min_price = _env_float("FUTURES_BTC_ROUND_LEVEL_MIN_PRICE", 79000.0)
    btc_round_level_volume_floor = _env_float("FUTURES_BTC_ROUND_LEVEL_VOLUME_FLOOR", 0.45)
    btc_round_level_adx_min = _env_float("FUTURES_BTC_ROUND_LEVEL_ADX_MIN", 14.0)
    btc_round_level_trend_24h_min = _env_float("FUTURES_BTC_ROUND_LEVEL_TREND_24H_MIN", 0.006)
    btc_round_level_trend_6h_min = _env_float("FUTURES_BTC_ROUND_LEVEL_TREND_6H_MIN", 0.0025)
    btc_round_level_rsi_1h_min = _env_float("FUTURES_BTC_ROUND_LEVEL_RSI_1H_MIN", 52.0)
    btc_round_level_rsi_1h_max = _env_float("FUTURES_BTC_ROUND_LEVEL_RSI_1H_MAX", 78.0)
    btc_round_level_rsi_15_min = _env_float("FUTURES_BTC_ROUND_LEVEL_RSI_15_MIN", 44.0)
    btc_round_level_rsi_15_max = _env_float("FUTURES_BTC_ROUND_LEVEL_RSI_15_MAX", 80.0)
    btc_round_level_max_extension_atr = _env_float("FUTURES_BTC_ROUND_LEVEL_MAX_EMA_EXTENSION_ATR", 4.0)
    btc_round_level_max_move_atr = _env_float("FUTURES_BTC_ROUND_LEVEL_MAX_MOVE_ATR", 3.0)
    btc_round_level_min_move_atr = _env_float("FUTURES_BTC_ROUND_LEVEL_MIN_MOVE_ATR", 0.35)
    btc_round_level_min_move_pct = _env_float("FUTURES_BTC_ROUND_LEVEL_MIN_MOVE_PCT", 0.0012)
    btc_round_level_long_ok = (
        btc_round_level_enabled
        and btc_round_level_symbol_ok
        and btc_round_level > 0
        and btc_round_level >= btc_round_level_min_price
        and current_price >= btc_round_level + btc_round_level_buffer
        and btc_round_level_recently_crossed
        and btc_round_level_close_ratio >= btc_round_level_min_close_ratio
        and btc_round_level_move_pct >= btc_round_level_min_move_pct
        and btc_round_level_move_atr >= btc_round_level_min_move_atr
        and btc_round_level_move_atr <= btc_round_level_max_move_atr
        and btc_round_level_volume_ratio >= btc_round_level_volume_floor
        and current_adx >= btc_round_level_adx_min
        and trend_24h >= btc_round_level_trend_24h_min
        and trend_6h >= btc_round_level_trend_6h_min
        and current_rsi_1h >= btc_round_level_rsi_1h_min
        and current_rsi_1h <= btc_round_level_rsi_1h_max
        and current_rsi_15 >= btc_round_level_rsi_15_min
        and current_rsi_15 <= btc_round_level_rsi_15_max
        and (current_price > current_ema20 or ema_slope > 0)
        and impulse_ema_extension <= btc_round_level_max_extension_atr
    )

    btc_reversal_short_enabled = _env_bool("FUTURES_BTC_REVERSAL_SHORT_ENABLED", True)
    btc_reversal_short_symbol_ok = symbol_name == "BTC_USDT" and _symbol_enabled(
        "FUTURES_BTC_REVERSAL_SHORT_SYMBOLS",
        symbol_name,
        "BTC_USDT",
    )
    btc_reversal_lookback = max(12, int(_env_float("FUTURES_BTC_REVERSAL_SHORT_LOOKBACK_BARS", 32.0)))
    btc_reversal_confirm_bars = max(1, int(_env_float("FUTURES_BTC_REVERSAL_SHORT_CONFIRM_BARS", 2.0)))
    btc_reversal_recent_high = 0.0
    btc_reversal_recent_low = 0.0
    btc_reversal_prior_low = 0.0
    btc_reversal_confirm_close_ratio = 0.0
    btc_reversal_drop_pct = 0.0
    btc_reversal_drop_atr = 0.0
    btc_reversal_volume_ratio = max(volume_ratio, impulse_window_volume_ratio)
    if len(frame_15m) > btc_reversal_lookback + btc_reversal_confirm_bars:
        reversal_window = frame_15m.iloc[-btc_reversal_lookback:]
        reversal_prior = frame_15m.iloc[-(btc_reversal_lookback + btc_reversal_confirm_bars):-btc_reversal_confirm_bars]
        reversal_confirmation = frame_15m.iloc[-btc_reversal_confirm_bars:]
        if not reversal_window.empty and not reversal_prior.empty and not reversal_confirmation.empty:
            btc_reversal_recent_high = float(reversal_window["high"].astype(float).max())
            btc_reversal_recent_low = float(reversal_confirmation["low"].astype(float).min())
            btc_reversal_prior_low = float(reversal_prior["low"].astype(float).min())
            reversal_buffer = max(
                current_atr_15 * _env_float("FUTURES_BTC_REVERSAL_SHORT_BREAK_BUFFER_ATR", 0.20),
                current_price * _env_float("FUTURES_BTC_REVERSAL_SHORT_BREAK_BUFFER_PCT", 0.0010),
            )
            reversal_closes = reversal_confirmation["close"].astype(float)
            btc_reversal_confirm_close_ratio = float((reversal_closes <= btc_reversal_prior_low + reversal_buffer).mean())
            prior_volume = reversal_prior["volume"].astype(float)
            prior_volume_mean = max(1e-9, float(prior_volume.mean()) if not prior_volume.empty else volume_baseline)
            confirmation_volume = float(reversal_confirmation["volume"].astype(float).sum())
            btc_reversal_volume_ratio = max(
                btc_reversal_volume_ratio,
                confirmation_volume / max(1e-9, prior_volume_mean * len(reversal_confirmation)),
            )
    if btc_reversal_recent_high > 0:
        btc_reversal_drop_pct = (btc_reversal_recent_high / current_price) - 1.0 if current_price > 0 else 0.0
        btc_reversal_drop_atr = (btc_reversal_recent_high - current_price) / current_atr_15 if current_atr_15 > 0 else 0.0

    btc_reversal_min_drop_pct = _env_float("FUTURES_BTC_REVERSAL_SHORT_MIN_DROP_PCT", 0.0070)
    btc_reversal_min_drop_atr = _env_float("FUTURES_BTC_REVERSAL_SHORT_MIN_DROP_ATR", 1.45)
    btc_reversal_strong_drop_atr = _env_float("FUTURES_BTC_REVERSAL_SHORT_STRONG_DROP_ATR", 2.45)
    btc_reversal_min_close_ratio = _env_float("FUTURES_BTC_REVERSAL_SHORT_MIN_CLOSE_RATIO", 0.50)
    btc_reversal_volume_floor = _env_float("FUTURES_BTC_REVERSAL_SHORT_VOLUME_FLOOR", 0.60)
    btc_reversal_adx_min = _env_float("FUTURES_BTC_REVERSAL_SHORT_ADX_MIN", 14.0)
    btc_reversal_rsi_1h_max = _env_float("FUTURES_BTC_REVERSAL_SHORT_RSI_1H_MAX", 66.0)
    btc_reversal_rsi_15_max = _env_float("FUTURES_BTC_REVERSAL_SHORT_RSI_15_MAX", 48.0)
    btc_reversal_rsi_15_min = _env_float("FUTURES_BTC_REVERSAL_SHORT_RSI_15_MIN", 12.0)
    btc_reversal_min_prior_trend_24h = _env_float("FUTURES_BTC_REVERSAL_SHORT_MIN_PRIOR_TREND_24H", 0.002)
    btc_reversal_min_prior_trend_6h = _env_float("FUTURES_BTC_REVERSAL_SHORT_MIN_PRIOR_TREND_6H", 0.001)
    btc_reversal_max_counter_trend_24h = _env_float("FUTURES_BTC_REVERSAL_SHORT_MAX_COUNTER_TREND_24H", 0.022)
    btc_reversal_max_counter_trend_6h = _env_float("FUTURES_BTC_REVERSAL_SHORT_MAX_COUNTER_TREND_6H", 0.006)
    btc_reversal_min_impulse_move_pct = _env_float("FUTURES_BTC_REVERSAL_SHORT_MIN_IMPULSE_MOVE_PCT", 0.006)
    btc_reversal_max_ema_extension_atr = _env_float("FUTURES_BTC_REVERSAL_SHORT_MAX_EMA_EXTENSION_ATR", 3.0)
    btc_reversal_breakdown_confirmed = (
        btc_reversal_confirm_close_ratio >= btc_reversal_min_close_ratio
        or btc_reversal_drop_atr >= btc_reversal_strong_drop_atr
    )
    btc_reversal_short_ok = (
        btc_reversal_short_enabled
        and btc_reversal_short_symbol_ok
        and btc_reversal_recent_high > current_price
        and btc_reversal_drop_pct >= btc_reversal_min_drop_pct
        and btc_reversal_drop_atr >= btc_reversal_min_drop_atr
        and btc_reversal_breakdown_confirmed
        and btc_reversal_volume_ratio >= btc_reversal_volume_floor
        and current_adx >= btc_reversal_adx_min
        and current_rsi_1h <= btc_reversal_rsi_1h_max
        and current_rsi_15 <= btc_reversal_rsi_15_max
        and current_rsi_15 >= btc_reversal_rsi_15_min
        and trend_24h >= btc_reversal_min_prior_trend_24h
        and trend_6h >= btc_reversal_min_prior_trend_6h
        and trend_24h <= btc_reversal_max_counter_trend_24h
        and trend_6h <= btc_reversal_max_counter_trend_6h
        and impulse_move_pct <= -btc_reversal_min_impulse_move_pct
        and impulse_close_near_low
        and impulse_ema_extension <= btc_reversal_max_ema_extension_atr
    )

    level_break_enabled = _env_bool("FUTURES_LEVEL_BREAK_ENABLED", True)
    level_break_symbol_ok = _symbol_enabled(
        "FUTURES_LEVEL_BREAK_SYMBOLS",
        symbol_name,
        _LEVEL_BREAK_DEFAULT_SYMBOLS,
    ) or bool(sharp_event_overlay_active)
    level_break_lookback = max(24, _level_break_int(symbol_name, "LOOKBACK_BARS", 96))
    level_break_confirm_bars = max(1, _level_break_int(symbol_name, "CONFIRM_BARS", 2))
    level_break_exclude_bars = max(
        level_break_confirm_bars,
        _level_break_int(symbol_name, "EXCLUDE_BARS", level_break_confirm_bars),
    )
    level_break_level_high = 0.0
    level_break_level_low = 0.0
    level_break_recent_high = 0.0
    level_break_recent_low = 0.0
    level_break_long_close_ratio = 0.0
    level_break_short_close_ratio = 0.0
    level_break_long_move_pct = 0.0
    level_break_short_move_pct = 0.0
    level_break_long_move_atr = 0.0
    level_break_short_move_atr = 0.0
    level_break_volume_ratio = max(volume_ratio, impulse_window_volume_ratio)
    if len(frame_15m) > level_break_lookback + level_break_exclude_bars:
        level_break_prior = frame_15m.iloc[-(level_break_lookback + level_break_exclude_bars):-level_break_exclude_bars]
        level_break_confirmation = frame_15m.iloc[-level_break_confirm_bars:]
        if not level_break_prior.empty and not level_break_confirmation.empty:
            level_break_level_high = float(level_break_prior["high"].max())
            level_break_level_low = float(level_break_prior["low"].min())
            level_break_recent_high = float(level_break_confirmation["high"].max())
            level_break_recent_low = float(level_break_confirmation["low"].min())
            confirm_buffer = current_atr_15 * _level_break_float(symbol_name, "CONFIRM_BUFFER_ATR", 0.05)
            level_break_long_close_ratio = float((level_break_confirmation["close"].astype(float) >= level_break_level_high + confirm_buffer).mean())
            level_break_short_close_ratio = float((level_break_confirmation["close"].astype(float) <= level_break_level_low - confirm_buffer).mean())
            if level_break_level_high > 0:
                level_break_long_move_pct = (current_price / level_break_level_high) - 1.0
                level_break_long_move_atr = (current_price - level_break_level_high) / current_atr_15 if current_atr_15 > 0 else 0.0
            if level_break_level_low > 0:
                level_break_short_move_pct = (level_break_level_low / current_price) - 1.0 if current_price > 0 else 0.0
                level_break_short_move_atr = (level_break_level_low - current_price) / current_atr_15 if current_atr_15 > 0 else 0.0
            prior_confirmation_volume = volume_15.iloc[-(level_break_confirm_bars + config.consolidation_window_bars):-level_break_confirm_bars]
            confirmation_volume_baseline = max(
                1e-9,
                float(prior_confirmation_volume.mean()) if not prior_confirmation_volume.empty else volume_baseline,
            )
            confirmation_volume_ratio = float(level_break_confirmation["volume"].astype(float).sum()) / (
                confirmation_volume_baseline * len(level_break_confirmation)
            )
            level_break_volume_ratio = max(level_break_volume_ratio, confirmation_volume_ratio)

    level_break_min_close_ratio = _level_break_float(symbol_name, "MIN_CLOSE_RATIO", 0.50)
    level_break_min_break_pct = _level_break_float(symbol_name, "MIN_BREAK_PCT", 0.004)
    level_break_min_break_atr = _level_break_float(symbol_name, "MIN_BREAK_ATR", 0.45)
    level_break_volume_floor = _level_break_float(symbol_name, "VOLUME_FLOOR", 0.60)
    level_break_adx_min = _level_break_float(symbol_name, "ADX_MIN", max(10.0, config.adx_floor - 6.0))
    level_break_counter_trend_24h_max = _level_break_float(symbol_name, "COUNTER_TREND_24H_MAX", 0.020)
    level_break_counter_trend_6h_max = _level_break_float(symbol_name, "COUNTER_TREND_6H_MAX", 0.014)
    level_break_rsi_15_long_min = _level_break_float(symbol_name, "RSI_15_LONG_MIN", 46.0)
    level_break_rsi_15_long_max = _level_break_float(symbol_name, "RSI_15_LONG_MAX", 88.0)
    level_break_rsi_15_short_min = _level_break_float(symbol_name, "RSI_15_SHORT_MIN", 12.0)
    level_break_rsi_15_short_max = _level_break_float(symbol_name, "RSI_15_SHORT_MAX", 54.0)
    level_break_max_ema_extension_atr = _level_break_float(symbol_name, "MAX_EMA_EXTENSION_ATR", 4.25)
    level_break_long_ok = (
        level_break_enabled
        and level_break_symbol_ok
        and level_break_level_high > 0
        and level_break_long_move_pct >= level_break_min_break_pct
        and level_break_long_move_atr >= level_break_min_break_atr
        and level_break_long_close_ratio >= level_break_min_close_ratio
        and level_break_volume_ratio >= level_break_volume_floor
        and current_adx >= level_break_adx_min
        and trend_24h >= -level_break_counter_trend_24h_max
        and trend_6h >= -level_break_counter_trend_6h_max
        and current_rsi_15 >= level_break_rsi_15_long_min
        and current_rsi_15 <= level_break_rsi_15_long_max
        and (current_price > current_ema20 or ema_slope > 0 or impulse_close_near_high)
        and impulse_ema_extension <= level_break_max_ema_extension_atr
    )
    level_break_short_ok = (
        level_break_enabled
        and level_break_symbol_ok
        and not btc_short_uptrend_guard_active
        and level_break_level_low > 0
        and level_break_short_move_pct >= level_break_min_break_pct
        and level_break_short_move_atr >= level_break_min_break_atr
        and level_break_short_close_ratio >= level_break_min_close_ratio
        and level_break_volume_ratio >= level_break_volume_floor
        and current_adx >= level_break_adx_min
        and trend_24h <= level_break_counter_trend_24h_max
        and trend_6h <= level_break_counter_trend_6h_max
        and current_rsi_15 <= level_break_rsi_15_short_max
        and current_rsi_15 >= level_break_rsi_15_short_min
        and (current_price < current_ema20 or ema_slope < 0 or impulse_close_near_low)
        and impulse_ema_extension <= level_break_max_ema_extension_atr
    )

    breakaway_symbol_ok = _symbol_enabled(
        "FUTURES_BREAKAWAY_SYMBOLS",
        getattr(config, "symbol", ""),
        "BTC_USDT,ETH_USDT,PEPE_USDT,TAO_USDT,BCH_USDT,SEI_USDT",
    ) or bool(sharp_event_overlay_active)
    breakaway_enabled = _env_bool("FUTURES_BREAKAWAY_ENABLED", True) and breakaway_symbol_ok
    breakaway_min_move_pct = _env_float("FUTURES_BREAKAWAY_MIN_MOVE_PCT", 0.006)
    breakaway_min_move_atr = _env_float("FUTURES_BREAKAWAY_MIN_MOVE_ATR", 1.45)
    breakaway_trigger_volume_floor = _env_float("FUTURES_BREAKAWAY_TRIGGER_VOLUME_FLOOR", 0.20)
    breakaway_window_volume_floor = _env_float("FUTURES_BREAKAWAY_WINDOW_VOLUME_FLOOR", 0.70)
    breakaway_adx_min = _env_float("FUTURES_BREAKAWAY_ADX_MIN", impulse_adx_min)
    breakaway_counter_trend_24h_max = _env_float("FUTURES_BREAKAWAY_COUNTER_TREND_24H_MAX", 0.018)
    breakaway_counter_trend_6h_max = _env_float("FUTURES_BREAKAWAY_COUNTER_TREND_6H_MAX", 0.012)
    breakaway_long_max_trend_24h_default = 0.030 if symbol_name == "SEI_USDT" else 999.0
    breakaway_long_max_trend_24h = _env_float(
        f"FUTURES_{_symbol_env_prefix(symbol_name)}_BREAKAWAY_LONG_MAX_TREND_24H",
        _env_float("FUTURES_BREAKAWAY_LONG_MAX_TREND_24H", breakaway_long_max_trend_24h_default),
    )
    breakaway_rsi_1h_long_min = _env_float("FUTURES_BREAKAWAY_RSI_1H_LONG_MIN", 48.0)
    breakaway_rsi_15_long_min = _env_float("FUTURES_BREAKAWAY_RSI_15_LONG_MIN", 46.0)
    breakaway_rsi_15_long_max = _env_float("FUTURES_BREAKAWAY_RSI_15_LONG_MAX", 82.0)
    breakaway_rsi_1h_short_max = _env_float("FUTURES_BREAKAWAY_RSI_1H_SHORT_MAX", 55.0)
    breakaway_rsi_15_short_max = _env_float("FUTURES_BREAKAWAY_RSI_15_SHORT_MAX", 54.0)
    breakaway_rsi_15_short_min = _env_float("FUTURES_BREAKAWAY_RSI_15_SHORT_MIN", 18.0)
    breakaway_max_ema_extension_atr = _env_float("FUTURES_BREAKAWAY_MAX_EMA_EXTENSION_ATR", 3.10)
    breakaway_volume_ok = (
        volume_ratio >= breakaway_trigger_volume_floor
        or impulse_window_volume_ratio >= breakaway_window_volume_floor
    )
    breakaway_long_ok = (
        breakaway_enabled
        and impulse_move_pct >= breakaway_min_move_pct
        and impulse_move_atr >= breakaway_min_move_atr
        and breakaway_volume_ok
        and current_adx >= breakaway_adx_min
        and trend_24h >= -breakaway_counter_trend_24h_max
        and trend_24h <= breakaway_long_max_trend_24h
        and trend_6h >= -breakaway_counter_trend_6h_max
        and current_rsi_1h >= breakaway_rsi_1h_long_min
        and current_rsi_15 >= breakaway_rsi_15_long_min
        and current_rsi_15 <= breakaway_rsi_15_long_max
        and (current_price > current_ema20 or ema_slope > 0 or impulse_move_atr >= breakaway_min_move_atr * 1.35)
        and (impulse_close_near_high or impulse_body >= 0.35)
        and impulse_ema_extension <= breakaway_max_ema_extension_atr
    )
    breakaway_short_ok = (
        breakaway_enabled
        and not btc_short_uptrend_guard_active
        and impulse_move_pct <= -breakaway_min_move_pct
        and impulse_move_atr >= breakaway_min_move_atr
        and breakaway_volume_ok
        and current_adx >= breakaway_adx_min
        and trend_24h <= breakaway_counter_trend_24h_max
        and trend_6h <= breakaway_counter_trend_6h_max
        and current_rsi_1h <= breakaway_rsi_1h_short_max
        and current_rsi_15 <= breakaway_rsi_15_short_max
        and current_rsi_15 >= breakaway_rsi_15_short_min
        and (current_price < current_ema20 or ema_slope < 0 or impulse_move_atr >= breakaway_min_move_atr * 1.35)
        and (impulse_close_near_low or impulse_body >= 0.35)
        and impulse_ema_extension <= breakaway_max_ema_extension_atr
    )
    impulse_long_ok = (
        impulse_enabled
        and not event_long_anti_chase_block
        and impulse_move_pct >= impulse_min_move_pct
        and impulse_move_atr >= impulse_min_move_atr
        and impulse_volume_ok
        and current_adx >= impulse_adx_min
        and current_rsi_1h >= impulse_rsi_1h_long_min
        and current_rsi_15 >= impulse_rsi_15_long_min
        and current_rsi_15 <= impulse_rsi_15_long_max
        and (impulse_soft_market_gates or impulse_long_market_ok)
        and impulse_close_near_high
        and impulse_ema_extension <= impulse_max_ema_extension_atr
    )
    impulse_short_ok = (
        impulse_enabled
        and not btc_short_uptrend_guard_active
        and not event_short_anti_chase_block
        and impulse_move_pct <= -impulse_min_move_pct
        and impulse_move_atr >= impulse_min_move_atr
        and impulse_volume_ok
        and current_adx >= impulse_adx_min
        and current_rsi_1h <= impulse_rsi_1h_short_max
        and current_rsi_15 <= impulse_rsi_15_short_max
        and current_rsi_15 >= impulse_rsi_15_short_min
        and (impulse_soft_market_gates or impulse_short_market_ok)
        and impulse_close_near_low
        and impulse_ema_extension <= impulse_max_ema_extension_atr
    )
    range_expansion_long_ok = (
        range_expansion_enabled
        and range_expansion_symbol_ok
        and range_is_wide_but_tradeable
        and current_adx >= range_adx_min
        and volume_ratio >= range_volume_floor
        and trend_24h >= range_min_trend_24h
        and trend_6h >= range_min_trend_6h
        and current_rsi_1h >= impulse_rsi_1h_long_min
        and current_rsi_15 >= impulse_rsi_15_long_min
        and current_rsi_15 <= range_rsi_15_long_max
        and (current_price > current_ema20 or ema_slope > 0)
        and impulse_close_near_high
        and impulse_ema_extension <= range_max_ema_extension_atr
    )
    range_expansion_short_ok = (
        range_expansion_enabled
        and range_expansion_symbol_ok
        and not btc_short_uptrend_guard_active
        and range_is_wide_but_tradeable
        and current_adx >= range_adx_min
        and volume_ratio >= range_volume_floor
        and trend_24h <= -range_min_trend_24h
        and trend_6h <= -range_min_trend_6h
        and current_rsi_1h <= impulse_rsi_1h_short_max
        and current_rsi_15 <= impulse_rsi_15_short_max
        and current_rsi_15 >= range_rsi_15_short_min
        and (current_price < current_ema20 or ema_slope < 0)
        and impulse_close_near_low
        and impulse_ema_extension <= range_max_ema_extension_atr
    )
    event_catalyst_long_ok = (
        event_active
        and event_bias_score > 0
        and not event_long_anti_chase_block
        and current_adx >= event_adx_min
        and volume_ratio >= event_volume_floor
        and impulse_move_pct >= event_min_move_pct
        and impulse_move_atr >= event_min_move_atr
        and current_rsi_15 >= event_rsi_15_long_min
        and current_rsi_15 <= event_rsi_15_long_max
        and (impulse_close_near_high or current_price >= current_ema20 or ema_slope > 0)
        and impulse_ema_extension <= event_max_ema_extension_atr
    )
    event_catalyst_short_ok = (
        event_active
        and not btc_short_uptrend_guard_active
        and event_bias_score < 0
        and not event_short_anti_chase_block
        and current_adx >= event_adx_min
        and volume_ratio >= event_volume_floor
        and impulse_move_pct <= -event_min_move_pct
        and impulse_move_atr >= event_min_move_atr
        and current_rsi_15 <= event_rsi_15_short_max
        and current_rsi_15 >= event_rsi_15_short_min
        and (impulse_close_near_low or current_price <= current_ema20 or ema_slope < 0)
        and impulse_ema_extension <= event_max_ema_extension_atr
    )

    long_ok = (
        consolidation_ok
        and current_adx >= config.adx_floor
        and trend_24h >= config.trend_24h_floor
        and trend_6h >= config.trend_6h_floor
        and long_stack
        and ema_slope > 0
        and current_rsi_1h >= rsi_1h_long_min
        and current_rsi_15 >= rsi_15_long_min
        and volume_ratio >= volume_floor_cfg
        and (breakout_long or pressure_long)
    )
    short_ok = (
        consolidation_ok
        and not btc_short_uptrend_guard_active
        and current_adx >= config.adx_floor
        and trend_24h <= -config.trend_24h_floor
        and trend_6h <= -config.trend_6h_floor
        and short_stack
        and ema_slope < 0
        and current_rsi_1h <= rsi_1h_short_max
        and current_rsi_15 <= rsi_15_short_max
        and volume_ratio >= volume_floor_cfg
        and (breakout_short or pressure_short)
    )
    # Continuation path is independent of coil/breakout gating but still
    # respects volume and RSI (with relaxed thresholds on the directional side).
    continuation_long_ok = (
        continuation_long
        and current_rsi_1h >= rsi_1h_long_cont
        and current_rsi_15 >= rsi_15_long_cont
        and volume_ratio >= volume_floor_cfg
    )
    continuation_short_ok = (
        continuation_short
        and not btc_short_uptrend_guard_active
        and current_rsi_1h <= rsi_1h_short_cont
        and current_rsi_15 <= rsi_15_short_cont
        and volume_ratio >= volume_floor_cfg
    )

    long_score = 40.0
    if major_threshold_long_ok:
        long_score += _major_threshold_float(symbol_name, "SCORE_BONUS", 18.0)
        long_score += min(18.0, max(0.0, major_threshold_long_move_atr * 4.5))
        long_score += min(14.0, max(0.0, major_threshold_long_move_pct * 1800.0))
        long_score += min(10.0, max(0.0, trend_24h * 300.0))
        long_score += min(8.0, max(0.0, trend_6h * 700.0))
        long_score += min(7.0, max(0.0, (current_adx - major_threshold_adx_min) * 0.7))
        long_score += min(6.0, max(0.0, (major_threshold_volume_ratio - major_threshold_volume_floor) * 7.0))
        long_score += min(5.0, max(0.0, major_threshold_long_close_ratio * 5.0))
        long_score += 3.0 if current_price > current_ema20 or ema_slope > 0 else 0.0
    elif btc_round_level_long_ok:
        long_score += _env_float("FUTURES_BTC_ROUND_LEVEL_SCORE_BONUS", 14.0)
        long_score += min(14.0, max(0.0, btc_round_level_move_atr * 4.0))
        long_score += min(10.0, max(0.0, btc_round_level_move_pct * 1800.0))
        long_score += min(8.0, max(0.0, trend_24h * 300.0))
        long_score += min(8.0, max(0.0, trend_6h * 700.0))
        long_score += min(7.0, max(0.0, (current_adx - btc_round_level_adx_min) * 0.7))
        long_score += min(6.0, max(0.0, (btc_round_level_volume_ratio - btc_round_level_volume_floor) * 7.0))
        long_score += min(6.0, max(0.0, btc_round_level_close_ratio * 6.0))
        long_score += 4.0 if ema_slope > 0 or current_price > current_ema20 else 0.0
    elif long_ok:
        long_score += min(18.0, max(0.0, (current_adx - config.adx_floor) * 1.25))
        long_score += min(16.0, max(0.0, trend_24h * 240.0))
        long_score += min(12.0, max(0.0, trend_6h * 420.0))
        long_score += min(10.0, max(0.0, ema_gap * 850.0))
        long_score += min(8.0, max(0.0, (volume_ratio - config.volume_ratio_floor) * 12.0))
        long_score += 7.0 if breakout_long else 3.5
        long_score += min(6.0, max(0.0, (consolidation_cap - consolidation_range_pct) / max(consolidation_cap, 1e-9) * 6.0))
    elif continuation_long_ok:
        long_score += min(16.0, max(0.0, (current_adx - config.adx_floor) * 1.1))
        long_score += min(14.0, max(0.0, trend_24h * 220.0))
        long_score += min(10.0, max(0.0, trend_6h * 380.0))
        long_score += min(10.0, max(0.0, ema_gap * 850.0))
        long_score += min(6.0, max(0.0, (volume_ratio - volume_floor_cfg) * 10.0))
        long_score -= 6.0
    elif breakout_hold_long_ok:
        long_score += min(14.0, max(0.0, trend_24h * 220.0))
        long_score += min(10.0, max(0.0, trend_6h * 420.0))
        long_score += min(10.0, max(0.0, ((current_price / breakout_hold_level) - 1.0) * 650.0))
        long_score += min(8.0, max(0.0, (current_adx - breakout_hold_adx_min) * 0.85))
        long_score += min(6.0, max(0.0, breakout_hold_support_margin_atr * 2.0))
        long_score += min(4.0, max(0.0, (breakout_hold_confirmation_volume_ratio - breakout_hold_volume_floor) * 5.0))
        long_score += min(6.0, max(0.0, breakout_hold_reclaim_score * 6.0))
        long_score += 5.0 if breakout_hold_shelf_ok else 0.0
        long_score += 4.0 if long_stack else 2.0
    elif level_break_long_ok:
        long_score += 8.0
        long_score += min(18.0, max(0.0, level_break_long_move_atr * 4.0))
        long_score += min(14.0, max(0.0, level_break_long_move_pct * 1000.0))
        long_score += min(10.0, max(0.0, trend_24h * 250.0))
        long_score += min(8.0, max(0.0, trend_6h * 420.0))
        long_score += min(8.0, max(0.0, (level_break_volume_ratio - level_break_volume_floor) * 8.0))
        long_score += min(6.0, max(0.0, (current_adx - level_break_adx_min) * 0.75))
        long_score += min(5.0, max(0.0, level_break_long_close_ratio * 5.0))
        long_score += 3.0 if current_price > current_ema20 or ema_slope > 0 else 0.0
        long_score += _level_break_float(symbol_name, "SCORE_BONUS", 4.0)
    elif impulse_long_ok:
        long_score += min(14.0, max(0.0, impulse_move_pct * 900.0))
        long_score += min(10.0, max(0.0, impulse_move_atr * 2.5))
        long_score += min(8.0, max(0.0, (volume_ratio - impulse_volume_floor) * 8.0))
        long_score += min(6.0, max(0.0, (current_adx - impulse_adx_min) * 0.8))
        long_score += 4.0 if trend_6h > 0 else 0.0
        long_score += 3.0 if current_ema20 > current_ema50 or ema_slope > 0 else 0.0
        long_score -= impulse_long_penalty
    elif breakaway_long_ok:
        long_score += min(16.0, max(0.0, impulse_move_pct * 950.0))
        long_score += min(12.0, max(0.0, impulse_move_atr * 2.8))
        long_score += min(7.0, max(0.0, (max(volume_ratio, impulse_window_volume_ratio) - breakaway_window_volume_floor) * 7.0))
        long_score += min(6.0, max(0.0, (current_adx - breakaway_adx_min) * 0.75))
        long_score += 4.0 if impulse_close_near_high else 1.5
        long_score += 3.0 if trend_6h > 0 or ema_slope > 0 else 0.0
        if trend_24h < 0:
            long_score -= min(5.0, abs(trend_24h) * 220.0)
    elif range_expansion_long_ok:
        long_score += min(16.0, max(0.0, trend_24h * 230.0))
        long_score += min(10.0, max(0.0, impulse_move_atr * 2.0))
        long_score += min(8.0, max(0.0, (volume_ratio - range_volume_floor) * 9.0))
        long_score += min(7.0, max(0.0, (current_adx - range_adx_min) * 0.7))
        long_score += min(6.0, max(0.0, consolidation_range_pct * 130.0))
        long_score += 3.0 if ema_slope > 0 else 0.0
    elif event_catalyst_long_ok:
        event_penalty = directional_market_penalty("LONG")
        long_score += min(15.0, max(0.0, event_abs_bias * 12.0 + float(event_max_severity or 0.0) * 4.0))
        long_score += min(10.0, max(0.0, impulse_move_atr * 2.0))
        long_score += min(8.0, max(0.0, (volume_ratio - event_volume_floor) * 8.0))
        long_score += min(6.0, max(0.0, (current_adx - event_adx_min) * 0.7))
        long_score += 4.0 if impulse_close_near_high else 0.0
        long_score += 3.0 if trend_6h > 0 or ema_slope > 0 else 0.0
        long_score -= event_penalty

    short_score = 40.0
    if major_threshold_short_ok:
        short_score += _major_threshold_float(symbol_name, "SHORT_SCORE_BONUS", _major_threshold_float(symbol_name, "SCORE_BONUS", 18.0))
        short_score += min(18.0, max(0.0, major_threshold_short_move_atr * 4.5))
        short_score += min(14.0, max(0.0, major_threshold_short_move_pct * 1800.0))
        short_score += min(10.0, max(0.0, abs(trend_24h) * 300.0))
        short_score += min(8.0, max(0.0, abs(trend_6h) * 700.0))
        short_score += min(7.0, max(0.0, (current_adx - major_threshold_adx_min) * 0.7))
        short_score += min(6.0, max(0.0, (major_threshold_volume_ratio - major_threshold_volume_floor) * 7.0))
        short_score += min(5.0, max(0.0, major_threshold_short_close_ratio * 5.0))
        short_score += 3.0 if current_price < current_ema20 or ema_slope < 0 else 0.0
    elif btc_reversal_short_ok:
        short_score += _env_float("FUTURES_BTC_REVERSAL_SHORT_SCORE_BONUS", 16.0)
        short_score += min(16.0, max(0.0, btc_reversal_drop_pct * 1100.0))
        short_score += min(12.0, max(0.0, btc_reversal_drop_atr * 3.0))
        short_score += min(8.0, max(0.0, (btc_reversal_volume_ratio - btc_reversal_volume_floor) * 8.0))
        short_score += min(7.0, max(0.0, (current_adx - btc_reversal_adx_min) * 0.65))
        short_score += min(5.0, max(0.0, btc_reversal_confirm_close_ratio * 5.0))
        short_score += 4.0 if trend_6h < 0 else 0.0
        short_score += 3.0 if ema_slope < 0 or current_price < current_ema20 else 0.0
    elif short_ok:
        short_score += min(18.0, max(0.0, (current_adx - config.adx_floor) * 1.25))
        short_score += min(16.0, max(0.0, abs(trend_24h) * 240.0))
        short_score += min(12.0, max(0.0, abs(trend_6h) * 420.0))
        short_score += min(10.0, max(0.0, abs(ema_gap) * 850.0))
        short_score += min(8.0, max(0.0, (volume_ratio - config.volume_ratio_floor) * 12.0))
        short_score += 7.0 if breakout_short else 3.5
        short_score += min(6.0, max(0.0, (consolidation_cap - consolidation_range_pct) / max(consolidation_cap, 1e-9) * 6.0))
    elif continuation_short_ok:
        short_score += min(16.0, max(0.0, (current_adx - config.adx_floor) * 1.1))
        short_score += min(14.0, max(0.0, abs(trend_24h) * 220.0))
        short_score += min(10.0, max(0.0, abs(trend_6h) * 380.0))
        short_score += min(10.0, max(0.0, abs(ema_gap) * 850.0))
        short_score += min(6.0, max(0.0, (volume_ratio - volume_floor_cfg) * 10.0))
        short_score -= 6.0
    elif impulse_short_ok:
        short_score += min(14.0, max(0.0, abs(impulse_move_pct) * 900.0))
        short_score += min(10.0, max(0.0, impulse_move_atr * 2.5))
        short_score += min(8.0, max(0.0, (volume_ratio - impulse_volume_floor) * 8.0))
        short_score += min(6.0, max(0.0, (current_adx - impulse_adx_min) * 0.8))
        short_score += 4.0 if trend_6h < 0 else 0.0
        short_score += 3.0 if current_ema20 < current_ema50 or ema_slope < 0 else 0.0
        short_score -= impulse_short_penalty
    elif level_break_short_ok:
        short_score += 8.0
        short_score += min(18.0, max(0.0, level_break_short_move_atr * 4.0))
        short_score += min(14.0, max(0.0, level_break_short_move_pct * 1000.0))
        short_score += min(10.0, max(0.0, abs(trend_24h) * 250.0))
        short_score += min(8.0, max(0.0, abs(trend_6h) * 420.0))
        short_score += min(8.0, max(0.0, (level_break_volume_ratio - level_break_volume_floor) * 8.0))
        short_score += min(6.0, max(0.0, (current_adx - level_break_adx_min) * 0.75))
        short_score += min(5.0, max(0.0, level_break_short_close_ratio * 5.0))
        short_score += 3.0 if current_price < current_ema20 or ema_slope < 0 else 0.0
        short_score += _level_break_float(symbol_name, "SHORT_SCORE_BONUS", _level_break_float(symbol_name, "SCORE_BONUS", 4.0) - 2.0)
    elif breakaway_short_ok:
        short_score += min(16.0, max(0.0, abs(impulse_move_pct) * 950.0))
        short_score += min(12.0, max(0.0, impulse_move_atr * 2.8))
        short_score += min(7.0, max(0.0, (max(volume_ratio, impulse_window_volume_ratio) - breakaway_window_volume_floor) * 7.0))
        short_score += min(6.0, max(0.0, (current_adx - breakaway_adx_min) * 0.75))
        short_score += 4.0 if impulse_close_near_low else 1.5
        short_score += 3.0 if trend_6h < 0 or ema_slope < 0 else 0.0
        if trend_24h > 0:
            short_score -= min(5.0, trend_24h * 220.0)
    elif range_expansion_short_ok:
        short_score += min(16.0, max(0.0, abs(trend_24h) * 230.0))
        short_score += min(10.0, max(0.0, impulse_move_atr * 2.0))
        short_score += min(8.0, max(0.0, (volume_ratio - range_volume_floor) * 9.0))
        short_score += min(7.0, max(0.0, (current_adx - range_adx_min) * 0.7))
        short_score += min(6.0, max(0.0, consolidation_range_pct * 130.0))
        short_score += 3.0 if ema_slope < 0 else 0.0
    elif event_catalyst_short_ok:
        event_penalty = directional_market_penalty("SHORT")
        short_score += min(15.0, max(0.0, event_abs_bias * 12.0 + float(event_max_severity or 0.0) * 4.0))
        short_score += min(10.0, max(0.0, impulse_move_atr * 2.0))
        short_score += min(8.0, max(0.0, (volume_ratio - event_volume_floor) * 8.0))
        short_score += min(6.0, max(0.0, (current_adx - event_adx_min) * 0.7))
        short_score += 4.0 if impulse_close_near_low else 0.0
        short_score += 3.0 if trend_6h < 0 or ema_slope < 0 else 0.0
        short_score -= event_penalty

    long_threshold = _side_threshold(config, "LONG", long_threshold_offset)
    short_threshold = _side_threshold(config, "SHORT", short_threshold_offset)
    long_passes = long_score >= long_threshold
    short_passes = short_score >= short_threshold
    if not long_passes and not short_passes:
        return None

    def build_direction(side: str) -> FuturesSignal | None:
        if side == "LONG":
            major_threshold_path = major_threshold_long_ok
            btc_round_level_path = btc_round_level_long_ok and not major_threshold_path
            impulse_path = impulse_long_ok and not (major_threshold_path or btc_round_level_path or long_ok or continuation_long_ok)
            breakout_hold_path = breakout_hold_long_ok and not (major_threshold_path or btc_round_level_path or long_ok or continuation_long_ok or impulse_long_ok)
            level_break_path = level_break_long_ok and not (long_ok or continuation_long_ok or impulse_long_ok or breakout_hold_path or btc_round_level_path or major_threshold_path)
            breakaway_path = breakaway_long_ok and not (long_ok or continuation_long_ok or impulse_long_ok or breakout_hold_path or level_break_path or btc_round_level_path or major_threshold_path)
            range_expansion_path = range_expansion_long_ok and not (long_ok or continuation_long_ok or impulse_long_ok or breakout_hold_path or level_break_path or btc_round_level_path or breakaway_long_ok or major_threshold_path)
            event_path = event_catalyst_long_ok and not (long_ok or continuation_long_ok or impulse_long_ok or breakout_hold_path or level_break_path or btc_round_level_path or breakaway_long_ok or range_expansion_long_ok or major_threshold_path)
            if major_threshold_path:
                configured_cap = _major_threshold_float(symbol_name, "LEVERAGE_MAX", 8.0)
                hard_cap = _major_threshold_float(symbol_name, "HARD_LEVERAGE_MAX", configured_cap)
                leverage_max = max(1, int(min(float(config.leverage_max), configured_cap, hard_cap)))
                leverage_min = min(config.leverage_min, leverage_max)
                target_from_grid = major_threshold_long_level + major_threshold_grid * _major_threshold_float(symbol_name, "TP_GRID_MULT", 4.0)
                tp_move = max(
                    _major_threshold_float(symbol_name, "TP_ATR_MULT", 8.0) * current_atr_15,
                    _major_threshold_float(symbol_name, "TP_FLOOR_PCT", 0.045) * current_price,
                    max(0.0, target_from_grid - current_price),
                )
                stop_pct = _major_threshold_float(symbol_name, "STOP_PCT", 0.008)
                min_stop_pct = _major_threshold_float(symbol_name, "MIN_STOP_PCT", 0.0045)
                max_stop_pct = _major_threshold_float(symbol_name, "MAX_STOP_PCT", 0.014)
                sl_price = max(
                    major_threshold_long_level - current_atr_15 * _major_threshold_float(symbol_name, "SL_BUFFER_ATR", 0.55),
                    major_threshold_recent_low - current_atr_15 * _major_threshold_float(symbol_name, "SWING_SL_BUFFER_ATR", 0.25),
                    major_threshold_long_level * (1.0 - stop_pct),
                    current_price * (1.0 - max_stop_pct),
                )
                threshold_stop_ceiling = major_threshold_long_level - max(
                    current_atr_15 * _major_threshold_float(symbol_name, "SL_BUFFER_ATR", 0.55),
                    major_threshold_buffer,
                )
                if sl_price >= current_price:
                    sl_price = current_price - current_atr_15 * _major_threshold_float(symbol_name, "FALLBACK_SL_ATR", 3.0)
                if sl_price >= major_threshold_long_level:
                    sl_price = min(current_price * (1.0 - min_stop_pct), threshold_stop_ceiling)
                if current_price > 0 and (current_price - sl_price) / current_price < min_stop_pct:
                    sl_price = min(current_price * (1.0 - min_stop_pct), threshold_stop_ceiling)
            elif breakout_hold_path:
                default_cap = min(float(config.leverage_max), 12.0)
                leverage_max = max(1, int(_env_float("FUTURES_BREAKOUT_HOLD_LEVERAGE_MAX", default_cap)))
                leverage_min = min(config.leverage_min, leverage_max)
                tp_move = max(
                    _env_float("FUTURES_BREAKOUT_HOLD_TP_ATR_MULT", config.tp_atr_mult) * current_atr_15,
                    _env_float("FUTURES_BREAKOUT_HOLD_TP_FLOOR_PCT", config.tp_floor_pct) * current_price,
                )
                sl_price = breakout_hold_level - current_atr_15 * _env_float("FUTURES_BREAKOUT_HOLD_SL_BUFFER_ATR", 0.45)
                if sl_price >= current_price:
                    sl_price = current_price - current_atr_15 * _env_float("FUTURES_BREAKOUT_HOLD_FALLBACK_SL_ATR", 2.5)
            elif btc_round_level_path:
                configured_cap = _env_float("FUTURES_BTC_ROUND_LEVEL_LEVERAGE_MAX", 8.0)
                hard_cap = _env_float("FUTURES_BTC_ROUND_LEVEL_HARD_LEVERAGE_MAX", 8.0)
                leverage_max = max(1, int(min(float(config.leverage_max), configured_cap, hard_cap)))
                leverage_min = min(config.leverage_min, leverage_max)
                tp_move = max(
                    _env_float("FUTURES_BTC_ROUND_LEVEL_TP_ATR_MULT", 5.0) * current_atr_15,
                    _env_float("FUTURES_BTC_ROUND_LEVEL_TP_FLOOR_PCT", 0.012) * current_price,
                )
                sl_price = max(
                    btc_round_level - current_atr_15 * _env_float("FUTURES_BTC_ROUND_LEVEL_SL_BUFFER_ATR", 1.20),
                    btc_round_level_recent_low - current_atr_15 * _env_float("FUTURES_BTC_ROUND_LEVEL_SWING_SL_BUFFER_ATR", 0.35),
                    current_price * (1.0 - _env_float("FUTURES_BTC_ROUND_LEVEL_MAX_STOP_PCT", 0.012)),
                )
                if sl_price >= current_price:
                    sl_price = current_price - current_atr_15 * _env_float("FUTURES_BTC_ROUND_LEVEL_FALLBACK_SL_ATR", 2.8)
            elif level_break_path:
                default_cap = min(float(config.leverage_max), _level_break_float(symbol_name, "LEVERAGE_MAX", 8.0))
                leverage_max = max(1, int(_level_break_float(symbol_name, "LEVERAGE_MAX", default_cap)))
                leverage_min = min(config.leverage_min, leverage_max)
                tp_move = max(
                    _level_break_float(symbol_name, "TP_ATR_MULT", 5.0) * current_atr_15,
                    _level_break_float(symbol_name, "TP_FLOOR_PCT", 0.014) * current_price,
                )
                sl_price = max(
                    level_break_level_high - current_atr_15 * _level_break_float(symbol_name, "SL_BUFFER_ATR", 0.55),
                    level_break_recent_low - current_atr_15 * _level_break_float(symbol_name, "SWING_SL_BUFFER_ATR", 0.20),
                    current_price * (1.0 - _level_break_float(symbol_name, "MAX_STOP_PCT", 0.014)),
                )
                if sl_price >= current_price:
                    sl_price = current_price - current_atr_15 * _level_break_float(symbol_name, "FALLBACK_SL_ATR", 2.5)
            elif impulse_path or breakaway_path or range_expansion_path or event_path:
                default_cap = min(float(config.leverage_max), 8.0)
                leverage_var = "FUTURES_EVENT_CATALYST_LEVERAGE_MAX" if event_path else "FUTURES_IMPULSE_LEVERAGE_MAX"
                leverage_max = max(1, int(_env_float(leverage_var, _env_float("FUTURES_IMPULSE_LEVERAGE_MAX", default_cap))))
                leverage_min = min(config.leverage_min, leverage_max)
                tp_move = max(_env_float("FUTURES_IMPULSE_TP_ATR_MULT", 5.0) * current_atr_15, _env_float("FUTURES_IMPULSE_TP_FLOOR_PCT", 0.012) * current_price)
                sl_price = max(
                    impulse_recent_low - current_atr_15 * _env_float("FUTURES_IMPULSE_SWING_SL_BUFFER_ATR", 0.25),
                    current_price - current_atr_15 * _env_float("FUTURES_IMPULSE_SL_ATR_MULT", 3.0),
                    current_price * (1.0 - _env_float("FUTURES_IMPULSE_MAX_STOP_PCT", 0.012)),
                )
                if sl_price >= current_price:
                    sl_price = current_price - current_atr_15 * _env_float("FUTURES_IMPULSE_SL_ATR_MULT", 3.0)
            else:
                leverage_min = leverage_max = None
                tp_move = max(config.tp_atr_mult * current_atr_1h, config.tp_range_mult * consolidation_range, config.tp_floor_pct * current_price)
                sl_price = min(consolidation_low - config.sl_buffer_atr_mult * current_atr_1h, current_ema50 - config.sl_trend_atr_mult * current_atr_1h, current_price - current_atr_1h * 0.85)
            risk = current_price - sl_price
            if risk <= 0:
                return None
            if (
                (major_threshold_path and _env_bool("FUTURES_MAJOR_THRESHOLD_EXTEND_TP_FOR_COST_BUDGET", True))
                or (breakout_hold_path and _env_bool("FUTURES_BREAKOUT_HOLD_EXTEND_TP_FOR_COST_BUDGET", True))
                or (level_break_path and _env_bool("FUTURES_LEVEL_BREAK_EXTEND_TP_FOR_COST_BUDGET", True))
                or (btc_round_level_path and _env_bool("FUTURES_BTC_ROUND_LEVEL_EXTEND_TP_FOR_COST_BUDGET", True))
            ):
                sl_distance_pct = risk / current_price if current_price > 0 else 0.0
                projected_leverage = _leverage_for_signal_with_bounds(
                    _confidence(long_score, config.min_confidence_score),
                    sl_distance_pct,
                    config,
                    leverage_min if leverage_min is not None else config.leverage_min,
                    leverage_max if leverage_max is not None else config.leverage_max,
                )
                if projected_leverage is not None:
                    required_tp_distance_pct = _cost_budget_required_tp_distance_pct(
                        entry_price=current_price,
                        sl_price=sl_price,
                        leverage=projected_leverage,
                        symbol=getattr(config, "symbol", None),
                    )
                    if required_tp_distance_pct is not None:
                        tp_move = max(tp_move, current_price * required_tp_distance_pct)
            if tp_move / risk < config.min_reward_risk:
                return None
            entry_signal = (
                "MAJOR_THRESHOLD_LONG" if major_threshold_path
                else "BTC_ROUND_LEVEL_LONG" if btc_round_level_path
                else "COIL_BREAKOUT_LONG" if long_ok and breakout_long
                else "PRESSURE_BREAK_LONG" if long_ok and pressure_long
                else "TREND_CONTINUATION_LONG" if continuation_long_ok
                else "BREAKOUT_HOLD_LONG" if breakout_hold_path
                else "LEVEL_BREAK_LONG" if level_break_path
                else "IMPULSE_EVENT_CONTINUATION_LONG" if impulse_path
                else "MOMENTUM_BREAKAWAY_LONG" if breakaway_path
                else "RANGE_EXPANSION_CONTINUATION_LONG" if range_expansion_path
                else "EVENT_CATALYST_LONG"
            )
            if _entry_signal_disabled(config, entry_signal):
                return None
            # R2 — env-gated: disable COIL_BREAKOUT_LONG on BTC_USDT (loss-leader in 30d baseline).
            if (
                entry_signal == "COIL_BREAKOUT_LONG"
                and str(getattr(config, "symbol", "") or "").upper() == "BTC_USDT"
                and _env_bool("FUTURES_BTC_COIL_BREAKOUT_DISABLE_ENABLED", False)
            ):
                return None
            return _build_signal(
                side="LONG",
                score=long_score,
                entry_price=current_price,
                tp_price=current_price + tp_move,
                sl_price=sl_price,
                entry_signal=entry_signal,
                config=config,
                leverage_min_override=leverage_min,
                leverage_max_override=leverage_max,
                metadata={
                    "trend_24h": round(trend_24h, 6),
                    "trend_6h": round(trend_6h, 6),
                    "adx_1h": round(current_adx, 4),
                    "volume_ratio": round(volume_ratio, 4),
                    "consolidation_range_pct": round(consolidation_range_pct, 6),
                    "impulse_move_pct": round(impulse_move_pct, 6),
                    "impulse_move_atr": round(impulse_move_atr, 4),
                    "impulse_body_atr": round(impulse_body, 4),
                    "impulse_window_volume_ratio": round(impulse_window_volume_ratio, 4),
                    "breakout_hold": 1.0 if breakout_hold_path else 0.0,
                    "breakout_hold_level": round(breakout_hold_level, 10),
                    "breakout_hold_bars": float(breakout_hold_bars),
                    "breakout_hold_close_ratio": round(breakout_hold_close_ratio, 4),
                    "breakout_hold_support_margin_atr": round(breakout_hold_support_margin_atr, 4),
                    "breakout_hold_reclaim_score": round(breakout_hold_reclaim_score, 4),
                    "breakout_hold_shelf": 1.0 if breakout_hold_shelf_ok else 0.0,
                    "breakout_hold_shelf_volume_ratio": round(breakout_hold_shelf_volume_ratio, 4),
                    "breakout_hold_volume_ratio": round(breakout_hold_confirmation_volume_ratio, 4),
                    "level_break": 1.0 if level_break_path else 0.0,
                    "level_break_level": round(level_break_level_high, 10) if level_break_path else 0.0,
                    "level_break_lookback_bars": float(level_break_lookback),
                    "level_break_confirm_close_ratio": round(level_break_long_close_ratio, 4),
                    "level_break_move_pct": round(level_break_long_move_pct, 6),
                    "level_break_move_atr": round(level_break_long_move_atr, 4),
                    "level_break_volume_ratio": round(level_break_volume_ratio, 4),
                    "major_threshold": 1.0 if major_threshold_path else 0.0,
                    "major_threshold_level": round(major_threshold_long_level, 10) if major_threshold_path else 0.0,
                    "major_threshold_grid": round(major_threshold_grid, 10) if major_threshold_path else 0.0,
                    "major_threshold_lookback_bars": float(major_threshold_lookback),
                    "major_threshold_confirm_close_ratio": round(major_threshold_long_close_ratio, 4),
                    "major_threshold_move_pct": round(major_threshold_long_move_pct, 6),
                    "major_threshold_move_atr": round(major_threshold_long_move_atr, 4),
                    "major_threshold_volume_ratio": round(major_threshold_volume_ratio, 4),
                    "trailing_exit_activation_progress": _major_threshold_float(symbol_name, "TRAILING_ACTIVATION_PROGRESS", 0.45) if major_threshold_path else config.trailing_exit_activation_progress,
                    "trailing_exit_drawdown_pct": _major_threshold_float(symbol_name, "TRAILING_DRAWDOWN_PCT", 0.018) if major_threshold_path else config.trailing_exit_drawdown_pct,
                    "btc_round_level": 1.0 if btc_round_level_path else 0.0,
                    "btc_round_level_price": round(btc_round_level, 2) if btc_round_level_path else 0.0,
                    "btc_round_level_confirm_close_ratio": round(btc_round_level_close_ratio, 4),
                    "btc_round_level_move_pct": round(btc_round_level_move_pct, 6),
                    "btc_round_level_move_atr": round(btc_round_level_move_atr, 4),
                    "btc_round_level_volume_ratio": round(btc_round_level_volume_ratio, 4),
                    "breakaway": 1.0 if breakaway_path else 0.0,
                    "range_expansion": 1.0 if range_expansion_path else 0.0,
                    "event_catalyst": 1.0 if event_path else 0.0,
                    "event_anti_chase_block": 1.0 if event_long_anti_chase_block else 0.0,
                    "event_distance_to_recent_high_pct": round(distance_to_recent_high_pct, 6),
                    "event_distance_to_recent_high_atr": round(distance_to_recent_high_atr, 4),
                    "event_fresh_break": 1.0 if event_long_fresh_break else 0.0,
                    "market_gate_penalty": directional_market_penalty("LONG") if impulse_path or event_path else 0.0,
                    "crypto_event_bias": round(float(event_bias_score or 0.0), 4),
                    "crypto_event_max_severity": round(float(event_max_severity or 0.0), 4),
                    "crypto_event_count": float(event_count or 0),
                },
            )

        major_threshold_path = major_threshold_short_ok
        btc_reversal_path = btc_reversal_short_ok and not major_threshold_path
        impulse_path = impulse_short_ok and not (major_threshold_path or btc_reversal_path or short_ok or continuation_short_ok)
        level_break_path = level_break_short_ok and not (major_threshold_path or btc_reversal_path or short_ok or continuation_short_ok or impulse_short_ok)
        breakaway_path = breakaway_short_ok and not (major_threshold_path or btc_reversal_path or short_ok or continuation_short_ok or impulse_short_ok or level_break_path)
        range_expansion_path = range_expansion_short_ok and not (major_threshold_path or btc_reversal_path or short_ok or continuation_short_ok or impulse_short_ok or level_break_path or breakaway_short_ok)
        event_path = event_catalyst_short_ok and not (major_threshold_path or btc_reversal_path or short_ok or continuation_short_ok or impulse_short_ok or level_break_path or breakaway_short_ok or range_expansion_short_ok)
        if major_threshold_path:
            configured_cap = _major_threshold_float(symbol_name, "LEVERAGE_MAX", 8.0)
            hard_cap = _major_threshold_float(symbol_name, "HARD_LEVERAGE_MAX", configured_cap)
            leverage_max = max(1, int(min(float(config.leverage_max), configured_cap, hard_cap)))
            leverage_min = min(config.leverage_min, leverage_max)
            target_from_grid = major_threshold_short_level - major_threshold_grid * _major_threshold_float(symbol_name, "TP_GRID_MULT", 4.0)
            tp_move = max(
                _major_threshold_float(symbol_name, "TP_ATR_MULT", 8.0) * current_atr_15,
                _major_threshold_float(symbol_name, "TP_FLOOR_PCT", 0.045) * current_price,
                max(0.0, current_price - target_from_grid),
            )
            stop_pct = _major_threshold_float(symbol_name, "STOP_PCT", 0.008)
            min_stop_pct = _major_threshold_float(symbol_name, "MIN_STOP_PCT", 0.0045)
            max_stop_pct = _major_threshold_float(symbol_name, "MAX_STOP_PCT", 0.014)
            sl_price = min(
                major_threshold_short_level + current_atr_15 * _major_threshold_float(symbol_name, "SL_BUFFER_ATR", 0.55),
                major_threshold_recent_high + current_atr_15 * _major_threshold_float(symbol_name, "SWING_SL_BUFFER_ATR", 0.25),
                major_threshold_short_level * (1.0 + stop_pct),
                current_price * (1.0 + max_stop_pct),
            )
            threshold_stop_floor = major_threshold_short_level + max(
                current_atr_15 * _major_threshold_float(symbol_name, "SL_BUFFER_ATR", 0.55),
                major_threshold_buffer,
            )
            if sl_price <= current_price:
                sl_price = current_price + current_atr_15 * _major_threshold_float(symbol_name, "FALLBACK_SL_ATR", 3.0)
            if sl_price <= major_threshold_short_level:
                sl_price = max(current_price * (1.0 + min_stop_pct), threshold_stop_floor)
            if current_price > 0 and (sl_price - current_price) / current_price < min_stop_pct:
                sl_price = max(current_price * (1.0 + min_stop_pct), threshold_stop_floor)
        elif btc_reversal_path:
            configured_cap = _env_float("FUTURES_BTC_REVERSAL_SHORT_LEVERAGE_MAX", 8.0)
            hard_cap = _env_float("FUTURES_BTC_REVERSAL_SHORT_HARD_LEVERAGE_MAX", 8.0)
            leverage_max = max(1, int(min(float(config.leverage_max), configured_cap, hard_cap)))
            leverage_min = min(config.leverage_min, leverage_max)
            tp_move = max(
                _env_float("FUTURES_BTC_REVERSAL_SHORT_TP_ATR_MULT", 5.0) * current_atr_15,
                _env_float("FUTURES_BTC_REVERSAL_SHORT_TP_FLOOR_PCT", 0.022) * current_price,
            )
            min_stop_pct = _env_float("FUTURES_BTC_REVERSAL_SHORT_MIN_STOP_PCT", 0.0045)
            max_stop_pct = _env_float("FUTURES_BTC_REVERSAL_SHORT_MAX_STOP_PCT", 0.014)
            sl_price = min(
                btc_reversal_recent_high + current_atr_15 * _env_float("FUTURES_BTC_REVERSAL_SHORT_SWING_SL_BUFFER_ATR", 0.25),
                current_price * (1.0 + max_stop_pct),
            )
            if sl_price <= current_price:
                sl_price = current_price + current_atr_15 * _env_float("FUTURES_BTC_REVERSAL_SHORT_FALLBACK_SL_ATR", 3.0)
            if current_price > 0 and (sl_price - current_price) / current_price < min_stop_pct:
                sl_price = current_price * (1.0 + min_stop_pct)
        elif level_break_path:
            default_cap = min(float(config.leverage_max), _level_break_float(symbol_name, "LEVERAGE_MAX", 8.0))
            leverage_max = max(1, int(_level_break_float(symbol_name, "LEVERAGE_MAX", default_cap)))
            leverage_min = min(config.leverage_min, leverage_max)
            tp_move = max(
                _level_break_float(symbol_name, "TP_ATR_MULT", 5.0) * current_atr_15,
                _level_break_float(symbol_name, "TP_FLOOR_PCT", 0.014) * current_price,
            )
            sl_price = min(
                level_break_level_low + current_atr_15 * _level_break_float(symbol_name, "SL_BUFFER_ATR", 0.55),
                level_break_recent_high + current_atr_15 * _level_break_float(symbol_name, "SWING_SL_BUFFER_ATR", 0.20),
                current_price * (1.0 + _level_break_float(symbol_name, "MAX_STOP_PCT", 0.014)),
            )
            if sl_price <= current_price:
                sl_price = current_price + current_atr_15 * _level_break_float(symbol_name, "FALLBACK_SL_ATR", 2.5)
        elif impulse_path or breakaway_path or range_expansion_path or event_path:
            default_cap = min(float(config.leverage_max), 8.0)
            leverage_var = "FUTURES_EVENT_CATALYST_LEVERAGE_MAX" if event_path else "FUTURES_IMPULSE_LEVERAGE_MAX"
            leverage_max = max(1, int(_env_float(leverage_var, _env_float("FUTURES_IMPULSE_LEVERAGE_MAX", default_cap))))
            leverage_min = min(config.leverage_min, leverage_max)
            tp_move = max(_env_float("FUTURES_IMPULSE_TP_ATR_MULT", 5.0) * current_atr_15, _env_float("FUTURES_IMPULSE_TP_FLOOR_PCT", 0.012) * current_price)
            sl_price = min(
                impulse_recent_high + current_atr_15 * _env_float("FUTURES_IMPULSE_SWING_SL_BUFFER_ATR", 0.25),
                current_price + current_atr_15 * _env_float("FUTURES_IMPULSE_SL_ATR_MULT", 3.0),
                current_price * (1.0 + _env_float("FUTURES_IMPULSE_MAX_STOP_PCT", 0.012)),
            )
            if sl_price <= current_price:
                sl_price = current_price + current_atr_15 * _env_float("FUTURES_IMPULSE_SL_ATR_MULT", 3.0)
        else:
            leverage_min = leverage_max = None
            tp_move = max(config.tp_atr_mult * current_atr_1h, config.tp_range_mult * consolidation_range, config.tp_floor_pct * current_price)
            sl_price = max(consolidation_high + config.sl_buffer_atr_mult * current_atr_1h, current_ema50 + config.sl_trend_atr_mult * current_atr_1h, current_price + current_atr_1h * 0.85)
        risk = sl_price - current_price
        if (
            risk > 0
            and (
                (major_threshold_path and _env_bool("FUTURES_MAJOR_THRESHOLD_EXTEND_TP_FOR_COST_BUDGET", True))
                or (btc_reversal_path and _env_bool("FUTURES_BTC_REVERSAL_SHORT_EXTEND_TP_FOR_COST_BUDGET", True))
                or (level_break_path and _env_bool("FUTURES_LEVEL_BREAK_EXTEND_TP_FOR_COST_BUDGET", True))
            )
        ):
            sl_distance_pct = risk / current_price if current_price > 0 else 0.0
            projected_leverage = _leverage_for_signal_with_bounds(
                _confidence(short_score, config.min_confidence_score),
                sl_distance_pct,
                config,
                leverage_min if leverage_min is not None else config.leverage_min,
                leverage_max if leverage_max is not None else config.leverage_max,
            )
            if projected_leverage is not None:
                required_tp_distance_pct = _cost_budget_required_tp_distance_pct(
                    entry_price=current_price,
                    sl_price=sl_price,
                    leverage=projected_leverage,
                    symbol=getattr(config, "symbol", None),
                )
                if required_tp_distance_pct is not None:
                    tp_move = max(tp_move, current_price * required_tp_distance_pct)
        if risk <= 0 or tp_move / risk < config.min_reward_risk:
            return None
        entry_signal = (
            "MAJOR_THRESHOLD_SHORT" if major_threshold_path
            else "BTC_REVERSAL_BREAKDOWN_SHORT" if btc_reversal_path
            else "COIL_BREAKDOWN_SHORT" if short_ok and breakout_short
            else "PRESSURE_BREAK_SHORT" if short_ok and pressure_short
            else "TREND_CONTINUATION_SHORT" if continuation_short_ok
            else "LEVEL_BREAK_SHORT" if level_break_path
            else "IMPULSE_EVENT_CONTINUATION_SHORT" if impulse_path
            else "MOMENTUM_BREAKAWAY_SHORT" if breakaway_path
            else "RANGE_EXPANSION_CONTINUATION_SHORT" if range_expansion_path
            else "EVENT_CATALYST_SHORT"
        )
        if _entry_signal_disabled(config, entry_signal):
            return None
        return _build_signal(
            side="SHORT",
            score=short_score,
            entry_price=current_price,
            tp_price=current_price - tp_move,
            sl_price=sl_price,
            entry_signal=entry_signal,
            config=config,
            leverage_min_override=leverage_min,
            leverage_max_override=leverage_max,
            metadata={
                "trend_24h": round(trend_24h, 6),
                "trend_6h": round(trend_6h, 6),
                "adx_1h": round(current_adx, 4),
                "volume_ratio": round(volume_ratio, 4),
                "consolidation_range_pct": round(consolidation_range_pct, 6),
                "impulse_move_pct": round(impulse_move_pct, 6),
                "impulse_move_atr": round(impulse_move_atr, 4),
                "impulse_body_atr": round(impulse_body, 4),
                "impulse_window_volume_ratio": round(impulse_window_volume_ratio, 4),
                "level_break": 1.0 if level_break_path else 0.0,
                "level_break_level": round(level_break_level_low, 10) if level_break_path else 0.0,
                "level_break_lookback_bars": float(level_break_lookback),
                "level_break_confirm_close_ratio": round(level_break_short_close_ratio, 4),
                "level_break_move_pct": round(level_break_short_move_pct, 6),
                "level_break_move_atr": round(level_break_short_move_atr, 4),
                "level_break_volume_ratio": round(level_break_volume_ratio, 4),
                "major_threshold": 1.0 if major_threshold_path else 0.0,
                "major_threshold_level": round(major_threshold_short_level, 10) if major_threshold_path else 0.0,
                "major_threshold_grid": round(major_threshold_grid, 10) if major_threshold_path else 0.0,
                "major_threshold_lookback_bars": float(major_threshold_lookback),
                "major_threshold_confirm_close_ratio": round(major_threshold_short_close_ratio, 4),
                "major_threshold_move_pct": round(major_threshold_short_move_pct, 6),
                "major_threshold_move_atr": round(major_threshold_short_move_atr, 4),
                "major_threshold_volume_ratio": round(major_threshold_volume_ratio, 4),
                "trailing_exit_activation_progress": _major_threshold_float(symbol_name, "TRAILING_ACTIVATION_PROGRESS", 0.45) if major_threshold_path else config.trailing_exit_activation_progress,
                "trailing_exit_drawdown_pct": _major_threshold_float(symbol_name, "TRAILING_DRAWDOWN_PCT", 0.018) if major_threshold_path else config.trailing_exit_drawdown_pct,
                "btc_reversal_short": 1.0 if btc_reversal_path else 0.0,
                "btc_reversal_recent_high": round(btc_reversal_recent_high, 10) if btc_reversal_path else 0.0,
                "btc_reversal_recent_low": round(btc_reversal_recent_low, 10) if btc_reversal_path else 0.0,
                "btc_reversal_prior_low": round(btc_reversal_prior_low, 10) if btc_reversal_path else 0.0,
                "btc_reversal_drop_pct": round(btc_reversal_drop_pct, 6),
                "btc_reversal_drop_atr": round(btc_reversal_drop_atr, 4),
                "btc_reversal_confirm_close_ratio": round(btc_reversal_confirm_close_ratio, 4),
                "btc_reversal_volume_ratio": round(btc_reversal_volume_ratio, 4),
                "breakaway": 1.0 if breakaway_path else 0.0,
                "range_expansion": 1.0 if range_expansion_path else 0.0,
                "event_catalyst": 1.0 if event_path else 0.0,
                "event_anti_chase_block": 1.0 if event_short_anti_chase_block else 0.0,
                "event_distance_to_recent_low_pct": round(distance_to_recent_low_pct, 6),
                "event_distance_to_recent_low_atr": round(distance_to_recent_low_atr, 4),
                "event_fresh_break": 1.0 if event_short_fresh_break else 0.0,
                "market_gate_penalty": directional_market_penalty("SHORT") if impulse_path or event_path else 0.0,
                "crypto_event_bias": round(float(event_bias_score or 0.0), 4),
                "crypto_event_max_severity": round(float(event_max_severity or 0.0), 4),
                "crypto_event_count": float(event_count or 0),
            },
        )

    order = ["LONG", "SHORT"] if long_score >= short_score else ["SHORT", "LONG"]
    for side in order:
        if side == "LONG" and not long_passes:
            continue
        if side == "SHORT" and not short_passes:
            continue
        signal = build_direction(side)
        if signal is not None:
            return signal
    return None


def diagnose_impulse_rejection(frame_15m: pd.DataFrame, config: StrategyConfig) -> str:
    try:
        if frame_15m is None or len(frame_15m) < 220:
            return f"impulse_insufficient_15m_bars={0 if frame_15m is None else len(frame_15m)}<220"
        frame_15m = frame_15m.copy()
        frame_1h = resample_ohlcv(frame_15m, "1h")
        if len(frame_1h) < 120:
            return f"impulse_insufficient_1h_bars={len(frame_1h)}<120"
        close_15 = frame_15m["close"].astype(float)
        open_15 = frame_15m["open"].astype(float)
        volume_15 = frame_15m["volume"].astype(float)
        close_1h = frame_1h["close"].astype(float)
        ema20 = calc_ema(close_1h, 20)
        rsi_1h = calc_rsi(close_1h, 14)
        rsi_15 = calc_rsi(close_15, 14)
        adx_1h = calc_adx(frame_1h, 14)
        atr_1h = calc_atr(frame_1h, 14)
        atr_15 = calc_atr(frame_15m, 14)

        current_price = float(close_15.iloc[-1])
        current_ema20 = _safe_float(ema20.iloc[-1])
        current_rsi_1h = _safe_float(rsi_1h.iloc[-1])
        current_rsi_15 = _safe_float(rsi_15.iloc[-1])
        current_adx = _safe_float(adx_1h.iloc[-1])
        current_atr_1h = _safe_float(atr_1h.iloc[-1])
        current_atr_15 = _safe_float(atr_15.iloc[-1])
        if not all(math.isfinite(value) and value > 0 for value in [current_price, current_ema20, current_adx, current_atr_1h, current_atr_15]):
            return "impulse_indicator_not_ready"

        lookback = max(3, int(_env_float("FUTURES_IMPULSE_LOOKBACK_BARS", 8.0)))
        reference = float(close_15.iloc[-(lookback + 1)]) if len(close_15) > lookback else current_price
        move_pct = (current_price / reference) - 1.0 if reference > 0 else 0.0
        move_atr = abs(current_price - reference) / current_atr_15 if current_atr_15 > 0 else 0.0
        recent_close_high = float(close_15.iloc[-lookback:].max())
        recent_close_low = float(close_15.iloc[-lookback:].min())
        close_buffer = _env_float("FUTURES_IMPULSE_CLOSE_BUFFER_ATR", 0.35)
        close_near_high = current_price >= recent_close_high - current_atr_15 * close_buffer
        close_near_low = current_price <= recent_close_low + current_atr_15 * close_buffer
        volume_baseline = max(1e-9, float(volume_15.iloc[-(config.consolidation_window_bars + 1):-1].mean()))
        volume_ratio = float(volume_15.iloc[-1]) / volume_baseline
        prior_volume_end = max(0, len(volume_15) - lookback)
        prior_volume_start = max(0, prior_volume_end - config.consolidation_window_bars)
        prior_volume = volume_15.iloc[prior_volume_start:prior_volume_end]
        if prior_volume.empty:
            prior_volume = volume_15.iloc[-(config.consolidation_window_bars + 1):-1]
        window_volume_baseline = max(1e-9, float(prior_volume.mean()))
        window_volume_ratio = float(volume_15.iloc[-lookback:].sum()) / (window_volume_baseline * lookback)
        trend_6h = (float(close_1h.iloc[-1]) / float(close_1h.iloc[-7])) - 1.0 if len(close_1h) >= 7 else 0.0
        ema_slope = (current_ema20 / float(ema20.iloc[-6])) - 1.0 if len(ema20) >= 6 and float(ema20.iloc[-6]) > 0 else 0.0
        ema_extension = abs(current_price - current_ema20) / current_atr_1h if current_atr_1h > 0 else 999.0
        body_atr = abs(float(close_15.iloc[-1]) - float(open_15.iloc[-1])) / current_atr_15 if current_atr_15 > 0 else 0.0
        side = "LONG" if move_pct >= 0 else "SHORT"
        return (
            "impulse_gate_block "
            f"side={side} move_pct={move_pct:+.4f} min={_env_float('FUTURES_IMPULSE_MIN_MOVE_PCT', 0.006):.4f} "
            f"move_atr={move_atr:.2f} min={_env_float('FUTURES_IMPULSE_MIN_MOVE_ATR', 1.10):.2f} "
            f"volume_ratio={volume_ratio:.2f} floor={_env_float('FUTURES_IMPULSE_VOLUME_FLOOR', 1.15):.2f} "
            f"window_volume_ratio={window_volume_ratio:.2f} breakaway_floor={_env_float('FUTURES_BREAKAWAY_WINDOW_VOLUME_FLOOR', 0.70):.2f} "
            f"adx={current_adx:.2f} floor={_env_float('FUTURES_IMPULSE_ADX_MIN', 12.0):.2f} "
            f"rsi_1h={current_rsi_1h:.1f} rsi_15={current_rsi_15:.1f} "
            f"trend_6h={trend_6h:+.4f} ema_slope={ema_slope:+.4f} "
            f"ema_extension_atr={ema_extension:.2f} max={_env_float('FUTURES_IMPULSE_MAX_EMA_EXTENSION_ATR', 2.75):.2f} "
            f"close_near_high={close_near_high} close_near_low={close_near_low} body_atr={body_atr:.2f}"
        )
    except Exception as exc:
        return f"impulse_diagnostic_error={type(exc).__name__}"


def diagnose_setup_rejection(frame_15m: pd.DataFrame, config: StrategyConfig) -> str:
    """Gate A A5 (memo 1 §7): return the *first* gate that rejected a bar.

    Pure function, no I/O. Used by the runtime to emit a ``[GATE_BLOCK]`` log
    line explaining why ``score_btc_futures_setup`` returned ``None``, so the
    operator can tell the difference between "market was quiet" and "filters
    are mathematically unreachable for this symbol" (the Futures-bot memo 1
    §3 finding on PEPE / TAO running BTC-tuned gates).

    The diagnosis is best-effort and conservative: any compute failure returns
    ``"diagnostic_error"`` rather than raising.
    """

    try:
        if frame_15m is None or len(frame_15m) < 220:
            return f"insufficient_15m_bars={0 if frame_15m is None else len(frame_15m)}<220"
        frame_1h = resample_ohlcv(frame_15m.copy(), "1h")
        if len(frame_1h) < 120:
            return f"insufficient_1h_bars={len(frame_1h)}<120"
        close_15 = frame_15m["close"].astype(float)
        volume_15 = frame_15m["volume"].astype(float)
        close_1h = frame_1h["close"].astype(float)
        ema20 = calc_ema(close_1h, 20)
        ema50 = calc_ema(close_1h, 50)
        ema100 = calc_ema(close_1h, 100)
        rsi_1h = calc_rsi(close_1h, 14)
        rsi_15 = calc_rsi(close_15, 14)
        adx_1h = calc_adx(frame_1h, 14)
        atr_1h = calc_atr(frame_1h, 14)
        atr_15 = calc_atr(frame_15m, 14)

        current_price = float(close_15.iloc[-1])
        current_ema20 = float(ema20.iloc[-1])
        current_ema50 = float(ema50.iloc[-1])
        current_ema100 = float(ema100.iloc[-1])
        current_rsi_1h = float(rsi_1h.iloc[-1])
        current_rsi_15 = float(rsi_15.iloc[-1])
        current_adx = float(adx_1h.iloc[-1])
        current_atr_1h = float(atr_1h.iloc[-1])
        current_atr_15 = float(atr_15.iloc[-1])

        consolidation = frame_15m.iloc[-(config.consolidation_window_bars + 1):-1]
        if consolidation.empty:
            return "consolidation_window_empty"
        consolidation_high = float(consolidation["high"].max())
        consolidation_low = float(consolidation["low"].min())
        consolidation_range_pct = (consolidation_high - consolidation_low) / current_price if current_price > 0 else 0.0
        consolidation_cap = max(
            config.consolidation_max_range_pct,
            (current_atr_15 / current_price) * config.consolidation_atr_mult if current_price > 0 else 0.0,
        )
        if consolidation_range_pct > consolidation_cap:
            return (
                f"consolidation_range_pct={consolidation_range_pct:.4f}>{consolidation_cap:.4f}"
            )

        if current_adx < config.adx_floor:
            return f"adx={current_adx:.2f}<{config.adx_floor:.2f}"

        trend_24h = (float(close_1h.iloc[-1]) / float(close_1h.iloc[-25])) - 1.0 if len(close_1h) >= 25 else 0.0
        trend_6h = (float(close_1h.iloc[-1]) / float(close_1h.iloc[-7])) - 1.0 if len(close_1h) >= 7 else 0.0
        if abs(trend_24h) < config.trend_24h_floor:
            return f"trend_24h={trend_24h:+.4f}|<{config.trend_24h_floor:.4f}"
        if abs(trend_6h) < config.trend_6h_floor:
            return f"trend_6h={trend_6h:+.4f}|<{config.trend_6h_floor:.4f}"

        # EMA alignment: price must be stacked in one direction
        long_stack = current_ema20 > current_ema50 > current_ema100
        short_stack = current_ema20 < current_ema50 < current_ema100
        if not (long_stack or short_stack):
            return (
                f"ema_not_aligned ema20={current_ema20:.2f} ema50={current_ema50:.2f} ema100={current_ema100:.2f}"
            )

        # Volume on the trigger bar
        volume_baseline = max(
            1e-9,
            float(volume_15.iloc[-(config.consolidation_window_bars + 1):-1].mean()),
        )
        volume_ratio = float(volume_15.iloc[-1]) / volume_baseline
        if volume_ratio < config.volume_ratio_floor:
            return f"volume_ratio={volume_ratio:.2f}<{config.volume_ratio_floor:.2f}"

        # RSI alignment (direction-aware)
        if long_stack:
            if current_rsi_1h < 50.0:
                return f"rsi_1h={current_rsi_1h:.1f}<50.0 (long-stack)"
            if current_rsi_15 < 48.0:
                return f"rsi_15={current_rsi_15:.1f}<48.0 (long-stack)"
        else:
            if current_rsi_1h > 50.0:
                return f"rsi_1h={current_rsi_1h:.1f}>50.0 (short-stack)"
            if current_rsi_15 > 52.0:
                return f"rsi_15={current_rsi_15:.1f}>52.0 (short-stack)"

        # Breakout / pressure zone — if we got here, stack and trend are fine
        # but the trigger bar is not in a breakout region.
        breakout_buffer = current_atr_15 * config.breakout_buffer_atr
        if long_stack:
            if current_price <= consolidation_high - breakout_buffer * 0.35:
                return (
                    f"no_breakout_long price={current_price:.2f} coil_high={consolidation_high:.2f} "
                    f"buffer={breakout_buffer:.2f}"
                )
        else:
            if current_price >= consolidation_low + breakout_buffer * 0.35:
                return (
                    f"no_breakdown_short price={current_price:.2f} coil_low={consolidation_low:.2f} "
                    f"buffer={breakout_buffer:.2f}"
                )

        # If everything above passed, the score probably landed below the
        # threshold or the reward/risk ratio rejected the entry.
        return "score_or_rr_below_threshold"
    except Exception as exc:
        return f"diagnostic_error={type(exc).__name__}"