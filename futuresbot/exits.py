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
) -> tuple[tuple[float, str] | None, bool]:
    if trigger_pct <= 0 or high <= 0 or low <= 0:
        return None, False
    metadata = position.metadata if isinstance(position.metadata, dict) else {}
    if metadata is not position.metadata:
        position.metadata = metadata
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
    reason = "PEAK_PROFIT_LOCK" if net_exit_pct is None or net_exit_pct > 0.0 else "PEAK_PROTECTION_GAP_EXIT"
    return (exit_price, reason), changed