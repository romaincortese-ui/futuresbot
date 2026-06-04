import os
import sys
import traceback

from futuresbot.config import DEFAULT_FUTURES_SYMBOLS

# Ensure logs flow to Railway/Docker stdout immediately rather than sitting in
# a block buffer until the container dies.
os.environ.setdefault("PYTHONUNBUFFERED", "1")

# ---------------------------------------------------------------------------
# Sprint 1 (FUTURES_BOT_INVESTMENT_REVIEW.md §7) — default ON for prod.
# Using ``setdefault`` so anything already set in the environment wins; operators
# can disable individual features by setting them to "0" in Railway.
# ---------------------------------------------------------------------------
os.environ.setdefault("USE_NAV_RISK_SIZING", "1")          # §2.1 NAV-anchored sizing
os.environ.setdefault("USE_COST_BUDGET_RR", "1")           # §2.2 R:R net of costs
os.environ.setdefault("USE_STRICT_RECV_WINDOW", "1")       # §2.4 recv_window 30 -> 5
os.environ.setdefault("USE_LIQ_BUFFER_GUARD", "1")         # §2.5 liquidation buffer
os.environ.setdefault("USE_HARD_LOSS_CAP_TIGHT", "1")      # §2.6 hard_loss_cap 0.75 -> 0.25
os.environ.setdefault("HARD_LOSS_CAP_TIGHT_PCT", "0.25")
os.environ.setdefault("FUTURES_DYNAMIC_LEVERAGE_ENABLED", "1")
os.environ.setdefault("FUTURES_DYNAMIC_LEVERAGE_MIN", "5")
os.environ.setdefault("FUTURES_DYNAMIC_LEVERAGE_MAX", "20")
os.environ.setdefault("FUTURES_DYNAMIC_LEVERAGE_MAX_MARGIN_LOSS_PCT", "0.25")
os.environ.setdefault("FUTURES_MAX_STOP_RISK_PCT_OF_MARGIN", "0.20")
os.environ.setdefault("FUTURES_MIN_ENTRY_MARGIN_USDT", "5.0")
os.environ.setdefault("FUTURES_OPPORTUNITY_MAX_LEVERAGE", "20")
os.environ.setdefault("FUTURES_DOWNTREND_MOMENTUM_PRIORITY_ENABLED", "1")
os.environ.setdefault("FUTURES_DOWNTREND_MOMENTUM_PRIORITY_SYMBOLS", "ZEC_USDT")
os.environ.setdefault("FUTURES_DOWNTREND_MOMENTUM_TREND_4H_MIN", "0.008")
# SIMPLE_TREND lane: trend-following short-circuit that ignores volume/impulse
# gates when ADX is strong and the EMA stack is aligned. Catches slow-bleed /
# slow-rally regimes the impulse and sharp-event lanes miss. Validated 30d
# backtest 2026-05-02..2026-06-01 beats baseline on PnL and drawdown.
os.environ.setdefault("FUTURES_SIMPLE_TREND_ENABLED", "1")
os.environ.setdefault("FUTURES_SIMPLE_TREND_ADX_MIN", "35")
os.environ.setdefault("FUTURES_SIMPLE_TREND_6H_MIN", "0.015")
os.environ.setdefault("USE_DRAWDOWN_KILL", "1")            # §2.7 30d/90d drawdown kill
os.environ.setdefault("USE_SESSION_LEVERAGE", "1")         # §2.8 session-aligned leverage
os.environ.setdefault("USE_FUTURES_PROFIT_LOCK", "1")      # live peak-profit + breakeven protection
os.environ.setdefault("FUTURES_PROFIT_LOCK_TRIGGER_PCT", "4.0")
os.environ.setdefault("FUTURES_PROFIT_LOCK_FLOOR_PCT", "2.0")
os.environ.setdefault("FUTURES_PROFIT_LOCK_PULLBACK_FRACTION", "0.20")
os.environ.setdefault("FUTURES_BREAKEVEN_ARM_PCT", "3.0")
os.environ.setdefault("FUTURES_BREAKEVEN_FLOOR_PCT", "0.5")
os.environ.setdefault("FUTURES_ADVERSE_PEAK_TRAIL_ENABLED", "1")
os.environ.setdefault("FUTURES_ADVERSE_PEAK_TRAIL_TRIGGER_PCT", "0.25")
os.environ.setdefault("FUTURES_ADVERSE_PEAK_TRAIL_GIVEBACK_PCT", "1.25")
os.environ.setdefault("FUTURES_ADVERSE_PEAK_TRAIL_PULLBACK_FRACTION", "0.45")
os.environ.setdefault("FUTURES_ADVERSE_PEAK_TRAIL_MAX_LOSS_PCT", "2.0")
os.environ.setdefault("FUTURES_ADVERSE_TRAIL_SIDEWAYS_ONLY", "1")
os.environ.setdefault("FUTURES_REGIME_TREND_GAP", "0.015")
os.environ.setdefault("FUTURES_REGIME_TREND_GAP_LOOKBACK_BARS", "1")
os.environ.setdefault("FUTURES_NO_PROGRESS_EXIT_ENABLED", "1")
os.environ.setdefault("FUTURES_NO_PROGRESS_EXIT_MINUTES", "60")
os.environ.setdefault("FUTURES_NO_PROGRESS_EXIT_MAX_FAVORABLE_PCT", "0.25")
os.environ.setdefault("FUTURES_NO_PROGRESS_EXIT_LOSS_PCT", "3.5")
os.environ.setdefault("FUTURES_NO_PROGRESS_EXIT_TIGHTEN_AFTER_MINUTES", "180")
os.environ.setdefault("FUTURES_NO_PROGRESS_EXIT_TIGHTENED_LOSS_PCT", "0.75")
os.environ.setdefault("USE_OPEN_POSITION_GUARD", "1")      # tight polling while a leveraged position is open
os.environ.setdefault("USE_FUTURES_FAIR_PRICE_WS", "1")    # stream fair price during open-position guard, REST fallback on stale data
os.environ.setdefault("FUTURES_FAIR_PRICE_WS_STALE_SECONDS", "5.0")
os.environ.setdefault("FUTURES_OPEN_POSITION_MONITOR_SECONDS", "1.0")

# ---------------------------------------------------------------------------
# Sprint 2 (FUTURES_BOT_INVESTMENT_REVIEW.md §7) — default ON for prod.
# ---------------------------------------------------------------------------
os.environ.setdefault("USE_FUNDING_AWARE_ENTRY", "1")      # §2.3 block entries 2min pre-funding unless receiving
os.environ.setdefault("USE_FUNDING_STOP_MULT", "1")        # §2.9 tighten crowded / widen counter stops
os.environ.setdefault("USE_REALISTIC_BACKTEST", "1")       # §3.1 funding + liquidation + leverage slippage in backtest

# ---------------------------------------------------------------------------
# Sprint 3 (FUTURES_BOT_INVESTMENT_REVIEW.md §7) — mixed defaults.
# §3.3 regime gate is ON (post-filter on coil-breakout signals). The
# remaining modules (mean_reversion strategy, maker_ladder execution,
# portfolio_var, walk_forward calibration gate, slippage_attribution) ship
# as tested pure modules; live wiring lands in a follow-up. They default
# OFF so the library remains behaviour-compatible.
# ---------------------------------------------------------------------------
os.environ.setdefault("USE_REGIME_CLASSIFIER", "1")        # §3.3 regime post-filter on entries
os.environ.setdefault("USE_MEAN_REVERSION", "1")           # §3.2 mean-reversion in CHOP
os.environ.setdefault("USE_MAKER_LADDER", "1")             # §3.5 maker-first execution
os.environ.setdefault("USE_PORTFOLIO_VAR", "1")            # §3.6 cross-symbol VaR cap
os.environ.setdefault("USE_WALK_FORWARD_GATE", "1")        # §3.4 walk-forward calibration gate
os.environ.setdefault("USE_SLIPPAGE_ATTRIBUTION", "1")     # §3.9 weekly slippage report

# ---------------------------------------------------------------------------
# P0 trend-conviction defaults (post 24h directional-correct-but-undersized
# review). These widen sizing, raise leverage on high-score entries, anchor SL
# beyond round-trip fees, and enable round-level signals on every symbol.
# Operators can disable any of these by setting them to "0" / empty in Railway.
# ---------------------------------------------------------------------------
os.environ.setdefault("FUTURES_FULL_BALANCE_SIZING_ENABLED", "1")
os.environ.setdefault("FUTURES_FULL_BALANCE_RISK_PCT", "1.00")
# Fresh PMT + mental-threshold strategy profile. Railway can still keep the
# whole strategy layer retired with an explicit FUTURES_STRATEGIES_RETIRED=1.
os.environ.setdefault("FUTURES_STRATEGY_MODE", "pmt_threshold")
os.environ.setdefault("FUTURES_STRATEGIES_RETIRED", "0")
os.environ.setdefault("FUTURES_RESUME_ON_BOOT", "1")
os.environ.setdefault("FUTURES_PMT_SYMBOLS", "BTC_USDT,ETH_USDT,SOL_USDT,BNB_USDT,SEI_USDT,ZEC_USDT")
os.environ.setdefault("FUTURES_PMT_MIN_SCORE", "95")
os.environ.setdefault("FUTURES_PMT_MIN_LEVERAGE", "15")
os.environ.setdefault("FUTURES_PMT_MAX_LEVERAGE", "25")
os.environ.setdefault("MEXC_PERP_DEFAULT_TAKER_FEE_RATE", "0.0008")
os.environ.setdefault("FUTURES_PMT_PROFIT_LOCK_TRIGGER_PCT", "20.0")
os.environ.setdefault("FUTURES_PMT_PROFIT_LOCK_GIVEBACK_PCT", "0.0")
os.environ.setdefault("FUTURES_PMT_PROFIT_LOCK_PULLBACK_FRACTION", "0.70")
os.environ.setdefault("FUTURES_PMT_PROFIT_LOCK_MIN_TP_PROGRESS", "0.0")
os.environ.setdefault("FUTURES_PMT_PROFIT_LOCK_EXIT_MIN_NET_PCT", "20.0")
os.environ.setdefault("FUTURES_PMT_TP_COOLDOWN_HOURS", "24")
os.environ.setdefault("FUTURES_LEVERAGE_MIN", "15")
os.environ.setdefault("FUTURES_LEVERAGE_MAX", "25")
os.environ.setdefault("FUTURES_ENTRY_MIN_SCORE", "70")
os.environ.setdefault("FUTURES_ENTRY_HIGH_SCORE", "85")
os.environ.setdefault("FUTURES_ENTRY_LEVERAGE_MIN", "15")
os.environ.setdefault("FUTURES_ENTRY_LEVERAGE_HIGH", "25")
os.environ.setdefault("FUTURES_SL_FEE_FLOOR_ENABLED", "1")
os.environ.setdefault("FUTURES_SL_FEE_FLOOR_PCT", "0.0060")
os.environ.setdefault("FUTURES_SL_FEE_FLOOR_MULT", "4.0")
os.environ.setdefault("FUTURES_SL_FEE_FLOOR_SLIPPAGE_BPS", "5.0")
os.environ.setdefault("FUTURES_ROUND_LEVEL_ENABLED", "1")
os.environ.setdefault("FUTURES_ROUND_LEVEL_SYMBOLS", "*")
os.environ.setdefault("FUTURES_PROFIT_LOCK_TRIGGER_PCT", "10.0")
os.environ.setdefault("FUTURES_PROFIT_LOCK_GIVEBACK_PCT", "1.0")
os.environ.setdefault("FUTURES_PROFIT_LOCK_FLOOR_PCT", "0.0")
# Mid-profit-lock tuning (2026-06-02): the previous defaults (trigger 3.0,
# pullback 0.35) chopped out a high-conviction ETH SHORT after a 5-min, +3.05%
# wiggle that immediately came back. Raise the trigger to 4.5% and loosen the
# pullback to 0.50, and require tp_progress >= 30% so it can't fire on a trade
# that has barely begun working.
os.environ.setdefault("FUTURES_MID_PROFIT_LOCK_TRIGGER_PCT", "4.5")
os.environ.setdefault("FUTURES_MID_PROFIT_LOCK_PULLBACK_FRACTION", "0.50")
os.environ.setdefault("FUTURES_MID_PROFIT_LOCK_FLOOR_PCT", "1.5")
os.environ.setdefault("FUTURES_MID_PROFIT_LOCK_MIN_TP_PROGRESS", "0.30")
# Keep MARGIN_LOSS_EXIT OFF — prior 30d backtest was catastrophic (-297 vs +27).
os.environ.setdefault("FUTURES_MARGIN_LOSS_EXIT_ENABLED", "0")

# Legacy Quarter 2 monitor-only probes. Funding observations are now published
# to Redis for the spot bot, so the old in-bot Telegram carry/basis alerts stay
# off unless an operator explicitly opts back in.
os.environ.setdefault("USE_FUNDING_CARRY_MONITOR", "0")    # §3.8 funding-delta-neutral carry alerts
os.environ.setdefault("USE_BASIS_TRADE_MONITOR", "0")      # §4.1 quarterly basis-trade alerts
os.environ.setdefault("USE_LIQUIDATION_CASCADE_MONITOR", "0")  # §3.7 needs Coinglass feed; off by default

# ---------------------------------------------------------------------------
# Production symbol list. Operators can override with the FUTURES_SYMBOLS env
# var on Railway; otherwise keep main.py in lockstep with futuresbot.config.
# ---------------------------------------------------------------------------
os.environ.setdefault("FUTURES_SYMBOLS", ",".join(DEFAULT_FUTURES_SYMBOLS))

try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

print("=== futuresbot main.py boot ===", flush=True)

try:
    from futuresbot.runtime import run_runtime
except Exception:
    print("=== IMPORT FAILED ===", flush=True)
    traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    raise


if __name__ == "__main__":
    try:
        run_runtime()
    except Exception:
        print("=== run_runtime CRASHED ===", flush=True)
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        raise
