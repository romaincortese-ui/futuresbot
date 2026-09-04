"""The weekly scorecard: is the trial going well, and how would we know?

Pre-registered on 2026-08-23, BEFORE the week it scores. That ordering is the
whole point. This project has run twelve trials and scored zero of them, because
every one closed on a discovered defect or on too-small n, and because "was that
a good week?" was always answered after seeing the number. Thresholds chosen
after the fact are not thresholds.

Every threshold below is derived from the 63 live convex closes to 2026-08-23,
not invented:

    reached +1R (arms the trail)  15/63 = 24%     (flat regime alone: 10%)
    reached +3R (ratchet fires)    3/63 =  5%
    win rate                              44%
    netR                            +27.03, ex-best +21.94
    worst single trade                  -3.79R
    trades worse than -1.1R         8/63 = 13%
    realised risk/trade            median 1.46% (pre-renormalisation)
    closes per day                        1.09

TWO OF THESE DESERVE THE READER'S ATTENTION MORE THAN P&L DOES.

The -1R stop is NOT a hard floor: 13% of trades lost more than 1.1R and the worst
lost 3.79R, nearly four times the intended risk. That is gap-through-stop, and it
is the mechanism that turns a 20% drawdown into the 48% the year-long replay
showed. It is the single most important input to how much capital this can carry.

And at 1.09 closes/day a week yields 7-8 closes, so a 30-close trial takes about
three and a half weeks. A week is not a verdict and the scorecard says so rather
than implying otherwise.

VERDICTS ARE Good / Bad / NA. NA is not a failure to measure — it means the
metric could not have had an impact this week, most often because the sample was
too small to distinguish anything. A scorecard that grades everything every week
teaches the reader to ignore it.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, NamedTuple

# Live baselines to 2026-08-23, 63 convex closes. Update only with a note saying
# what changed and why — these are the reference the verdicts are read against.
BASE_ARM_RATE = 0.24
BASE_ARM_RATE_FLAT = 0.10
BASE_RATCHET_RATE = 0.05
BASE_TAIL_RATE = 0.13
BASE_WORST_R = -3.79
BASE_RISK_PCT = 1.46
BASE_CLOSES_PER_DAY = 1.09
TARGET_RISK_PCT = 1.87          # long-run MEAN after the regime scaler
BASE_RISK_PCT_TARGET = 2.41     # FUTURES_WILDCARD_RISK_PCT, pre-scaler


class KPI(NamedTuple):
    name: str
    value: str
    verdict: str                # Good | Bad | NA
    note: str


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v if v is not None else d)
    except (TypeError, ValueError):
        return d


def _flow_invariant_drawdown(rows: Sequence[Mapping[str, Any]]) -> float | None:
    """Peak-to-trough of the TRADING curve, immune to deposits and withdrawals.

    Each close contributes ``pnl_usdt / equity_at_close_usdt`` - its return
    against the equity it actually closed against - and those are compounded.
    An external cash flow moves both sides of that ratio for every subsequent
    trade, so it cancels; only trading moves the curve.

    Returns None when no row carries a usable equity stamp, so the caller can
    fall back explicitly rather than grade a silent zero.
    """
    ordered = sorted(rows, key=lambda r: _f(r.get("ts")))
    v, peak, dd, used = 1.0, 1.0, 0.0, 0
    for r in ordered:
        eq = _f(r.get("equity_at_close_usdt"))
        if eq <= 0:
            continue
        # pnl is realised against the equity BEFORE this close, which is what
        # equity_at_close already reflects; the small self-reference is well
        # under the rounding of the percentage this feeds.
        v *= 1.0 + (_f(r.get("pnl_usdt")) / eq)
        used += 1
        if v > peak:
            peak = v
        if peak > 0:
            dd = max(dd, (peak - v) / peak)
    return dd if used else None


def _median(xs: Sequence[float]) -> float:
    s = sorted(xs)
    if not s:
        return 0.0
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def build_scorecard(rows: Sequence[Mapping[str, Any]], *, days: float,
                    exchange_closes: int | None = None,
                    recorded_closes: int | None = None,
                    btc_move_of: Callable[[float], float] | None = None,
                    equity_now: float = 0.0,
                    peak_equity: float = 0.0) -> list[KPI]:
    """Ten KPIs, in the order they should be read.

    Integrity first, because a ledger that has lost rows makes every number below
    it meaningless. Then the trial's own pass criterion. Then risk. Only then
    edge, and only last the things that need a bigger sample than a week.
    """
    n = len(rows)
    out: list[KPI] = []

    # 1. INTEGRITY -- if this fails nothing else can be trusted.
    #
    # This counts RECORDED CLOSES, which is not the same set as the trial's
    # trades. `exchange_closes` counts positions whose CLOSE time falls in the
    # window; `rows` is filtered by ENTRY time, so a trade that opened before
    # the trial and settled inside it appears on the exchange side and not in
    # rows. Comparing the two directly reported "MISSING ROWS — the ledger is
    # not trustworthy" for two ordinary carryovers, on the morning of a
    # deposit. `recorded_closes` is the exit-time count and is the like-for-like
    # figure; it falls back to n so callers that do not filter are unaffected.
    rec = n if recorded_closes is None else recorded_closes
    if exchange_closes is None:
        out.append(KPI("Ledger integrity", "not checked", "NA",
                       "exchange history unavailable"))
    elif rec == exchange_closes:
        note = "every exchange close recorded"
        if rec != n:
            note += f" ({rec - n} opened before the trial, excluded from scoring)"
        out.append(KPI("Ledger integrity", f"{rec} = {exchange_closes}", "Good", note))
    else:
        out.append(KPI("Ledger integrity", f"{rec} vs {exchange_closes}", "Bad",
                       "MISSING ROWS — losses vanish first; investigate before reading on"))

    # 2. The trial's own criterion -- measured BEFORE the regime scaler.
    #
    # The first version of this KPI graded the REALISED risk against 1.87% and
    # called 1.30% a failure on day one. That was a specification error, not a
    # finding: 1.87% is the long-run MEAN across the regime distribution, and the
    # realised figure is that base times the regime multiplier. In a chop stretch
    # the multiplier floors at 0.25, so a correct implementation MUST read low.
    # Grading it that way conflates "did the change take effect" with "what
    # regime are we in", and only the first is the trial's criterion.
    #
    # The direct test is the pre-scaler base: margin_wanted x sl_margin_pct /
    # available, which should equal BASE_RISK_PCT_TARGET on every entry
    # regardless of regime. Verified on the first three post-change entries:
    # TUT 24.349, ZEC 17.676, ZEN 19.967, all exact.
    bases = []
    for r in rows:
        want = _f(r.get("margin_wanted"))
        slm = _f(r.get("sl_margin_pct"))
        av = _f(r.get("equity_at_entry") or r.get("equity_at_open_usdt"))
        if want > 0 and slm > 0 and av > 0:
            bases.append(want * slm / 100.0 / av * 100.0)
    realised = [_f(r.get("risk_pct_actual")) for r in rows if _f(r.get("risk_pct_actual")) > 0]
    med_real = _median(realised) if realised else 0.0
    if len(bases) < 2:
        out.append(KPI("Risk sizing", f"{len(bases)} stamped", "NA",
                       f"need 2+; base target {BASE_RISK_PCT_TARGET:.2f}% pre-scaler"))
    else:
        med = _median(bases)
        ok = abs(med - BASE_RISK_PCT_TARGET) <= 0.15
        out.append(KPI("Risk sizing", f"base {med:.2f}%", "Good" if ok else "Bad",
                       f"pre-scaler target {BASE_RISK_PCT_TARGET:.2f}%; off by more "
                       f"than 0.15 VOIDS the trial. Realised after the regime "
                       f"scaler: {med_real:.2f}% (long-run mean {TARGET_RISK_PCT:.2f}%, "
                       f"lower in chop BY DESIGN)"))

    # 3. Tail losses -- the capital question.
    rs = [_f(r.get("r_multiple")) for r in rows]
    tail = [x for x in rs if x < -1.1]
    worst = min(rs) if rs else 0.0
    if not rs:
        out.append(KPI("Tail losses", "no closes", "NA", "nothing to judge"))
    elif worst < -2.0:
        out.append(KPI("Tail losses", f"{len(tail)}, worst {worst:.2f}R", "Bad",
                       "a beyond -2R loss is a gap through the stop, not a normal stop"))
    elif len(tail) <= 1:
        out.append(KPI("Tail losses", f"{len(tail)}, worst {worst:.2f}R", "Good",
                       f"baseline {BASE_TAIL_RATE*100:.0f}% of trades, worst ever {BASE_WORST_R:.2f}R"))
    else:
        out.append(KPI("Tail losses", f"{len(tail)}, worst {worst:.2f}R", "Bad",
                       f"{len(tail)} beyond -1.1R vs ~{BASE_TAIL_RATE*n:.0f} expected"))

    # 4. 1R conversion -- the leading indicator of edge.
    armed = sum(1 for r in rows if _f(r.get("peak_r")) >= 1.0)
    if n < 8:
        out.append(KPI("Reached +1R", f"{armed}/{n}", "NA",
                       f"need 8+ closes; baseline {BASE_ARM_RATE*100:.0f}%"))
    else:
        rate = armed / n
        out.append(KPI("Reached +1R", f"{armed}/{n} = {rate*100:.0f}%",
                       "Good" if rate >= 0.20 else "Bad",
                       f"baseline {BASE_ARM_RATE*100:.0f}% overall, "
                       f"{BASE_ARM_RATE_FLAT*100:.0f}% in flat tape"))

    # 5. Regime coverage -- the POINT of this week.
    if btc_move_of is None:
        out.append(KPI("Regime coverage", "unknown", "NA", "BTC data unavailable"))
    else:
        non_surge = sum(1 for r in rows if btc_move_of(_f(r.get("ts"))) < 0.05)
        out.append(KPI("Regime coverage", f"{non_surge}/{n} outside surge",
                       "Good" if non_surge >= 4 else ("NA" if n < 4 else "Bad"),
                       "another surge week teaches nothing new — 17 of 18 "
                       "current-config closes are already surge"))

    # 6. Is the week one lucky trade?
    # Stripping the best of four closes is guaranteed to look bad when one of
    # them is a 5R outlier; the arm-rate KPI already waits for 8, and the same
    # sample discipline applies here.
    if n < 8:
        out.append(KPI("netR ex-best", f"{sum(rs):+.2f}", "NA",
                       f"need 8+ closes; have {n}"))
    else:
        net = sum(rs)
        exb = net - max(rs)
        out.append(KPI("netR ex-best", f"{net:+.2f} -> {exb:+.2f}",
                       "Good" if exb > 0 else "Bad",
                       "one trade was 46% of all live P&L once; strip the best and look again"))

    # 7. Time to verdict.
    expect = BASE_CLOSES_PER_DAY * days
    if days < 2.0:
        # A trial a few hours old has no cadence to judge; grading it Bad would
        # make the summary read "failing" on its first morning.
        cadence = "NA"
    elif n >= max(3, expect * 0.6):
        cadence = "Good"
    elif n < 3:
        cadence = "Bad"
    else:
        cadence = "NA"
    out.append(KPI("Closes", f"{n} in {days:.1f}d", cadence,
                   f"~{expect:.0f} expected at {BASE_CLOSES_PER_DAY}/day; "
                   f"30 needed for a verdict"))

    # 8. Drawdown shape.
    #
    # Measured on a FLOW-INVARIANT curve, not on absolute equity. The old form
    # graded (peak_equity - equity_now)/peak_equity where peak came from the
    # trial's own equity_at_close stamps, so an external cash flow read as
    # performance: withdrawing $900 from a $1,074 account on the last day of the
    # funded week scores 83.8% -- "Bad" -- and drags overall() to MIXED on a week
    # that may have been entirely profitable. The single readout the funded
    # experiment exists to produce was degraded by the act of taking the money
    # out.
    #
    # Each trade's return is taken against the equity it actually closed
    # against, then compounded. A deposit or withdrawal moves the denominator
    # and the numerator together and cancels; only trading moves the curve.
    dd = _flow_invariant_drawdown(rows)
    if dd is None:
        # No usable per-trade equity stamps; fall back to the absolute form and
        # say so, rather than silently grading a number of unknown provenance.
        if peak_equity <= 0 or equity_now <= 0:
            out.append(KPI("Drawdown", "unknown", "NA", "no equity history"))
        else:
            dd_abs = max(0.0, (peak_equity - equity_now) / peak_equity)
            out.append(KPI("Drawdown", f"{dd_abs*100:.1f}% off peak",
                           "Good" if dd_abs < 0.10 else ("NA" if dd_abs < 0.15 else "Bad"),
                           "absolute equity basis - distorted by any deposit or "
                           "withdrawal in the window"))
    else:
        out.append(KPI("Drawdown", f"{dd*100:.1f}% off peak",
                       "Good" if dd < 0.10 else ("NA" if dd < 0.15 else "Bad"),
                       "trading-only basis, deposits and withdrawals excluded; "
                       "the year-long replay shows 48% peak-to-trough is in range"))

    # 9. Ratchet -- informational, too rare to grade on a week.
    fired = sum(1 for r in rows if _f(r.get("peak_r")) >= 3.0)
    out.append(KPI("Ratchet firings", f"{fired}", "NA",
                   f"only {BASE_RATCHET_RATE*100:.0f}% of trades reach 3R — "
                   "expect 0-1 a week, read nothing into either"))

    # 10. Reconstructed rows -- a defect tripwire, not a performance metric.
    recon = sum(1 for r in rows if _f(r.get("reconstructed")) > 0)
    out.append(KPI("Backfilled rows", f"{recon}",
                   "NA" if not rows else ("Good" if recon == 0 else "Bad"),
                   "any row rebuilt after the fact means a close was missed live"))
    return out


def overall(kpis: Sequence[KPI]) -> str:
    """One line. Bad beats Good — a broken ledger is not offset by a nice week."""
    bad = [k for k in kpis if k.verdict == "Bad"]
    good = [k for k in kpis if k.verdict == "Good"]
    if any(k.name in ("Ledger integrity", "Backfilled rows") and k.verdict == "Bad"
           for k in kpis):
        return "INVESTIGATE — the ledger is not trustworthy, so the P&L is not either"
    if bad:
        return f"MIXED — {len(good)} good, {len(bad)} bad: " + ", ".join(k.name for k in bad)
    if not good:
        return "TOO EARLY — not enough closes to judge anything yet"
    return f"ON TRACK — {len(good)} good, nothing failing"
