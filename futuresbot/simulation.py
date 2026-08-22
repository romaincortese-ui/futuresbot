"""What would this trial have paid on a bigger account?

The bot sizes every convex entry as a FRACTION of equity — margin = risk_pct x
available x 100 / sl_margin_pct, then scaled by the regime multiplier — so the
per-trade risk is a percentage, not a dollar amount. Two consequences, and they
are the whole basis of this module:

1. The R outcome of a trade is INDEPENDENT of account size. Same entry, same
   stop, same target, same price path.
2. Therefore the equity CURVE in percentage terms is identical at any starting
   balance, and a simulated account is obtained by compounding the real trial's
   own per-trade risk fractions and R multiples from a different starting point.

That makes the simulation exact rather than an estimate — under one assumption
that stops being true as the balance grows, which is why `capacity_notional`
exists below. A $165 account trading 2.4% risk on a 15% stop carries roughly $50
of notional; the same rule on $10,000 carries ~$3,000, and the measured median
top-10 book depth in the wildcard band is about $20,000, with names in the tail
holding a few hundred dollars. Beyond some balance the fills stop being free and
the simulated P&L becomes optimistic. The report says so with numbers rather than
leaving the reader to assume linearity holds forever.

Scoped to the CURRENT trial by the caller (rows filtered on TRIAL_START), so it
resets itself whenever a new trial opens — no separate ledger to drift out of
sync with the feature store, which this codebase has been bitten by before.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

# The balances the /simulation command reports. Deliberately spanning the range
# where capacity starts to bind, so the table shows the effect rather than
# hiding it.
SIM_BALANCES: tuple[float, ...] = (1000.0, 2000.0, 5000.0, 10000.0)


def risk_fraction(row: Mapping[str, Any]) -> float:
    """Fraction of equity this trade actually risked, from the row's own stamp.

    `risk_pct_actual` is written by the sizing path at entry and already includes
    the regime multiplier, so it reproduces the real allocation rather than a
    reconstruction of it. Falls back to risk_usdt/equity_at_entry, then to the
    designed margin geometry, and finally to 0.0 — a row that cannot be priced
    contributes nothing instead of silently contributing a guess.
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


def simulate(rows: Sequence[Mapping[str, Any]], opening: float,
             open_positions: Iterable[tuple[float, float]] = ()) -> dict[str, Any]:
    """Compound `opening` through this trial's closed trades, then mark the open ones.

    `open_positions` is an iterable of (risk_fraction, unrealised_r) so the
    figure matches what the account actually shows, which includes open P&L.
    Realised and unrealised are reported separately because only the first is
    banked.
    """
    # SIZE AT ENTRY, CREDIT AT EXIT. Compounding the rows in close order looked
    # right and was not: this book runs up to five slots at once, so overlapping
    # trades were each sized off an equity that did NOT yet contain the others'
    # P&L. Sequential compounding sizes trade N off gains that had not landed
    # when it opened, and on trial 15 that read +20.94% against a real +18.33%.
    # Each row carries hold_hours, so the entry time is recoverable and the real
    # ordering can be reproduced.
    # AND THE FRACTION IS OF AVAILABLE, NOT EQUITY. The sizing path stamps
    # `equity_at_entry` from `available_balance` — equity MINUS the margin already
    # committed to open positions. Treating it as a fraction of total equity
    # over-sizes every entry made while the book was busy, which read trial 15 at
    # +20.32% against a real +18.33%. So the walk tracks committed margin too and
    # sizes off what was actually free.
    events: list[tuple[float, int, int, float, float, float]] = []
    for seq, row in enumerate(rows):
        frac = risk_fraction(row)
        if frac <= 0:
            continue
        try:
            r = float(row.get("r_multiple") or 0.0)
            close_ts = float(row.get("ts") or 0.0)
            hold_s = float(row.get("hold_hours") or 0.0) * 3600.0
            margin = float(row.get("margin_used") or 0.0)
            avail = float(row.get("equity_at_entry") or row.get("equity_at_open_usdt") or 0.0)
        except (TypeError, ValueError):
            continue
        m_frac = (margin / avail) if (margin > 0 and avail > 0) else 0.0
        events.append((close_ts - hold_s, 0, seq, frac, r, m_frac))   # 0 = open
        events.append((close_ts, 1, seq, frac, r, m_frac))            # 1 = close
    # Closes settle before opens at the same instant, so freed capital is
    # available to the next entry exactly as it is live.
    events.sort(key=lambda e: (e[0], -e[1]))

    balance = float(opening)
    realised = 0.0
    committed = 0.0
    staked: dict[int, tuple[float, float]] = {}
    for _ts, kind, sid, frac, r, m_frac in events:
        if kind == 0:
            free = max(0.0, balance - committed)
            stake = free * frac
            margin = free * m_frac
            committed += margin
            staked[sid] = (stake, margin)
        else:
            stake, margin = staked.pop(sid, (max(0.0, balance - committed) * frac, 0.0))
            committed = max(0.0, committed - margin)
            pnl = stake * r
            balance += pnl
            realised += pnl
    unrealised = sum(balance * frac * r for frac, r in open_positions if frac > 0)
    return {
        "opening": float(opening),
        "realised": realised,
        "unrealised": unrealised,
        "equity": balance + unrealised,
        "return_pct": ((balance + unrealised) / opening - 1.0) * 100.0 if opening else 0.0,
    }


def capacity_notional(rows: Sequence[Mapping[str, Any]], opening: float) -> dict[str, float]:
    """Position notional this trial would have carried at `opening`.

    Notional = margin x leverage, scaled by the balance ratio. This is the number
    that has to fit inside somebody else's order book, and it is the only part of
    the simulation that does NOT scale harmlessly.
    """
    vals: list[float] = []
    for row in rows:
        try:
            margin = float(row.get("margin_used") or 0.0)
            lev = float(row.get("leverage") or 0.0)
            eq = float(row.get("equity_at_entry") or row.get("equity_at_open_usdt") or 0.0)
        except (TypeError, ValueError):
            continue
        if margin <= 0 or lev <= 0 or eq <= 0:
            continue
        vals.append(margin * lev * (float(opening) / eq))
    if not vals:
        return {"median": 0.0, "max": 0.0, "n": 0}
    vals.sort()
    return {"median": vals[len(vals) // 2], "max": vals[-1], "n": len(vals)}
