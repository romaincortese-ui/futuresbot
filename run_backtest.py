from __future__ import annotations

import argparse
import dataclasses
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from futuresbot.calibration import build_trade_calibration, publish_trade_calibration, write_trade_calibration
from futuresbot.backtest import FuturesBacktestEngine, build_report, build_signal_summary, export_artifacts
from futuresbot.config import DEFAULT_FUTURES_SYMBOLS, FuturesBacktestConfig, FuturesConfig, parse_utc_datetime
from futuresbot.gate_b_readiness import SymbolResult, evaluate_gate_b_readiness
from futuresbot.marketdata import FuturesHistoricalDataProvider, MexcFuturesClient
from futuresbot.models import FuturesPosition, FuturesSignal
from futuresbot.pmt_core_weight import SymbolMarketInput, build_core_weight_payload
from futuresbot.pmt_strategy import pmt_strategy_enabled, pmt_win_cooldown_exit_reason


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


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


def _calibration_output_file() -> str:
    raw = os.getenv("FUTURES_CALIBRATION_OUTPUT_FILE", "backtest_output/calibration.json")
    path = Path(raw)
    if path.is_absolute():
        return str(path)
    return str((Path(__file__).resolve().parent / path).resolve())


def _historical_replay_ticker(symbol: str, frame_slice: pd.DataFrame) -> dict[str, Any]:
    close = pd.to_numeric(frame_slice.get("close", pd.Series(dtype="float64")), errors="coerce").dropna()
    volume = pd.to_numeric(frame_slice.get("volume", pd.Series(dtype="float64")), errors="coerce").dropna()
    if close.empty:
        return {"symbol": symbol}
    last_price = float(close.iloc[-1])
    quote_amount = 0.0
    base_volume = 0.0
    if not volume.empty:
        recent_close = close.tail(96)
        recent_volume = volume.reindex(recent_close.index).fillna(0.0)
        quote_amount = float((recent_close * recent_volume).sum())
        base_volume = float(recent_volume.sum())
    return {
        "symbol": symbol,
        "lastPrice": last_price,
        "fairPrice": last_price,
        "indexPrice": last_price,
        "amount24": quote_amount,
        "volume24": base_volume,
    }


def _historical_core_weight_inputs(
    frames: dict[str, pd.DataFrame],
    indexes: dict[str, dict[Any, int]],
    timestamp: Any,
    *,
    lookback_bars: int,
) -> list[SymbolMarketInput]:
    inputs: list[SymbolMarketInput] = []
    for symbol, frame in frames.items():
        idx = indexes.get(symbol, {}).get(timestamp)
        if idx is None:
            continue
        start = max(0, idx + 1 - lookback_bars)
        frame_slice = frame.iloc[start : idx + 1]
        if len(frame_slice) < 96:
            continue
        inputs.append(
            SymbolMarketInput(
                symbol=symbol,
                frame=frame_slice,
                ticker=_historical_replay_ticker(symbol, frame_slice),
                funding_rate=0.0,
            )
        )
    return inputs


def _core_weight_replay_record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": payload.get("generated_at"),
        "recommended_core_weight": payload.get("recommended_core_weight"),
        "calculated_core_weight": payload.get("calculated_core_weight"),
        "previous_core_weight": payload.get("previous_core_weight"),
        "portfolio": payload.get("portfolio"),
        "symbols": payload.get("symbols"),
    }


def _pmt_stop_chase_exit_reason(reason: object) -> bool:
    raw = str(reason or "").upper()
    configured = os.environ.get("FUTURES_PMT_STOP_CHASE_EXIT_REASONS", "STOP_LOSS,PEAK_PROTECTION_GAP_EXIT")
    allowed = {part.strip().upper() for part in configured.replace(";", ",").split(",") if part.strip()}
    return raw in (allowed or {"STOP_LOSS"})


def _pmt_stop_chase_blocked(signal: FuturesSignal, now: pd.Timestamp, cooldowns: dict[tuple[str, str], pd.Timestamp]) -> bool:
    if not pmt_strategy_enabled():
        return False
    cooldown_hours = max(0.0, _env_float("FUTURES_PMT_STOP_CHASE_COOLDOWN_HOURS", 0.0))
    if cooldown_hours <= 0.0:
        return False
    key = (signal.symbol.upper(), signal.side.upper())
    until = cooldowns.get(key)
    return until is not None and now < until


DEFAULT_LIVE_SYMBOLS = DEFAULT_FUTURES_SYMBOLS


def _resolve_symbols(cli_symbols: str | None, config: FuturesBacktestConfig) -> list[str]:
    if cli_symbols:
        raw = cli_symbols
    else:
        raw = os.environ.get("FUTURES_BACKTEST_SYMBOLS", "")
    if raw.strip():
        items = [s.strip().upper() for s in raw.split(",") if s.strip()]
    else:
        live = FuturesConfig.from_env()
        items = [s.upper() for s in live.symbols] if live.symbols else [config.symbol]
        if not items or (len(items) == 1 and items[0] == "BTC_USDT"):
            items = list(DEFAULT_LIVE_SYMBOLS)
    seen: set[str] = set()
    ordered: list[str] = []
    for sym in items:
        if sym not in seen:
            seen.add(sym)
            ordered.append(sym)
    return ordered


def _run_single_symbol(
    base_config: FuturesBacktestConfig,
    client: MexcFuturesClient,
    provider: FuturesHistoricalDataProvider,
    symbol: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    cfg = _scoped_backtest_config(base_config, symbol)
    engine = FuturesBacktestEngine(cfg, provider, client)
    equity_curve, trades = engine.run()
    report = build_report(equity_curve, trades, cfg.initial_balance)
    export_artifacts(cfg.output_dir, equity_curve, trades, report)
    return equity_curve, trades, report


def _scoped_backtest_config(base_config: FuturesBacktestConfig, symbol: str) -> FuturesBacktestConfig:
    old_symbol = os.environ.get("FUTURES_SYMBOL")
    os.environ["FUTURES_SYMBOL"] = symbol
    try:
        scoped_config = FuturesBacktestConfig.from_env()
    finally:
        if old_symbol is None:
            os.environ.pop("FUTURES_SYMBOL", None)
        else:
            os.environ["FUTURES_SYMBOL"] = old_symbol
    cfg = dataclasses.replace(
        scoped_config,
        start=base_config.start,
        end=base_config.end,
        initial_balance=base_config.initial_balance,
        output_dir=str(Path(base_config.output_dir) / symbol.lower()),
        cache_dir=base_config.cache_dir,
    )
    return cfg


def _run_portfolio_backtest(
    base_config: FuturesBacktestConfig,
    client: MexcFuturesClient,
    provider: FuturesHistoricalDataProvider,
    symbols: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    start_ts = int(base_config.start.timestamp())
    end_ts = int(base_config.end.timestamp())
    frames: dict[str, Any] = {}
    indexes: dict[str, dict[Any, int]] = {}
    engines: dict[str, FuturesBacktestEngine] = {}
    configs: dict[str, FuturesBacktestConfig] = {}
    for symbol in symbols:
        cfg = dataclasses.replace(_scoped_backtest_config(base_config, symbol), output_dir=str(Path(base_config.output_dir) / symbol.lower()))
        frame = provider.fetch_klines(symbol, interval="Min15", start=start_ts, end=end_ts).sort_index()
        if len(frame) <= 220:
            continue
        configs[symbol] = cfg
        engines[symbol] = FuturesBacktestEngine(cfg, provider, client)
        frames[symbol] = frame
        indexes[symbol] = {timestamp: idx for idx, timestamp in enumerate(frame.index)}

    all_times = sorted({timestamp for frame in frames.values() for timestamp in frame.index[220:]})
    progress_every = max(0, int(os.environ.get("FUTURES_BACKTEST_PROGRESS_EVERY", "0") or 0))
    balance = float(base_config.initial_balance)
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    step = pd.Timedelta(minutes=15)
    # Capacity-N slot list (FUTURES_BACKTEST_MAX_POSITIONS, default 1 = legacy
    # behavior). Entries are additive: a second slot only opens when the live
    # margin calc fits the remaining balance (mirrors [LIVE_MARGIN_CAP]).
    max_slots = max(1, _env_int("FUTURES_BACKTEST_MAX_POSITIONS", 1))
    open_slots: list[tuple[FuturesBacktestEngine, FuturesPosition]] = []
    pending_signal: FuturesSignal | None = None
    pending_symbol = ""
    pending_entry_time = None
    pmt_cooldown_until = None
    core_weight_replay_enabled = _env_bool("FUTURES_PMT_CORE_WEIGHT_REPLAY_ENABLED", False)
    core_weight_replay_interval_seconds = int(max(900.0, _env_float("FUTURES_PMT_CORE_WEIGHT_REPLAY_INTERVAL_HOURS", 6.0) * 3600.0))
    core_weight_replay_lookback_bars = max(96, _env_int("FUTURES_PMT_CORE_WEIGHT_REPLAY_LOOKBACK_BARS", 192))
    core_weight_replay_slot: int | None = None
    core_weight_replay_payload: dict[str, Any] | None = None
    core_weight_replay_rows: list[dict[str, Any]] = []
    pmt_stop_chase_cooldowns: dict[tuple[str, str], pd.Timestamp] = {}
    pmt_stop_chase_blocks = 0

    def register_pmt_exit(position: FuturesPosition, reason: str, closed_at: pd.Timestamp) -> None:
        if not pmt_strategy_enabled() or not str(position.entry_signal or "").upper().startswith("PMT_THRESHOLD_"):
            return
        cooldown_hours = max(0.0, _env_float("FUTURES_PMT_STOP_CHASE_COOLDOWN_HOURS", 0.0))
        if cooldown_hours <= 0.0 or not _pmt_stop_chase_exit_reason(reason):
            return
        pmt_stop_chase_cooldowns[(position.symbol.upper(), position.side.upper())] = closed_at + pd.Timedelta(hours=cooldown_hours)

    for step_index, timestamp in enumerate(all_times, start=1):
        if progress_every > 0 and (step_index == 1 or step_index % progress_every == 0 or step_index == len(all_times)):
            print(
                json.dumps(
                    {
                        "portfolio_backtest_progress": {
                            "step": step_index,
                            "total_steps": len(all_times),
                            "pct": round(step_index / max(1, len(all_times)) * 100.0, 2),
                            "timestamp": timestamp.isoformat(),
                            "open_position": bool(open_slots),
                            "trades": len(trades),
                            "balance": round(balance, 6),
                        }
                    }
                ),
                flush=True,
            )
        if (
            pending_signal is not None
            and pending_entry_time == timestamp
            and len(open_slots) < max_slots
            and pending_symbol not in {pos.symbol for _, pos in open_slots}
        ):
            frame = frames.get(pending_symbol)
            engine = engines.get(pending_symbol)
            idx = indexes.get(pending_symbol, {}).get(timestamp)
            if frame is not None and engine is not None and idx is not None:
                held_margin = sum(float(pos.margin_usdt or 0.0) for _, pos in open_slots)
                position = engine._open_position(pending_signal, timestamp, float(frame.iloc[idx]["open"]), balance - held_margin)
                if position is not None:
                    open_slots.append((engine, position))
            pending_signal = None
            pending_symbol = ""
            pending_entry_time = None

        close_time = timestamp + step
        for slot in list(open_slots):
            slot_engine, slot_position = slot
            frame = frames.get(slot_position.symbol)
            idx = indexes.get(slot_position.symbol, {}).get(timestamp)
            if frame is not None and idx is not None:
                bar = frame.iloc[idx]
                slot_engine._latest_regime_frame = frame.iloc[: idx + 1]
                bar_exit = slot_engine._bar_exit(slot_position, bar)
                if bar_exit is not None:
                    exit_price, reason = bar_exit
                    liquidated = reason == "LIQUIDATED"
                    trade = slot_engine._close_position(
                        slot_position,
                        close_time,
                        exit_price,
                        reason,
                        liquidated=liquidated,
                        liq_price=exit_price if liquidated else None,
                    )
                    balance += float(trade["pnl_usdt"])
                    trades.append(trade)
                    register_pmt_exit(slot_position, reason, close_time)
                    if pmt_strategy_enabled() and pmt_win_cooldown_exit_reason(reason):
                        cooldown_hours = max(0.0, _env_float("FUTURES_PMT_TP_COOLDOWN_HOURS", 24.0))
                        pmt_cooldown_until = close_time + pd.Timedelta(hours=cooldown_hours) if cooldown_hours > 0 else None
                    open_slots.remove(slot)

        if close_time.minute == 0:
            for slot in list(open_slots):
                slot_engine, slot_position = slot
                frame = frames.get(slot_position.symbol)
                idx = indexes.get(slot_position.symbol, {}).get(timestamp)
                if frame is not None and idx is not None:
                    hourly_exit = slot_engine._hourly_exit(slot_position, float(frame.iloc[idx]["close"]), close_time.to_pydatetime())
                    if hourly_exit is not None:
                        exit_price, reason = hourly_exit
                        trade = slot_engine._close_position(slot_position, close_time, exit_price, reason)
                        balance += float(trade["pnl_usdt"])
                        trades.append(trade)
                        register_pmt_exit(slot_position, reason, close_time)
                        if pmt_strategy_enabled() and pmt_win_cooldown_exit_reason(reason):
                            cooldown_hours = max(0.0, _env_float("FUTURES_PMT_TP_COOLDOWN_HOURS", 24.0))
                            pmt_cooldown_until = close_time + pd.Timedelta(hours=cooldown_hours) if cooldown_hours > 0 else None
                        open_slots.remove(slot)

        pmt_cooldown_active = pmt_strategy_enabled() and pmt_cooldown_until is not None and close_time < pmt_cooldown_until
        if core_weight_replay_enabled and pmt_strategy_enabled():
            replay_slot = int(close_time.timestamp()) // core_weight_replay_interval_seconds
            if replay_slot != core_weight_replay_slot:
                replay_inputs = _historical_core_weight_inputs(
                    frames,
                    indexes,
                    timestamp,
                    lookback_bars=core_weight_replay_lookback_bars,
                )
                if replay_inputs:
                    core_weight_replay_payload = build_core_weight_payload(
                        replay_inputs,
                        previous_payload=core_weight_replay_payload,
                        now_unix=close_time.timestamp(),
                    )
                    replay_weight = float(core_weight_replay_payload["recommended_core_weight"])
                    os.environ["FUTURES_PMT_SIMPLE_CORE_WEIGHT"] = f"{replay_weight:.2f}"
                    os.environ["FUTURES_PMT_SIMPLE_CORE_WEIGHT_SOURCE"] = "historical_replay"
                    core_weight_replay_rows.append(_core_weight_replay_record(core_weight_replay_payload))
                    core_weight_replay_slot = replay_slot
        if (
            len(open_slots) >= max_slots
            and pending_signal is None
            and not pmt_cooldown_active
            and pmt_strategy_enabled()
            and _env_bool("FUTURES_PMT_PREEMPT_LOWER_SCORE_ENABLED", False)
        ):
            candidates: list[tuple[int, float, float, str, FuturesSignal]] = []
            for symbol, frame in frames.items():
                idx = indexes[symbol].get(timestamp)
                if idx is None or idx < 220 or idx + 1 >= len(frame):
                    continue
                signal = engines[symbol]._candidate_signal_for_frame(frame.iloc[: idx + 1], close_time.to_pydatetime(), len(frame) - idx - 1)
                if signal is None:
                    continue
                if _pmt_stop_chase_blocked(signal, close_time, pmt_stop_chase_cooldowns):
                    pmt_stop_chase_blocks += 1
                    continue
                metadata = signal.metadata or {}
                candidates.append(
                    (
                        int(metadata.get("opportunity_score_10") or 0),
                        float(signal.score),
                        float(signal.certainty),
                        symbol,
                        signal,
                    )
                )
            candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
            if candidates and open_slots:
                _score10, score, _certainty, symbol, signal = candidates[0]
                weakest = min(open_slots, key=lambda sl: float(sl[1].score or 0.0))
                weakest_engine, weakest_position = weakest
                current_score = float(weakest_position.score or 0.0)
                min_preempt_score = max(0.0, _env_float("FUTURES_PMT_PREEMPT_MIN_SCORE", 97.0))
                min_preempt_delta = max(0.0, _env_float("FUTURES_PMT_PREEMPT_MIN_SCORE_DELTA", 3.0))
                open_exposures = {(pos.symbol, pos.side) for _, pos in open_slots}
                different_exposure = (signal.symbol, signal.side) not in open_exposures
                if different_exposure and score >= min_preempt_score and score >= current_score + min_preempt_delta:
                    frame = frames.get(weakest_position.symbol)
                    idx = indexes.get(weakest_position.symbol, {}).get(timestamp)
                    if frame is not None and idx is not None:
                        trade = weakest_engine._close_position(
                            weakest_position,
                            close_time,
                            float(frame.iloc[idx]["close"]),
                            "PMT_PREEMPTED_BY_SUPERIOR_SIGNAL",
                        )
                        balance += float(trade["pnl_usdt"])
                        trades.append(trade)
                        open_slots.remove(weakest)
                        pending_signal = signal
                        pending_symbol = symbol
                        pending_entry_time = frames[symbol].index[indexes[symbol][timestamp] + 1]

        if len(open_slots) < max_slots and pending_signal is None and not pmt_cooldown_active and (pmt_strategy_enabled() or close_time.minute == 0):
            open_symbols = {pos.symbol for _, pos in open_slots}
            candidates: list[tuple[int, float, float, str, FuturesSignal]] = []
            for symbol, frame in frames.items():
                if symbol in open_symbols:
                    continue
                idx = indexes[symbol].get(timestamp)
                if idx is None or idx < 220 or idx + 1 >= len(frame):
                    continue
                signal = engines[symbol]._candidate_signal_for_frame(frame.iloc[: idx + 1], close_time.to_pydatetime(), len(frame) - idx - 1)
                if signal is None:
                    continue
                if _pmt_stop_chase_blocked(signal, close_time, pmt_stop_chase_cooldowns):
                    pmt_stop_chase_blocks += 1
                    continue
                metadata = signal.metadata or {}
                candidates.append(
                    (
                        int(metadata.get("opportunity_score_10") or 0),
                        float(signal.score),
                        float(signal.certainty),
                        symbol,
                        signal,
                    )
                )
            candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
            if candidates:
                _score10, _score, _certainty, symbol, signal = candidates[0]
                pending_signal = signal
                pending_symbol = symbol
                pending_entry_time = frames[symbol].index[indexes[symbol][timestamp] + 1]

        mtm = 0.0
        for slot_engine, slot_position in open_slots:
            frame = frames.get(slot_position.symbol)
            idx = indexes.get(slot_position.symbol, {}).get(timestamp)
            if frame is not None and idx is not None:
                mtm += slot_engine._mark_to_market(slot_position, float(frame.iloc[idx]["close"]))
        equity_curve.append(
            {
                "timestamp": close_time.isoformat(),
                "equity": round(balance + mtm, 8),
                "cash_balance": round(balance, 8),
                "open_positions": len(open_slots),
            }
        )

    for slot_engine, slot_position in list(open_slots):
        frame = frames[slot_position.symbol]
        final_timestamp = frame.index[-1] + step
        final_close = float(frame.iloc[-1]["close"])
        trade = slot_engine._close_position(slot_position, final_timestamp, final_close, "END_OF_TEST")
        balance += float(trade["pnl_usdt"])
        trades.append(trade)
        register_pmt_exit(slot_position, "END_OF_TEST", final_timestamp)
    if open_slots:
        open_slots = []
        equity_curve.append({"timestamp": final_timestamp.isoformat(), "equity": round(balance, 8), "cash_balance": round(balance, 8), "open_positions": 0})

    report = build_report(equity_curve, trades, base_config.initial_balance)
    report["portfolio_mode"] = True
    report["symbols"] = list(frames.keys())
    report["usable_symbols"] = len(frames)
    report["max_open_positions"] = max_slots
    cooldown_hours = max(0.0, _env_float("FUTURES_PMT_STOP_CHASE_COOLDOWN_HOURS", 0.0))
    if cooldown_hours > 0.0:
        report["pmt_stop_chase_cooldown"] = {
            "enabled": True,
            "cooldown_hours": cooldown_hours,
            "blocks": pmt_stop_chase_blocks,
            "exit_reasons": sorted({part.strip().upper() for part in os.environ.get("FUTURES_PMT_STOP_CHASE_EXIT_REASONS", "STOP_LOSS,PEAK_PROTECTION_GAP_EXIT").replace(";", ",").split(",") if part.strip()}),
        }
    if core_weight_replay_enabled:
        weights: dict[str, int] = {}
        for row in core_weight_replay_rows:
            weight = str(row.get("recommended_core_weight"))
            weights[weight] = weights.get(weight, 0) + 1
        report["pmt_core_weight_replay"] = {
            "enabled": True,
            "interval_hours": round(core_weight_replay_interval_seconds / 3600.0, 4),
            "lookback_bars": core_weight_replay_lookback_bars,
            "updates": len(core_weight_replay_rows),
            "weight_counts": weights,
        }
    export_artifacts(base_config.output_dir, equity_curve, trades, report)
    if core_weight_replay_enabled:
        replay_path = Path(base_config.output_dir) / "pmt_core_weight_replay.json"
        replay_path.write_text(json.dumps(core_weight_replay_rows, indent=2), encoding="utf-8")
    return equity_curve, trades, report


def _aggregate_report(per_symbol: dict[str, dict[str, Any]], initial_balance: float) -> dict[str, Any]:
    total_pnl = 0.0
    total_trades = 0
    wins = 0
    worst_dd = 0.0
    wins_pnl = 0.0
    losses_pnl = 0.0
    for rep in per_symbol.values():
        pnl = float(rep.get("total_pnl") or 0.0)
        trades = int(rep.get("total_trades") or 0)
        total_pnl += pnl
        total_trades += trades
        wr = float(rep.get("win_rate") or 0.0)
        wins += int(round(wr * trades))
        dd = float(rep.get("max_drawdown") or 0.0)
        worst_dd = min(worst_dd, dd)
        if pnl >= 0:
            wins_pnl += pnl
        else:
            losses_pnl += abs(pnl)
    win_rate = (wins / total_trades) if total_trades else 0.0
    pf = (wins_pnl / losses_pnl) if losses_pnl > 0 else (999.0 if wins_pnl > 0 else 0.0)
    return {
        "initial_balance_per_symbol": initial_balance,
        "symbols": list(per_symbol.keys()),
        "total_trades": total_trades,
        "total_pnl": round(total_pnl, 8),
        "portfolio_win_rate": round(win_rate, 4),
        "portfolio_profit_factor_approx": round(pf, 4),
        "worst_symbol_max_drawdown": round(worst_dd, 6),
        "per_symbol": {
            sym: {
                "total_trades": int(rep.get("total_trades") or 0),
                "total_pnl": float(rep.get("total_pnl") or 0.0),
                "win_rate": float(rep.get("win_rate") or 0.0),
                "profit_factor": float(rep.get("profit_factor") or 0.0),
                "max_drawdown": float(rep.get("max_drawdown") or 0.0),
                "ending_balance": float(rep.get("ending_balance") or 0.0),
            }
            for sym, rep in per_symbol.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the futures backtest (single- or multi-symbol)")
    parser.add_argument("--start", help="UTC ISO start datetime")
    parser.add_argument("--end", help="UTC ISO end datetime")
    parser.add_argument(
        "--symbols",
        help="Comma-separated symbol list. Overrides FUTURES_BACKTEST_SYMBOLS and FUTURES_SYMBOLS.",
    )
    parser.add_argument("--single-symbol", help="Restrict the run to one symbol.")
    parser.add_argument("--portfolio", action="store_true", help="Scan all symbols into one portfolio with one open trade at a time.")
    args = parser.parse_args()

    config = FuturesBacktestConfig.from_env()
    if args.start:
        config.start = parse_utc_datetime(args.start)
    if args.end:
        config.end = parse_utc_datetime(args.end)

    symbols = [args.single_symbol.strip().upper()] if args.single_symbol else _resolve_symbols(args.symbols, config)

    client = MexcFuturesClient(FuturesConfig.from_env())
    provider = FuturesHistoricalDataProvider(client, cache_dir=config.cache_dir)

    print(json.dumps({
        "backtest_run": {
            "symbols": symbols,
            "start": config.start.isoformat(),
            "end": config.end.isoformat(),
            "output_dir": config.output_dir,
        }
    }, indent=2))

    portfolio_mode = bool(args.portfolio or _env_bool("FUTURES_BACKTEST_PORTFOLIO_MODE", False)) and not args.single_symbol

    if portfolio_mode:
        _, combined_trades, portfolio_report = _run_portfolio_backtest(config, client, provider, symbols)
        calibration = build_trade_calibration(
            combined_trades,
            window_start=config.start,
            window_end=config.end,
            min_strategy_trades=config.calibration_min_total_trades,
            min_symbol_trades=config.calibration_min_total_trades,
        )
        calibration_file = _calibration_output_file()
        write_trade_calibration(calibration_file, calibration)
        published = publish_trade_calibration(config.redis_url, config.calibration_redis_key, calibration)
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)
        (Path(config.output_dir) / "portfolio_summary.json").write_text(json.dumps(portfolio_report, indent=2), encoding="utf-8")
        print(json.dumps({"calibration": {"file": calibration_file, "redis_key": config.calibration_redis_key, "published": published}}, indent=2))
        print(json.dumps({"portfolio_summary": portfolio_report}, indent=2))
        return

    per_symbol_report: dict[str, dict[str, Any]] = {}
    combined_trades: list[dict[str, Any]] = []

    for sym in symbols:
        try:
            _, trades, report = _run_single_symbol(config, client, provider, sym)
        except Exception as exc:
            print(json.dumps({"symbol_error": {"symbol": sym, "error": str(exc)}}, indent=2))
            continue
        per_symbol_report[sym] = report
        combined_trades.extend(trades)
        print(json.dumps({
            "symbol_done": {
                "symbol": sym,
                "total_trades": report.get("total_trades"),
                "total_pnl": report.get("total_pnl"),
                "win_rate": report.get("win_rate"),
                "profit_factor": report.get("profit_factor"),
                "max_drawdown": report.get("max_drawdown"),
                "ending_balance": report.get("ending_balance"),
            }
        }, indent=2))

    calibration = build_trade_calibration(
        combined_trades,
        window_start=config.start,
        window_end=config.end,
        min_strategy_trades=config.calibration_min_total_trades,
        min_symbol_trades=config.calibration_min_total_trades,
    )
    calibration_file = _calibration_output_file()
    write_trade_calibration(calibration_file, calibration)
    published = publish_trade_calibration(config.redis_url, config.calibration_redis_key, calibration)

    aggregate = _aggregate_report(per_symbol_report, config.initial_balance)
    Path(config.output_dir).mkdir(parents=True, exist_ok=True)
    (Path(config.output_dir) / "portfolio_summary.json").write_text(
        json.dumps(aggregate, indent=2), encoding="utf-8"
    )

    # Gate B B3 (memo 1 §7): feed the per-symbol OOS metrics into the
    # allocation-readiness aggregator so the backtest emits an explicit
    # pass/fail verdict alongside the portfolio summary.
    symbol_results: dict[str, SymbolResult] = {}
    for sym, rep in per_symbol_report.items():
        symbol_results[sym] = SymbolResult(
            symbol=sym,
            oos_trades=int(rep.get("total_trades") or 0),
            oos_profit_factor=float(rep.get("profit_factor") or 0.0),
            total_pnl_usdt=float(rep.get("total_pnl") or 0.0),
            # ``max_drawdown`` from build_report is a negative fraction of the
            # equity peak. Convert to an absolute USDT figure on the per-symbol
            # initial balance so the aggregator can compare against the total
            # margin budget.
            max_drawdown_usdt=abs(float(rep.get("max_drawdown") or 0.0)) * float(config.initial_balance),
        )
    margin_budget = float(config.initial_balance) * max(1, len(symbol_results))
    readiness = evaluate_gate_b_readiness(
        symbol_results=symbol_results,
        margin_budget_usdt=margin_budget,
    )
    readiness_payload = {
        "passed": readiness.passed,
        "reasons": readiness.reasons,
        "per_symbol_pf": readiness.per_symbol_pf,
        "per_symbol_trades": readiness.per_symbol_trades,
        "concentration": readiness.concentration,
        "aggregate_pnl_usdt": readiness.aggregate_pnl_usdt,
        "aggregate_max_drawdown_usdt": readiness.aggregate_max_drawdown_usdt,
        "aggregate_drawdown_pct": readiness.aggregate_drawdown_pct,
        "thresholds": readiness.thresholds,
    }
    (Path(config.output_dir) / "gate_b_readiness.json").write_text(
        json.dumps(readiness_payload, indent=2), encoding="utf-8"
    )

    print(json.dumps({
        "calibration": {
            "file": calibration_file,
            "redis_key": config.calibration_redis_key,
            "published": published,
        }
    }, indent=2))
    print(json.dumps({"portfolio_summary": aggregate}, indent=2))
    print(json.dumps({"gate_b_readiness": readiness_payload}, indent=2))


if __name__ == "__main__":
    main()
