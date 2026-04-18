# BTC Futures Bot

Standalone BTC-only MEXC futures bot repository.

This repo is intentionally isolated from the spot bot:

- separate margin budget
- separate calibration and daily review files
- separate runtime state and status files
- separate backtest process
- separate Railway runtime and cron services

## Strategy

The strategy only trades BTC perpetual futures and only when the setup is strong enough in one direction.

- Uses 15m candles for consolidation and breakout context
- Uses 1h resampled structure for higher-timeframe trend strength
- Can open both long and short
- Dynamically sizes leverage between x20 and x50 from setup certainty
- Rejects setups where the stop distance would violate the configured hard loss cap on margin
- Uses full-size exits only
- Lets exchange TP/SL manage the hard exit path
- Adds an hourly early-take-profit check when price is already very close to TP

## Environment

Important variables:

- `FUTURES_PAPER_TRADE=true`
- `FUTURES_SYMBOL=BTC_USDT`
- `FUTURES_MARGIN_BUDGET_USDT=75`
- `FUTURES_TELEGRAM_TOKEN=...`
- `FUTURES_TELEGRAM_CHAT_ID=...`
- `FUTURES_HEARTBEAT_SECONDS=3600`
- `FUTURES_SCORE_THRESHOLD=56`
- `FUTURES_LEVERAGE_MIN=20`
- `FUTURES_LEVERAGE_MAX=50`
- `FUTURES_HARD_LOSS_CAP_PCT=0.75`
- `FUTURES_ADX_FLOOR=18`
- `FUTURES_TREND_24H_FLOOR=0.009`
- `FUTURES_TREND_6H_FLOOR=0.003`
- `FUTURES_VOLUME_RATIO_FLOOR=1.0`
- `FUTURES_MIN_REWARD_RISK=1.15`
- `FUTURES_CALIBRATION_MIN_TOTAL_TRADES=4`
- `FUTURES_CALIBRATION_FILE=backtest_output/calibration.json`
- `FUTURES_DAILY_REVIEW_FILE=backtest_output/daily_review.json`
- `FUTURES_RUNTIME_STATE_FILE=futures_runtime_state.json`
- `FUTURES_STATUS_FILE=futures_runtime_status.json`

The project reuses `MEXC_API_KEY`, `MEXC_API_SECRET`, `REDIS_URL`, and `ANTHROPIC_API_KEY` when present.

If you do not set `FUTURES_TELEGRAM_TOKEN` or `FUTURES_TELEGRAM_CHAT_ID`, the runtime falls back to `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`.

## Run Live Runtime

```bash
python main.py
```

The runtime now sends Telegram notifications for:

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

## Railway

Recommended Railway setup uses two services in the same project:

1. Runtime service
	- config file: `railway.toml`
	- start command: `python main.py`
	- persistent volume mounted at `/data`
	- variables:
	  - `FUTURES_RUNTIME_STATE_FILE=/data/futures_runtime_state.json`
	  - `FUTURES_STATUS_FILE=/data/futures_runtime_status.json`
	  - `FUTURES_CALIBRATION_FILE=/data/calibration.json`
	  - `FUTURES_DAILY_REVIEW_FILE=/data/daily_review.json`

2. Calibration cron service
	- config file: `railway.calibration.toml`
	- start command: `python run_daily_calibration.py`
	- same `/data` volume mounted
	- same `FUTURES_CALIBRATION_FILE` and `FUTURES_DAILY_REVIEW_FILE` values

This keeps the live runtime and the calibration cron reading and writing the same files.

## Tests

```bash
pytest tests
```