from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
from typing import Any

from futuresbot.calibration import build_trade_calibration, publish_trade_calibration, write_trade_calibration
from futuresbot.backtest import FuturesBacktestEngine, build_report, build_signal_summary, export_artifacts
from futuresbot.config import DEFAULT_FUTURES_SYMBOLS, FuturesBacktestConfig, FuturesConfig, parse_utc_datetime
from futuresbot.gate_b_readiness import SymbolResult, evaluate_gate_b_readiness
from futuresbot.marketdata import FuturesHistoricalDataProvider, MexcFuturesClient


def _calibration_output_file() -> str:
    raw = os.getenv("FUTURES_CALIBRATION_OUTPUT_FILE", "backtest_output/calibration.json")
    path = Path(raw)
    if path.is_absolute():
        return str(path)
    return str((Path(__file__).resolve().parent / path).resolve())


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
    cfg = copy.copy(base_config)
    cfg.symbol = symbol
    cfg.output_dir = str(Path(base_config.output_dir) / symbol.lower())
    engine = FuturesBacktestEngine(cfg, provider, client)
    equity_curve, trades = engine.run()
    report = build_report(equity_curve, trades, cfg.initial_balance)
    export_artifacts(cfg.output_dir, equity_curve, trades, report)
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
