"""POINT-IN-TIME majors band. Shared by the pit_* studies.

THE DEFECT THIS FIXES (found 2026-08-28). Every pit_* study computed its
candidate pool as:

    band = rt._major_symbols(today's tickers, 24)     # ONE snapshot
    pool = [s for s in crypto if s not in band][:N]   # ranked on TODAY

...and then applied that fixed pool to 200-400 days of history. The turnover
FLOOR was already point-in-time (a symbol enters and leaves as it did live),
but the BAND was not. So a symbol that is a "major" today was excluded for the
entire history, including the months when it was a small cap.

That is not a modelling nicety. Measured against the 36 live fills since
2026-08-14: TUT_USDT (+$18.73 live) and ENA_USDT (+$11.11) are both inside
today's majors band and therefore absent from every replay pool - the two
trades that made the fortnight's money. Nine of the 19 wildcard symbols the
bot actually traded were missing, and those nine carry +$15.78 of live P&L
against a +$9.07 total. The replay was blind to the profitable tail and kept
the losing body, which is the exact opposite of a conservative bias.

The mechanism is the same endogeneity the live deflator was built to fix
(runtime.py _turnover_deflator, 2026-08-26): turnover created BY a move
causes the symbol to be classified as a major, so the mover gets excluded.
Fixed there for the live bot, still present here in the replay pool - one
level up.

HOW THE BAND IS REBUILT. Per symbol per DAY (the band moves on a scale of
days, and per-bar ranking of 150 symbols x 38k bars buys nothing):

    baseline(sym, day) = median of that symbol's daily turnover over the
                         SEVEN PRECEDING days
    majors(day)        = top N symbols by baseline(., day)

Using the prior week's median rather than the day's own turnover is the
replay equivalent of the live deflator: it ranks on BASELINE liquidity, so a
symbol having one exceptional day does not price itself out of the pool. A
symbol with under 4 prior days of history is not eligible to be a major - it
cannot have a baseline, and a brand-new listing is by definition not a major.

WHAT THIS STILL DOES NOT FIX: symbols delisted before today are absent from
get_all_tickers entirely and cannot enter any pool. That residual
survivorship is stated, not solved.
"""
from __future__ import annotations

import datetime as _dt
from collections import defaultdict


def day_key(ts: float) -> str:
    return _dt.datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d")


def daily_turnover(rolls: dict[str, list[tuple[float, float]]]) -> dict[str, dict[str, float]]:
    """rolls: {symbol: [(bar_ts, rolling_24h_turnover), ...]}
    Returns {symbol: {day: median rolling turnover that day}}."""
    out: dict[str, dict[str, float]] = {}
    for sym, series in rolls.items():
        buckets: dict[str, list[float]] = defaultdict(list)
        for ts, v in series:
            if v > 0:
                buckets[day_key(ts)].append(v)
        out[sym] = {d: sorted(v)[len(v) // 2] for d, v in buckets.items() if v}
    return out


def pit_majors(daily: dict[str, dict[str, float]], n: int = 24,
               lookback: int = 7, min_days: int = 4) -> dict[str, set[str]]:
    """{day: set of symbols that were majors THAT day}.

    Ranked on the median of the preceding `lookback` days, so a symbol having
    one huge day is not promoted into the band by the move itself."""
    days = sorted({d for m in daily.values() for d in m})
    idx = {d: i for i, d in enumerate(days)}
    out: dict[str, set[str]] = {}
    for d in days:
        i = idx[d]
        prior = days[max(0, i - lookback):i]
        if not prior:
            out[d] = set()
            continue
        scored = []
        for sym, m in daily.items():
            vals = [m[p] for p in prior if p in m]
            if len(vals) < min_days:
                continue          # no baseline -> cannot be a major
            vals.sort()
            scored.append((vals[len(vals) // 2], sym))
        scored.sort(reverse=True)
        out[d] = {s for _v, s in scored[:n]}
    return out


def describe(pit: dict[str, set[str]], watch: tuple[str, ...] = ()) -> str:
    """Human-readable churn summary, plus per-symbol in-band day counts for
    any symbols worth watching (e.g. ones the live bot actually traded)."""
    if not pit:
        return "no band computed"
    days = sorted(pit)
    sizes = [len(pit[d]) for d in days]
    churn = [len(pit[days[i]] ^ pit[days[i - 1]]) for i in range(1, len(days))]
    lines = ["band over %d days: size %d-%d, median daily churn %d symbols"
             % (len(days), min(sizes), max(sizes),
                (sorted(churn)[len(churn) // 2] if churn else 0))]
    for w in watch:
        k = sum(1 for d in days if w in pit[d])
        lines.append("  %-14s in band on %d of %d days (%.0f%%)"
                     % (w, k, len(days), 100.0 * k / len(days)))
    return "\n".join(lines)
