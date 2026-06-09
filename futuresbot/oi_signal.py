"""Open-interest vs price continuation signal (crypto perps).

The single most informative continuation tell in perps: does a price move have
*new money* behind it, or is it position-unwinding that will snap back?

  price moving in our favour + OI RISING  -> new positions fuel the move
                                             = continuation likely (CONFIRMED)
  price moving in our favour + OI FALLING  -> move is short-covering / longs
                                             closing = no new demand = fakeout /
                                             exhaustion risk (DIVERGENT)
  otherwise (OI or move ~flat)             -> no read (NEUTRAL)

Pure function, no I/O. `price_move_pct` is signed toward the trade's intended
direction (favourable = positive). OI history is supplied by the caller (the
sampler), so this stays a pure, testable rule. score_adj is the eventual
scoring contribution — applied only AFTER the forward lift study proves edge;
until then it is logged in shadow mode and does not affect entries.
"""
from __future__ import annotations

from typing import NamedTuple


class OISignal(NamedTuple):
    state: str          # CONFIRMED | DIVERGENT | NEUTRAL
    score_adj: float    # eventual score contribution (shadow until validated)
    oi_change_pct: float | None


def oi_price_confirmation(
    oi_change_pct: float | None,
    price_move_pct: float | None,
    *,
    min_oi_change: float = 0.5,
    min_price_move: float = 0.1,
    confirm_bonus: float = 6.0,
    diverge_penalty: float = 8.0,
) -> OISignal:
    """Classify OI-vs-price for a candidate. Fail open (NEUTRAL) on missing data."""
    if oi_change_pct is None or price_move_pct is None:
        return OISignal("NEUTRAL", 0.0, oi_change_pct)
    # Only judges continuation of a favourable move; flat tape = no read.
    if price_move_pct < min_price_move:
        return OISignal("NEUTRAL", 0.0, oi_change_pct)
    if oi_change_pct >= min_oi_change:
        return OISignal("CONFIRMED", +abs(confirm_bonus), oi_change_pct)
    if oi_change_pct <= -min_oi_change:
        return OISignal("DIVERGENT", -abs(diverge_penalty), oi_change_pct)
    return OISignal("NEUTRAL", 0.0, oi_change_pct)


def pct_change(now: float | None, prev: float | None) -> float | None:
    if now is None or prev is None or prev == 0:
        return None
    return (now / prev - 1.0) * 100.0
