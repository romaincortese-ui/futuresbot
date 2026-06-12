"""Partial profit bank at +1R for stop-first positions ("small win first").

Replay-calibrated rationale (177 real fills, 48h windows, 2026-06-10): the
deployed T5R/lock@4R design has the best expectancy (+0.77R net) but round-trips
46% of trades that reach +0.5R — the operator's explicit pain point. Banking
half the position at +1R keeps ~60% of the runner edge (~+0.46R est.) while
making the whole-trade worst case ~breakeven once banked: a small win is
guaranteed before the runner half chases +5R with the existing peak lock.

Pure decision logic — no I/O. The runtime executes the reduce-only close.
"""
from __future__ import annotations

import os
from typing import NamedTuple


def _env_float(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name)
        if raw is None or raw.strip() == "":
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def partial_bank_enabled() -> bool:
    return _env_bool("FUTURES_PMT_STOP_FIRST_PARTIAL_BANK_ENABLED", True)


class PartialBankDecision(NamedTuple):
    vol_to_close: int
    trigger_margin_pct: float


def partial_bank_decision(
    *,
    gross_pnl_pct: float | None,
    sl_margin_pct: float | None,
    contracts: int,
    already_banked: bool,
    trigger_r: float | None = None,
    bank_fraction: float | None = None,
) -> PartialBankDecision | None:
    """Return the reduce-only volume to bank, or None.

    Fires once per position, when gross margin P&L reaches ``trigger_r`` x 1R
    (1R = ``sl_margin_pct``, the stop distance in margin %). Requires at least
    2 contracts so a runner remains; never closes the full position.
    """
    if already_banked or not partial_bank_enabled():
        return None
    if gross_pnl_pct is None or sl_margin_pct is None or sl_margin_pct <= 0:
        return None
    if contracts < 2:
        return None
    trigger_r = trigger_r if trigger_r is not None else _env_float("FUTURES_PMT_STOP_FIRST_PARTIAL_BANK_TRIGGER_R", 1.0)
    fraction = bank_fraction if bank_fraction is not None else _env_float("FUTURES_PMT_STOP_FIRST_PARTIAL_BANK_FRACTION", 0.5)
    fraction = min(0.9, max(0.1, fraction))
    trigger_margin_pct = max(0.0, trigger_r) * float(sl_margin_pct)
    if trigger_margin_pct <= 0 or float(gross_pnl_pct) < trigger_margin_pct:
        return None
    vol = int(round(contracts * fraction))
    vol = max(1, min(contracts - 1, vol))
    return PartialBankDecision(vol_to_close=vol, trigger_margin_pct=trigger_margin_pct)


def breakeven_stop_price(entry_price: float, side: str, buffer_pct: float | None = None) -> float:
    """Runner stop after a bank: entry +/- a small buffer that covers the
    round-trip fee in price terms, so a breakeven-stopped runner still nets
    >= 0 for the whole trade (the banked rung stays profit)."""
    buf = buffer_pct if buffer_pct is not None else _env_float("FUTURES_PMT_BANK_BREAKEVEN_BUFFER_PCT", 0.15)
    buf = max(0.0, buf) / 100.0
    return entry_price * (1.0 + buf) if str(side).upper() == "LONG" else entry_price * (1.0 - buf)


def bank_protect_enabled() -> bool:
    """P2 feature flag: breakeven-after-bank + the +2R second rung."""
    return _env_bool("FUTURES_PMT_BANK_PROTECT_ENABLED", True)
