from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

import pandas as pd

from futuresbot.pmt_strategy import ELIGIBLE_PMT_SYMBOLS, mental_threshold_step


log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_REDIS_KEY = "mexc:pmt_simple_core_weight"
DEFAULT_TTL_SECONDS = 9 * 60 * 60
DEFAULT_STALE_SECONDS = 9 * 60 * 60
DEFAULT_REFRESH_SECONDS = 300
DEFAULT_GRID: tuple[float, ...] = (0.95, 0.90, 0.85, 0.80, 0.75)
PORTFOLIO_SYMBOL_WEIGHTS: dict[str, float] = {
    "BTC_USDT": 0.32,
    "ETH_USDT": 0.24,
    "SOL_USDT": 0.16,
    "BNB_USDT": 0.12,
    "SEI_USDT": 0.08,
    "ZEC_USDT": 0.08,
}


@dataclass(frozen=True, slots=True)
class SymbolMarketInput:
    symbol: str
    frame: pd.DataFrame
    ticker: Mapping[str, Any]
    funding_rate: float = 0.0


@dataclass(frozen=True, slots=True)
class CoreWeightRefreshResult:
    applied: bool
    weight: float | None = None
    reason: str = ""
    payload: dict[str, Any] | None = None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return default
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, "") or default))
    except (TypeError, ValueError):
        return default


def _parse_grid(raw: str | None = None) -> tuple[float, ...]:
    raw = raw if raw is not None else os.environ.get("FUTURES_PMT_SIMPLE_CORE_WEIGHT_GRID", "")
    values = [_safe_float(part, -1.0) for part in str(raw or "").replace(",", " ").split()]
    grid = sorted({value for value in values if 0.0 < value <= 1.0}, reverse=True)
    return tuple(grid) if grid else DEFAULT_GRID


def _round_to_grid(value: float, grid: Iterable[float] | None = None) -> float:
    choices = tuple(grid or DEFAULT_GRID)
    return min(choices, key=lambda choice: abs(choice - value))


def _weighted_average(values: Iterable[tuple[float, float]]) -> float:
    total = 0.0
    total_weight = 0.0
    for value, weight in values:
        clean_weight = max(0.0, float(weight))
        total += float(value) * clean_weight
        total_weight += clean_weight
    return total / total_weight if total_weight > 0 else 0.0


def _weighted_median(values: Iterable[tuple[float, float]]) -> float:
    rows = sorted((float(value), max(0.0, float(weight))) for value, weight in values)
    total_weight = sum(weight for _value, weight in rows)
    if total_weight <= 0:
        return 0.90
    cumulative = 0.0
    for value, weight in rows:
        cumulative += weight
        if cumulative >= total_weight / 2.0:
            return value
    return rows[-1][0]


def _series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def _close(frame: pd.DataFrame) -> pd.Series:
    return _series(frame, "close")


def _move(frame: pd.DataFrame, bars: int) -> float:
    close = _close(frame)
    if len(close) <= bars:
        return 0.0
    start = float(close.iloc[-bars - 1])
    end = float(close.iloc[-1])
    return (end - start) / start if start > 0 else 0.0


def _direction(value: float, dead_zone: float = 0.001) -> int:
    if value > dead_zone:
        return 1
    if value < -dead_zone:
        return -1
    return 0


def _ema(series: pd.Series, span: int) -> float:
    return float(series.ewm(span=span, adjust=False).mean().iloc[-1]) if not series.empty else 0.0


def _efficiency_ratio(frame: pd.DataFrame, bars: int = 32) -> float:
    close = _close(frame)
    if len(close) <= bars:
        return 0.0
    window = close.tail(bars + 1)
    path = _safe_float(window.diff().abs().sum(), 0.0)
    return _clamp(abs(float(window.iloc[-1]) - float(window.iloc[0])) / path) if path > 0 else 0.0


def _atr_metrics(frame: pd.DataFrame, window: int = 14, lookback: int = 96) -> tuple[float, float]:
    close = _close(frame)
    high = _series(frame, "high")
    low = _series(frame, "low")
    if len(close) < max(window + 2, lookback // 2) or len(high) != len(close) or len(low) != len(close):
        return 0.0, 1.0
    previous_close = close.shift(1)
    true_range = pd.concat([high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
    atr_pct_series = true_range.rolling(window).mean() / close.replace(0, math.nan)
    atr_pct = _safe_float(atr_pct_series.iloc[-1], 0.0)
    baseline = _safe_float(atr_pct_series.tail(lookback).median(), 0.0)
    return atr_pct, atr_pct / baseline if baseline > 0 else 1.0


def _trend_metrics(frame: pd.DataFrame) -> tuple[float, int, dict[str, float]]:
    close = _close(frame)
    move_1h = _move(frame, 4)
    move_4h = _move(frame, 16)
    move_24h = _move(frame, 96)
    direction = _direction(move_4h, 0.002) or _direction(move_24h, 0.004) or _direction(move_1h, 0.001)
    ema20, ema50, ema100 = _ema(close, 20), _ema(close, 50), _ema(close, 100)
    aligned_moves = sum(
        1.0
        for move, threshold in ((move_1h, 0.001), (move_4h, 0.003), (move_24h, 0.006))
        if direction and _direction(move, threshold) == direction
    )
    ema_stack = 0.0
    if direction > 0 and ema20 > ema50 > ema100:
        ema_stack = 1.0
    elif direction < 0 and ema20 < ema50 < ema100:
        ema_stack = 1.0
    elif direction and ((direction > 0 and ema20 > ema50) or (direction < 0 and ema20 < ema50)):
        ema_stack = 0.6
    efficiency = _efficiency_ratio(frame)
    move_strength = _clamp((abs(move_4h) / 0.018) * 0.45 + (abs(move_24h) / 0.045) * 0.55)
    score = _clamp(0.30 * (aligned_moves / 3.0) + 0.25 * ema_stack + 0.25 * efficiency + 0.20 * move_strength)
    return score, direction, {
        "move_1h": move_1h,
        "move_4h": move_4h,
        "move_24h": move_24h,
        "ema20": ema20,
        "ema50": ema50,
        "ema100": ema100,
        "efficiency_ratio": efficiency,
    }


def _threshold_cleanliness(symbol: str, frame: pd.DataFrame) -> float:
    close = _close(frame)
    if len(close) < 8:
        return 0.5
    step = mental_threshold_step(symbol)
    current = float(close.iloc[-1])
    if step <= 0 or current <= 0:
        return 0.5
    lower = math.floor(current / step) * step
    nearest = min(abs(current - lower), abs(lower + step - current))
    near_score = 1.0 - _clamp(nearest / max(step * 0.35, 1e-12))
    cross_score = 0.0
    recent = close.tail(8)
    for previous, latest in zip(recent.iloc[:-1], recent.iloc[1:]):
        previous_bucket = math.floor(float(previous) / step)
        latest_bucket = math.floor(float(latest) / step)
        if previous_bucket != latest_bucket:
            crossed_level = max(previous_bucket, latest_bucket) * step
            cross_score = max(cross_score, 1.0 - _clamp(abs(current - crossed_level) / max(step * 0.45, 1e-12)))
    return _clamp(max(near_score * 0.65, cross_score))


def _volume_participation(frame: pd.DataFrame) -> float:
    volume = _series(frame, "volume")
    if len(volume) < 32:
        return 0.5
    recent = _safe_float(volume.tail(4).mean(), 0.0)
    baseline = _safe_float(volume.iloc[:-4].tail(96).median(), 0.0)
    ratio = recent / baseline if baseline > 0 else 1.0
    return _clamp((ratio - 0.80) / 0.80)


def _ticker_float(ticker: Mapping[str, Any], *names: str) -> float:
    lowered = {str(key).lower(): value for key, value in ticker.items()}
    for name in names:
        parsed = _safe_float(ticker.get(name, lowered.get(name.lower())), 0.0)
        if parsed != 0.0:
            return parsed
    return 0.0


def _liquidity_quality(ticker: Mapping[str, Any], frame: pd.DataFrame) -> tuple[float, dict[str, float]]:
    close = _close(frame)
    last_price = _ticker_float(ticker, "lastPrice", "last_price", "fairPrice", "indexPrice")
    if last_price <= 0 and not close.empty:
        last_price = float(close.iloc[-1])
    bid = _ticker_float(ticker, "bid1", "bid", "bidPrice", "bestBid")
    ask = _ticker_float(ticker, "ask1", "ask", "askPrice", "bestAsk")
    spread_bps = 8.0
    if bid > 0 and ask > 0 and last_price > 0 and ask >= bid:
        spread_bps = ((ask - bid) / last_price) * 10000.0
    spread_score = 1.0 - _clamp((spread_bps - 2.0) / 18.0)
    quote_amount = _ticker_float(ticker, "amount24", "turnover24", "quoteVolume", "volumeUsd24")
    base_volume = _ticker_float(ticker, "volume24", "vol24", "volume")
    if quote_amount <= 0 and base_volume > 0 and last_price > 0:
        quote_amount = base_volume * last_price
    amount_score = _clamp((math.log10(max(quote_amount, 1.0)) - 6.0) / 2.0) if quote_amount > 0 else 0.55
    return _clamp(0.65 * spread_score + 0.35 * amount_score), {"spread_bps": spread_bps, "quote_amount_24h": quote_amount}


def _open_interest_confirmation(symbol: str, ticker: Mapping[str, Any], direction: int, previous_payload: Mapping[str, Any] | None) -> tuple[float, float, float]:
    current = _ticker_float(ticker, "holdVol", "hold_volume", "openInterest", "open_interest")
    if current <= 0:
        return 0.50, 0.0, 0.0
    previous = 0.0
    observations = previous_payload.get("observations") if isinstance(previous_payload, Mapping) else None
    if isinstance(observations, Mapping) and isinstance(observations.get(symbol), Mapping):
        previous = _safe_float(observations[symbol].get("open_interest"), 0.0)
    if previous <= 0:
        return 0.50, 0.0, current
    change = (current - previous) / previous
    limit = 0.30 if direction else 0.20
    return _clamp(0.50 + _clamp(change / 0.08, -limit, limit)), change, current


def _risk_metrics(frame: pd.DataFrame, funding_rate: float, liquidity_quality: float, trend_alignment: float) -> tuple[float, dict[str, float]]:
    atr_pct, atr_ratio = _atr_metrics(frame)
    efficiency = _efficiency_ratio(frame)
    close = _close(frame)
    overextension = 0.0
    if len(close) >= 50 and atr_pct > 0:
        current = float(close.iloc[-1])
        overextension = abs(current - _ema(close, 50)) / max(current * atr_pct, 1e-12)
    chop_risk = _clamp(0.60 * (1.0 - efficiency) + 0.40 * (1.0 - trend_alignment))
    funding_crowding = _clamp(abs(float(funding_rate)) / 0.0008)
    volatility_extreme = _clamp((atr_ratio - 1.20) / 1.60)
    liquidity_risk = 1.0 - liquidity_quality
    overextension_risk = _clamp((overextension - 1.5) / 2.5)
    risk = _clamp(0.30 * chop_risk + 0.25 * funding_crowding + 0.20 * volatility_extreme + 0.15 * liquidity_risk + 0.10 * overextension_risk)
    return risk, {
        "chop_risk": chop_risk,
        "funding_crowding": funding_crowding,
        "volatility_extreme": volatility_extreme,
        "liquidity_risk": liquidity_risk,
        "overextension_risk": overextension_risk,
        "atr_pct": atr_pct,
        "atr_ratio": atr_ratio,
        "overextension_atr": overextension,
    }


def _portfolio_breadth(rows: Mapping[str, Mapping[str, Any]]) -> float:
    up_weight = down_weight = total_weight = 0.0
    trends: list[tuple[float, float]] = []
    for symbol, row in rows.items():
        weight = PORTFOLIO_SYMBOL_WEIGHTS.get(symbol, 0.05)
        direction = int(row.get("direction") or 0)
        if direction > 0:
            up_weight += weight
        elif direction < 0:
            down_weight += weight
        total_weight += weight
        trends.append((float(row.get("trend_alignment") or 0.0), weight))
    if total_weight <= 0:
        return 0.0
    dominant = max(up_weight, down_weight) / total_weight
    return _clamp(((dominant - 0.45) / 0.40) * (0.40 + 0.60 * _weighted_average(trends)))


def _symbol_core_weight(context_support: float, market_risk: float, grid: tuple[float, ...]) -> float:
    raw = 0.95 - (0.20 * context_support) + (0.10 * market_risk)
    return _round_to_grid(_clamp(raw, min(grid), max(grid)), grid)


def _exceptional_impulse_allowed(rows: Mapping[str, Mapping[str, Any]], portfolio: Mapping[str, float]) -> bool:
    core_rows = [rows.get(symbol) for symbol in ("BTC_USDT", "ETH_USDT", "SOL_USDT")]
    if any(row is None for row in core_rows):
        return False
    directions = {int(row.get("direction") or 0) for row in core_rows if row is not None}
    return (
        len(directions) == 1
        and 0 not in directions
        and float(portfolio.get("market_breadth") or 0.0) >= 0.80
        and float(portfolio.get("volume_participation") or 0.0) >= 0.70
        and float(portfolio.get("liquidity_quality") or 0.0) >= 0.70
        and float(portfolio.get("funding_crowding") or 0.0) <= 0.40
        and float(portfolio.get("chop_risk") or 0.0) <= 0.35
    )


def build_core_weight_payload(
    inputs: Iterable[SymbolMarketInput],
    *,
    previous_payload: Mapping[str, Any] | None = None,
    now_unix: float | None = None,
    grid: tuple[float, ...] | None = None,
) -> dict[str, Any]:
    ts = float(now_unix if now_unix is not None else time.time())
    grid = grid or _parse_grid()
    base_rows: dict[str, dict[str, Any]] = {}
    for item in inputs:
        symbol = str(item.symbol or "").upper()
        if symbol not in ELIGIBLE_PMT_SYMBOLS:
            continue
        frame = item.frame.sort_index() if isinstance(item.frame, pd.DataFrame) else pd.DataFrame()
        if frame.empty:
            continue
        trend_alignment, direction, trend_features = _trend_metrics(frame)
        liquidity, liquidity_features = _liquidity_quality(item.ticker, frame)
        oi_score, oi_change, open_interest = _open_interest_confirmation(symbol, item.ticker, direction, previous_payload)
        risk, risk_features = _risk_metrics(frame, item.funding_rate, liquidity, trend_alignment)
        base_rows[symbol] = {
            "symbol": symbol,
            "direction": direction,
            "trend_alignment": trend_alignment,
            "threshold_cleanliness": _threshold_cleanliness(symbol, frame),
            "volume_participation": _volume_participation(frame),
            "liquidity_quality": liquidity,
            "open_interest_confirmation": oi_score,
            "open_interest_change": oi_change,
            "open_interest": open_interest,
            "funding_rate_8h": float(item.funding_rate),
            "market_risk": risk,
            **trend_features,
            **liquidity_features,
            **risk_features,
        }
    if not base_rows:
        raise ValueError("No usable PMT live market inputs were available.")

    breadth = _portfolio_breadth(base_rows)
    observations: dict[str, dict[str, Any]] = {}
    for symbol, row in base_rows.items():
        context = _clamp(
            0.25 * float(row["trend_alignment"])
            + 0.20 * float(row["threshold_cleanliness"])
            + 0.20 * float(row["volume_participation"])
            + 0.15 * breadth
            + 0.10 * float(row["open_interest_confirmation"])
            + 0.10 * float(row["liquidity_quality"])
        )
        risk = float(row["market_risk"])
        observations[symbol] = {
            key: round(value, 6) if isinstance(value, float) else value
            for key, value in {
                **row,
                "market_breadth": breadth,
                "context_support": context,
                "raw_core_weight": 0.95 - (0.20 * context) + (0.10 * risk),
                "recommended_core_weight": _symbol_core_weight(context, risk, grid),
            }.items()
        }

    def average(name: str) -> float:
        return _weighted_average((float(row[name]), PORTFOLIO_SYMBOL_WEIGHTS.get(symbol, 0.05)) for symbol, row in observations.items())

    portfolio = {
        "context_support": average("context_support"),
        "market_risk": average("market_risk"),
        "market_breadth": breadth,
        "volume_participation": average("volume_participation"),
        "liquidity_quality": average("liquidity_quality"),
        "funding_crowding": average("funding_crowding"),
        "chop_risk": average("chop_risk"),
    }
    calculated = _weighted_median((float(row["recommended_core_weight"]), PORTFOLIO_SYMBOL_WEIGHTS.get(symbol, 0.05)) for symbol, row in observations.items())
    if calculated <= 0.75 and not _exceptional_impulse_allowed(observations, portfolio):
        calculated = max(0.80, calculated)
    previous_weight = _safe_float((previous_payload or {}).get("recommended_core_weight"), 0.0)
    selected = calculated
    if previous_weight in grid:
        selected = _round_to_grid(0.70 * previous_weight + 0.30 * calculated, grid)
        if abs(selected - previous_weight) > 0.05 + 1e-9:
            selected = _round_to_grid(previous_weight + (0.05 if selected > previous_weight else -0.05), grid)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        "produced_at_unix": ts,
        "source": "futuresbot_pmt_live_market_core_weight",
        "venue": "mexc_perp_public",
        "symbols": sorted(observations),
        "grid": list(grid),
        "calculated_core_weight": calculated,
        "recommended_core_weight": selected,
        "previous_core_weight": previous_weight or None,
        "portfolio": {key: round(float(value), 6) for key, value in portfolio.items()},
        "observations": observations,
    }


def collect_live_market_inputs(client: Any, symbols: Iterable[str]) -> list[SymbolMarketInput]:
    end = int(time.time())
    start = end - 900 * 192
    all_tickers: dict[str, Mapping[str, Any]] = {}
    try:
        for row in client.get_all_tickers():
            symbol = str(row.get("symbol") or "").upper()
            if symbol:
                all_tickers[symbol] = row
    except Exception as exc:
        log.debug("PMT core-weight all-ticker fetch skipped: %s", exc)
    out: list[SymbolMarketInput] = []
    for raw_symbol in symbols:
        symbol = str(raw_symbol or "").upper()
        if symbol not in ELIGIBLE_PMT_SYMBOLS:
            continue
        frame = client.get_klines(symbol, interval="Min15", start=start, end=end)
        ticker = all_tickers.get(symbol) or client.get_ticker(symbol)
        try:
            funding_rate = float(client.get_funding_rate(symbol))
        except Exception as exc:
            log.debug("PMT core-weight funding fetch skipped for %s: %s", symbol, exc)
            funding_rate = 0.0
        out.append(SymbolMarketInput(symbol=symbol, frame=frame, ticker=ticker or {}, funding_rate=funding_rate))
    return out


def publish_payload_to_redis(redis_client: Any, payload: Mapping[str, Any], *, key: str = DEFAULT_REDIS_KEY, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
    if redis_client is None:
        return False
    try:
        redis_client.set(key, json.dumps(payload, separators=(",", ":"), sort_keys=True), ex=int(max(60, ttl_seconds)))
        return True
    except Exception as exc:
        log.warning("PMT core-weight Redis publish failed for %s: %s", key, exc)
        return False


def publish_payload_via_url(redis_url: str, payload: Mapping[str, Any], *, key: str = DEFAULT_REDIS_KEY, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
    if not redis_url:
        return False
    try:
        import redis  # type: ignore

        client = redis.Redis.from_url(redis_url, socket_timeout=2.0, socket_connect_timeout=2.0)
    except Exception as exc:
        log.warning("PMT core-weight Redis client unavailable: %s", exc)
        return False
    return publish_payload_to_redis(client, payload, key=key, ttl_seconds=ttl_seconds)


def load_payload_via_url(redis_url: str, *, key: str = DEFAULT_REDIS_KEY) -> dict[str, Any] | None:
    if not redis_url:
        return None
    try:
        import redis  # type: ignore

        client = redis.Redis.from_url(redis_url, socket_timeout=1.5, socket_connect_timeout=1.5)
        raw = client.get(key)
    except Exception as exc:
        log.debug("PMT core-weight Redis load skipped: %s", exc)
        return None
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def core_weight_from_payload(payload: Mapping[str, Any] | None, *, now_unix: float | None = None, stale_seconds: int = DEFAULT_STALE_SECONDS) -> CoreWeightRefreshResult:
    if not isinstance(payload, Mapping):
        return CoreWeightRefreshResult(False, reason="missing_payload")
    if int(payload.get("schema_version") or 0) != SCHEMA_VERSION:
        return CoreWeightRefreshResult(False, reason="schema_mismatch", payload=dict(payload))
    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        return CoreWeightRefreshResult(False, reason="missing_symbols", payload=dict(payload))
    if any(str(symbol).upper() not in ELIGIBLE_PMT_SYMBOLS for symbol in symbols):
        return CoreWeightRefreshResult(False, reason="unknown_symbols", payload=dict(payload))
    produced_at = _safe_float(payload.get("produced_at_unix"), 0.0)
    now = float(now_unix if now_unix is not None else time.time())
    if produced_at <= 0 or now - produced_at > max(1, stale_seconds):
        return CoreWeightRefreshResult(False, reason="stale_payload", payload=dict(payload))
    weight = _safe_float(payload.get("recommended_core_weight"), 0.0)
    if weight <= 0.0:
        return CoreWeightRefreshResult(False, reason="invalid_weight", payload=dict(payload))
    return CoreWeightRefreshResult(True, weight=_round_to_grid(weight, _parse_grid()), reason="fresh_payload", payload=dict(payload))


def refresh_env_from_redis(redis_url: str) -> CoreWeightRefreshResult:
    if not _env_bool("FUTURES_PMT_DYNAMIC_CORE_WEIGHT_ENABLED", False):
        return CoreWeightRefreshResult(False, reason="disabled")
    key = os.environ.get("FUTURES_PMT_SIMPLE_CORE_WEIGHT_REDIS_KEY", DEFAULT_REDIS_KEY).strip() or DEFAULT_REDIS_KEY
    payload = load_payload_via_url(redis_url, key=key)
    result = core_weight_from_payload(payload, stale_seconds=_env_int("FUTURES_PMT_SIMPLE_CORE_WEIGHT_STALE_SECONDS", DEFAULT_STALE_SECONDS))
    if result.applied and result.weight is not None:
        os.environ["FUTURES_PMT_SIMPLE_CORE_WEIGHT"] = f"{result.weight:.2f}"
        os.environ["FUTURES_PMT_SIMPLE_CORE_WEIGHT_SOURCE"] = "redis_live_market"
    return result
