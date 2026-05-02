from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


PRODUCTION_FLAG_DEFAULTS: dict[str, str] = {
    "USE_NAV_RISK_SIZING": "1",
    "USE_COST_BUDGET_RR": "1",
    "USE_STRICT_RECV_WINDOW": "1",
    "USE_LIQ_BUFFER_GUARD": "1",
    "USE_HARD_LOSS_CAP_TIGHT": "1",
    "USE_DRAWDOWN_KILL": "1",
    "USE_SESSION_LEVERAGE": "1",
    "USE_FUNDING_AWARE_ENTRY": "1",
    "USE_FUNDING_STOP_MULT": "1",
    "USE_REALISTIC_BACKTEST": "1",
    "USE_REGIME_CLASSIFIER": "1",
    "USE_MEAN_REVERSION": "1",
    "USE_MAKER_LADDER": "1",
    "USE_PORTFOLIO_VAR": "1",
    "USE_WALK_FORWARD_GATE": "1",
    "USE_SLIPPAGE_ATTRIBUTION": "1",
    "USE_FUNDING_CARRY_MONITOR": "0",
    "USE_BASIS_TRADE_MONITOR": "0",
    "USE_LIQUIDATION_CASCADE_MONITOR": "0",
    "NAV_LEVERAGE_MIN": "20",
    "NAV_LEVERAGE_MAX": "50",
}

for key, value in PRODUCTION_FLAG_DEFAULTS.items():
    os.environ.setdefault(key, value)

from futuresbot.backtest import FuturesBacktestEngine, build_report, export_artifacts
from futuresbot.calibration import apply_signal_calibration
from futuresbot.config import DEFAULT_FUTURES_SYMBOLS, FuturesBacktestConfig, FuturesConfig, parse_utc_datetime, utc_now
from futuresbot.marketdata import FuturesHistoricalDataProvider, MexcFuturesClient
from futuresbot.models import FuturesSignal
from futuresbot.strategy import score_btc_futures_setup


@dataclass(slots=True)
class Candidate:
    signal: FuturesSignal
    score_10: float
    scan_time: pd.Timestamp
    mover_bucket: str = ""
    move_pct: float = 0.0
    rank: int = 0
    consecutive_top3_runs: int = 0
    playbook: str = ""


@dataclass(slots=True)
class OpenTrade:
    symbol: str
    side: str
    close_time: pd.Timestamp
    margin_usdt: float
    trade: dict[str, Any]


@dataclass(slots=True)
class WatchState:
    symbol: str
    bucket: str
    first_seen: pd.Timestamp
    last_seen: pd.Timestamp
    seen_count: int = 0
    max_positive_move: float = 0.0
    max_negative_move: float = 0.0


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return parse_utc_datetime(value)


def _default_window() -> tuple[datetime, datetime]:
    end = utc_now().replace(minute=0, second=0, microsecond=0)
    return end - timedelta(days=3), end


def _active_usdt_symbols(client: MexcFuturesClient, exclude: set[str], *, max_symbols: int | None = None) -> tuple[str, ...]:
    payload = client.public_get("/api/v1/contract/detail")
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    symbols: list[str] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("symbol") or "").upper()
        if not symbol.endswith("_USDT") or symbol in exclude:
            continue
        state = row.get("state")
        if state is not None:
            try:
                if int(float(state)) != 0:
                    continue
            except (TypeError, ValueError):
                continue
        symbols.append(symbol)
    ordered = tuple(dict.fromkeys(symbols))
    return ordered[:max_symbols] if max_symbols else ordered


def _config_for_symbol(
    base: FuturesBacktestConfig,
    live: FuturesConfig,
    symbol: str,
    margin_budget_mult: float,
    leverage_min: int,
) -> FuturesBacktestConfig:
    scoped = live.for_symbol(symbol)
    min_leverage = max(1, int(leverage_min), int(scoped.leverage_min))
    max_leverage = max(min_leverage, int(scoped.leverage_max))
    return dataclasses.replace(
        copy.copy(base),
        symbol=symbol,
        margin_budget_usdt=max(0.0, float(base.margin_budget_usdt) * margin_budget_mult),
        min_confidence_score=scoped.min_confidence_score,
        leverage_min=min_leverage,
        leverage_max=max_leverage,
        hard_loss_cap_pct=scoped.hard_loss_cap_pct,
        adx_floor=scoped.adx_floor,
        trend_24h_floor=scoped.trend_24h_floor,
        trend_6h_floor=scoped.trend_6h_floor,
        breakout_buffer_atr=scoped.breakout_buffer_atr,
        consolidation_window_bars=scoped.consolidation_window_bars,
        consolidation_max_range_pct=scoped.consolidation_max_range_pct,
        consolidation_atr_mult=scoped.consolidation_atr_mult,
        volume_ratio_floor=scoped.volume_ratio_floor,
        tp_atr_mult=scoped.tp_atr_mult,
        tp_range_mult=scoped.tp_range_mult,
        tp_floor_pct=scoped.tp_floor_pct,
        sl_buffer_atr_mult=scoped.sl_buffer_atr_mult,
        sl_trend_atr_mult=scoped.sl_trend_atr_mult,
        min_reward_risk=scoped.min_reward_risk,
        early_exit_tp_progress=scoped.early_exit_tp_progress,
        early_exit_min_profit_pct=scoped.early_exit_min_profit_pct,
        early_exit_buffer_pct=scoped.early_exit_buffer_pct,
    )


def _load_calibration(path: str) -> dict[str, Any] | None:
    calibration_path = Path(path)
    if not calibration_path.exists():
        return None
    return json.loads(calibration_path.read_text(encoding="utf-8"))


def _safe_scan_times(start: datetime, end: datetime, minutes: int) -> list[pd.Timestamp]:
    first = pd.Timestamp(start).tz_convert("UTC") if pd.Timestamp(start).tzinfo else pd.Timestamp(start, tz="UTC")
    last = pd.Timestamp(end).tz_convert("UTC") if pd.Timestamp(end).tzinfo else pd.Timestamp(end, tz="UTC")
    return list(pd.date_range(first, last, freq=f"{minutes}min", inclusive="left"))


def _frame_pos_at_or_before(frame: pd.DataFrame, timestamp: pd.Timestamp) -> int | None:
    if frame.empty:
        return None
    pos = int(frame.index.searchsorted(timestamp, side="right")) - 1
    return pos if pos >= 0 else None


def _mover_candidates_at(
    frames: Mapping[str, pd.DataFrame],
    timestamp: pd.Timestamp,
    *,
    lookback_hours: float,
    side_count: int,
) -> dict[str, tuple[str, float]]:
    lookback = pd.Timedelta(hours=float(lookback_hours))
    rows: list[tuple[str, float]] = []
    for symbol, frame in frames.items():
        pos_now = _frame_pos_at_or_before(frame, timestamp)
        if pos_now is None:
            continue
        pos_then = _frame_pos_at_or_before(frame, timestamp - lookback)
        if pos_then is None:
            continue
        current = float(frame.iloc[pos_now]["close"])
        previous = float(frame.iloc[pos_then]["close"])
        if current <= 0 or previous <= 0:
            continue
        rows.append((symbol, (current / previous) - 1.0))

    positive = sorted((row for row in rows if row[1] > 0), key=lambda item: item[1], reverse=True)[:side_count]
    negative = sorted((row for row in rows if row[1] < 0), key=lambda item: item[1])[:side_count]
    selected: dict[str, tuple[str, float]] = {}
    for symbol, move_pct in positive:
        selected[symbol] = ("positive", move_pct)
    for symbol, move_pct in negative:
        selected[symbol] = ("negative", move_pct)
    return selected


def _ema(values: pd.Series, span: int) -> pd.Series:
    return values.ewm(span=span, adjust=False).mean()


def _atr(frame: pd.DataFrame, window: int = 14) -> pd.Series:
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    close = frame["close"].astype(float)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            (high - low).abs(),
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window).mean()


def _rolling_vwap(frame: pd.DataFrame, window: int = 96) -> pd.Series:
    typical = (frame["high"].astype(float) + frame["low"].astype(float) + frame["close"].astype(float)) / 3.0
    volume = frame.get("volume", pd.Series(1.0, index=frame.index)).astype(float).clip(lower=0.0)
    weighted = (typical * volume).rolling(window).sum()
    total_volume = volume.rolling(window).sum()
    fallback = typical.rolling(window).mean()
    return (weighted / total_volume.replace(0.0, pd.NA)).fillna(fallback)


def _risk_reward_signal(
    *,
    symbol: str,
    side: str,
    entry_ref: float,
    stop: float,
    reward_risk: float,
    leverage: int,
    score: float,
    certainty: float,
    entry_signal: str,
    metadata: dict[str, Any],
    min_stop_pct: float,
    max_stop_pct: float,
) -> FuturesSignal | None:
    if entry_ref <= 0 or stop <= 0:
        return None
    if side == "LONG":
        risk = entry_ref - stop
        if risk <= 0:
            return None
        target = entry_ref + risk * reward_risk
    else:
        risk = stop - entry_ref
        if risk <= 0:
            return None
        target = entry_ref - risk * reward_risk
        if target <= 0:
            return None
    stop_pct = risk / entry_ref
    if stop_pct < min_stop_pct or stop_pct > max_stop_pct:
        return None
    return FuturesSignal(
        symbol=symbol,
        side=side,
        score=round(float(score), 2),
        certainty=round(float(certainty), 4),
        entry_price=float(entry_ref),
        tp_price=float(target),
        sl_price=float(stop),
        leverage=int(leverage),
        entry_signal=entry_signal,
        metadata=metadata,
    )


def _build_v2_signal(
    *,
    symbol: str,
    frame: pd.DataFrame,
    timestamp: pd.Timestamp,
    mover_bucket: str,
    move_pct: float,
    watch: WatchState,
    leverage: int,
    reward_risk: float,
    min_stop_pct: float,
    max_stop_pct: float,
    continuation_min_move: float,
    continuation_max_move: float,
    exhaustion_min_move: float,
) -> Candidate | None:
    pos = _frame_pos_at_or_before(frame, timestamp)
    if pos is None or pos < 120 or watch.seen_count < 2:
        return None
    history = frame.iloc[: pos + 1].copy()
    close = history["close"].astype(float)
    high = history["high"].astype(float)
    low = history["low"].astype(float)
    open_ = history["open"].astype(float)
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    atr14 = _atr(history, 14)
    vwap = _rolling_vwap(history, 96)
    if any(pd.isna(value) for value in (ema20.iloc[-1], ema50.iloc[-1], atr14.iloc[-1], vwap.iloc[-1])):
        return None

    entry = float(close.iloc[-1])
    atr_value = float(atr14.iloc[-1])
    if entry <= 0 or atr_value <= 0:
        return None
    last_high = float(high.iloc[-12:].max())
    last_low = float(low.iloc[-12:].min())
    recent_high = float(high.iloc[-32:].max())
    recent_low = float(low.iloc[-32:].min())
    ema20_now = float(ema20.iloc[-1])
    ema50_now = float(ema50.iloc[-1])
    vwap_now = float(vwap.iloc[-1])
    previous_close = float(close.iloc[-2])
    current_open = float(open_.iloc[-1])
    current_high = float(high.iloc[-1])
    current_low = float(low.iloc[-1])
    volume = history.get("volume", pd.Series(1.0, index=history.index)).astype(float)
    volume_ratio = float(volume.iloc[-8:].mean() / max(volume.iloc[-96:].mean(), 1e-12))
    atr_pct = atr_value / entry
    extension_ema = (entry - ema20_now) / entry
    pullback_from_high = (recent_high - entry) / recent_high if recent_high > 0 else 0.0
    bounce_from_low = (entry - recent_low) / recent_low if recent_low > 0 else 0.0
    body = abs(entry - current_open)
    upper_wick = max(0.0, current_high - max(entry, current_open))
    lower_wick = max(0.0, min(entry, current_open) - current_low)

    base_metadata = {
        "opportunist_mode": "v2_structure",
        "mover_bucket": mover_bucket,
        "mover_move_pct": round(float(move_pct), 8),
        "watch_seen_count": watch.seen_count,
        "atr_pct": round(atr_pct, 6),
        "volume_ratio": round(volume_ratio, 4),
        "reward_risk": round(float(reward_risk), 4),
    }

    signal: FuturesSignal | None = None
    playbook = ""
    if mover_bucket == "positive":
        if continuation_min_move <= move_pct <= continuation_max_move:
            pulled_back = 0.012 <= pullback_from_high <= 0.12 and min(low.iloc[-8:]) <= max(ema20_now, vwap_now) + 0.45 * atr_value
            reclaimed = entry > ema20_now and entry > vwap_now and entry > previous_close and entry >= current_open
            trend_ok = ema20_now >= ema50_now * 0.995 and volume_ratio >= 0.75
            if pulled_back and reclaimed and trend_ok:
                stop = min(last_low, ema20_now - 0.35 * atr_value)
                score = 62.0 + min(18.0, move_pct * 45.0) + min(10.0, pullback_from_high * 90.0) + min(6.0, volume_ratio * 2.0)
                signal = _risk_reward_signal(
                    symbol=symbol,
                    side="LONG",
                    entry_ref=entry,
                    stop=stop,
                    reward_risk=reward_risk,
                    leverage=leverage,
                    score=score,
                    certainty=min(0.9, 0.52 + pullback_from_high * 1.4 + min(0.12, volume_ratio / 20.0)),
                    entry_signal="OPPORTUNIST_PULLBACK_RECLAIM_LONG",
                    metadata={**base_metadata, "pullback_from_high": round(pullback_from_high, 6)},
                    min_stop_pct=min_stop_pct,
                    max_stop_pct=max_stop_pct,
                )
                playbook = "pullback_reclaim"
        if signal is None and move_pct >= exhaustion_min_move:
            exhausted = pullback_from_high >= 0.025 and extension_ema < 0.0
            breakdown = entry < ema20_now and entry < previous_close and (upper_wick > body * 0.6 or entry < float(low.iloc[-4:-1].min()))
            if exhausted and breakdown and volume_ratio >= 0.65:
                stop = max(last_high, ema20_now + 0.35 * atr_value)
                score = 64.0 + min(16.0, move_pct * 30.0) + min(12.0, pullback_from_high * 120.0) + min(6.0, upper_wick / max(atr_value, 1e-12))
                signal = _risk_reward_signal(
                    symbol=symbol,
                    side="SHORT",
                    entry_ref=entry,
                    stop=stop,
                    reward_risk=reward_risk,
                    leverage=leverage,
                    score=score,
                    certainty=min(0.88, 0.50 + pullback_from_high * 1.7 + min(0.1, volume_ratio / 25.0)),
                    entry_signal="OPPORTUNIST_EXHAUSTION_BREAK_SHORT",
                    metadata={**base_metadata, "pullback_from_high": round(pullback_from_high, 6)},
                    min_stop_pct=min_stop_pct,
                    max_stop_pct=max_stop_pct,
                )
                playbook = "exhaustion_reversal"
    else:
        abs_move = abs(move_pct)
        if continuation_min_move <= abs_move <= continuation_max_move:
            bounced = 0.012 <= bounce_from_low <= 0.12 and max(high.iloc[-8:]) >= min(ema20_now, vwap_now) - 0.45 * atr_value
            rejected = entry < ema20_now and entry < vwap_now and entry < previous_close and entry <= current_open
            trend_ok = ema20_now <= ema50_now * 1.005 and volume_ratio >= 0.75
            if bounced and rejected and trend_ok:
                stop = max(last_high, ema20_now + 0.35 * atr_value)
                score = 62.0 + min(18.0, abs_move * 45.0) + min(10.0, bounce_from_low * 90.0) + min(6.0, volume_ratio * 2.0)
                signal = _risk_reward_signal(
                    symbol=symbol,
                    side="SHORT",
                    entry_ref=entry,
                    stop=stop,
                    reward_risk=reward_risk,
                    leverage=leverage,
                    score=score,
                    certainty=min(0.9, 0.52 + bounce_from_low * 1.4 + min(0.12, volume_ratio / 20.0)),
                    entry_signal="OPPORTUNIST_PULLBACK_REJECT_SHORT",
                    metadata={**base_metadata, "bounce_from_low": round(bounce_from_low, 6)},
                    min_stop_pct=min_stop_pct,
                    max_stop_pct=max_stop_pct,
                )
                playbook = "pullback_reject"
        if signal is None and abs_move >= exhaustion_min_move:
            exhausted = bounce_from_low >= 0.025 and extension_ema > 0.0
            reclaim = entry > ema20_now and entry > previous_close and (lower_wick > body * 0.6 or entry > float(high.iloc[-4:-1].max()))
            if exhausted and reclaim and volume_ratio >= 0.65:
                stop = min(last_low, ema20_now - 0.35 * atr_value)
                score = 64.0 + min(16.0, abs_move * 30.0) + min(12.0, bounce_from_low * 120.0) + min(6.0, lower_wick / max(atr_value, 1e-12))
                signal = _risk_reward_signal(
                    symbol=symbol,
                    side="LONG",
                    entry_ref=entry,
                    stop=stop,
                    reward_risk=reward_risk,
                    leverage=leverage,
                    score=score,
                    certainty=min(0.88, 0.50 + bounce_from_low * 1.7 + min(0.1, volume_ratio / 25.0)),
                    entry_signal="OPPORTUNIST_EXHAUSTION_RECLAIM_LONG",
                    metadata={**base_metadata, "bounce_from_low": round(bounce_from_low, 6)},
                    min_stop_pct=min_stop_pct,
                    max_stop_pct=max_stop_pct,
                )
                playbook = "exhaustion_reversal"
    if signal is None:
        return None
    return Candidate(
        signal=signal,
        score_10=round(min(10.0, max(0.0, float(signal.score) / 10.0)), 2),
        scan_time=timestamp,
        mover_bucket=mover_bucket,
        move_pct=float(move_pct),
        playbook=playbook,
    )


def _parse_csv_set(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _score_symbol_at(
    *,
    frame: pd.DataFrame,
    timestamp: pd.Timestamp,
    config: FuturesBacktestConfig,
    calibration: Mapping[str, Any] | None,
    leverage_min: int,
    leverage_max: int | None,
    min_score: float,
) -> FuturesSignal | None:
    pos = _frame_pos_at_or_before(frame, timestamp)
    if pos is None or pos < 220:
        return None
    raw = score_btc_futures_setup(frame.iloc[: pos + 1], config)
    if raw is None:
        return None
    calibrated = apply_signal_calibration(
        raw,
        calibration,
        base_threshold=config.min_confidence_score,
        leverage_min=config.leverage_min,
        leverage_max=config.leverage_max,
    )
    if calibrated is None:
        return None
    if float(calibrated.score) < float(min_score):
        return None
    if int(calibrated.leverage) < int(leverage_min):
        calibrated = dataclasses.replace(
            calibrated,
            leverage=max(1, int(leverage_min)),
            metadata={**(calibrated.metadata or {}), "opportunist_leverage_min": int(leverage_min)},
        )
    if leverage_max is not None and leverage_max > 0 and int(calibrated.leverage) > leverage_max:
        calibrated = dataclasses.replace(
            calibrated,
            leverage=max(1, int(leverage_max)),
            metadata={**(calibrated.metadata or {}), "opportunist_leverage_cap": int(leverage_max)},
        )
    return calibrated


def _next_entry_bar(frame: pd.DataFrame, timestamp: pd.Timestamp) -> tuple[pd.Timestamp, pd.Series] | None:
    pos = int(frame.index.searchsorted(timestamp, side="right"))
    if pos >= len(frame):
        return None
    return frame.index[pos], frame.iloc[pos]


def _simulate_trade(
    *,
    engine: FuturesBacktestEngine,
    frame: pd.DataFrame,
    signal: FuturesSignal,
    scan_time: pd.Timestamp,
    balance: float,
) -> tuple[dict[str, Any] | None, pd.Timestamp | None, float]:
    entry = _next_entry_bar(frame, scan_time)
    if entry is None:
        return None, None, balance
    entry_time, entry_bar = entry
    position = engine._open_position(signal, entry_time, float(entry_bar["open"]), balance)
    if position is None:
        return None, entry_time, balance

    step = pd.Timedelta(minutes=15)
    start_pos = int(frame.index.get_loc(entry_time))
    for index in range(start_pos, len(frame)):
        timestamp = frame.index[index]
        bar = frame.iloc[index]
        bar_exit = engine._bar_exit(position, bar)
        if bar_exit is not None:
            exit_price, reason = bar_exit
            liquidated = reason == "LIQUIDATED"
            trade = engine._close_position(
                position,
                timestamp + step,
                exit_price,
                reason,
                liquidated=liquidated,
                liq_price=exit_price if liquidated else None,
            )
            balance += float(trade["pnl_usdt"])
            return trade, timestamp + step, balance
        close_time = timestamp + step
        if close_time.minute == 0:
            hourly_exit = engine._hourly_exit(position, float(bar["close"]))
            if hourly_exit is not None:
                exit_price, reason = hourly_exit
                trade = engine._close_position(position, close_time, exit_price, reason)
                balance += float(trade["pnl_usdt"])
                return trade, close_time, balance

    final_time = frame.index[-1] + step
    trade = engine._close_position(position, final_time, float(frame.iloc[-1]["close"]), "END_OF_TEST")
    balance += float(trade["pnl_usdt"])
    return trade, final_time, balance


def _max_drawdown(curve: list[dict[str, Any]]) -> float:
    peak = -math.inf
    worst = 0.0
    for point in curve:
        equity = float(point.get("equity", 0.0) or 0.0)
        peak = max(peak, equity)
        if peak > 0:
            worst = min(worst, (equity - peak) / peak)
    return worst


def run_opportunist_backtest(args: argparse.Namespace) -> dict[str, Any]:
    start, end = _default_window()
    start = _parse_time(args.start) or start
    end = _parse_time(args.end) or end
    if start >= end:
        raise ValueError("start must be earlier than end")
    warmup_start = start - timedelta(days=float(args.warmup_days))

    allowed_v2_buckets = _parse_csv_set(args.v2_allowed_buckets)
    allowed_v2_playbooks = _parse_csv_set(args.v2_allowed_playbooks)

    os.environ["FUTURES_BACKTEST_START"] = warmup_start.isoformat()
    os.environ["FUTURES_BACKTEST_END"] = end.isoformat()
    os.environ.setdefault("FUTURES_BACKTEST_CACHE_DIR", str(Path("backtest_cache") / "opportunist"))
    os.environ.setdefault("FUTURES_BACKTEST_OUTPUT_DIR", str(Path(args.out)))
    os.environ["NAV_LEVERAGE_MIN"] = str(max(1, int(args.leverage_min)))
    if args.leverage_max is not None:
        os.environ["NAV_LEVERAGE_MAX"] = str(max(int(args.leverage_min), int(args.leverage_max)))

    live = FuturesConfig.from_env()
    base = FuturesBacktestConfig.from_env()
    base = dataclasses.replace(base, start=start, end=end)
    client = MexcFuturesClient(live)
    provider = FuturesHistoricalDataProvider(client, cache_dir=base.cache_dir)
    calibration = _load_calibration(base.calibration_file) if args.calibration else None
    max_open_positions = max(1, int(args.max_open_positions))
    opportunist_budget_pct = max(0.0, float(args.opportunist_budget_pct))
    if args.margin_budget_mult is None:
        margin_budget_mult = opportunist_budget_pct / max_open_positions
    else:
        margin_budget_mult = max(0.0, float(args.margin_budget_mult))
    opportunist_margin_cap = max(0.0, float(base.margin_budget_usdt) * opportunist_budget_pct)

    exclude = {s.upper() for s in DEFAULT_FUTURES_SYMBOLS}
    symbols = _active_usdt_symbols(client, exclude, max_symbols=args.max_symbols)
    if args.symbols:
        requested = tuple(s.strip().upper() for s in args.symbols.split(",") if s.strip())
        symbols = tuple(sym for sym in requested if sym not in exclude)

    print(json.dumps({
        "opportunist_setup": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "warmup_start": warmup_start.isoformat(),
            "scan_minutes": args.scan_minutes,
            "top_n": args.top_n,
            "required_streak": args.required_streak,
            "entry_mode": args.entry_mode,
            "mover_side_count": args.mover_side_count,
            "mover_lookback_hours": args.mover_lookback_hours,
            "match_mover_side": bool(args.match_mover_side),
            "v2_reward_risk": args.v2_reward_risk,
            "v2_min_stop_pct": args.v2_min_stop_pct,
            "v2_max_stop_pct": args.v2_max_stop_pct,
            "v2_watchlist_hours": args.v2_watchlist_hours,
            "v2_continuation_min_move": args.v2_continuation_min_move,
            "v2_continuation_max_move": args.v2_continuation_max_move,
            "v2_exhaustion_min_move": args.v2_exhaustion_min_move,
            "v2_allowed_buckets": sorted(allowed_v2_buckets),
            "v2_allowed_playbooks": sorted(allowed_v2_playbooks),
            "opportunist_budget_pct": opportunist_budget_pct,
            "opportunist_margin_cap_usdt": opportunist_margin_cap,
            "max_open_positions": max_open_positions,
            "per_trade_margin_budget_mult": margin_budget_mult,
            "leverage_min": args.leverage_min,
            "leverage_max": args.leverage_max,
            "candidate_symbols": len(symbols),
            "excluded_production_symbols": sorted(exclude),
        }
    }, indent=2), flush=True)

    frames: dict[str, pd.DataFrame] = {}
    configs: dict[str, FuturesBacktestConfig] = {}
    engines: dict[str, FuturesBacktestEngine] = {}
    fetch_start = int(warmup_start.timestamp())
    fetch_end = int(end.timestamp())
    for idx, symbol in enumerate(symbols, start=1):
        try:
            frame = provider.fetch_klines(symbol, interval="Min15", start=fetch_start, end=fetch_end).sort_index()
        except Exception as exc:
            print(json.dumps({"fetch_error": {"symbol": symbol, "error": str(exc)}}), flush=True)
            continue
        if len(frame) < 240:
            continue
        cfg = _config_for_symbol(base, live, symbol, margin_budget_mult, int(args.leverage_min))
        frames[symbol] = frame
        configs[symbol] = cfg
        engines[symbol] = FuturesBacktestEngine(cfg, provider, client, calibration=calibration)
        if idx % 50 == 0:
            print(json.dumps({"fetch_progress": {"seen": idx, "usable": len(frames)}}), flush=True)

    scan_times = _safe_scan_times(start, end, int(args.scan_minutes))
    streaks: dict[tuple[str, str], int] = {}
    previous_top_keys: set[tuple[str, str]] = set()
    trades: list[dict[str, Any]] = []
    pending_trades: list[OpenTrade] = []
    equity_curve: list[dict[str, Any]] = []
    watchlist: dict[str, WatchState] = {}
    balance = float(base.initial_balance)
    scans_with_candidates = 0
    scans_with_movers = 0
    top3_snapshots: list[dict[str, Any]] = []

    for scan_idx, scan_time in enumerate(scan_times, start=1):
        still_open: list[OpenTrade] = []
        for open_trade in pending_trades:
            if scan_time >= open_trade.close_time:
                balance += float(open_trade.trade.get("pnl_usdt", 0.0) or 0.0)
                trades.append(open_trade.trade)
            else:
                still_open.append(open_trade)
        pending_trades = still_open

        candidates: list[Candidate] = []
        mover_map = _mover_candidates_at(
            frames,
            scan_time,
            lookback_hours=float(args.mover_lookback_hours),
            side_count=max(1, int(args.mover_side_count)),
        )
        if mover_map:
            scans_with_movers += 1
        if args.entry_mode == "v2-structure":
            ttl = pd.Timedelta(hours=float(args.v2_watchlist_hours))
            for symbol, mover in mover_map.items():
                mover_bucket, move_pct = mover
                watch = watchlist.get(symbol)
                if watch is None or watch.bucket != mover_bucket:
                    watch = WatchState(symbol=symbol, bucket=mover_bucket, first_seen=scan_time, last_seen=scan_time)
                    watchlist[symbol] = watch
                watch.last_seen = scan_time
                watch.seen_count += 1
                if move_pct > 0:
                    watch.max_positive_move = max(watch.max_positive_move, float(move_pct))
                if move_pct < 0:
                    watch.max_negative_move = min(watch.max_negative_move, float(move_pct))
            for symbol, watch in list(watchlist.items()):
                if scan_time - watch.last_seen > ttl:
                    watchlist.pop(symbol, None)
        open_symbols = {trade.symbol for trade in pending_trades}
        for symbol, mover in mover_map.items():
            if symbol in open_symbols:
                continue
            mover_bucket, move_pct = mover
            if args.entry_mode == "v2-structure":
                if allowed_v2_buckets and mover_bucket.lower() not in allowed_v2_buckets:
                    continue
                watch = watchlist.get(symbol)
                if watch is None:
                    continue
                candidate = _build_v2_signal(
                    symbol=symbol,
                    frame=frames[symbol],
                    timestamp=scan_time,
                    mover_bucket=mover_bucket,
                    move_pct=float(move_pct),
                    watch=watch,
                    leverage=int(args.leverage_min),
                    reward_risk=float(args.v2_reward_risk),
                    min_stop_pct=float(args.v2_min_stop_pct),
                    max_stop_pct=float(args.v2_max_stop_pct),
                    continuation_min_move=float(args.v2_continuation_min_move),
                    continuation_max_move=float(args.v2_continuation_max_move),
                    exhaustion_min_move=float(args.v2_exhaustion_min_move),
                )
                if candidate is not None:
                    if float(candidate.signal.score) < float(args.min_score):
                        continue
                    if allowed_v2_playbooks and candidate.playbook.lower() not in allowed_v2_playbooks:
                        continue
                    candidates.append(candidate)
                continue
            signal = _score_symbol_at(
                frame=frames[symbol],
                timestamp=scan_time,
                config=configs[symbol],
                calibration=calibration,
                leverage_min=int(args.leverage_min),
                leverage_max=args.leverage_max,
                min_score=float(args.min_score),
            )
            if signal is None:
                continue
            if args.match_mover_side:
                expected_side = "LONG" if mover_bucket == "positive" else "SHORT"
                if signal.side != expected_side:
                    continue
            candidates.append(
                Candidate(
                    signal=signal,
                    score_10=round(min(10.0, max(0.0, float(signal.score) / 10.0)), 2),
                    scan_time=scan_time,
                    mover_bucket=mover_bucket,
                    move_pct=float(move_pct),
                )
            )

        if scan_idx % 24 == 0:
            print(
                json.dumps({
                    "scan_progress": {
                        "scan": scan_idx,
                        "of": len(scan_times),
                        "movers": len(mover_map),
                        "candidates": len(candidates),
                        "open_opportunist": len(pending_trades),
                    }
                }),
                flush=True,
            )

        candidates.sort(key=lambda item: (float(item.signal.score), float(item.signal.certainty)), reverse=True)
        top = candidates[: int(args.top_n)]
        if top:
            scans_with_candidates += 1
        current_top_keys = {(item.signal.symbol, item.signal.side) for item in top}
        for key in list(streaks):
            if key not in current_top_keys:
                streaks.pop(key, None)
        for rank, item in enumerate(top, start=1):
            key = (item.signal.symbol, item.signal.side)
            streaks[key] = (streaks.get(key, 0) + 1) if key in previous_top_keys else 1
            item.rank = rank
            item.consecutive_top3_runs = streaks[key]
        previous_top_keys = current_top_keys

        if top and (scan_idx <= 5 or scan_idx % 24 == 0):
            top3_snapshots.append({
                "scan_time": scan_time.isoformat(),
                "top": [
                    {
                        "rank": item.rank,
                        "symbol": item.signal.symbol,
                        "side": item.signal.side,
                        "entry_signal": item.signal.entry_signal,
                        "score": item.signal.score,
                        "score_10": item.score_10,
                        "playbook": item.playbook,
                        "mover_bucket": item.mover_bucket,
                        "move_pct": round(item.move_pct, 6),
                        "streak": item.consecutive_top3_runs,
                    }
                    for item in top
                ],
            })

        triggered = top if args.entry_mode == "v2-structure" else [item for item in top if item.consecutive_top3_runs >= int(args.required_streak)]
        if triggered:
            for chosen in triggered:
                if len(pending_trades) >= max_open_positions:
                    break
                symbol = chosen.signal.symbol
                if any(open_trade.symbol == symbol for open_trade in pending_trades):
                    continue
                open_margin = sum(float(open_trade.margin_usdt) for open_trade in pending_trades)
                if open_margin >= opportunist_margin_cap * 0.999:
                    break
                trade, close_time, projected_balance = _simulate_trade(
                    engine=engines[symbol],
                    frame=frames[symbol],
                    signal=chosen.signal,
                    scan_time=scan_time,
                    balance=balance,
                )
                streaks.pop((symbol, chosen.signal.side), None)
                if trade is None or close_time is None:
                    continue
                margin_usdt = float(trade.get("margin_usdt", 0.0) or 0.0)
                if open_margin + margin_usdt > opportunist_margin_cap * 1.0001:
                    continue
                trade["strategy"] = "OPPORTUNIST_FUTURES"
                trade["trigger_scan_time"] = scan_time.isoformat()
                trade["trigger_rank"] = chosen.rank
                trade["trigger_score_10"] = chosen.score_10
                trade["trigger_streak"] = chosen.consecutive_top3_runs
                trade["opportunist_entry_mode"] = args.entry_mode
                trade["opportunist_playbook"] = chosen.playbook
                trade["mover_bucket"] = chosen.mover_bucket
                trade["mover_move_pct"] = round(chosen.move_pct, 8)
                trade["opportunist_margin_cap_usdt"] = round(opportunist_margin_cap, 8)
                trade["opportunist_open_positions_at_entry"] = len(pending_trades) + 1
                pending_trades.append(
                    OpenTrade(
                        symbol=symbol,
                        side=chosen.signal.side,
                        close_time=close_time,
                        margin_usdt=margin_usdt,
                        trade=trade,
                    )
                )
                if projected_balance <= 0:
                    break
            previous_top_keys = set()

        equity_curve.append({
            "timestamp": scan_time.isoformat(),
            "equity": round(balance, 8),
            "cash_balance": round(balance, 8),
            "open_opportunist_positions": len(pending_trades),
            "open_opportunist_margin_usdt": round(sum(float(trade.margin_usdt) for trade in pending_trades), 8),
        })

    for open_trade in pending_trades:
        balance += float(open_trade.trade.get("pnl_usdt", 0.0) or 0.0)
        trades.append(open_trade.trade)
    equity_curve.append({
        "timestamp": pd.Timestamp(end).isoformat(),
        "equity": round(balance, 8),
        "cash_balance": round(balance, 8),
        "open_opportunist_positions": 0,
        "open_opportunist_margin_usdt": 0.0,
    })

    report = build_report(equity_curve, trades, base.initial_balance)
    report["strategy_name"] = "OPPORTUNIST_FUTURES"
    report["entry_mode"] = args.entry_mode
    report["candidate_symbols"] = len(symbols)
    report["usable_symbols"] = len(frames)
    report["scan_count"] = len(scan_times)
    report["mover_side_count"] = int(args.mover_side_count)
    report["mover_lookback_hours"] = float(args.mover_lookback_hours)
    report["scans_with_movers"] = scans_with_movers
    report["scans_with_candidates"] = scans_with_candidates
    report["opportunist_budget_pct"] = opportunist_budget_pct
    report["opportunist_margin_cap_usdt"] = opportunist_margin_cap
    report["max_open_positions"] = max_open_positions
    report["per_trade_margin_budget_mult"] = margin_budget_mult
    report["leverage_min"] = int(args.leverage_min)
    report["leverage_max"] = args.leverage_max
    report["v2_reward_risk"] = float(args.v2_reward_risk)
    report["v2_min_stop_pct"] = float(args.v2_min_stop_pct)
    report["v2_max_stop_pct"] = float(args.v2_max_stop_pct)
    report["v2_watchlist_hours"] = float(args.v2_watchlist_hours)
    report["v2_continuation_min_move"] = float(args.v2_continuation_min_move)
    report["v2_continuation_max_move"] = float(args.v2_continuation_max_move)
    report["v2_exhaustion_min_move"] = float(args.v2_exhaustion_min_move)
    report["v2_allowed_buckets"] = sorted(allowed_v2_buckets)
    report["v2_allowed_playbooks"] = sorted(allowed_v2_playbooks)
    report["max_drawdown"] = _max_drawdown(equity_curve)
    report["top3_snapshots"] = top3_snapshots[-20:]

    out_dir = Path(args.out)
    export_artifacts(str(out_dir), equity_curve, trades, report)
    (out_dir / "opportunist_summary.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the non-default MEXC futures opportunist-pair rule.")
    parser.add_argument("--start", help="UTC start for the 3-day trade window")
    parser.add_argument("--end", help="UTC end for the trade window")
    parser.add_argument("--warmup-days", type=float, default=5.5)
    parser.add_argument("--scan-minutes", type=int, default=30)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--required-streak", type=int, default=3)
    parser.add_argument("--entry-mode", choices=("top3-continuation", "v2-structure"), default="top3-continuation")
    parser.add_argument("--mover-side-count", type=int, default=25, help="Select this many positive movers and this many negative movers per scan.")
    parser.add_argument("--mover-lookback-hours", type=float, default=24.0, help="Lookback used to rank MEXC movers.")
    parser.add_argument("--no-match-mover-side", action="store_false", dest="match_mover_side", default=True, help="Allow scorer side to differ from mover direction.")
    parser.add_argument("--v2-reward-risk", type=float, default=2.2, help="Reward/risk target for v2 structural opportunist entries.")
    parser.add_argument("--v2-min-stop-pct", type=float, default=0.004, help="Minimum stop distance as a fraction of entry for v2 entries.")
    parser.add_argument("--v2-max-stop-pct", type=float, default=0.026, help="Maximum stop distance as a fraction of entry for x20 liquidation-buffer discipline.")
    parser.add_argument("--v2-watchlist-hours", type=float, default=4.0, help="Keep mover symbols on the v2 radar for this many hours.")
    parser.add_argument("--v2-continuation-min-move", type=float, default=0.06, help="Minimum absolute 24h move for v2 second-leg continuation setups.")
    parser.add_argument("--v2-continuation-max-move", type=float, default=0.24, help="Maximum absolute 24h move for v2 continuation before treating it as exhaustion.")
    parser.add_argument("--v2-exhaustion-min-move", type=float, default=0.25, help="Minimum absolute 24h move for v2 exhaustion-reversal setups.")
    parser.add_argument("--v2-allowed-buckets", default="positive,negative", help="Comma-separated mover buckets allowed for v2 entries; empty allows all.")
    parser.add_argument("--v2-allowed-playbooks", default="pullback_reclaim,pullback_reject,exhaustion_reversal", help="Comma-separated v2 playbooks allowed; empty allows all.")
    parser.add_argument("--opportunist-budget-pct", type=float, default=0.10, help="Total margin sleeve reserved for opportunist positions.")
    parser.add_argument("--max-open-positions", type=int, default=3, help="Maximum simultaneous opportunist positions.")
    parser.add_argument("--margin-budget-mult", type=float, default=None, help="Optional per-trade margin multiplier; defaults to budget_pct / max_open_positions.")
    parser.add_argument("--leverage-min", type=int, default=20, help="Minimum leverage for opportunist signals.")
    parser.add_argument("--leverage-max", type=int, default=None, help="Optional post-calibration leverage cap for opportunist probes.")
    parser.add_argument("--min-score", type=float, default=0.0, help="Optional minimum raw score after calibration.")
    parser.add_argument("--max-symbols", type=int, default=None, help="Optional cap for a quick smoke test.")
    parser.add_argument("--symbols", help="Optional comma-separated override universe, still excluding the production 10.")
    parser.add_argument("--no-calibration", action="store_false", dest="calibration", default=True)
    parser.add_argument("--out", default="backtest_output/opportunist_3d")
    args = parser.parse_args()

    report = run_opportunist_backtest(args)
    print(json.dumps({
        "opportunist_result": {
            "total_trades": report.get("total_trades"),
            "entry_mode": report.get("entry_mode"),
            "total_pnl": report.get("total_pnl"),
            "win_rate": report.get("win_rate"),
            "profit_factor": report.get("profit_factor"),
            "max_drawdown": report.get("max_drawdown"),
            "candidate_symbols": report.get("candidate_symbols"),
            "usable_symbols": report.get("usable_symbols"),
            "mover_side_count": report.get("mover_side_count"),
            "scan_count": report.get("scan_count"),
            "scans_with_movers": report.get("scans_with_movers"),
            "scans_with_candidates": report.get("scans_with_candidates"),
            "opportunist_budget_pct": report.get("opportunist_budget_pct"),
            "max_open_positions": report.get("max_open_positions"),
            "leverage_min": report.get("leverage_min"),
        }
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
