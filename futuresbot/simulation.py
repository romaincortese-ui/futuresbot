"""What would this trial have paid on a bigger account?

The bot sizes every convex entry as a FRACTION of the balance — margin =
risk_pct x available x 100 / sl_margin_pct, then scaled by the regime multiplier.
Nothing in that chain refers to an absolute dollar amount.

So the answer is exact and it is one line: SCALE THE REAL RESULT. If the account
had started the trial at k times the balance, every position's margin, every
stake, every realised P&L and the equity path itself are k times larger. The
percentage return is unchanged.

THIS REPLACED A RECONSTRUCTION AND THE REPLACEMENT IS THE POINT. The first
version rebuilt the equity path from each trade's stamped risk fraction and R
multiple. That is strictly harder and strictly worse: it has to model trade
overlap (this book runs up to five slots, so simultaneous positions were each
sized off an equity that did not yet contain the others' P&L) and it has to model
committed margin (the sizing path stamps `equity_at_entry` from AVAILABLE
balance, not equity). Getting the first wrong read trial 15 at +20.94% against a
real +18.33%; fixing it and getting the second wrong read -8.3% the other way.
Scaling the real path has neither problem, because the real path already contains
both effects.

WHAT DOES NOT SCALE is the order book. A $165 account carries ~$50 of notional;
the same rule on $10,000 carries ~$3,000, against a measured median top-10 depth
of ~$20k in this band with names in the tail holding a few hundred. That is the
one place the linear answer stops being true, so `capacity_notional` prints it
rather than leaving the reader to assume linearity holds forever.

Scoped to the CURRENT trial by the caller (rows filtered on TRIAL_START), so it
resets itself whenever a new trial opens — no second ledger to drift out of sync
with the feature store, a failure this codebase has already paid for once.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

# The balances /simulation reports. Deliberately spanning the range where
# capacity starts to bind, so the table shows the effect rather than hiding it.
SIM_BALANCES: tuple[float, ...] = (1000.0, 2000.0, 5000.0, 10000.0)


def risk_fraction(row: Mapping[str, Any]) -> float:
    """Fraction of AVAILABLE balance this trade risked, from the row's own stamp.

    Not used for the simulation itself — scaling needs no per-trade detail — but
    reported so the reader can see what the trial actually risked, and used by
    callers that want the open positions' contribution.
    """
    try:
        pct = float(row.get("risk_pct_actual") or 0.0)
        if pct > 0:
            return pct / 100.0
    except (TypeError, ValueError):
        pass
    try:
        risk = float(row.get("risk_usdt") or 0.0)
        eq = float(row.get("equity_at_entry") or row.get("equity_at_open_usdt") or 0.0)
        if risk > 0 and eq > 0:
            return risk / eq
    except (TypeError, ValueError):
        pass
    try:
        margin = float(row.get("margin_used") or 0.0)
        slm = float(row.get("sl_margin_pct") or 0.0)
        eq = float(row.get("equity_at_entry") or row.get("equity_at_open_usdt") or 0.0)
        if margin > 0 and slm > 0 and eq > 0:
            return (margin * slm / 100.0) / eq
    except (TypeError, ValueError):
        pass
    return 0.0


def realised_pnl(rows: Sequence[Mapping[str, Any]]) -> float:
    total = 0.0
    for row in rows:
        try:
            total += float(row.get("pnl_usdt") or 0.0)
        except (TypeError, ValueError):
            continue
    return total


def trial_opening_equity(rows: Sequence[Mapping[str, Any]], *,
                         current_equity: float | None = None,
                         open_unrealised: float = 0.0) -> float:
    """What the account was worth when the trial opened.

    Preferred: today's equity minus everything the trial has made. Falls back to
    the last close's stamped equity minus the realised total, which is the same
    identity read from the store alone.
    """
    real = realised_pnl(rows)
    if current_equity and current_equity > 0:
        return float(current_equity) - real - float(open_unrealised)
    for row in reversed(rows):
        try:
            eq = float(row.get("equity_at_close_usdt") or 0.0)
        except (TypeError, ValueError):
            continue
        if eq > 0:
            return eq - real
    return 0.0


def simulate(rows: Sequence[Mapping[str, Any]], opening: float, *,
             actual_opening: float, open_unrealised: float = 0.0) -> dict[str, Any]:
    """This trial's result if the account had opened it at `opening`.

    Exact under fractional sizing: scale by opening / actual_opening. Realised and
    unrealised are kept apart because only the first is banked.
    """
    opening = float(opening)
    if actual_opening <= 0 or opening <= 0:
        return {"opening": opening, "realised": 0.0, "unrealised": 0.0,
                "equity": opening, "return_pct": 0.0, "scale": 0.0}
    k = opening / float(actual_opening)
    realised = realised_pnl(rows) * k
    unrealised = float(open_unrealised) * k
    equity = opening + realised + unrealised
    return {
        "opening": opening,
        "realised": realised,
        "unrealised": unrealised,
        "equity": equity,
        "return_pct": (equity / opening - 1.0) * 100.0,
        "scale": k,
    }


def capacity_notional(rows: Sequence[Mapping[str, Any]], opening: float, *,
                      actual_opening: float) -> dict[str, float]:
    """Position notional this trial would have carried at `opening`.

    Notional = margin x leverage, scaled by the balance ratio. This is the number
    that has to fit inside somebody else's order book, and it is the only part of
    the simulation that does NOT scale harmlessly.
    """
    if actual_opening <= 0:
        return {"median": 0.0, "max": 0.0, "n": 0}
    k = float(opening) / float(actual_opening)
    vals: list[float] = []
    for row in rows:
        try:
            margin = float(row.get("margin_used") or 0.0)
            lev = float(row.get("leverage") or 0.0)
        except (TypeError, ValueError):
            continue
        if margin <= 0 or lev <= 0:
            continue
        vals.append(margin * lev * k)
    if not vals:
        return {"median": 0.0, "max": 0.0, "n": 0}
    vals.sort()
    return {"median": vals[len(vals) // 2], "max": vals[-1], "n": len(vals)}
