"""The standard control for any REGIME study. Run this before believing one.

    from pit_placebo import placebo_test, format_placebo

WHY THIS EXISTS. On 2026-09-02 a majors-up gate looked genuinely good: applied
to the real live trades it turned trials 17+18 from -$4.32 into +$12.89, and a
permutation test against random same-size subsets returned p < 1%. It was one
step from being pre-registered as a trial.

It was an artifact, and the permutation test could not see it.

THE FLAW IN PERMUTATION TESTING HERE. A permutation test asks: did this filter
pick better trades than a RANDOM subset of the same size? That is the right
control for a filter that selects trades independently. But a regime gate does
not - it selects by TIME, in contiguous stretches. And this book is
autocorrelated: it has good weeks and bad weeks. So ANY time-correlated filter
beats random subsets, whether or not it knows anything about markets. The p<1%
was measuring autocorrelation.

THE PLACEBO. Run the identical gate on a TIME-SHIFTED signal. A gate driven by
the majors from seven days earlier has exactly the same time-clustering
behaviour, exactly the same open/closed duty cycle, and NO information about the
market each trade actually traded in. If it scores as well as the real gate, the
gate is reading the calendar.

WHAT IT FOUND, on the gate that had passed the permutation test:

    WHOLE HISTORY (actual $+23.27)
      REAL gate, no shift        +$13.95
      majors signal -7 days      +$17.07   <- the PLACEBO won
      majors signal +3 days       +$6.73
      majors signal -3 days       +$4.82
      majors signal +14 days      +$0.34
      majors signal -14 days     -$22.37
      majors signal +7 days      -$35.52

The real result sits inside a placebo spread running from -$35.52 to +$17.07,
and a signal from a week earlier beat it. That is the definition of no effect.

READ THE RANK, NOT THE VALUE. The question is not "did the gate make money" -
it is "did the gate beat signals that cannot possibly work". If the real result
is not clearly at the top of the placebo distribution, there is nothing there.

APPLIES TO: majors gates, majors tilts, divergence policies, direction filters,
news-regime policies, cooldowns keyed on market state - anything whose decision
is a function of TIME rather than of the individual trade. It does NOT apply to
per-trade filters (score, calm_ratio, turnover, ROC band), which select
independently and for which a permutation test is the correct control.

READ-ONLY helper. No I/O.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Sequence

def _dense_shifts(min_days: float = 4.0, max_days: float = 30.0,
                  step_hours: float = 6.0) -> tuple[float, ...]:
    """A DENSE null distribution, not a handful of samples.

    CORRECTED 2026-09-02, hours after this module was first committed. The first
    version used six shifts, which meant the strongest possible verdict was
    "beat all six" - an outcome a null gate reaches roughly one time in seven.
    Pointed at ten KNOWN-NULL regime hypotheses it declared five of them
    survivors. The control was not measuring anything; it was reporting which
    gates happened to top a six-sample draw.

    ~180 shifts make the rank a real percentile: topping them all is p < 0.6%.

    min_days exists because a shift shorter than the signal's own lookback still
    correlates with it. A 72h majors signal shifted by one day is largely the
    same signal, so it is not a placebo - it is a slightly blurred copy, and
    including it would make every gate look unbeatable.
    """
    out, d = [], min_days
    while d <= max_days:
        out.extend((-d, d))
        d += step_hours / 24.0
    return tuple(sorted(out))


DEFAULT_SHIFTS_DAYS: tuple[float, ...] = _dense_shifts()


class PlaceboResult:
    def __init__(self, real: float, real_n: int,
                 shifted: list[tuple[float, float, int]], min_n: int):
        self.real = real
        self.real_n = real_n
        self.shifted = shifted          # (shift_days, value, n)
        self.min_n = min_n

    @property
    def usable(self) -> list[tuple[float, float, int]]:
        return [s for s in self.shifted if s[2] >= self.min_n]

    @property
    def beaten_by(self) -> list[tuple[float, float, int]]:
        """Placebos that did AS WELL OR BETTER than the real gate."""
        return [s for s in self.usable if s[1] >= self.real]

    @property
    def rank(self) -> float | None:
        """Share of usable placebos scoring >= the real gate, as a percentage.

        This is a PERCENTILE against a dense null, so it reads like a p-value:
        1% means only one placebo in a hundred matched the real gate. With the
        six-shift default this module shipped with for a few hours, the best
        achievable value was 0% and it meant almost nothing.
        """
        u = self.usable
        if not u:
            return None
        return 100.0 * len(self.beaten_by) / len(u)

    @property
    def verdict(self) -> str:
        r = self.rank
        if r is None:
            return "INCONCLUSIVE - no shift produced enough trades to compare"
        if len(self.usable) < 30:
            return ("INCONCLUSIVE - only %d usable placebos, need >= 30 for a "
                    "percentile" % len(self.usable))
        if r <= 1.0:
            return "SURVIVES - beat %.0f%% of a dense null" % (100 - r)
        if r <= 5.0:
            return "WEAK - inside the top %.0f%% of the null" % r
        return "REFUTED - %.0f%% of signals that cannot work did as well" % r


def placebo_test(pool: Iterable[Any], gate_at: Callable[[float], bool], *,
                 time_of: Callable[[Any], float],
                 value_of: Callable[[Any], float],
                 shifts_days: Sequence[float] = DEFAULT_SHIFTS_DAYS,
                 min_n: int = 3) -> PlaceboResult:
    """Score a time-based gate against the same gate on shifted signals.

    gate_at(t)  -> True when the gate is OPEN at unix time t. Shifting is applied
                   to the QUERY, so `gate_at(t + shift)` reads the signal from a
                   different period while keeping the trade set fixed.
    time_of(x)  -> the entry time of a trade (NOT its exit; a gate decides at
                   entry, and using exit time would leak the trade's own outcome
                   window into the decision).
    value_of(x) -> what to sum, normally dollars.
    """
    items = list(pool)
    def run(shift_s: float) -> tuple[float, int]:
        kept = [x for x in items if gate_at(time_of(x) + shift_s)]
        return (sum(value_of(x) for x in kept), len(kept))

    real, real_n = run(0.0)
    shifted = []
    for d in shifts_days:
        v, n = run(d * 86400.0)
        shifted.append((d, v, n))
    return PlaceboResult(real, real_n, shifted, min_n)


def format_placebo(res: PlaceboResult, *, baseline: float | None = None,
                   label: str = "") -> str:
    out = []
    if label:
        out.append(label)
    b = "" if baseline is None else "  (ungated %+.2f)" % baseline
    out.append("  %-24s %5s %11s %11s" % ("signal", "kept", "value", "vs ungated"))
    def row(nm, v, n):
        d = "" if baseline is None else "%+11.2f" % (v - baseline)
        return "  %-24s %5d %+11.2f %s" % (nm, n, v, d)
    out.append(row("REAL (no shift)", res.real, res.real_n) + "   <- the gate")
    for d, v, n in res.shifted:
        if n < res.min_n:
            out.append("  %-24s %5d %11s" % ("%+.0f days" % d, n, "too few"))
        else:
            out.append(row("%+.0f days" % d, v, n))
    out.append("")
    out.append("  placebos beating the real gate: %d of %d%s"
               % (len(res.beaten_by), len(res.usable),
                  "" if res.rank is None else "  (%.0f%%)" % res.rank))
    out.append("  VERDICT: %s" % res.verdict)
    if baseline is not None:
        out.append("  ungated baseline%s" % b)
    return "\n".join(out)
