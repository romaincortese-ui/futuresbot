from __future__ import annotations

from futuresbot.models import FuturesPosition


TRAILING_EXIT_ARMED_KEY = "trailing_exit_armed"
TRAILING_EXIT_BEST_PRICE_KEY = "trailing_exit_best_price"
TRAILING_EXIT_STOP_PRICE_KEY = "trailing_exit_stop_price"


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