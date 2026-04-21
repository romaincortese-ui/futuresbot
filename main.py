import os
import sys
import traceback

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
os.environ.setdefault("USE_HARD_LOSS_CAP_TIGHT", "1")      # §2.6 hard_loss_cap 0.75 -> 0.40
os.environ.setdefault("USE_DRAWDOWN_KILL", "1")            # §2.7 30d/90d drawdown kill
os.environ.setdefault("USE_SESSION_LEVERAGE", "1")         # §2.8 session-aligned leverage

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
os.environ.setdefault("USE_MEAN_REVERSION", "0")           # §3.2 mean-reversion in CHOP (wiring pending)
os.environ.setdefault("USE_MAKER_LADDER", "0")             # §3.5 maker-first execution (wiring pending)
os.environ.setdefault("USE_PORTFOLIO_VAR", "0")            # §3.6 cross-symbol VaR cap (wiring pending)
os.environ.setdefault("USE_WALK_FORWARD_GATE", "0")        # §3.4 walk-forward calibration gate (wiring pending)
os.environ.setdefault("USE_SLIPPAGE_ATTRIBUTION", "0")     # §3.9 weekly slippage report (wiring pending)

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
