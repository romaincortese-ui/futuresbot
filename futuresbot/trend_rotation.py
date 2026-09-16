"""ONE ROTATING SYMBOL for the TREND universe, re-picked every 48 hours.

WHY THIS EXISTS. TREND's static list (ETH/XRP/ZEC) earns its dollars from ZEC:
over 2025-09 -> 2026-09 the sleeve replays at about +$109/month with ZEC and
+$2/month without it, and over the preceding year on Binance bars the same list
replays at about -$86/month. Three pre-registered universe studies (2026-09-13
5-6 symbols, 2026-09-15 rotating slot, 2026-09-15 full rotation) asked whether a
wider or rotating universe fixes that. Two facts came out of all three:

  1. Ranking candidates by volatility / momentum / attention BEATS RANDOM PICKS
     from the same liquid pool, on two engines and in both years (random picks
     lose $32-78/month; the ranked rules win that back and more).
  2. Nothing beat the static list by enough to clear the +$10/month bar with a
     confidence interval clear of zero. The best design measured
     +$50.6/month [-$0.2, +$102.7] on 53.8 fills/month: the list plus ONE coin
     re-picked every 48h by average rank, sharing the same 2 slots.

So this is a LEAD SHIPPED AS A TRIAL, not a proven edge, and the honest caveats
are part of the design: about half the gain is carried by a handful of capped
take-profits on pump bars, the picking skill is visible only in the second year,
and priced with 25% stop slippage and 0.285% fees the gain roughly halves. It is
default OFF; the owner switched it on deliberately with a written kill rule.

THE RULE (exactly what was measured — do not tune it here)
  pool        : MEXC crypto USDT perps, excluding the static TREND symbols,
                >= FUTURES_TREND_ROTATION_MIN_HISTORY_DAYS (60) of hourly history,
                7-day median daily turnover >= $2M, then the top 40 by 30-day
                median daily turnover.
  score       : average of three ranks, best (lowest) wins —
                  VOL  7-day annualised realised volatility from hourly returns
                  MOM  return over the refresh window (48h)
                  ATTN last-24h turnover / 30-day median daily turnover
  refresh     : every 48h; the pick is held between refreshes and a position
                opened on it runs to its normal exit after it rotates out.

Pure ranking lives here so it can be tested without an exchange; the runtime
does the IO and the caching.
"""
from __future__ import annotations

import os
import statistics
from dataclasses import dataclass


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def rotation_enabled() -> bool:
    """Default OFF. The static list is the fallback in every failure path."""
    return _b("FUTURES_TREND_ROTATION_ENABLED", False)


def rotation_seconds() -> float:
    """48h, the refresh that measured best (24h and 72h were weaker)."""
    return max(3600.0, _f("FUTURES_TREND_ROTATION_HOURS", 48.0) * 3600.0)


def min_turnover_usdt() -> float:
    """$2M/day floor. The earlier monthly-rotation study picked names trading
    $0.1-0.5M/day, where a stop on a pump bar is not fillable at any price and
    one symbol's max order size was $325. This floor is what fixed that."""
    return max(0.0, _f("FUTURES_TREND_ROTATION_MIN_TURNOVER_USDT", 2_000_000.0))


def pool_top_n() -> int:
    return max(1, int(_f("FUTURES_TREND_ROTATION_POOL_TOP", 40)))


def shortlist_n() -> int:
    """How many names by 24h turnover get hourly bars fetched each refresh."""
    return max(1, int(_f("FUTURES_TREND_ROTATION_SHORTLIST", 60)))


def min_history_days() -> float:
    return max(1.0, _f("FUTURES_TREND_ROTATION_MIN_HISTORY_DAYS", 60.0))


@dataclass(frozen=True, slots=True)
class Candidate:
    """Metrics for one pool member, all computed from bars BEFORE the refresh."""
    symbol: str
    vol_7d: float            # annualised realised volatility, hourly returns
    mom: float               # return over the refresh window
    attn: float              # last-24h turnover / 30-day median daily turnover
    turnover_30d: float      # median daily turnover, USDT
    turnover_7d: float       # median daily turnover over the last 7 days, USDT
    history_days: float


@dataclass(frozen=True, slots=True)
class Pick:
    symbol: str
    score: float             # mean rank, lower is better
    vol_7d: float
    mom: float
    attn: float
    turnover_7d: float
    pool_size: int


def eligible(candidates: list[Candidate],
             *, min_turnover: float | None = None,
             min_days: float | None = None,
             top_n: int | None = None) -> list[Candidate]:
    """Liquidity + history filters, then the top N by 30-day median turnover."""
    floor = min_turnover_usdt() if min_turnover is None else min_turnover
    days = min_history_days() if min_days is None else min_days
    keep = [c for c in candidates
            if c.history_days >= days and c.turnover_7d >= floor and c.turnover_30d > 0
            and c.vol_7d > 0]
    keep.sort(key=lambda c: -c.turnover_30d)
    return keep[: (pool_top_n() if top_n is None else top_n)]


def rank_pick(candidates: list[Candidate], **filters) -> Pick | None:
    """The D4 RANK rule: average of the three descending ranks, lowest wins.

    Ties break on turnover (deeper book first), which is decision-free: it only
    orders names the score cannot separate."""
    pool = eligible(candidates, **filters)
    if not pool:
        return None
    n = len(pool)
    if n == 1:
        c = pool[0]
        return Pick(c.symbol, 1.0, c.vol_7d, c.mom, c.attn, c.turnover_7d, n)

    def ranks(key) -> dict[str, float]:
        ordered = sorted(pool, key=lambda c: (-key(c), -c.turnover_30d))
        return {c.symbol: float(i + 1) for i, c in enumerate(ordered)}

    r_vol = ranks(lambda c: c.vol_7d)
    r_mom = ranks(lambda c: c.mom)
    r_attn = ranks(lambda c: c.attn)
    scored = sorted(
        pool,
        key=lambda c: ((r_vol[c.symbol] + r_mom[c.symbol] + r_attn[c.symbol]) / 3.0,
                       -c.turnover_30d),
    )
    best = scored[0]
    score = (r_vol[best.symbol] + r_mom[best.symbol] + r_attn[best.symbol]) / 3.0
    return Pick(best.symbol, round(score, 4), best.vol_7d, best.mom, best.attn,
                best.turnover_7d, n)


def metrics_from_hourly(symbol: str, bars: list[tuple[float, float, float]],
                        *, window_hours: float) -> Candidate | None:
    """Build a Candidate from hourly (timestamp, close, quote turnover) rows.

    Rows must END at or before the refresh instant: this function never looks at
    a bar it is given, so the caller owns the no-look-ahead contract.
    """
    import math
    from collections import defaultdict

    rows = [(float(t), float(c), float(a)) for t, c, a in bars if float(c) > 0]
    rows.sort(key=lambda r: r[0])
    history_days = (rows[-1][0] - rows[0][0]) / 86400.0 if rows else 0.0
    # A SPAN IS NOT A HISTORY. 60 prints spread over 62 days used to pass the
    # 60-day floor and then win every rank: sparse prints annualise like hourly
    # ones (volatility), a multi-week move reads as a 48h move (momentum), and a
    # day's worth of prints collapses into one bucket (attention). Require the
    # bars to be there, not just the first and last timestamps.
    min_bars = max(48, int(min_history_days() * 24.0 * 0.8))
    if len(rows) < min_bars:
        return None
    closes = [r[1] for r in rows]
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
            if closes[i] > 0 and closes[i - 1] > 0]
    tail = rets[-168:]
    if len(tail) < 24:
        return None
    sd = statistics.pstdev(tail)
    vol_7d = sd * math.sqrt(24.0 * 365.0)
    # WALL-CLOCK windows, not bar counts: on a gappy tape "48 bars back" can be
    # 96 hours back, which scores that name on a different move from its rivals.
    cutoff = rows[-1][0] - max(1.0, float(window_hours)) * 3600.0
    base = next((c for t, c, _a in reversed(rows) if t <= cutoff), closes[0])
    mom = (closes[-1] / base - 1.0) if base > 0 else 0.0
    # Turnover bucketed by CALENDAR DAY. Bucketing by row index inflates a gappy
    # tape by 1/fill-rate — largest for the thinnest names, which is backwards
    # for a liquidity floor.
    by_day: dict[int, float] = defaultdict(float)
    for t, _c, a in rows:
        by_day[int(t // 86400)] += a
    ordered_days = sorted(by_day)
    daily = [by_day[d] for d in ordered_days]
    if len(daily) < 2:
        return None
    # The newest bucket is partial unless the tape ends exactly at a day boundary;
    # medians use the completed days, attention compares the last FULL day.
    complete = daily[:-1] if len(daily) > 2 else daily
    turnover_30d = statistics.median(complete[-30:])
    turnover_7d = statistics.median(complete[-7:])
    attn = (complete[-1] / turnover_30d) if turnover_30d > 0 else 0.0
    return Candidate(symbol=symbol.upper(), vol_7d=vol_7d, mom=mom, attn=attn,
                     turnover_30d=turnover_30d, turnover_7d=turnover_7d,
                     history_days=history_days)
