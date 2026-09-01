"""The slot book and sizing model, as the LIVE bot actually runs them.

Every replay in this repo shared three fidelity gaps, found 2026-09-01 by
comparing replay fill counts against the live shadow ledger. This module is the
corrected book; tools should call `take()` instead of hand-rolling a slot loop.

GAP 1 - SIZING OFF FULL EQUITY. Every tool computed risk as
`risk_pct * equity` for every fill. Live computes margin from AVAILABLE balance
(runtime.py `_entry_margin`), which shrinks as slots fill: with three positions
holding ~15% of margin each, the fourth entry sizes off ~55% of the base and the
fifth off ~40%. The old model therefore overstated the value of every marginal
slot - which is exactly the question pit_slots.py was asked. FIXED here by
tracking committed margin and releasing it at exit.

GAP 2 - THE CALM FILTER WAS MISSING. `calm_ratio >= FUTURES_WILDCARD_MAX_CALM_RATIO`
is applied live in runtime.py AFTER the candidate list, not inside
detect_wildcard_signal - so no replay ever applied it. Live refuses ~13 signals a
fortnight this way, and they resolve at -0.472R, so the replay was scoring trades
live would decline. FIXED here.

GAP 3 - FILL-RATE INFLATION, ~2.3x. The old book refilled a freed slot on the
very next bar from a dense candidate stream. Live scans every
FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS (900s) and opens AT MOST ONE position per
pass. Measured over 12 days: replay 5.92 wildcard fills/day against live's 2.58.
FIXED here by bucketing candidates into scan windows and taking one per window.

NOT FIXED - THE EXTERNAL GATE. Vetoing a signal needs a point-in-time answer from
Bybit/OKX that cannot be reconstructed historically. Its direction is known and
CONSERVATIVE: live refuses at -0.565R over 24 rows, so a replay that includes
those trades scores LOWER than the filtered live population would. Leaving it out
biases results against any change, which is the safe direction, but it means
absolute totals still are not live-comparable.

READ-ONLY helper. No I/O.
"""
from __future__ import annotations

from typing import Any, Callable


def take(cands: list[dict[str, Any]], *, slots: int, equity: float, risk_pct: float,
         sl_margin_pct: float = 20.0, scan_s: float = 900.0,
         one_per_scan: bool = True, calm_max: float = 0.75,
         cooldown_s: float = 0.0,
         exclude: Callable[[dict], bool] | None = None) -> list[dict[str, Any]]:
    """Walk time-ordered candidates through the live slot book and sizing.

    Each candidate needs: ts, sym, exit_ts, net (in R). Optional: calm_ratio.
    cooldown_s freezes a symbol for that long after one of its trades exits.
    Returns the taken fills, each stamped with:
        risk_usdt  the dollar risk this fill ACTUALLY carried, off available margin
        usd        net R x risk_usdt, the fill's dollar result
        avail_frac available margin as a fraction of equity at entry
    """
    occupied: list[tuple[float, float]] = []      # (exit_ts, margin_committed)
    per: dict[str, list[float]] = {}
    frozen: dict[str, float] = {}                 # symbol -> cooldown expiry
    taken: list[dict[str, Any]] = []
    last_scan = -1.0

    for x in cands:
        ts = float(x["ts"])
        if exclude is not None and exclude(x):
            continue
        # GAP 2: the calm-shock filter, applied where live applies it
        cr = x.get("calm_ratio")
        if calm_max > 0 and cr is not None and float(cr) >= calm_max:
            continue
        # GAP 3: live evaluates once per scan window and opens at most one
        if one_per_scan and scan_s > 0:
            bucket = ts // scan_s
            if bucket == last_scan:
                continue
        occupied[:] = [q for q in occupied if q[0] > ts]
        per[x["sym"]] = [q for q in per.get(x["sym"], []) if q > ts]
        # per-symbol freeze after a prior exit, if one is configured
        if cooldown_s > 0 and frozen.get(x["sym"], 0.0) > ts:
            continue
        if per[x["sym"]] or len(occupied) >= slots:
            continue
        # GAP 1: size off AVAILABLE margin, not full equity
        committed = sum(m for _, m in occupied)
        avail = max(0.0, equity - committed)
        if avail <= 0:
            continue
        risk_usdt = risk_pct * avail
        margin = risk_usdt * 100.0 / sl_margin_pct if sl_margin_pct > 0 else risk_usdt
        margin = min(margin, avail)
        occupied.append((float(x["exit_ts"]), margin))
        per[x["sym"]].append(float(x["exit_ts"]))
        if one_per_scan and scan_s > 0:
            last_scan = ts // scan_s
        if cooldown_s > 0:
            frozen[x["sym"]] = float(x["exit_ts"]) + cooldown_s
        taken.append({**x, "risk_usdt": risk_usdt,
                      "usd": float(x["net"]) * risk_usdt * float(x.get("mult", 1.0)),
                      "avail_frac": avail / equity if equity else 0.0})
    return taken


def usd(fills: list[dict[str, Any]]) -> float:
    return sum(f["usd"] for f in fills)


def summary(fills: list[dict[str, Any]], equity: float) -> str:
    if not fills:
        return "no fills"
    span = (fills[-1]["ts"] - fills[0]["ts"]) / 86400.0
    af = sum(f["avail_frac"] for f in fills) / len(fills)
    return ("%d fills over %.0fd (%.2f/day) | mean available %.0f%% of equity | "
            "mean risk $%.2f" % (len(fills), span, len(fills) / max(1e-9, span),
                                 100 * af,
                                 sum(f["risk_usdt"] for f in fills) / len(fills)))
