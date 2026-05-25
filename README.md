# MEXC Futures Bot

Standalone MEXC perpetual-futures bot repository deployed independently from the spot bot.

It is intentionally isolated from the live spot runtime:

- separate margin budget
- separate calibration and daily review files
- separate runtime state and status files
- separate backtest process
- separate Railway runtime and cron services

## Strategy

The production universe was pruned after the 2026-05-05 tuning pass and now scans 5 perpetual pairs:

```text
BTC_USDT, SOL_USDT, BNB_USDT, SEI_USDT, ZEC_USDT
```

The wider candidate pool remains BTC, ETH, SOL, PEPE, TAO, BNB, BCH, SEI, LINK, and ZEC. ETH, PEPE, TAO, BCH, and LINK are currently symbol-blocked by the packaged calibration until a future replay shows a durable edge again.

The 2026-05-17 30-day production-calibrated replay kept the five-symbol universe but pruned the losing BTC coil/hold lanes and BNB coil breakout lane. It also adds modest risk multipliers to the strongest current lanes: SOL pressure break long, BNB trend-continuation long, and ZEC impulse/level continuation.

Each pair uses the shared futures scorer with a dedicated profile for volatility, funding, score threshold, reward/risk, and leverage cap. A packaged signal-lane calibration in `calibration/multi_symbol_calibration.json` blocks symbol/signal combinations that were persistently negative in the latest 60-day replay, so the bot can scan broadly without treating every pair like BTC.

- Uses 15m candles for consolidation and breakout context
- Uses 1h resampled structure for higher-timeframe trend strength
- Can open both long and short
- Dynamically sizes leverage from x5 to x20 using setup score, stop distance, symbol, signal family, and the hard margin-loss cap
- Rejects setups where the stop distance would violate the configured hard loss cap on margin
- Uses full-size exits only
- Lets exchange TP/SL manage the hard exit path
- Adds an hourly early-take-profit check when price is already very close to TP
- Applies per-symbol profiles and calibration blocks before entry

## Environment

Important variables:

- `FUTURES_PAPER_TRADE=true`
- `FUTURES_SYMBOLS=BTC_USDT,SOL_USDT,BNB_USDT,SEI_USDT,ZEC_USDT`
- `FUTURES_SYMBOL=BTC_USDT` for a one-symbol run or single-symbol backtest
- `FUTURES_MARGIN_BUDGET_USDT=75`
- `FUTURES_TELEGRAM_TOKEN=...`
- `FUTURES_TELEGRAM_CHAT_ID=...`
- `FUTURES_HEARTBEAT_SECONDS=21600`
- `FUTURES_SCORE_THRESHOLD=56`
- Default symbol profiles keep ZEC at a 65 score floor and block weak Apr-May 2026 lanes (`BNB_USDT:COIL_BREAKOUT_LONG`, `SOL_USDT:COIL_BREAKOUT_LONG/TREND_CONTINUATION_LONG`, `BTC_USDT:MAJOR_THRESHOLD_SHORT`) unless overridden with per-symbol `FUTURES_<SYMBOL>_DISABLED_ENTRY_SIGNALS` or score env vars.
- `FUTURES_DYNAMIC_LEVERAGE_ENABLED=1`
- `FUTURES_DYNAMIC_LEVERAGE_MIN=5`
- `FUTURES_DYNAMIC_LEVERAGE_MAX=20`
- `FUTURES_DYNAMIC_LEVERAGE_MAX_MARGIN_LOSS_PCT=0.25`
- `FUTURES_HARD_LOSS_CAP_PCT=0.75`
- `FUTURES_ADX_FLOOR=18`
- `FUTURES_TREND_24H_FLOOR=0.009`
- `FUTURES_TREND_6H_FLOOR=0.003`
- `FUTURES_VOLUME_RATIO_FLOOR=1.0`
- `FUTURES_MIN_REWARD_RISK=1.15`
- `FUTURES_CALIBRATION_MIN_TOTAL_TRADES=15`
- `FUTURES_CALIBRATION_FILE=calibration/multi_symbol_calibration.json`
- `FUTURES_CALIBRATION_OUTPUT_FILE=backtest_output/calibration.json`
- `FUTURES_DAILY_REVIEW_FILE=backtest_output/daily_review.json`
- `FUTURES_RUNTIME_STATE_FILE=futures_runtime_state.json`
- `FUTURES_STATUS_FILE=futures_runtime_status.json`
- `MEXC_PERP_DEFAULT_TAKER_FEE_RATE=0.0006` keeps the live cost model on the conservative 6 bp taker fee unless a lower account tier is verified.
- `MEXC_PERP_FEE_TIER_VERIFIED=1` allows the bot to trust lower MEXC/API taker fee rates; set it only after checking real account trade fees.
- `MAKER_LADDER_TAKER_FALLBACK_MIN_SCORE=0` and `MAKER_LADDER_TAKER_FALLBACK_MIN_CERTAINTY=0` are optional maker-or-skip guards. Raising either value skips the market-order fallback after an unfilled maker ladder when the setup is below that threshold.
- `FUTURES_ADVERSE_PEAK_TRAIL_ENABLED=1` arms an early adverse trail after a tiny favorable peak. Defaults arm at `FUTURES_ADVERSE_PEAK_TRAIL_TRIGGER_PCT=0.25` and close after roughly `FUTURES_ADVERSE_PEAK_TRAIL_GIVEBACK_PCT=1.25` percentage points of margin giveback, capped by `FUTURES_ADVERSE_PEAK_TRAIL_MAX_LOSS_PCT=2.0`.
- `FUTURES_NO_PROGRESS_EXIT_ENABLED=1` cuts trades that never show a small favorable spark. Defaults wait `FUTURES_NO_PROGRESS_EXIT_MINUTES=60`, require peak gross margin P&L to stay below `FUTURES_NO_PROGRESS_EXIT_MAX_FAVORABLE_PCT=0.25`, then close only if loss breaches a threshold that tightens from `FUTURES_NO_PROGRESS_EXIT_LOSS_PCT=3.5` to `FUTURES_NO_PROGRESS_EXIT_TIGHTENED_LOSS_PCT=0.75` by `FUTURES_NO_PROGRESS_EXIT_TIGHTEN_AFTER_MINUTES=180`.
- `USE_FUTURES_PROFIT_LOCK=1` applies peak-profit tracking and pullback exits to every open futures position.
- `USE_OPEN_POSITION_GUARD=1` monitors MEXC fair price every `FUTURES_OPEN_POSITION_MONITOR_SECONDS` while a futures trade is open, so peak protection, breakeven protection, liquidation-buffer exits, and trailing exits do not wait for the next full scan cycle.
- `USE_FUTURES_FAIR_PRICE_WS=1` subscribes to MEXC futures `sub.fair.price` streams for open positions and falls back to REST when the stream is stale or unavailable.

The project reuses `MEXC_API_KEY`, `MEXC_API_SECRET`, `REDIS_URL`, and `ANTHROPIC_API_KEY` when present.

Crypto event state is consumed from Redis key `mexc:crypto_event_intelligence`, normally published by the `mexc-bot-v2` event-intelligence service. Keep `FUTURES_CRYPTO_EVENT_OVERLAY_ENABLED=true` and `REDIS_URL` set in the runtime service to use news, headline-risk, stablecoin-flow, and depeg overlays. Missing or stale state fails open, so the producer service should be treated as a shared dependency rather than a nice-to-have feed.

Backtests can replay event state with `FUTURES_BACKTEST_CRYPTO_EVENT_STATE_FILE`. The file may contain one state object or a `timeline`/`states` list with `from`/`until` windows and nested `state` payloads, letting historical news/event datasets exercise the same threshold, score, sizing, leverage, and block logic used live.

Opportunity bucket sizing is available with `FUTURES_OPPORTUNITY_BUCKET_SIZING_ENABLED=true`. It maps the existing technical/event score to a 0-10 opportunity score, skips scores 0-5, uses 50% of available balance for scores 6-7, 75% for scores 8-9, and 100% for score 10. In that mode `FUTURES_OPPORTUNITY_MAX_LEVERAGE` defaults to `20`, `max_concurrent_positions` is forced to one, and `USE_NAV_RISK_SIZING=1` caps contracts by `FUTURES_OPPORTUNITY_NAV_RISK_PCT` of equity before the bucket margin is spent. Dynamic leverage is still risk-capped first: score-10 setups can only reach high leverage when the stop is tight enough, the symbol/signal caps allow it, and `stop_distance_pct × leverage` stays under `FUTURES_DYNAMIC_LEVERAGE_MAX_MARGIN_LOSS_PCT`. Sharp-event risk multipliers reduce this NAV risk budget as well as available margin.

If you do not set `FUTURES_TELEGRAM_TOKEN` or `FUTURES_TELEGRAM_CHAT_ID`, the runtime falls back to `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`.

## Run Live Runtime

```bash
python main.py
```

The runtime sends Telegram notifications for:

- startup
- hourly heartbeat/status
- new position opened
- position closed
- loop errors with cooldown protection

Supported Telegram commands:

- `/status`
- `/pnl`
- `/logs`
- `/pause`
- `/resume`
- `/close`
- `/help`

## Run 60-Day Backtest

```bash
python run_backtest.py
```

Rolling-window runs default to 60 days. You can override the window with:

- `FUTURES_BACKTEST_START`
- `FUTURES_BACKTEST_END`
- `FUTURES_BACKTEST_ROLLING_DAYS`

## Run Daily Calibration + AI Review

```bash
python run_daily_calibration.py
```

This writes:

- `backtest_output/summary.json`
- `backtest_output/calibration.json`
- `backtest_output/daily_review.json`

If Redis is configured, it also publishes the calibration and review payloads for the runtime to consume on the next loop.

## Run Multi-Symbol Replay

```powershell
Set-Location c:/Users/Rocot/Downloads/futuresbot
$env:PYTHONPATH=(Get-Location).Path
c:/Users/Rocot/Downloads/mexc-bot2/.venv/Scripts/python.exe tools/run_multi_symbol_backtest.py --start 2026-03-02 --end 2026-05-01 --mode both
```

Use `USE_REALISTIC_BACKTEST=1`, `REALISTIC_FUNDING_RATE_8H`, `REALISTIC_SLIPPAGE_BPS_PER_LEV`, and `REALISTIC_EXIT_SLIP_MULT` to include conservative funding and slippage assumptions.

## Railway

Recommended Railway setup uses two services in the same project:

1. Runtime service
   - config file: `railway.toml`
   - start command: `python main.py`
   - persistent volume mounted at `/data`
   - variables:
     - `FUTURES_RUNTIME_STATE_FILE=/data/futures_runtime_state.json`
     - `FUTURES_STATUS_FILE=/data/futures_runtime_status.json`
     - optional `FUTURES_CALIBRATION_FILE=/data/calibration.json` if the calibration cron publishes a shared file
     - optional `FUTURES_DAILY_REVIEW_FILE=/data/daily_review.json`

2. Calibration cron service
   - config file: `railway.calibration.toml`
   - start command: `python run_daily_calibration.py`
   - same `/data` volume mounted
   - optional `FUTURES_CALIBRATION_OUTPUT_FILE=/data/calibration.json` and `FUTURES_DAILY_REVIEW_FILE=/data/daily_review.json`

Without a shared file override, the live runtime falls back to the packaged `calibration/multi_symbol_calibration.json` while generated calibration writes to `backtest_output/calibration.json`.

## Tests

```bash
pytest tests
```