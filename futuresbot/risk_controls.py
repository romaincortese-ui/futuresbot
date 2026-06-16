"""Account-level risk controls — risk-based position sizing + regime size scaling.

Two pure, side-effect-free helpers the runtime wires into the PMT and wildcard
entry paths (both behind default-off flags):

1. risk_capped_contracts — cap a position so the stop (1R) loses at most
   FUTURES_MAX_TRADE_RISK_PCT of equity. Proven on the live 263-trade ledger:
   ~2-5% risk/trade is the growth-optimal band; the full-balance sizing that
   produced the BNB -$19.94 (1R ~= 19% of equity) sits in the ruin zone.

2. regime_size_multiplier — scale size CONTINUOUSLY by trend efficiency (full
   size in clean trends, floor in chop). Validated on the 2026-06-15/16 window:
   a hard efficiency *block* also kills good trend trades (the BTC 2nd-leg entry
   read eff 0.21), so we scale rather than block.
"""
from __future__ import annotations

from collections.abc import Sequence


def risk_capped_contracts(
    *,
    contracts: int,
    entry_price: float,
    sl_price: float,
    contract_size: float,
    equity_usdt: float,
    max_risk_pct: float,
) -> int:
    """Largest position whose 1R loss <= max_risk_pct% of equity.

    1R loss ($) = contracts * contract_size * |entry - sl|. Returns 0 when even
    the minimum size would exceed the budget (caller then skips the trade —
    correct: never take a position you cannot size within risk). Returns the
    input unchanged when inputs are degenerate (fail-open)."""
    if max_risk_pct <= 0 or equity_usdt <= 0 or contract_size <= 0:
        return int(contracts)
    stop_distance = abs(float(entry_price) - float(sl_price))
    if stop_distance <= 0:
        return int(contracts)
    risk_per_contract = contract_size * stop_distance
    max_risk_usdt = (max_risk_pct / 100.0) * equity_usdt
    cap = int(max_risk_usdt / risk_per_contract)
    return max(0, min(int(contracts), cap))


def trend_efficiency(closes: Sequence[float], window: int = 24) -> float:
    """Kaufman efficiency ratio over the last `window` bars: net directional
    move / sum of absolute bar moves. ~1.0 = clean one-way trend, ~0 = chop."""
    cs = [float(x) for x in closes][-(window + 1):]
    if len(cs) < 2:
        return 0.0
    net = abs(cs[-1] - cs[0])
    churn = sum(abs(cs[i] - cs[i - 1]) for i in range(1, len(cs)))
    return net / churn if churn > 0 else 0.0


def regime_size_multiplier(
    efficiency: float,
    *,
    lo: float = 0.20,
    hi: float = 0.45,
    floor_mult: float = 0.25,
) -> float:
    """Continuous size scaler in [floor_mult, 1.0]: full size when efficiency
    >= hi (clean trend), floor_mult when <= lo (chop), linear between. Never a
    hard block — a trend trade with a transiently low reading is sized down, not
    forfeited."""
    floor_mult = max(0.0, min(1.0, floor_mult))
    if hi <= lo:
        return 1.0
    if efficiency >= hi:
        return 1.0
    if efficiency <= lo:
        return floor_mult
    frac = (efficiency - lo) / (hi - lo)
    return floor_mult + frac * (1.0 - floor_mult)
