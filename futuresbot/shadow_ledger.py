"""Shadow ledger — the counterfactual record of trades the bot did NOT take.

The feature store only records CLOSED trades, so the learning stack is
selection-biased: it can evaluate exits/holds but is structurally blind on entry
gates and the external vetoes (which shipped 'monitored' with nothing actually
monitoring them). This module appends a row for every candidate that produced a
SIGNAL but was not taken (external-gate veto, occupied slot, sizing skip), then
later resolves a paper counterfactual under THE EXIT POLICY THAT SLEEVE ACTUALLY
RUNS.

That last clause is the 2026-08-09 fix. The resolver used to score every row on
a -1R / +TP / 48h hold-to-target bracket, which the convex sleeves retired two
trials ago: trial 7 runs a 24h clock plus a 0.30xpeak retention trail that books
~7% of trades at TP where the bracket books ~13-16%. Every wildcard cfR in the
scorecard was therefore answering a question the bot had stopped asking, and
reading it as "this veto cost me +5R" overstated what the live stack would have
banked. SNIPER is unaffected: it is excluded from the convex stack by design
(its exit IS the exchange SL/TP), so the bracket was always right for it.

Every resolved row now also carries `cost_r` and `outcome_net`. The gross
`outcome` remains fee-free by construction; on a 0.37% sniper stop the round
trip is ~0.5R, which is the difference between "cfR +1.1" and zero.

Pure helpers; the runtime owns file paths and kline fetches. Fail-soft.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

RESOLVE_HORIZON_S = 48 * 3600
TP_R = 5.0

# Live convex exit (runtime._convex_runner_trail_exit / _convex_time_stop_exit).
# Mirrored here so the replay scores the policy that is actually running; keep
# the defaults in step with FUTURES_CONVEX_* or the counterfactual drifts again.
CONVEX_ARM_R = 1.0
CONVEX_RETAIN = 0.30
CONVEX_COST_FLOOR_MULT = 1.5
CONVEX_HORIZON_S = 24 * 3600
# Sleeves the convex stack applies to. SNIPER is deliberately absent: it is
# excluded from the convex exits in the runtime too, so the bracket is right.
CONVEX_SLEEVES = frozenset({"WILDCARD", "SQUEEZE"})
# Round-trip taker + slippage as a percent of notional; same constant the live
# trail floors on (FUTURES_CONVEX_COST_PCT).
COST_PCT = 0.190


def cost_r(row: dict[str, Any]) -> float:
    """Round-trip cost expressed in R, from the signal's own stop geometry.

    ``cost_drag = (2*fee + slip) / sl_frac`` — leverage cancels. A wildcard's
    wide stop pays ~0.01-0.05R; a sniper's 0.37% stop pays ~0.5R, which is why
    a fee-free sniper cfR is not comparable to a fee-free wildcard one."""
    try:
        entry = abs(float(row.get("entry") or 0.0))
        sl_frac = abs(entry - float(row.get("sl") or 0.0)) / entry if entry else 0.0
    except (TypeError, ValueError):
        return 0.0
    if sl_frac <= 0:
        return 0.0
    try:
        pct = float(os.environ.get("FUTURES_CONVEX_COST_PCT") or COST_PCT)
    except (TypeError, ValueError):
        pct = COST_PCT
    return (pct / 100.0) / sl_frac


def ledger_path(state_dir: str) -> str:
    return os.environ.get("FUTURES_SHADOW_LEDGER_FILE") or os.path.join(state_dir, "futures_shadow_ledger.jsonl")


def signal_tp_r(sig: Any) -> float:
    """Target R implied by a signal's own geometry.

    Not every sleeve targets +5R — the Sniper aims at +2R/+3R. Deriving it from
    (tp - entry) / (entry - sl) means the ledger scores each sleeve at ITS OWN
    target instead of crediting every TP hit as +5R, which would silently
    inflate the counterfactual for any short-target sleeve.
    """

    try:
        entry = float(sig.entry_price); sl = float(sig.sl_price); tp = float(sig.tp_price)
        one_r = abs(entry - sl)
        return round(abs(tp - entry) / one_r, 3) if one_r > 0 else TP_R
    except (TypeError, ValueError, AttributeError):
        return TP_R


def candidate_row(sig: Any, *, sleeve: str, reject_reason: str, lateness: float | None = None,
                  extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        **(extra or {}),
        "ts": round(time.time()),
        "symbol": sig.symbol, "side": sig.side, "sleeve": sleeve,
        "reject_reason": reject_reason,
        "entry": float(sig.entry_price), "sl": float(sig.sl_price), "tp": float(sig.tp_price),
        "leverage": int(sig.leverage), "sl_margin_pct": float(sig.sl_margin_pct),
        "roc_pct": round(float(sig.roc_pct), 4), "rsi": float(sig.rsi),
        "tp_r": signal_tp_r(sig),
        "entry_lateness": round(lateness, 3) if lateness is not None else None,
        "outcome": None,  # resolved later: -1.0 stop / +tp_r tp / timeout mark
    }


def append_row(path: str, row: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


DEDUPE_WINDOW_S = 90


def load_raw(path: str) -> list[dict[str, Any]]:
    """Every line, duplicates included. The WRITE path must use this.

    load_rows() collapses duplicate rows for analysis; feeding that collapsed
    list back into rewrite() deletes the duplicates from the only on-disk
    record — including their distinct reject_reason, which the veto scorecard
    buckets on. Dedupe is a read-time view, never a mutation."""
    if not os.path.exists(path):
        return []
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


def load_rows(path: str) -> list[dict[str, Any]]:
    """Read the ledger, collapsing rows that record the SAME signal twice.

    The sniper live path used to write a second row (`slot_occupied`) for a
    signal the caller had already written as `shadow_only` one line earlier —
    same symbol, side, entry, sl and tp, ~1s apart. That writer is fixed, but
    four such pairs are already on the /data volume and every consumer of this
    file (status, learning digest, any counterfactual analysis) would keep
    double-counting them. Deduping on read makes the historical rows correct
    without rewriting the ledger.

    Keyed on the signal's identity, not its reject reason: two rows describing
    one candidate resolve identically, so counting both overstates the sample
    and double-weights that candidate in cfR and win rate.
    """
    rows = load_raw(path)
    seen: dict[tuple, float] = {}
    out: list[dict[str, Any]] = []
    for r in rows:
        key = (r.get("sleeve"), r.get("symbol"), r.get("side"), r.get("entry"), r.get("sl"))
        try:
            ts = float(r.get("ts") or 0.0)
        except (TypeError, ValueError):
            ts = 0.0
        prev = seen.get(key)
        if prev is not None and abs(ts - prev) <= DEDUPE_WINDOW_S:
            continue          # same candidate, same scan — already recorded
        seen[key] = ts
        out.append(r)
    return out


def _resolved(row: dict[str, Any], outcome: float, kind: str, ts: float,
              *, convex: bool) -> dict[str, Any]:
    """Stamp an outcome with its cost and the policy it was scored under.

    ``exit_policy`` exists so a scorecard can never silently mix rows resolved
    under the retired bracket with rows resolved under the live convex stack —
    the defect this whole change fixes. Rows written before 2026-08-09 carry no
    tag and must be read as "legacy"."""
    c = cost_r(row)
    return {**row, "outcome": round(float(outcome), 3), "outcome_kind": kind,
            "resolved_ts": round(ts), "cost_r": round(c, 3),
            "outcome_net": round(float(outcome) - c, 3),
            "exit_policy": "convex_v7" if convex else "bracket"}


def resolve_outcome(row: dict[str, Any], bars: list[tuple[int, float, float]], now_ts: float,
                    horizon_s: float = RESOLVE_HORIZON_S,
                    convex: bool = False) -> dict[str, Any] | None:
    """Walk (ts, high, low) bars after the candidate ts and mark the outcome.

    ``convex=False`` is the plain bracket: -1R stop before TP (adverse-first
    within a bar), TP at the signal's own target, or a timeout mark at the final
    bar's midpoint. Correct for SNIPER, whose live exit really is the resting
    SL/TP.

    ``convex=True`` adds the live WILDCARD/SQUEEZE stack on top: once the trade
    has peaked at or above +1R, a retention floor of ``0.30 x peak`` (never
    below 1.5x the round-trip cost) becomes a ratcheting exit. The floor is
    tested against the peak from PRIOR bars only — within one bar we cannot know
    whether the high or the low came first, and crediting an intrabar peak would
    bank a floor the trade may never have earned.

    Returns the updated row, or None if still unresolved."""
    entry = float(row["entry"]); sl = float(row["sl"]); tp = float(row["tp"])
    sgn = 1.0 if row["side"] == "LONG" else -1.0
    one_r = abs(entry - sl)
    if one_r <= 0:
        return _resolved(row, 0.0, "degenerate", now_ts, convex=convex)
    floor_min = CONVEX_COST_FLOOR_MULT * cost_r(row)
    seen = False
    last_mark = entry
    peak_r = 0.0
    for bar in bars:
        ts, hi, lo = bar[0], bar[1], bar[2]
        close = bar[3] if len(bar) > 3 else None
        if ts <= row["ts"]:
            continue
        # The row's OWN clock, enforced here rather than left to whatever
        # window the caller happened to fetch. Without this a 23-day-old row
        # sharing a kline fetch with a fresh one was walked across 23 days
        # against a 24h clock, where a stop or a TP is near-certain — exactly
        # the overstatement this whole change exists to remove.
        if ts - float(row["ts"]) > horizon_s:
            break
        seen = True
        armed = convex and peak_r >= CONVEX_ARM_R
        level = max(CONVEX_RETAIN * peak_r, floor_min) if armed else 0.0
        # An armed position's retention floor sits ABOVE its hard stop, so on a
        # bar spanning both, the floor is what price reaches first — live polls
        # the mark every ~1s and cannot pass the floor without triggering it.
        # (A true gap through both is still credited the floor; that is the
        # same optimism the live trail carries.) Checked BEFORE the stop for
        # exactly this reason; unarmed rows keep the adverse-first convention.
        #
        # `level < peak_r` mirrors the live guard: when the cost floor exceeds
        # the peak the trail does not fire at all, otherwise the replay books
        # more than the trade's own maximum favourable excursion.
        if armed and level < peak_r:
            adverse_r = ((lo if sgn > 0 else hi) - entry) * sgn / one_r
            if adverse_r <= level:
                return _resolved(row, level, "trail", ts, convex=convex)
        adverse_hit = (lo <= sl) if sgn > 0 else (hi >= sl)
        if adverse_hit:  # adverse-first: the stop wins ties
            return _resolved(row, -1.0, "stop", ts, convex=convex)
        tp_hit = (hi >= tp) if sgn > 0 else (lo <= tp)
        if tp_hit:
            # Credit the signal's OWN target, not a global +5R (rows written
            # before tp_r existed fall back to it).
            return _resolved(row, float(row.get("tp_r") or TP_R), "tp", ts, convex=convex)
        fav_r = ((hi if sgn > 0 else lo) - entry) * sgn / one_r
        peak_r = max(peak_r, fav_r)
        # Live closes at the mark when the clock expires; the bar close is the
        # right proxy. Midpoint is the fallback for callers that drop close.
        last_mark = float(close) if close is not None else (hi + lo) / 2.0
    if not seen:
        # Zero observations is NOT a flat outcome. Marking it 0.0 fabricated a
        # measurement and — once exit_policy was stamped — froze it there,
        # permanently replacing the row's real counterfactual.
        return None
    if now_ts - float(row["ts"]) >= horizon_s:
        mark_r = (last_mark - entry) * sgn / one_r
        # Stamp the CLOCK, not the wall clock. A timeout ends when the horizon
        # expires; recording `now_ts` said a trade opened 9 days ago was still
        # running until the moment the resolver happened to run, which made the
        # row's own duration meaningless and any slot-occupancy analysis built
        # on it wrong by days.
        return _resolved(row, mark_r, "timeout", float(row["ts"]) + horizon_s,
                         convex=convex)
    return None


def needs_reresolve(row: dict[str, Any]) -> bool:
    """A resolved row scored under the retired bracket on a convex sleeve.

    Its `outcome` is preserved as `outcome_legacy` before re-resolution, so the
    migration can never destroy a counterfactual it then fails to recompute."""
    return (row.get("outcome") is not None
            and not row.get("exit_policy")
            and str(row.get("sleeve") or "") in CONVEX_SLEEVES)


def mark_for_reresolve(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "outcome_legacy": row.get("outcome"),
            "outcome_kind_legacy": row.get("outcome_kind"), "outcome": None}


def rewrite(path: str, rows: list[dict[str, Any]]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str) + "\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Pricing a counterfactual in DOLLARS
#
# Every consumer of this ledger has reported R, and R is the right unit for a
# verdict: it is deposit-invariant and comparable across symbols. It is the
# wrong unit for the question "is this gate worth keeping", which is asked in
# money. 1R is not a constant — it is the stop distance times the size actually
# risked — so a -1R block on a 20%-stop candidate costs more than twice what a
# -1R block on a 9%-stop candidate costs, and an R-only scorecard hides that.
#
# HONESTY NOTE, because this number is the easiest one in the repo to misuse:
# it is NOT "upside we left on the table". It prices the signal the DETECTOR
# would have fired, resolved forward at the sleeve's own stop, target and 24h
# clock, at the size the bot would actually have taken — so blocked candidates
# that spiked and reversed come out NEGATIVE, and a negative total means the
# gate paid for itself. Ranking symbols by how far they moved and pricing the
# move would produce a large positive number every week and justify deleting
# every gate in the stack.
# ---------------------------------------------------------------------------

DEFAULT_BALANCE_FRACTION = 0.12


def _balance_fraction(explicit: float | None = None) -> float:
    if explicit is not None and explicit > 0:
        return float(explicit)
    try:
        raw = float(os.environ.get("FUTURES_WILDCARD_BALANCE_PCT") or DEFAULT_BALANCE_FRACTION)
    except (TypeError, ValueError):
        raw = DEFAULT_BALANCE_FRACTION
    return min(0.15, max(0.05, raw))


def one_r_usd(row: dict[str, Any], equity_usdt: float,
              balance_fraction: float | None = None) -> float:
    """Dollar value of 1R for this candidate, at the size the sleeve would take.

    ``margin = balance_fraction x equity``; 1R is ``sl_margin_pct`` of that
    margin. Deliberately EXCLUDES the regime and cold-streak trims: both are
    backward-looking state that was not knowable for a trade never taken, and
    including them would make the same blocked candidate worth a different
    amount depending on an unrelated position's outcome."""
    try:
        sl_margin_pct = float(row.get("sl_margin_pct") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if sl_margin_pct <= 0 or equity_usdt <= 0:
        return 0.0
    return float(equity_usdt) * _balance_fraction(balance_fraction) * sl_margin_pct / 100.0


def net_usd(row: dict[str, Any], equity_usdt: float,
            balance_fraction: float | None = None) -> float | None:
    """Net counterfactual dollars for a RESOLVED row, cost included.

    None for an unresolved row — a signal still in flight has no P&L, and
    treating it as zero would drag every average toward nothing."""
    if row.get("outcome") is None:
        return None
    net_r = row.get("outcome_net")
    if net_r is None:
        try:
            net_r = float(row.get("outcome") or 0.0) - cost_r(row)
        except (TypeError, ValueError):
            return None
    return float(net_r) * one_r_usd(row, equity_usdt, balance_fraction)


def gate_cost_usd(rows: list[dict[str, Any]], equity_usdt: float, *,
                  since_ts: float = 0.0, balance_fraction: float | None = None,
                  ) -> dict[str, tuple[int, float]]:
    """{reject reason class -> (resolved n, net $)} over rows since ``since_ts``.

    Keyed on the reason CLASS (``veto:crowded_longs(funding=0.10%)`` ->
    ``veto``) so a scorecard does not fragment into one bucket per funding
    rate. A POSITIVE total is money the gate cost; a NEGATIVE total is money it
    saved."""
    out: dict[str, list[Any]] = {}
    for row in rows:
        try:
            if float(row.get("ts") or 0.0) < since_ts:
                continue
        except (TypeError, ValueError):
            continue
        usd = net_usd(row, equity_usdt, balance_fraction)
        if usd is None:
            continue
        key = str(row.get("reject_reason") or "?").split(":", 1)[0].split("(", 1)[0].strip()
        agg = out.setdefault(key or "?", [0, 0.0])
        agg[0] += 1
        agg[1] += usd
    return {k: (int(n), round(v, 2)) for k, (n, v) in out.items()}
