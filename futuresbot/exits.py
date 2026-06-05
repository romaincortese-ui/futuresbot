from __future__ import annotations

from datetime import datetime, timezone

from futuresbot.models import FuturesPosition


TRAILING_EXIT_ARMED_KEY = "trailing_exit_armed"
TRAILING_EXIT_BEST_PRICE_KEY = "trailing_exit_best_price"
TRAILING_EXIT_STOP_PRICE_KEY = "trailing_exit_stop_price"
PROFIT_LOCK_PEAK_PCT_KEY = "profit_lock_peak_pnl_pct"
PROFIT_LOCK_PEAK_GROSS_PCT_KEY = "profit_lock_peak_gross_pnl_pct"
PROFIT_LOCK_PEAK_USDT_KEY = "profit_lock_peak_pnl_usdt"
PROFIT_LOCK_PEAK_PRICE_KEY = "profit_lock_peak_price"
PROFIT_LOCK_STOP_PCT_KEY = "profit_lock_stop_pnl_pct"
PROFIT_LOCK_STOP_GROSS_PCT_KEY = "profit_lock_stop_gross_pnl_pct"
MICRO_LOCK_PEAK_PCT_KEY = "micro_profit_lock_peak_pnl_pct"
MICRO_LOCK_PEAK_GROSS_PCT_KEY = "micro_profit_lock_peak_gross_pnl_pct"
MICRO_LOCK_PEAK_PRICE_KEY = "micro_profit_lock_peak_price"
MICRO_LOCK_STOP_PCT_KEY = "micro_profit_lock_stop_pnl_pct"
MICRO_LOCK_STOP_GROSS_PCT_KEY = "micro_profit_lock_stop_gross_pnl_pct"
MICRO_LOCK_RELEASED_KEY = "micro_profit_lock_released"
ADVERSE_PEAK_TRAIL_PEAK_GROSS_PCT_KEY = "adverse_peak_trail_peak_gross_pnl_pct"
ADVERSE_PEAK_TRAIL_PEAK_PRICE_KEY = "adverse_peak_trail_peak_price"
ADVERSE_PEAK_TRAIL_STOP_GROSS_PCT_KEY = "adverse_peak_trail_stop_gross_pnl_pct"
NO_PROGRESS_EXIT_PEAK_GROSS_PCT_KEY = "no_progress_exit_peak_gross_pnl_pct"
NO_PROGRESS_EXIT_PEAK_PRICE_KEY = "no_progress_exit_peak_price"
NO_PROGRESS_EXIT_LOSS_LIMIT_GROSS_PCT_KEY = "no_progress_exit_loss_limit_gross_pnl_pct"
STAGNATION_EXIT_PEAK_PROGRESS_KEY = "stagnation_exit_peak_tp_progress"
STAGNATION_EXIT_PEAK_PRICE_KEY = "stagnation_exit_peak_price"
STAGNATION_EXIT_DEFAULT_ENTRY_SIGNALS = frozenset(
    {
        "IMPULSE_EVENT_CONTINUATION_LONG",
        "IMPULSE_EVENT_CONTINUATION_SHORT",
        "EVENT_CATALYST_LONG",
        "EVENT_CATALYST_SHORT",
    }
)
MICRO_LOCK_DEFAULT_ENTRY_SIGNALS = frozenset({"*"})
MICRO_LOCK_DEFAULT_RECOVERED_ENTRY_SIGNALS = frozenset({"RECOVERED"})

MICRO_LOCK_DEFAULT_SYMBOLS = frozenset(
    {
        "ADA_USDT",
        "APT_USDT",
        "AVAX_USDT",
        "DOGE_USDT",
        "HYPE_USDT",
        "LINK_USDT",
        "PEPE_USDT",
        "SEI_USDT",
        "SUI_USDT",
        "TAO_USDT",
        "XRP_USDT",
        "ZEC_USDT",
    }
)
# SOL is intentionally NOT in the exclusion list: its micro-lock releases at
# 50% TP progress (FUTURES_MICRO_LOCK_MAX_PEAK_TP_PROGRESS), which already
# prevents the lock from cutting large SOL runs short.  Keeping SOL excluded
# meant that trades peaking at 2–3% gross (below the 4% peak-lock trigger)
# had no protection at all against giving back their gains.
MICRO_LOCK_DEFAULT_EXCLUDED_SYMBOLS = frozenset({"BTC_USDT", "ETH_USDT", "BNB_USDT"})


def _total_and_current_move(position: FuturesPosition, price: float) -> tuple[float, float]:
    if position.side == "LONG":
        return position.tp_price - position.entry_price, price - position.entry_price
    return position.entry_price - position.tp_price, position.entry_price - price


def trailing_activation_reached(
    position: FuturesPosition,
    price: float,
    *,
    activation_progress: float,
    min_profit_pct: float,
) -> bool:
    total_move, current_move = _total_and_current_move(position, price)
    if total_move <= 0 or current_move <= 0 or position.entry_price <= 0:
        return False
    return current_move / total_move >= activation_progress and current_move / position.entry_price >= min_profit_pct


def tp_progress(position: FuturesPosition, price: float) -> float | None:
    total_move, current_move = _total_and_current_move(position, price)
    if total_move <= 0:
        return None
    return current_move / total_move


def is_trailing_exit_armed(position: FuturesPosition) -> bool:
    return bool((position.metadata or {}).get(TRAILING_EXIT_ARMED_KEY))


def trailing_best_price(position: FuturesPosition) -> float | None:
    try:
        value = float((position.metadata or {}).get(TRAILING_EXIT_BEST_PRICE_KEY) or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    return value if value > 0 else None


def arm_trailing_exit(position: FuturesPosition, price: float) -> bool:
    if price <= 0:
        return False
    changed = False
    if not is_trailing_exit_armed(position):
        position.metadata[TRAILING_EXIT_ARMED_KEY] = True
        changed = True
    return update_trailing_best_price(position, price) or changed


def update_trailing_best_price(position: FuturesPosition, price: float) -> bool:
    if price <= 0:
        return False
    current = trailing_best_price(position)
    better = current is None or (position.side == "LONG" and price > current) or (position.side == "SHORT" and price < current)
    if not better:
        return False
    position.metadata[TRAILING_EXIT_BEST_PRICE_KEY] = float(price)
    return True


def trailing_stop_price(position: FuturesPosition, drawdown_pct: float) -> float | None:
    if drawdown_pct <= 0:
        return None
    best = trailing_best_price(position)
    if best is None:
        return None
    if position.side == "LONG":
        stop = best * (1.0 - drawdown_pct)
    else:
        stop = best * (1.0 + drawdown_pct)
    position.metadata[TRAILING_EXIT_STOP_PRICE_KEY] = float(stop)
    return stop


def trailing_stop_hit(position: FuturesPosition, price: float, drawdown_pct: float) -> bool:
    stop = trailing_stop_price(position, drawdown_pct)
    if stop is None or price <= 0:
        return False
    return price <= stop if position.side == "LONG" else price >= stop


def evaluate_trailing_tick(
    position: FuturesPosition,
    price: float,
    *,
    activation_progress: float,
    min_profit_pct: float,
    drawdown_pct: float,
) -> tuple[bool, bool]:
    if drawdown_pct <= 0:
        return False, False
    changed = False
    if not is_trailing_exit_armed(position):
        if not trailing_activation_reached(
            position,
            price,
            activation_progress=activation_progress,
            min_profit_pct=min_profit_pct,
        ):
            return False, False
        changed = arm_trailing_exit(position, price)
        return False, changed
    changed = update_trailing_best_price(position, price)
    return trailing_stop_hit(position, price, drawdown_pct), changed


def evaluate_trailing_bar(
    position: FuturesPosition,
    *,
    high: float,
    low: float,
    activation_progress: float,
    min_profit_pct: float,
    drawdown_pct: float,
) -> tuple[tuple[float, str] | None, bool]:
    if drawdown_pct <= 0:
        return None, False
    favorable_price = high if position.side == "LONG" else low
    adverse_price = low if position.side == "LONG" else high
    armed_before_bar = is_trailing_exit_armed(position)
    if not armed_before_bar:
        if trailing_activation_reached(
            position,
            favorable_price,
            activation_progress=activation_progress,
            min_profit_pct=min_profit_pct,
        ):
            return None, arm_trailing_exit(position, favorable_price)
        return None, False
    changed = update_trailing_best_price(position, favorable_price)
    stop = trailing_stop_price(position, drawdown_pct)
    if stop is not None and (adverse_price <= stop if position.side == "LONG" else adverse_price >= stop):
        return (stop, "TRAILING_TAKE_PROFIT"), changed
    return None, changed


def _metadata_float(metadata: dict, key: str) -> float | None:
    try:
        value = float(metadata.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return None
    return value if value != 0.0 else None


def _metadata_override_float(metadata: dict, key: str) -> float | None:
    if key not in metadata:
        return None
    raw_value = metadata.get(key)
    if raw_value is None:
        return None
    if isinstance(raw_value, str) and raw_value.strip() == "":
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _metadata_override_or(metadata: dict, key: str, default: float) -> float:
    override = _metadata_override_float(metadata, key)
    return default if override is None else override


def _symbol_tokens(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        raw_items = value.replace(";", ",").replace(" ", ",").split(",")
    else:
        try:
            raw_items = list(value)  # type: ignore[arg-type]
        except TypeError:
            raw_items = []
    return {str(item).strip().upper() for item in raw_items if str(item).strip()}


def _normalized_entry_signals(value: object) -> set[str]:
    if value is None:
        return set(STAGNATION_EXIT_DEFAULT_ENTRY_SIGNALS)
    if isinstance(value, str):
        raw_items = value.replace(";", ",").replace(" ", ",").split(",")
    else:
        try:
            raw_items = list(value)  # type: ignore[arg-type]
        except TypeError:
            raw_items = []
    return {str(item).strip().upper() for item in raw_items if str(item).strip()}


def micro_lock_eligible(
    position: FuturesPosition,
    *,
    symbols: object = None,
    excluded_symbols: object = None,
    entry_signals: object = None,
    recovered_entry_signals: object = None,
    min_atr_pct: float = 0.006,
    max_entry_price: float = 25.0,
) -> bool:
    symbol = str(position.symbol or "").upper()
    included = _symbol_tokens(symbols) if symbols is not None else set(MICRO_LOCK_DEFAULT_SYMBOLS)
    excluded = _symbol_tokens(excluded_symbols) if excluded_symbols is not None else set(MICRO_LOCK_DEFAULT_EXCLUDED_SYMBOLS)
    included_by_symbol = "*" in included or symbol in included
    if symbol in excluded:
        return False

    # Entry-signal parameters are retained for env/backtest compatibility, but
    # micro-lock protection is lane-agnostic: eligible positions should not give
    # back small gains just because they came from a different setup lane.
    _ = (entry_signals, recovered_entry_signals)

    if included_by_symbol:
        return True
    metadata = position.metadata if isinstance(position.metadata, dict) else {}
    atr_pct = _metadata_float(metadata, "atr_15m_pct") or _metadata_float(metadata, "current_atr_15_pct") or 0.0
    try:
        entry_price = float(position.entry_price or 0.0)
    except (TypeError, ValueError):
        entry_price = 0.0
    return atr_pct >= max(0.0, min_atr_pct) or (0.0 < entry_price <= max(0.0, max_entry_price))


def _update_micro_lock_peak(
    position: FuturesPosition,
    price: float,
    *,
    taker_fee_rate: float,
) -> tuple[bool, float, float]:
    metadata = position.metadata if isinstance(position.metadata, dict) else {}
    if metadata is not position.metadata:
        position.metadata = metadata
    gross_pnl_pct = position_margin_pnl_pct(position, price)
    net_pnl_pct = position_net_pnl_pct(position, price, taker_fee_rate)
    if gross_pnl_pct is None or net_pnl_pct is None:
        return False, 0.0, 0.0

    changed = False
    net_peak_pct = _metadata_float(metadata, MICRO_LOCK_PEAK_PCT_KEY) or 0.0
    if net_pnl_pct > net_peak_pct:
        net_peak_pct = net_pnl_pct
        metadata[MICRO_LOCK_PEAK_PCT_KEY] = float(net_pnl_pct)
        metadata[MICRO_LOCK_PEAK_PRICE_KEY] = float(price)
        changed = True

    gross_peak_pct = _metadata_float(metadata, MICRO_LOCK_PEAK_GROSS_PCT_KEY) or max(0.0, net_peak_pct)
    if gross_pnl_pct > gross_peak_pct:
        gross_peak_pct = gross_pnl_pct
        metadata[MICRO_LOCK_PEAK_GROSS_PCT_KEY] = float(gross_pnl_pct)
        changed = True
    return changed, gross_peak_pct, net_peak_pct


def _micro_lock_exit_from_stop(
    position: FuturesPosition,
    *,
    stop_pct: float,
    taker_fee_rate: float,
    min_exit_net_pct: float,
    exit_slippage_buffer_pct: float = 0.0,
) -> tuple[float, str] | None:
    exit_price = price_for_margin_pnl_pct(position, stop_pct)
    if exit_price is None or exit_price <= 0:
        return None
    net_exit_pct = position_net_pnl_pct(position, exit_price, taker_fee_rate)
    required_net_pct = max(0.0, min_exit_net_pct) + max(0.0, exit_slippage_buffer_pct)
    if net_exit_pct is not None and net_exit_pct < required_net_pct:
        return None
    reason = "MICRO_PROFIT_LOCK" if net_exit_pct is None or net_exit_pct > 0.0 else "MICRO_PROTECTION_GAP_EXIT"
    return exit_price, reason


def evaluate_micro_lock_tick(
    position: FuturesPosition,
    price: float,
    *,
    taker_fee_rate: float,
    trigger_pct: float,
    pullback_fraction: float,
    floor_pct: float,
    min_exit_net_pct: float = 0.0,
    max_peak_tp_progress: float = 0.50,
    symbols: object = None,
    excluded_symbols: object = None,
    entry_signals: object = None,
    recovered_entry_signals: object = None,
    min_atr_pct: float = 0.006,
    max_entry_price: float = 25.0,
    exit_slippage_buffer_pct: float = 0.0,
) -> tuple[tuple[float, str] | None, bool]:
    if trigger_pct <= 0 or price <= 0:
        return None, False
    if not micro_lock_eligible(
        position,
        symbols=symbols,
        excluded_symbols=excluded_symbols,
        entry_signals=entry_signals,
        recovered_entry_signals=recovered_entry_signals,
        min_atr_pct=min_atr_pct,
        max_entry_price=max_entry_price,
    ):
        return None, False
    metadata = position.metadata if isinstance(position.metadata, dict) else {}
    if metadata is not position.metadata:
        position.metadata = metadata
    if metadata.get(MICRO_LOCK_RELEASED_KEY):
        return None, False

    trigger_pct = _metadata_float(metadata, "micro_profit_lock_trigger_pct_override") or trigger_pct
    pullback_fraction = _metadata_float(metadata, "micro_profit_lock_pullback_fraction_override") or pullback_fraction
    floor_pct = _metadata_float(metadata, "micro_profit_lock_floor_pct_override") or floor_pct
    min_exit_net_pct = _metadata_float(metadata, "micro_profit_lock_exit_min_net_pct_override") or min_exit_net_pct
    max_peak_tp_progress = _metadata_float(metadata, "micro_profit_lock_max_peak_tp_progress_override") or max_peak_tp_progress

    changed, gross_peak_pct, net_peak_pct = _update_micro_lock_peak(position, price, taker_fee_rate=taker_fee_rate)
    progress = tp_progress(position, price)
    if max_peak_tp_progress > 0 and progress is not None and progress >= max(0.0, max_peak_tp_progress):
        metadata[MICRO_LOCK_RELEASED_KEY] = True
        return None, True
    if gross_peak_pct < trigger_pct:
        return None, changed

    bounded_pullback = min(0.95, max(0.0, pullback_fraction))
    stop_pct = max(0.0, floor_pct, gross_peak_pct * (1.0 - bounded_pullback))
    net_stop_pct = max(0.0, net_peak_pct * (1.0 - bounded_pullback))
    if metadata.get(MICRO_LOCK_STOP_GROSS_PCT_KEY) != stop_pct:
        metadata[MICRO_LOCK_STOP_GROSS_PCT_KEY] = float(stop_pct)
        changed = True
    if metadata.get(MICRO_LOCK_STOP_PCT_KEY) != net_stop_pct:
        metadata[MICRO_LOCK_STOP_PCT_KEY] = float(net_stop_pct)
        changed = True

    gross_pnl_pct = position_margin_pnl_pct(position, price)
    if gross_pnl_pct is None or gross_pnl_pct > stop_pct:
        return None, changed
    return _micro_lock_exit_from_stop(
        position,
        stop_pct=stop_pct,
        taker_fee_rate=taker_fee_rate,
        min_exit_net_pct=min_exit_net_pct,
        exit_slippage_buffer_pct=exit_slippage_buffer_pct,
    ), changed


def evaluate_micro_lock_bar(
    position: FuturesPosition,
    *,
    high: float,
    low: float,
    taker_fee_rate: float,
    trigger_pct: float,
    pullback_fraction: float,
    floor_pct: float,
    min_exit_net_pct: float = 0.0,
    max_peak_tp_progress: float = 0.50,
    symbols: object = None,
    excluded_symbols: object = None,
    entry_signals: object = None,
    recovered_entry_signals: object = None,
    min_atr_pct: float = 0.006,
    max_entry_price: float = 25.0,
    exit_slippage_buffer_pct: float = 0.0,
) -> tuple[tuple[float, str] | None, bool]:
    if trigger_pct <= 0 or high <= 0 or low <= 0:
        return None, False
    if not micro_lock_eligible(
        position,
        symbols=symbols,
        excluded_symbols=excluded_symbols,
        entry_signals=entry_signals,
        recovered_entry_signals=recovered_entry_signals,
        min_atr_pct=min_atr_pct,
        max_entry_price=max_entry_price,
    ):
        return None, False
    metadata = position.metadata if isinstance(position.metadata, dict) else {}
    if metadata is not position.metadata:
        position.metadata = metadata
    if metadata.get(MICRO_LOCK_RELEASED_KEY):
        return None, False

    trigger_pct = _metadata_float(metadata, "micro_profit_lock_trigger_pct_override") or trigger_pct
    pullback_fraction = _metadata_float(metadata, "micro_profit_lock_pullback_fraction_override") or pullback_fraction
    floor_pct = _metadata_float(metadata, "micro_profit_lock_floor_pct_override") or floor_pct
    min_exit_net_pct = _metadata_float(metadata, "micro_profit_lock_exit_min_net_pct_override") or min_exit_net_pct
    max_peak_tp_progress = _metadata_float(metadata, "micro_profit_lock_max_peak_tp_progress_override") or max_peak_tp_progress

    armed_before_bar = (_metadata_float(metadata, MICRO_LOCK_STOP_GROSS_PCT_KEY) or 0.0) > 0.0
    favorable_price = high if position.side == "LONG" else low
    adverse_price = low if position.side == "LONG" else high
    changed, gross_peak_pct, net_peak_pct = _update_micro_lock_peak(position, favorable_price, taker_fee_rate=taker_fee_rate)
    favorable_progress = tp_progress(position, favorable_price)
    if max_peak_tp_progress > 0 and favorable_progress is not None and favorable_progress >= max(0.0, max_peak_tp_progress):
        metadata[MICRO_LOCK_RELEASED_KEY] = True
        return None, True
    if gross_peak_pct < trigger_pct:
        return None, changed

    bounded_pullback = min(0.95, max(0.0, pullback_fraction))
    stop_pct = max(0.0, floor_pct, gross_peak_pct * (1.0 - bounded_pullback))
    net_stop_pct = max(0.0, net_peak_pct * (1.0 - bounded_pullback))
    if metadata.get(MICRO_LOCK_STOP_GROSS_PCT_KEY) != stop_pct:
        metadata[MICRO_LOCK_STOP_GROSS_PCT_KEY] = float(stop_pct)
        changed = True
    if metadata.get(MICRO_LOCK_STOP_PCT_KEY) != net_stop_pct:
        metadata[MICRO_LOCK_STOP_PCT_KEY] = float(net_stop_pct)
        changed = True
    if not armed_before_bar:
        return None, changed

    adverse_gross_pct = position_margin_pnl_pct(position, adverse_price)
    if adverse_gross_pct is None or adverse_gross_pct > stop_pct:
        return None, changed
    return _micro_lock_exit_from_stop(
        position,
        stop_pct=stop_pct,
        taker_fee_rate=taker_fee_rate,
        min_exit_net_pct=min_exit_net_pct,
        exit_slippage_buffer_pct=exit_slippage_buffer_pct,
    ), changed


def position_margin_pnl_usdt(position: FuturesPosition, price: float) -> float:
    if price <= 0:
        return 0.0
    direction = 1.0 if position.side == "LONG" else -1.0
    return position.base_qty * (price - position.entry_price) * direction


def position_margin_pnl_pct(position: FuturesPosition, price: float) -> float | None:
    if position.margin_usdt <= 0:
        return None
    return position_margin_pnl_usdt(position, price) / position.margin_usdt * 100.0


def estimated_round_trip_fees_usdt(position: FuturesPosition, price: float, taker_fee_rate: float) -> float:
    if price <= 0 or taker_fee_rate <= 0:
        return 0.0
    return (position.base_qty * position.entry_price + position.base_qty * price) * taker_fee_rate


def position_net_pnl_pct(position: FuturesPosition, price: float, taker_fee_rate: float) -> float | None:
    if position.margin_usdt <= 0:
        return None
    net_pnl = position_margin_pnl_usdt(position, price) - estimated_round_trip_fees_usdt(position, price, taker_fee_rate)
    return net_pnl / position.margin_usdt * 100.0


def _update_adverse_peak_trail_peak(position: FuturesPosition, price: float) -> tuple[bool, float]:
    metadata = position.metadata if isinstance(position.metadata, dict) else {}
    if metadata is not position.metadata:
        position.metadata = metadata
    gross_pnl_pct = position_margin_pnl_pct(position, price)
    if gross_pnl_pct is None:
        return False, 0.0
    changed = False
    peak_pct = _metadata_float(metadata, ADVERSE_PEAK_TRAIL_PEAK_GROSS_PCT_KEY) or 0.0
    if gross_pnl_pct > peak_pct:
        peak_pct = gross_pnl_pct
        metadata[ADVERSE_PEAK_TRAIL_PEAK_GROSS_PCT_KEY] = float(gross_pnl_pct)
        metadata[ADVERSE_PEAK_TRAIL_PEAK_PRICE_KEY] = float(price)
        changed = True
    return changed, peak_pct


def _adverse_peak_trail_stop_pct(
    peak_pct: float,
    *,
    giveback_pct: float,
    pullback_fraction: float,
    max_loss_pct: float,
) -> float:
    fixed_stop = peak_pct - max(0.0, giveback_pct)
    bounded_pullback = min(0.95, max(0.0, pullback_fraction))
    proportional_stop = peak_pct * (1.0 - bounded_pullback)
    stop_pct = min(fixed_stop, proportional_stop)
    if max_loss_pct > 0:
        stop_pct = max(stop_pct, -max_loss_pct)
    return stop_pct


def evaluate_adverse_peak_trail_tick(
    position: FuturesPosition,
    price: float,
    *,
    trigger_pct: float,
    giveback_pct: float,
    pullback_fraction: float = 0.45,
    max_loss_pct: float = 2.0,
) -> tuple[tuple[float, str] | None, bool]:
    if trigger_pct <= 0 or price <= 0:
        return None, False
    metadata = position.metadata if isinstance(position.metadata, dict) else {}
    if metadata is not position.metadata:
        position.metadata = metadata
    trigger_pct = _metadata_float(metadata, "adverse_peak_trail_trigger_pct_override") or trigger_pct
    giveback_pct = _metadata_float(metadata, "adverse_peak_trail_giveback_pct_override") or giveback_pct
    pullback_fraction = _metadata_float(metadata, "adverse_peak_trail_pullback_fraction_override") or pullback_fraction
    max_loss_pct = _metadata_float(metadata, "adverse_peak_trail_max_loss_pct_override") or max_loss_pct

    changed, peak_pct = _update_adverse_peak_trail_peak(position, price)
    if peak_pct < max(0.0, trigger_pct):
        return None, changed
    stop_pct = _adverse_peak_trail_stop_pct(
        peak_pct,
        giveback_pct=giveback_pct,
        pullback_fraction=pullback_fraction,
        max_loss_pct=max_loss_pct,
    )
    if metadata.get(ADVERSE_PEAK_TRAIL_STOP_GROSS_PCT_KEY) != stop_pct:
        metadata[ADVERSE_PEAK_TRAIL_STOP_GROSS_PCT_KEY] = float(stop_pct)
        changed = True
    gross_pnl_pct = position_margin_pnl_pct(position, price)
    if gross_pnl_pct is None or gross_pnl_pct > stop_pct:
        return None, changed
    return (price, "ADVERSE_PEAK_TRAIL"), changed


def evaluate_adverse_peak_trail_bar(
    position: FuturesPosition,
    *,
    high: float,
    low: float,
    trigger_pct: float,
    giveback_pct: float,
    pullback_fraction: float = 0.45,
    max_loss_pct: float = 2.0,
) -> tuple[tuple[float, str] | None, bool]:
    if trigger_pct <= 0 or high <= 0 or low <= 0:
        return None, False
    metadata = position.metadata if isinstance(position.metadata, dict) else {}
    if metadata is not position.metadata:
        position.metadata = metadata
    trigger_pct = _metadata_float(metadata, "adverse_peak_trail_trigger_pct_override") or trigger_pct
    giveback_pct = _metadata_float(metadata, "adverse_peak_trail_giveback_pct_override") or giveback_pct
    pullback_fraction = _metadata_float(metadata, "adverse_peak_trail_pullback_fraction_override") or pullback_fraction
    max_loss_pct = _metadata_float(metadata, "adverse_peak_trail_max_loss_pct_override") or max_loss_pct

    armed_before_bar = (_metadata_float(metadata, ADVERSE_PEAK_TRAIL_STOP_GROSS_PCT_KEY) or 0.0) != 0.0
    favorable_price = high if position.side == "LONG" else low
    adverse_price = low if position.side == "LONG" else high
    changed, peak_pct = _update_adverse_peak_trail_peak(position, favorable_price)
    if peak_pct < max(0.0, trigger_pct):
        return None, changed
    stop_pct = _adverse_peak_trail_stop_pct(
        peak_pct,
        giveback_pct=giveback_pct,
        pullback_fraction=pullback_fraction,
        max_loss_pct=max_loss_pct,
    )
    if metadata.get(ADVERSE_PEAK_TRAIL_STOP_GROSS_PCT_KEY) != stop_pct:
        metadata[ADVERSE_PEAK_TRAIL_STOP_GROSS_PCT_KEY] = float(stop_pct)
        changed = True
    if not armed_before_bar:
        return None, changed
    adverse_gross_pct = position_margin_pnl_pct(position, adverse_price)
    if adverse_gross_pct is None or adverse_gross_pct > stop_pct:
        return None, changed
    exit_price = price_for_margin_pnl_pct(position, stop_pct)
    if exit_price is None or exit_price <= 0:
        exit_price = adverse_price
    return (exit_price, "ADVERSE_PEAK_TRAIL"), changed


def _update_no_progress_peak(position: FuturesPosition, price: float) -> tuple[bool, float]:
    metadata = position.metadata if isinstance(position.metadata, dict) else {}
    if metadata is not position.metadata:
        position.metadata = metadata
    gross_pnl_pct = position_margin_pnl_pct(position, price)
    if gross_pnl_pct is None:
        return False, 0.0
    changed = False
    peak_pct = _metadata_float(metadata, NO_PROGRESS_EXIT_PEAK_GROSS_PCT_KEY) or 0.0
    if gross_pnl_pct > peak_pct:
        peak_pct = gross_pnl_pct
        metadata[NO_PROGRESS_EXIT_PEAK_GROSS_PCT_KEY] = float(gross_pnl_pct)
        metadata[NO_PROGRESS_EXIT_PEAK_PRICE_KEY] = float(price)
        changed = True
    return changed, peak_pct


def _no_progress_loss_limit_pct(
    elapsed_minutes: float,
    *,
    activation_minutes: float,
    loss_pct: float,
    tighten_after_minutes: float,
    tightened_loss_pct: float,
) -> float:
    initial_loss_pct = max(0.0, loss_pct)
    if initial_loss_pct <= 0:
        return 0.0
    final_loss_pct = max(0.0, tightened_loss_pct)
    if final_loss_pct <= 0:
        final_loss_pct = initial_loss_pct
    final_loss_pct = min(initial_loss_pct, final_loss_pct)
    if tighten_after_minutes <= activation_minutes:
        return -final_loss_pct
    if elapsed_minutes <= activation_minutes:
        return -initial_loss_pct
    if elapsed_minutes >= tighten_after_minutes:
        return -final_loss_pct
    age_progress = (elapsed_minutes - activation_minutes) / (tighten_after_minutes - activation_minutes)
    loss_pct_now = initial_loss_pct + (final_loss_pct - initial_loss_pct) * max(0.0, min(1.0, age_progress))
    return -loss_pct_now


def evaluate_no_progress_loss_exit(
    position: FuturesPosition,
    price: float,
    *,
    now: datetime,
    activation_minutes: float,
    max_favorable_pct: float,
    loss_pct: float,
    tighten_after_minutes: float,
    tightened_loss_pct: float,
) -> tuple[tuple[float, str] | None, bool]:
    if activation_minutes <= 0 or price <= 0:
        return None, False
    metadata = position.metadata if isinstance(position.metadata, dict) else {}
    if metadata is not position.metadata:
        position.metadata = metadata
    activation_minutes = _metadata_float(metadata, "no_progress_exit_minutes_override") or activation_minutes
    max_favorable_pct = _metadata_float(metadata, "no_progress_exit_max_favorable_pct_override") or max_favorable_pct
    loss_pct = _metadata_float(metadata, "no_progress_exit_loss_pct_override") or loss_pct
    tighten_after_minutes = _metadata_float(metadata, "no_progress_exit_tighten_after_minutes_override") or tighten_after_minutes
    tightened_loss_pct = _metadata_float(metadata, "no_progress_exit_tightened_loss_pct_override") or tightened_loss_pct

    changed, peak_pct = _update_no_progress_peak(position, price)
    if peak_pct >= max(0.0, max_favorable_pct):
        return None, changed

    opened_at = _opened_at_utc(position)
    if opened_at is None:
        return None, changed
    current = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    elapsed_minutes = (current - opened_at).total_seconds() / 60.0
    if elapsed_minutes < activation_minutes:
        return None, changed

    gross_pnl_pct = position_margin_pnl_pct(position, price)
    if gross_pnl_pct is None:
        return None, changed
    loss_limit_pct = _no_progress_loss_limit_pct(
        elapsed_minutes,
        activation_minutes=activation_minutes,
        loss_pct=loss_pct,
        tighten_after_minutes=tighten_after_minutes,
        tightened_loss_pct=tightened_loss_pct,
    )
    if metadata.get(NO_PROGRESS_EXIT_LOSS_LIMIT_GROSS_PCT_KEY) != loss_limit_pct:
        metadata[NO_PROGRESS_EXIT_LOSS_LIMIT_GROSS_PCT_KEY] = float(loss_limit_pct)
        changed = True
    if gross_pnl_pct > loss_limit_pct:
        return None, changed
    return (price, "NO_PROGRESS_LOSS_EXIT"), changed


def _opened_at_utc(position: FuturesPosition) -> datetime | None:
    opened_at = getattr(position, "opened_at", None)
    if isinstance(opened_at, datetime):
        return opened_at.astimezone(timezone.utc) if opened_at.tzinfo else opened_at.replace(tzinfo=timezone.utc)
    if not opened_at:
        return None
    try:
        parsed = datetime.fromisoformat(str(opened_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def evaluate_stagnation_exit(
    position: FuturesPosition,
    price: float,
    *,
    now: datetime,
    activation_minutes: float,
    max_peak_progress: float,
    min_peak_progress: float,
    retrace_fraction: float,
    min_net_pnl_pct: float,
    taker_fee_rate: float,
    require_chase_watch: bool = True,
) -> tuple[bool, bool, str]:
    if activation_minutes <= 0 or price <= 0:
        return False, False, "disabled"
    metadata = position.metadata if isinstance(position.metadata, dict) else {}
    if metadata is not position.metadata:
        position.metadata = metadata
    allowed_signals = _normalized_entry_signals(metadata.get("stagnation_exit_entry_signals"))
    if allowed_signals and str(position.entry_signal).upper() not in allowed_signals:
        return False, False, "unsupported_entry_signal"
    if require_chase_watch and not bool(metadata.get("late_impulse_chase_watch")):
        return False, False, "no_chase_watch"

    progress = tp_progress(position, price)
    if progress is None:
        return False, False, "no_tp_progress"
    changed = False
    stored_peak = _metadata_float(metadata, STAGNATION_EXIT_PEAK_PROGRESS_KEY) or 0.0
    peak_progress = max(stored_peak, progress)
    if peak_progress > stored_peak:
        metadata[STAGNATION_EXIT_PEAK_PROGRESS_KEY] = float(peak_progress)
        metadata[STAGNATION_EXIT_PEAK_PRICE_KEY] = float(price)
        changed = True

    opened_at = _opened_at_utc(position)
    if opened_at is None:
        return False, changed, "missing_opened_at"
    current = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    elapsed_minutes = (current - opened_at).total_seconds() / 60.0
    if elapsed_minutes < activation_minutes:
        return False, changed, "too_young"
    if peak_progress < max(0.0, min_peak_progress):
        return False, changed, "peak_too_small"
    if peak_progress > max(0.0, max_peak_progress):
        return False, changed, "peak_not_stagnant"

    bounded_retrace = min(1.0, max(0.0, retrace_fraction))
    if progress > max(0.0, peak_progress * (1.0 - bounded_retrace)):
        return False, changed, "not_retraced"
    net_pnl_pct = position_net_pnl_pct(position, price, taker_fee_rate)
    if net_pnl_pct is None:
        return False, changed, "no_net_pnl"
    if net_pnl_pct < min_net_pnl_pct:
        return False, changed, "loss_too_deep"
    return True, changed, "stagnation_retrace"


def price_for_margin_pnl_pct(position: FuturesPosition, pnl_pct: float) -> float | None:
    if position.base_qty <= 0 or position.margin_usdt <= 0:
        return None
    pnl_usdt = position.margin_usdt * pnl_pct / 100.0
    direction = 1.0 if position.side == "LONG" else -1.0
    return position.entry_price + direction * pnl_usdt / position.base_qty


def _update_profit_lock_peak(
    position: FuturesPosition,
    price: float,
    *,
    taker_fee_rate: float,
) -> tuple[bool, float, float]:
    metadata = position.metadata if isinstance(position.metadata, dict) else {}
    if metadata is not position.metadata:
        position.metadata = metadata
    gross_pnl_pct = position_margin_pnl_pct(position, price)
    net_pnl_pct = position_net_pnl_pct(position, price, taker_fee_rate)
    if gross_pnl_pct is None or net_pnl_pct is None:
        return False, 0.0, 0.0

    changed = False
    net_peak_pct = _metadata_float(metadata, PROFIT_LOCK_PEAK_PCT_KEY) or 0.0
    if net_pnl_pct > net_peak_pct:
        net_peak_pct = net_pnl_pct
        metadata[PROFIT_LOCK_PEAK_PCT_KEY] = float(net_pnl_pct)
        metadata[PROFIT_LOCK_PEAK_USDT_KEY] = float(position.margin_usdt * net_pnl_pct / 100.0)
        metadata[PROFIT_LOCK_PEAK_PRICE_KEY] = float(price)
        changed = True

    stored_gross_peak_pct = _metadata_float(metadata, PROFIT_LOCK_PEAK_GROSS_PCT_KEY)
    gross_peak_pct = stored_gross_peak_pct
    if gross_peak_pct is None:
        gross_peak_pct = max(0.0, net_peak_pct)
    if gross_pnl_pct > gross_peak_pct:
        gross_peak_pct = gross_pnl_pct
        metadata[PROFIT_LOCK_PEAK_GROSS_PCT_KEY] = float(gross_pnl_pct)
        changed = True
    elif stored_gross_peak_pct is None and gross_peak_pct > 0.0:
        metadata[PROFIT_LOCK_PEAK_GROSS_PCT_KEY] = float(gross_peak_pct)
        changed = True

    return changed, gross_peak_pct, net_peak_pct


def evaluate_profit_lock_bar(
    position: FuturesPosition,
    *,
    high: float,
    low: float,
    taker_fee_rate: float,
    trigger_pct: float,
    pullback_fraction: float,
    floor_pct: float,
    min_exit_net_pct: float = 0.0,
    exit_slippage_buffer_pct: float = 0.0,
    giveback_pct: float = 0.0,
    min_tp_progress: float = 0.0,
) -> tuple[tuple[float, str] | None, bool]:
    if trigger_pct <= 0 or high <= 0 or low <= 0:
        return None, False
    metadata = position.metadata if isinstance(position.metadata, dict) else {}
    if metadata is not position.metadata:
        position.metadata = metadata
    trigger_pct = _metadata_override_or(metadata, "profit_lock_trigger_pct_override", trigger_pct)
    pullback_fraction = _metadata_override_or(metadata, "profit_lock_pullback_fraction_override", pullback_fraction)
    floor_pct = _metadata_override_or(metadata, "profit_lock_floor_pct_override", floor_pct)
    min_exit_net_pct = _metadata_override_or(metadata, "profit_lock_exit_min_net_pct_override", min_exit_net_pct)
    giveback_pct = _metadata_override_or(metadata, "profit_lock_giveback_pct_override", giveback_pct)
    min_tp_progress = _metadata_override_or(metadata, "profit_lock_min_tp_progress_override", min_tp_progress)
    armed_before_bar = (_metadata_float(metadata, PROFIT_LOCK_STOP_GROSS_PCT_KEY) or 0.0) > 0.0
    favorable_price = high if position.side == "LONG" else low
    adverse_price = low if position.side == "LONG" else high

    changed, gross_peak_pct, net_peak_pct = _update_profit_lock_peak(
        position,
        favorable_price,
        taker_fee_rate=taker_fee_rate,
    )
    if gross_peak_pct < trigger_pct:
        return None, changed
    progress = tp_progress(position, favorable_price)
    if min_tp_progress > 0 and (progress is None or progress < min_tp_progress):
        return None, changed

    if giveback_pct > 0:
        stop_pct = max(0.0, floor_pct, gross_peak_pct - giveback_pct)
        net_stop_pct = max(0.0, net_peak_pct - giveback_pct)
    else:
        bounded_pullback = min(0.95, max(0.0, pullback_fraction))
        stop_pct = max(0.0, floor_pct, gross_peak_pct * (1.0 - bounded_pullback))
        net_stop_pct = max(0.0, net_peak_pct * (1.0 - bounded_pullback))
    if metadata.get(PROFIT_LOCK_STOP_GROSS_PCT_KEY) != stop_pct:
        metadata[PROFIT_LOCK_STOP_GROSS_PCT_KEY] = float(stop_pct)
        changed = True
    if metadata.get(PROFIT_LOCK_STOP_PCT_KEY) != net_stop_pct:
        metadata[PROFIT_LOCK_STOP_PCT_KEY] = float(net_stop_pct)
        changed = True

    if not armed_before_bar:
        return None, changed

    adverse_gross_pct = position_margin_pnl_pct(position, adverse_price)
    if adverse_gross_pct is None or adverse_gross_pct > stop_pct:
        return None, changed

    exit_price = price_for_margin_pnl_pct(position, stop_pct)
    if exit_price is None or exit_price <= 0:
        return None, changed
    net_exit_pct = position_net_pnl_pct(position, exit_price, taker_fee_rate)
    required_net_pct = max(0.0, min_exit_net_pct) + max(0.0, exit_slippage_buffer_pct)
    if net_exit_pct is not None and net_exit_pct < required_net_pct:
        return None, changed
    reason = "PEAK_PROFIT_LOCK" if net_exit_pct is None or net_exit_pct > 0.0 else "PEAK_PROTECTION_GAP_EXIT"
    return (exit_price, reason), changed