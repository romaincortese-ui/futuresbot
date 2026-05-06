from __future__ import annotations

import argparse
import json
import os
import traceback
from pathlib import Path
from typing import Any

from futuresbot.backtest import FuturesBacktestEngine, build_report, export_artifacts
from futuresbot.config import DEFAULT_FUTURES_SYMBOLS, FuturesBacktestConfig, FuturesConfig, parse_utc_datetime, resolve_repo_path
from futuresbot.marketdata import FuturesHistoricalDataProvider, MexcFuturesClient
from futuresbot.universe import select_major_usdt_symbols


PRESERVED_FUTURES_ENV = {
    "FUTURES_BACKTEST_START",
    "FUTURES_BACKTEST_END",
    "FUTURES_BACKTEST_CACHE_DIR",
    "FUTURES_BACKTEST_INITIAL_BALANCE",
    "FUTURES_BACKTEST_MARGIN_BUDGET_USDT",
    "FUTURES_BACKTEST_TAKER_FEE_RATE",
    "FUTURES_SHARP_EVENT_OVERLAY_ENABLED",
    "FUTURES_SHARP_EVENT_CORE_SYMBOLS",
    "FUTURES_SHARP_EVENT_RISK_MULTIPLIER",
    "FUTURES_SHARP_EVENT_BYPASS_SYMBOL_CALIBRATION",
    "FUTURES_SHARP_EVENT_LOOKBACK_BARS",
    "FUTURES_SHARP_EVENT_CONFIRM_BARS",
    "FUTURES_SHARP_EVENT_MIN_MOVE_PCT",
    "FUTURES_SHARP_EVENT_MIN_MOVE_ATR",
    "FUTURES_SHARP_EVENT_MIN_VOLUME_RATIO",
    "FUTURES_SHARP_EVENT_MIN_WINDOW_VOLUME_RATIO",
    "FUTURES_SHARP_EVENT_MIN_CLOSE_RATIO",
    "FUTURES_SHARP_EVENT_MAX_EMA_EXTENSION_ATR",
    "FUTURES_SHARP_EVENT_MAX_MOVE_ATR",
    "FUTURES_SHARP_EVENT_MIN_SCORE",
}


def _clear_symbol_env() -> None:
    for key in list(os.environ):
        if key.startswith("FUTURES_") and key not in PRESERVED_FUTURES_ENV:
            os.environ.pop(key, None)


def _run_one(
    *,
    symbol: str,
    start: str,
    end: str,
    out_root: Path,
    calibration: dict[str, Any] | None,
    sharp_enabled: bool,
) -> dict[str, Any]:
    _clear_symbol_env()
    os.environ["FUTURES_SYMBOL"] = symbol
    os.environ["FUTURES_BACKTEST_START"] = start
    os.environ["FUTURES_BACKTEST_END"] = end
    os.environ["FUTURES_BACKTEST_OUTPUT_DIR"] = str(out_root / symbol)
    os.environ["FUTURES_SHARP_EVENT_OVERLAY_ENABLED"] = "1" if sharp_enabled else "0"
    os.environ["FUTURES_SHARP_EVENT_CORE_SYMBOLS"] = ",".join(DEFAULT_FUTURES_SYMBOLS)

    config = FuturesBacktestConfig.from_env()
    config.start = parse_utc_datetime(start)
    config.end = parse_utc_datetime(end)
    live = FuturesConfig.from_env()
    client = MexcFuturesClient(live)
    provider = FuturesHistoricalDataProvider(client, cache_dir=config.cache_dir)
    engine = FuturesBacktestEngine(config, provider, client, calibration=calibration)
    equity_curve, trades = engine.run()
    report = build_report(equity_curve, trades, config.initial_balance)
    export_artifacts(config.output_dir, equity_curve, trades, report)
    sharp_trades = sum(1 for trade in trades if trade.get("sharp_event_overlay"))
    return {
        "symbol": symbol,
        "rank": 0,
        "core": symbol in DEFAULT_FUTURES_SYMBOLS,
        "trades": int(report.get("total_trades", 0) or 0),
        "sharp_event_trades": int(sharp_trades),
        "win_rate": float(report.get("win_rate", 0.0) or 0.0),
        "total_pnl": float(report.get("total_pnl", 0.0) or 0.0),
        "profit_factor": float(report.get("profit_factor", 0.0) or 0.0),
        "max_drawdown": float(report.get("max_drawdown", 0.0) or 0.0),
    }


def _fmt_pf(value: float) -> str:
    if value == float("inf") or value >= 999:
        return "inf"
    return f"{value:.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the intraday sharp-opportunity overlay across a top-N MEXC universe.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--top-n", type=int, default=75, help="Top MEXC crypto USDT perps to test; 50-100 recommended.")
    parser.add_argument("--out", default="backtest_output/sharp_event_overlay")
    parser.add_argument("--baseline-out", default="backtest_output/sharp_event_baseline")
    parser.add_argument("--calibration", default="calibration/multi_symbol_calibration.json")
    args = parser.parse_args()

    top_n = max(50, min(100, int(args.top_n)))
    out_root = Path(args.out)
    baseline_root = Path(args.baseline_out)
    out_root.mkdir(parents=True, exist_ok=True)
    baseline_root.mkdir(parents=True, exist_ok=True)

    live = FuturesConfig.from_env()
    client = MexcFuturesClient(live)
    tickers = client.get_all_tickers()
    details = client.get_all_contract_details()
    symbols = list(
        select_major_usdt_symbols(
            tickers,
            details,
            top_n=top_n,
            include_symbols=DEFAULT_FUTURES_SYMBOLS,
        )
    )
    print(f"Selected {len(symbols)} MEXC crypto-USDT futures symbols for sharp-overlay scan (top_n={top_n}).")
    print(",".join(symbols))

    calibration = None
    calibration_path = Path(resolve_repo_path(args.calibration))
    if calibration_path.exists():
        calibration = json.loads(calibration_path.read_text(encoding="utf-8"))

    print("\n# Baseline core run")
    baseline_rows: list[dict[str, Any]] = []
    for symbol in DEFAULT_FUTURES_SYMBOLS:
        try:
            row = _run_one(symbol=symbol, start=args.start, end=args.end, out_root=baseline_root, calibration=calibration, sharp_enabled=False)
            baseline_rows.append(row)
            print(f"{symbol:<12} trades={row['trades']:>3} pnl=${row['total_pnl']:+8.2f} wr={row['win_rate']*100:5.1f}% pf={_fmt_pf(row['profit_factor'])}")
        except Exception as exc:
            traceback.print_exc()
            baseline_rows.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}", "total_pnl": 0.0})

    print("\n# Sharp-event overlay run")
    overlay_rows: list[dict[str, Any]] = []
    for rank, symbol in enumerate(symbols, start=1):
        try:
            row = _run_one(symbol=symbol, start=args.start, end=args.end, out_root=out_root, calibration=calibration, sharp_enabled=True)
            row["rank"] = rank
            overlay_rows.append(row)
            print(
                f"{rank:>3}. {symbol:<16} trades={row['trades']:>3} event={row['sharp_event_trades']:>3} "
                f"pnl=${row['total_pnl']:+8.2f} wr={row['win_rate']*100:5.1f}% pf={_fmt_pf(row['profit_factor'])}"
            )
        except Exception as exc:
            traceback.print_exc()
            overlay_rows.append({"symbol": symbol, "rank": rank, "error": f"{type(exc).__name__}: {exc}", "total_pnl": 0.0})

    baseline_total = sum(float(row.get("total_pnl") or 0.0) for row in baseline_rows)
    print("\n# Aggregate comparison")
    print(f"Baseline core total: ${baseline_total:+.2f}")
    aggregate_rows = []
    checkpoints = sorted({50, 60, 75, 100, top_n})
    for count in checkpoints:
        if count > len(overlay_rows):
            continue
        subset = overlay_rows[:count]
        total = sum(float(row.get("total_pnl") or 0.0) for row in subset)
        event_trades = sum(int(row.get("sharp_event_trades") or 0) for row in subset)
        trades = sum(int(row.get("trades") or 0) for row in subset)
        aggregate = {
            "top_n": count,
            "total_pnl": total,
            "delta_vs_core_baseline": total - baseline_total,
            "trades": trades,
            "sharp_event_trades": event_trades,
        }
        aggregate_rows.append(aggregate)
        print(
            f"Top {count:<3} overlay total: ${total:+.2f} "
            f"delta=${total - baseline_total:+.2f} trades={trades} event_trades={event_trades}"
        )

    best = max(aggregate_rows, key=lambda row: row["total_pnl"], default=None)
    if best:
        print(f"Best tested breadth: top {best['top_n']} total=${best['total_pnl']:+.2f} delta=${best['delta_vs_core_baseline']:+.2f}")

    summary = {
        "start": args.start,
        "end": args.end,
        "selected_symbols": symbols,
        "baseline_rows": baseline_rows,
        "overlay_rows": overlay_rows,
        "aggregate_rows": aggregate_rows,
        "best_breadth": best,
    }
    (out_root / "sharp_event_overlay_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (baseline_root / "baseline_summary.json").write_text(json.dumps(baseline_rows, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
