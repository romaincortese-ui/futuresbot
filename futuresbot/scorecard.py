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


# ---------------------------------------------------------------------------
# THE DAILY CARD (wc/DAILY, pre-registered 2026-09-23)
# ---------------------------------------------------------------------------
# The scorecard above grades a TRIAL. This grades a DAY, and the two are
# different objects: at 2-4 fills a day with a per-fill sd of 1.57R, one day's
# P&L carries about +-$35 of noise against a $10/month ship bar. Detecting a 25%
# change in the edge needs 44,551 fills; detecting the $10/month that decides
# ship/no-ship needs about 240,000. The book has 199. So the card does NOT grade
# the edge daily. It grades the MACHINE, prints the day's draw as a percentile so
# an ordinary bad day is visibly ordinary, and says NO ACTION - which is the
# correct answer on about 95% of days, including the worst dollar day in this
# book's life (2026-09-08, -$77.16, which reached 44% of a once-a-year alarm and
# was back to 0% eight days later with nothing changed).
#
# Three blocks that must never be mixed:
#   MACHINE - integrity and mechanics. Readable daily. Act when it fails.
#   MARKET  - context. NO ACTION IS EVER TAKEN ON THIS BLOCK.
#   EDGE    - not readable in one day, and the card says so rather than implying
#             a verdict it cannot support.
#
# Every threshold below was frozen on 2026-09-22 from 199 live fills, and each is
# set OUTSIDE the in-control range rather than at a percentile, so a healthy book
# does not trip it. THERE IS NOT ONE OUT-OF-SAMPLE DAY YET: the retrospective
# firing counts in docs/DECISION_RULE.md are in-control estimates, not a test.
# If the trailing per-fill sd moves more than 25% from 1.57R these must be
# re-derived - September alone ran 1.12R, which would make them ~40% too loose.

# M1 - a STOP that settles outside this band is a defect (gap, wrong stop price,
# wrong sizing), not a loss. 63 of 68 live stops settled in [-1.16, -0.98], sd
# 0.038. Fired 4 times in 88 days, all inside 2026-08-06..08-10.
STOP_BAND_R = (-1.22, -0.92)
# M2 - 196 of 199 fills settled at or above -1.5R.
FILL_FLOOR_R = -1.5
# M3 - realised risk as a % of equity. All 145 rows since 2026-08-11 sit inside.
RISK_PCT_BAND = (0.35, 3.0)
# M4 - one fill's entry slippage. TREND p98 is 14 bps, WILDCARD p98 is 89 bps.
# Fired once in 88 days (2026-09-10, +510 bps).
SLIP_MAX_BPS = 100.0
# M6 - portfolio margin as a % of equity.
MARGIN_HALT_PCT = 45.0
# Exit reasons the machine is allowed to produce. Anything else is M5.
SANCTIONED_EXITS = frozenset({
    "EXCHANGE_CLOSE", "STOP_LOSS", "TAKE_PROFIT", "MANUAL_CLOSE",
    "CONVEX_RETENTION_TRAIL", "CONVEX_RUNNER_TRAIL", "CONVEX_TIME_STOP",
    "CONVEX_EARLY_STOP", "CONVEX_PREEMPTED", "PEAK_PROFIT_LOCK",
    # reachable on a convex position through the legacy exit ladder, and therefore
    # not evidence of anything when they appear
    "PEAK_PROTECTION_GAP_EXIT", "BREAKEVEN_PROFIT_LOCK",
    "BREAKEVEN_PROTECTION_GAP_EXIT", "ADVERSE_PEAK_TRAIL", "MID_PROFIT_LOCK",
    "TRAILING_TAKE_PROFIT", "HOURLY_TAKE_PROFIT", "STAGNATION_EXIT",
    "MARGIN_LOSS_EXIT", "STOP_RISK_CAP_EXIT", "LIQ_BUFFER",
})
# The decay meter: a one-sided CUSUM on per-fill R, in R units, EXIT-ORDERED
# (R is not known until a trade closes, so a sequential statistic cannot be
# updated at entry - the same meter reads 16% exit-ordered and 27% entry-ordered
# for 2026-09-22, and exit order is the correct one). h is calibrated to fire
# about once a year on a book that has not changed. It has never fired in 199
# fills; its lifetime peak is 89%, on 2026-07-30. NOTE: four independent calibrations
# of the same k returned h = 4.14, 5.05, 8.0 and 10.48, so the card does NOT claim a
# firing rate - it prints the percentage and leaves the rate to be measured. Nothing
# below 100% is an instruction to do anything.
DECAY_K_R = 0.50
DECAY_H_R = 10.48
# FROZEN, like every other threshold here: the mean per-fill R of the 191 convex fills
# to 2026-09-22. Re-derive it only with a note saying what changed and why.
DECAY_MU_R = 0.1009
CONVEX_KINDS = frozenset({"WILDCARD", "TREND", "SQUEEZE", "SNIPER"})


class DailyCard(NamedTuple):
    lines: list[str]        # the card itself - eleven lines, verdict last
    detail: list[str]       # the second message, on request
    verdict: str            # NO ACTION | INVESTIGATE | CHANGE ONE THING
    tripwires: list[str]    # the machine tripwires that fired, by name


def _day_key(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def _opened_at(r: Mapping[str, Any]) -> float:
    """Entry stamp of a close row; `ts` is the EXIT stamp.

    hold_hours is missing on every row before 2026-08-07, where hold_min is present;
    without the fallback those rows silently date their entry to their exit."""
    hold_s = _f(r.get("hold_hours")) * 3600.0
    if hold_s <= 0:
        hold_s = _f(r.get("hold_min")) * 60.0
    return _f(r.get("ts")) - hold_s


def _r_of(r: Mapping[str, Any]) -> float | None:
    """R for one fill, preferring the measured ratio over the stored tag.

    pnl/risk is the correct one: the bot's own `r_multiple` disagreed with it on
    12 of 17 fills in the trial-19 window, by up to 0.12R, because the two use
    different denominators (signal-anchored vs fill-anchored). Never mix them
    inside one total.
    """
    risk = _f(r.get("risk_usdt"))
    if risk > 0:
        return _f(r.get("pnl_usdt")) / risk
    v = r.get("r_multiple")
    return None if v is None else _f(v)


def decay_meter(rows: Sequence[Mapping[str, Any]], *, until_ts: float | None = None
                ) -> tuple[float, float]:
    """(CUSUM value in R, fraction of the alarm threshold), exit-ordered.

    C_i = max(0, C_{i-1} - (R_i - DECAY_MU_R) - k). It accumulates only while fills
    come in worse than the frozen reference by more than k, and decays to zero on
    an ordinary one, which is why the worst dollar day in the book's history
    (2026-09-08, -$77.16) reached 43% and returned to 0% eight days later without
    anything being changed. Measured over the 191 convex fills to 2026-09-22: zero
    crossings, peak 89% on 2026-07-30.

    The reference is a CONSTANT and must stay one. Estimating it from the stream it
    monitors manufactured four crossings of a once-a-year threshold, one of them on a
    day with no tripwire at all, and would hide exactly the slow decay this is for.
    """
    c = 0.0
    for r in sorted(rows, key=lambda x: _f(x.get("ts"))):
        if until_ts is not None and _f(r.get("ts")) > until_ts:
            break
        rr = _r_of(r)
        if rr is None:
            continue
        c = max(0.0, c - (rr - DECAY_MU_R) - DECAY_K_R)
    return c, (c / DECAY_H_R if DECAY_H_R > 0 else 0.0)


def day_draw(net_r: float, n_fills: int, pool: Sequence[float],
             *, draws: int = 20000, seed: int = 0) -> str:
    """How ordinary the day's draw was, CONDITIONAL ON THE FILL COUNT.

    Any daily chart that does not condition on the fill count is measuring the
    fill count: P(a day <= -4.83R) is 1-in-180 at 2 fills, 1-in-22 at 4 and
    1-in-8 at 7. Fixed seed, so the same day always prints the same number.
    """
    import random
    if n_fills <= 0 or len(pool) < 5:
        return ""
    rng = random.Random(seed)
    hits = 0
    for _ in range(draws):
        if sum(rng.choice(pool) for _ in range(n_fills)) <= net_r:
            hits += 1
    p = max(hits, 1) / float(draws)
    if p < 0.5:
        return "1-in-%d day at %d fills" % (round(1.0 / p), n_fills)
    return "%.0fth pct at %d fills" % (p * 100.0, n_fills)


def _tripwires(day_rows: Sequence[Mapping[str, Any]], *,
               exchange_closes: int | None, recorded_closes: int | None,
               margin_pct: float | None) -> tuple[list[str], list[str]]:
    """(fired, detail lines). Six binary checks, each decidable from one fill."""
    fired: list[str] = []
    detail: list[str] = []

    stops = [r for r in day_rows
             if str(r.get("exit_kind") or "").upper() == "STOP"
             and (_r_of(r) or 0.0) < 0]
    srs = [x for x in (_r_of(r) for r in stops) if x is not None]
    if not srs:
        detail.append("  stops     none today                    band NA")
    else:
        bad = [x for x in srs if not (STOP_BAND_R[0] <= x <= STOP_BAND_R[1])]
        if bad:
            fired.append("M1 stop outside [%.2f,%.2f]R: %s"
                         % (STOP_BAND_R[0], STOP_BAND_R[1],
                            ", ".join("%.2f" % x for x in bad)))
        detail.append("  stops     %s   band [%.2f,%.2f]"
                      % (" ".join("%.2f" % x for x in srs), *STOP_BAND_R))

    deep = [(r.get("symbol"), x) for r in day_rows
            for x in [_r_of(r)] if x is not None and x < FILL_FLOOR_R]
    if deep:
        fired.append("M2 fill below %.1fR: %s"
                     % (FILL_FLOOR_R, ", ".join("%s %.2f" % d for d in deep)))

    risks = [_f(r.get("risk_pct_actual")) for r in day_rows
             if r.get("risk_pct_actual") is not None]
    if risks:
        out = [x for x in risks if not (RISK_PCT_BAND[0] <= x <= RISK_PCT_BAND[1])]
        if out:
            fired.append("M3 risk%% outside [%.2f,%.1f]: %s"
                         % (*RISK_PCT_BAND, ", ".join("%.2f" % x for x in out)))
        detail.append("  risk%%     %.2f - %.2f                    band [%.2f, %.1f]"
                      % (min(risks), max(risks), *RISK_PCT_BAND))

    slips = [(r.get("symbol"), _f(r.get("entry_slippage_bps"))) for r in day_rows
             if r.get("entry_slippage_bps") is not None]
    # SIGNED: entry_slippage_bps is already side-adjusted and positive means the
    # fill was WORSE than the signal price (runtime.py ~9665). A favourable fill is
    # not a defect - grading |slippage| fired M4 on 2026-09-16, a five-for-five day
    # whose worst "offence" was a WILDCARD entry filling 107 bps in our favour.
    hot = [s for s in slips if s[1] > SLIP_MAX_BPS]
    if hot:
        fired.append("M4 slippage over %.0f bps: %s"
                     % (SLIP_MAX_BPS, ", ".join("%s %+.0f" % s for s in hot)))
    if slips:
        detail.append("  slippage  %+.0f to %+.0f bps                 limit %.0f"
                      % (min(s[1] for s in slips), max(s[1] for s in slips), SLIP_MAX_BPS))

    odd = sorted({str(r.get("exit_reason") or "?").upper()
                  .replace("_RECONSTRUCTED", "") for r in day_rows}
                 - SANCTIONED_EXITS)
    recon = sum(1 for r in day_rows if _f(r.get("reconstructed")) > 0
                or "RECONSTRUCTED" in str(r.get("exit_reason") or "").upper())
    if odd or recon:
        fired.append("M5 unsanctioned exit or backfilled row: %s%s"
                     % (", ".join(odd) or "-", " (%d backfilled)" % recon if recon else ""))
    if day_rows:
        detail.append("  exits     %s"
                      % ", ".join(sorted({str(r.get("exit_reason") or "?") for r in day_rows})))

    if exchange_closes is not None and recorded_closes is not None:
        if recorded_closes != exchange_closes:
            fired.append("M6 ledger %d vs exchange %d" % (recorded_closes, exchange_closes))
        detail.append("  ledger    %d recorded = %d exchange closes"
                      % (recorded_closes, exchange_closes))
    else:
        detail.append("  ledger    not checked - exchange history unavailable")
    if margin_pct is not None:
        if margin_pct >= MARGIN_HALT_PCT:
            fired.append("M6 portfolio margin %.0f%% >= %.0f%%" % (margin_pct, MARGIN_HALT_PCT))
        detail.append("  margin    %.0f%% of equity                   halt at %.0f%%"
                      % (margin_pct, MARGIN_HALT_PCT))
    return fired, detail


def build_daily_card(rows: Sequence[Mapping[str, Any]], *, day: str,
                     exchange_closes: int | None = None,
                     recorded_closes: int | None = None,
                     open_positions: int = 0,
                     refused: int | None = None,
                     margin_pct: float | None = None,
                     stake_note: str = "") -> DailyCard:
    """The card for one UTC day, built from the feature store alone.

    P&L is ENTRY-DATED PRIMARY - the card grades decisions, and the decision was
    made at entry - with the exit-dated figure always printed beside it, because
    25% of fills straddle a UTC boundary and the two differed by $8.71 on the day
    this card was designed around. The decay meter is exit-ordered by necessity.
    """
    conv = [r for r in rows if str(r.get("kind") or "").upper() in CONVEX_KINDS]
    entered = [r for r in conv if _day_key(_opened_at(r)) == day]
    exited = [r for r in conv if _day_key(_f(r.get("ts"))) == day]
    upto = [r for r in conv if _day_key(_f(r.get("ts"))) <= day]

    ent_r = [x for x in (_r_of(r) for r in entered) if x is not None]
    ext_r = [x for x in (_r_of(r) for r in exited) if x is not None]
    ent_usd = sum(_f(r.get("pnl_usdt")) for r in entered)
    ext_usd = sum(_f(r.get("pnl_usdt")) for r in exited)

    # The ledger check must compare LIKE WITH LIKE: the exchange counts every close on
    # the account, so the recorded side has to be every settled row, not the convex
    # subset the rest of the card grades. Passing the convex count would fire a false
    # M6 on all 13 days in this book that carry a non-convex close, and a false ledger
    # alarm is the fastest way to teach the reader to ignore the card.
    all_exited = sum(1 for r in rows if _day_key(_f(r.get("ts"))) == day)
    fired, mach_detail = _tripwires(
        exited, exchange_closes=exchange_closes,
        recorded_closes=(recorded_closes if recorded_closes is not None else all_exited)
        if exchange_closes is not None else None,
        margin_pct=margin_pct)

    cusum, frac = decay_meter(upto)
    pool = [x for x in (_r_of(r) for r in upto) if x is not None]
    draw = day_draw(sum(ent_r), len(ent_r), pool)

    breadths = [_f(r.get("breadth_24h")) for r in entered if r.get("breadth_24h") is not None]
    if not breadths:
        market = "--"
    else:
        market = "broad" if _median(breadths) >= 0.45 else "narrow"

    # A NAMED MECHANISM OUTRANKS A STATISTIC. Reading the meter first relabels a real
    # stop defect as an edge verdict, which is exactly the confusion this card exists to
    # prevent: a tripwire points at a fill and says what broke, the meter points at
    # nothing and says "maybe".
    if fired:
        verdict = "INVESTIGATE"
    elif frac >= 1.0:
        verdict = "CHANGE ONE THING"
    elif frac >= 0.40:
        verdict = "NO ACTION - meter elevated"
    else:
        verdict = "NO ACTION"

    lines = [
        "DAILY %s  00:00-24:00Z" % day,
        "%d in / %d out / %d open%s" % (len(entered), len(exited), open_positions,
                                        " / %d refused" % refused if refused is not None else ""),
        "",
        "MACHINE   %-15s %d of 6 tripwires" % ("OK" if not fired else "CHECK", len(fired)),
        "MARKET    %-15s context only" % market,
        "EDGE      %-15s of the alarm level" % ("%.0f%%" % (frac * 100.0)),
        "",
        "  %-13s /  %+.2fR exit" % ("%+.2fR entry" % sum(ent_r), sum(ext_r)),
        "  %-13s /  %s" % ("%s$%.2f" % ("-" if ent_usd < 0 else "+", abs(ent_usd)),
                             "%s$%.2f" % ("-" if ext_usd < 0 else "+", abs(ext_usd))),
        "  %s" % (draw or "no fills entered"),
        "",
        ">>> %s" % verdict,
    ]

    detail = ["MACHINE"] + mach_detail
    for f in fired:
        detail.append("  ! " + f)
    detail += [
        "",
        "MARKET  (no action is ever taken on this block)",
        "  breadth %s" % ("%.2f" % _median(breadths) if breadths else "--"),
        "",
        "EDGE  (not readable in one day - this is the honest part)",
        "  decay meter  %.2f of %.2fR = %.0f%%" % (cusum, DECAY_H_R, frac * 100.0),
        "  a day cannot see a $10/month change: that needs ~240,000 fills.",
        "  cumulative R since the last change is the number that decides;",
        "  9:1 odds that something changed needs -13R to -17R.",
    ]
    if stake_note:
        detail.append("  " + stake_note)
    return DailyCard(lines=lines, detail=detail, verdict=verdict, tripwires=fired)
