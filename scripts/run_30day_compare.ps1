# Futures bot 30-day backtest comparison.
# Use -ApplyAggressive to enable R1/R2/R3/R4 flags (default OFF).

param(
    [string]$Label = "baseline_30d",
    [string]$Start = "2026-04-14T00:00:00Z",
    [string]$End   = "2026-05-14T00:00:00Z",
    [switch]$ApplyAggressive,
    [switch]$ApplySimplified,
    [switch]$ApplyAggressiveV2,
    [switch]$FullBalance
)

$ErrorActionPreference = "Stop"
$py = "C:/Users/Rocot/AppData/Local/Python/pythoncore-3.14-64/python.exe"
$root = "C:\Users\Rocot\Downloads\futuresbot"

# Mirror live config
$env:PYTHONPATH = $root
$env:FUTURES_BACKTEST_START = $Start
$env:FUTURES_BACKTEST_END = $End
$env:FUTURES_BACKTEST_INITIAL_BALANCE = "300.0"
$env:FUTURES_BACKTEST_OUTPUT_DIR = "backtest_output_$Label"
$env:FUTURES_BACKTEST_CACHE_DIR = "backtest_cache"
$env:FUTURES_SYMBOLS = "BTC_USDT,SOL_USDT,BNB_USDT,SEI_USDT,ZEC_USDT"
$env:FUTURES_PAPER_TRADE = "true"

# Mirror prod symbol thresholds (NOT including SEI override in baseline).
$env:FUTURES_BTCUSDT_SCORE_THRESHOLD = "80"
$env:FUTURES_SEIUSDT_SCORE_THRESHOLD = "85"
$env:FUTURES_TAOUSDT_SCORE_THRESHOLD = "72"
$env:FUTURES_PEPEUSDT_SCORE_THRESHOLD = "82"
$env:FUTURES_SEIUSDT_LEVERAGE_MAX = "20"
$env:FUTURES_ETHUSDT_LEVERAGE_MAX = "8"
$env:FUTURES_PEPEUSDT_LEVERAGE_MAX = "10"
$env:FUTURES_MAJOR_THRESHOLD_ENABLED = "1"
$env:FUTURES_MAJOR_THRESHOLD_SYMBOLS = "BTC_USDT SOL_USDT ETH_USDT"
$env:FUTURES_BREAKAWAY_ENABLED = "1"
$env:FUTURES_BREAKAWAY_SYMBOLS = "BTC_USDT,ETH_USDT,PEPE_USDT,TAO_USDT,BCH_USDT,SEI_USDT"
$env:FUTURES_SHARP_EVENT_OVERLAY_ENABLED = "1"
$env:FUTURES_SHARP_EVENT_OVERLAY_TOP_N = "100"
$env:FUTURES_SHARP_EVENT_RISK_MULTIPLIER = "0.35"
$env:FUTURES_SHARP_EVENT_BYPASS_SYMBOL_CALIBRATION = "1"
$env:NAV_LEVERAGE_MIN = "20"
$env:NAV_LEVERAGE_MAX = "50"
$env:SESSION_ASIA_LEVERAGE_CAP = "20"
$env:SESSION_FULL_LEVERAGE_CAP = "50"
$env:USE_PORTFOLIO_VAR = "0"

# Aggressive flags (R1-R4).
if ($ApplyAggressive) {
    $env:FUTURES_SHARP_EVENT_RELAX_ENABLED = "true"
    $env:FUTURES_SHARP_EVENT_RELAX_MIN_SCORE = "85.0"
    $env:FUTURES_BTC_COIL_BREAKOUT_DISABLE_ENABLED = "true"
    $env:FUTURES_SEIUSDT_SCORE_THRESHOLD = "75.0"   # R3 override
    $env:FUTURES_TREND_CONTINUATION_SIZE_BOOST_ENABLED = "true"
    $env:FUTURES_TREND_CONTINUATION_SIZE_MULT = "1.5"
    $env:FUTURES_TREND_CONTINUATION_SIZE_CAP = "2.0"
} else {
    Remove-Item Env:FUTURES_SHARP_EVENT_RELAX_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:FUTURES_SHARP_EVENT_RELAX_MIN_SCORE -ErrorAction SilentlyContinue
    Remove-Item Env:FUTURES_BTC_COIL_BREAKOUT_DISABLE_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:FUTURES_TREND_CONTINUATION_SIZE_BOOST_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:FUTURES_TREND_CONTINUATION_SIZE_MULT -ErrorAction SilentlyContinue
    Remove-Item Env:FUTURES_TREND_CONTINUATION_SIZE_CAP -ErrorAction SilentlyContinue
}

# Simplified strategy whitelist (canonical 3-signal set).
if ($ApplySimplified) {
    $env:FUTURES_SIMPLIFIED_STRATEGY_ENABLED = "true"
} else {
    Remove-Item Env:FUTURES_SIMPLIFIED_STRATEGY_ENABLED -ErrorAction SilentlyContinue
}

# Aggressive V2 — audit-driven fixes + aggressive profit capture.
# Combines: earlier profit-lock (4%), earlier breakeven arm (3%), EMA-stack
# bypass when ADX>=40 and RSI extreme. Default OFF.
if ($ApplyAggressiveV2) {
    $env:FUTURES_PROFIT_LOCK_TRIGGER_PCT = "4.0"
    $env:FUTURES_PROFIT_LOCK_FLOOR_PCT = "2.0"
    $env:FUTURES_PROFIT_LOCK_PULLBACK_FRACTION = "0.35"
    $env:FUTURES_BREAKEVEN_ARM_PCT = "3.0"
    $env:FUTURES_BREAKEVEN_FLOOR_PCT = "0.5"
    $env:FUTURES_AGGRESSIVE_EMA_BYPASS_ENABLED = "true"
    $env:FUTURES_AGGRESSIVE_EMA_BYPASS_ADX_MIN = "40.0"
    $env:FUTURES_AGGRESSIVE_EMA_BYPASS_RSI_OB = "75.0"
    $env:FUTURES_AGGRESSIVE_EMA_BYPASS_RSI_OS = "25.0"
} else {
    Remove-Item Env:FUTURES_PROFIT_LOCK_TRIGGER_PCT -ErrorAction SilentlyContinue
    Remove-Item Env:FUTURES_PROFIT_LOCK_FLOOR_PCT -ErrorAction SilentlyContinue
    Remove-Item Env:FUTURES_PROFIT_LOCK_PULLBACK_FRACTION -ErrorAction SilentlyContinue
    Remove-Item Env:FUTURES_BREAKEVEN_ARM_PCT -ErrorAction SilentlyContinue
    Remove-Item Env:FUTURES_BREAKEVEN_FLOOR_PCT -ErrorAction SilentlyContinue
    Remove-Item Env:FUTURES_AGGRESSIVE_EMA_BYPASS_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:FUTURES_AGGRESSIVE_EMA_BYPASS_ADX_MIN -ErrorAction SilentlyContinue
    Remove-Item Env:FUTURES_AGGRESSIVE_EMA_BYPASS_RSI_OB -ErrorAction SilentlyContinue
    Remove-Item Env:FUTURES_AGGRESSIVE_EMA_BYPASS_RSI_OS -ErrorAction SilentlyContinue
}

# Full-balance allocation: every trade uses ~100% of available margin.
if ($FullBalance) {
    $env:FUTURES_FULL_BALANCE_SIZING_ENABLED = "true"
    $env:FUTURES_FULL_BALANCE_RISK_PCT = "1.00"
} else {
    Remove-Item Env:FUTURES_FULL_BALANCE_SIZING_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:FUTURES_FULL_BALANCE_RISK_PCT -ErrorAction SilentlyContinue
}

Push-Location $root
$out = Join-Path $root "backtest_30day_$Label.txt"
& $py run_backtest.py *>&1 | Tee-Object -FilePath $out
$exitCode = $LASTEXITCODE
Pop-Location

Write-Host "exit=$exitCode  output=$out  dir=$env:FUTURES_BACKTEST_OUTPUT_DIR"
