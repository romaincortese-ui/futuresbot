"""BIG-3 TREND sleeve — sustained multi-hour directional moves on BTC/ETH/SOL.

WHY THIS EXISTS. On 2026-08-19 the US Treasury doubled its long-dated bond
buybacks and the SEC proposed a crypto framework; ETH ran +17.4%/24h, SOL
+11.7%, BTC +8.3%, amplified by $1.11B of short liquidations on BTC alone. The
bot could not touch any of it, and not by accident — three independent blocks:

  - the WILDCARD excludes majors by design (its edge is the small-cap band) and
    triggers on a 3h impulse; BTC's peak 3h was +6.00% and SOL's +6.16%, under
    its 8% floor. ETH's peak 3h was +9.45% and DID clear the floor — then died
    on the pullback-resume shape filter, 7 times.
  - the SQUEEZE needs a Bollinger-inside-Keltner coil to RELEASE. Replayed over
    those 72h it produced 0 signals on all three: 285/247/230 bars rejected
    "no_active_coil". These markets were EXPANDED, not coiled. It is the wrong
    detector for a trend, not a dormant one that happened to miss.
  - PMT, the only sleeve that ever traded majors, is decommissioned.

So the gap was structural. This sleeve is the narrowest thing that closes it.

WHAT IT DETECTS. A 24h return clearing a threshold, confirmed by a NEW 24h
CLOSING extreme in the same direction — i.e. the move is still being made, not
being faded. Deliberately absent: no pullback-resume (it vetoed the ETH move
seven times and its own A/B could not prove it pays), no majors exclusion (the
whole point), no coil requirement.

EVIDENCE, and its limits. Over 63d x 29 majors the rule beat a RANDOM-ENTRY
control — same universe, sizing and exits — by $50-105 per 120 trades in all 27
parameter cells tested; the control itself bled -$0.389/trade, so the convex
exit structure loses money on a random draw and the trend filter more than pays
for it. But no cell exceeded 5/8 positive windows and the parameter surface is
non-monotonic. This is a LEAN, not a proven edge, and it goes live as a
real-money observation test — exactly as the wildcard did.

Pure detection. The runtime sizes, opens and manages it; via metadata trend=1 +
wildcard=1 it inherits the -20% SL cap and the convex exit stack.
"""
from __future__ import annotations

import os

import pandas as pd

from futuresbot.wildcard import ATR_PERIOD, WildcardSignal, _atr_pct, _b, _f, _rsi

DEFAULT_SYMBOLS = ("BTC_USDT", "ETH_USDT", "SOL_USDT")


def trend_enabled() -> bool:
    raw = os.environ.get("FUTURES_TREND_ENABLED")
    return raw is not None and raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def trend_symbols() -> tuple[str, ...]:
    """The big 3 by default. A named tier, not a turnover ranking: this sleeve
    is sized and stopped for instruments whose ATR is small and whose books are
    deep, and that is a property of these three specifically."""
    raw = (os.environ.get("FUTURES_TREND_SYMBOLS") or "").strip()
    if not raw:
        return DEFAULT_SYMBOLS
    out = tuple(s.strip().upper() for s in raw.split(",") if s.strip())
    return out or DEFAULT_SYMBOLS


def trend_max_positions() -> int:
    """Three by default — one per big-3 name, which is the natural ceiling since
    the scan already refuses a symbol it is holding.

    Measured 2026-08-20, 63d x 8 windows, long arm, shipped detector and exits:

        slots   net $    trades   maxDD    return/DD
          1     +6.45      19    -15.62      0.41
          2    +14.31      25    -18.19      0.79
          3    +16.12      30    -17.64      0.91

    Return more than doubles while drawdown rises 13%, and the third slot
    LOWERS drawdown against the second. That is not what adding leverage looks
    like. BTC/ETH are correlated at r=+0.914, so the naive expectation was that
    three concurrent longs are one 3x bet — but the entries fire at different
    moments (each name sets its own new 24h closing extreme), so the holdings
    only partly overlap and the diversification is real."""
    try:
        return max(1, int(_f("FUTURES_TREND_MAX_POSITIONS", 3)))
    except ValueError:
        return 3


def trend_scan_interval_seconds() -> int:
    return max(60, int(_f("FUTURES_TREND_SCAN_INTERVAL_SECONDS", 900.0)))


def trend_long_only() -> bool:
    """Shorts are DETECTED by default and taken unless this is on.

    Shipped bidirectional on 2026-08-20 at the operator's request, with the
    caveat recorded that the 90-day drift-controlled study put the entire edge
    in the LONGS and the probe behind this sleeve was long-only. Measuring the
    short arm on the big 3 the same day settled it:

        arm          1 slot    2 slots   3 slots   win%
        LONG only    +$6.45   +$14.31   +$16.12   53%
        SHORT only  -$14.05   -$24.78   -$33.64   24% and falling

    Shorts lose, and slots AMPLIFY whichever arm they are given — so shipping
    the 3-slot change with shorts enabled would have taken the sleeve to its
    worst configuration of all (-$17.51). The two are coupled, which is why the
    default flipped with the slot count.

    Set FUTURES_TREND_LONG_ONLY=0 to restore shorts; env-only, no deploy. Short
    signals are still DETECTED and shadow-logged either way, so the question
    stays answerable from live data."""
    return _b("FUTURES_TREND_LONG_ONLY", True)


def _rej(reasons, tag):
    if reasons is not None:
        reasons.append(tag)
    return None


def lookback_bars() -> int:
    """Min15 bars in the return window (24h = 96)."""
    return max(8, int(_f("FUTURES_TREND_LOOKBACK_HOURS", 24.0) * 4))


def detect_trend_signal(frame: pd.DataFrame, symbol: str,
                        reasons: list[str] | None = None) -> WildcardSignal | None:
    """Sustained-trend entry. Returns a signal or None.

    Gates, all on completed bars, no look-ahead:
      1. |lookback-hour return| >= FUTURES_TREND_MIN_ROC (0.04).
      2. NEW CLOSING EXTREME over the same window, in the move's direction.
         CLOSING, not intraday: an intraday-high test demands the close sit
         within a whisker of the bar's own high, which a violent 15m bar never
         does — the first version of the probe used the intraday form and
         filtered out the entire ETH move it was written to catch.
      3. Optional RSI exhaustion cap, default OFF: it is untested, and the rule
         that was measured did not include one.
    """
    lb = lookback_bars()
    if frame is None or "close" not in frame or len(frame) < lb + ATR_PERIOD + 2:
        return _rej(reasons, "short_frame")
    c = frame["close"].astype(float)
    cur = float(c.iloc[-1])
    base = float(c.iloc[-(lb + 1)])
    if cur <= 0 or base <= 0:
        return _rej(reasons, "bad_price")
    roc = cur / base - 1.0
    if abs(roc) < _f("FUTURES_TREND_MIN_ROC", 0.04):
        return _rej(reasons, "roc_below_min")
    side = "LONG" if roc > 0 else "SHORT"
    s = 1 if side == "LONG" else -1

    window = c.iloc[-(lb + 1):-1]
    if s > 0 and cur < float(window.max()):
        return _rej(reasons, "no_new_extreme")
    if s < 0 and cur > float(window.min()):
        return _rej(reasons, "no_new_extreme")

    rsi = _rsi(frame)
    rsi_max = _f("FUTURES_TREND_RSI_MAX", 0.0)
    rsi_min = _f("FUTURES_TREND_RSI_MIN", 0.0)
    if rsi_max > 0 and s > 0 and rsi >= rsi_max:
        return _rej(reasons, "rsi_exhausted")
    if rsi_min > 0 and s < 0 and rsi <= rsi_min:
        return _rej(reasons, "rsi_exhausted")

    atr_pct = _atr_pct(frame)
    if atr_pct is None or atr_pct <= 0:
        return _rej(reasons, "no_atr")

    leverage = int(min(20.0, max(1.0, _f("FUTURES_TREND_LEVERAGE_MAX", 10.0))))
    sl_frac = _f("FUTURES_TREND_SL_ATR_MULT", 3.0) * atr_pct
    sl_frac_designed = sl_frac
    tp_r = _f("FUTURES_TREND_TP_R", 3.0)
    # Same hard cap the wildcard carries, and for the same reason: trim LEVERAGE
    # first so the ATR stop keeps its distance, and only tighten the stop if even
    # x1 would breach. On a major the ATR is small, so this is what re-derives
    # x5-x10 — the leverage is a consequence of a tight stop, not a risk choice,
    # and the dollar risk per trade is unchanged.
    max_sl_margin = _f("FUTURES_TREND_MAX_SL_MARGIN_PCT", 20.0)
    if max_sl_margin > 0 and sl_frac > 0:
        if sl_frac * leverage * 100.0 > max_sl_margin:
            leverage = max(1, int(max_sl_margin / (sl_frac * 100.0)))
        if sl_frac * leverage * 100.0 > max_sl_margin:
            sl_frac = max_sl_margin / 100.0 / leverage
    sl_margin = sl_frac * leverage * 100.0
    tp_margin = tp_r * sl_margin
    sl_price = cur * (1 - sl_frac) if s > 0 else cur * (1 + sl_frac)

    tp_dist = sl_frac * tp_r
    # Shorts are bounded below by zero; same clamp the wildcard applies.
    max_short = _f("FUTURES_TREND_MAX_SHORT_TP_DIST", 0.50)
    if s < 0 and tp_dist >= max_short:
        tp_dist = max_short
        if reasons is not None:
            reasons.append("short_tp_clamped")
    tp_price = cur * (1 + tp_dist) if s > 0 else cur * (1 - tp_dist)

    return WildcardSignal(
        symbol=symbol.upper(), side=side, entry_price=cur, leverage=leverage,
        roc_pct=roc, atr_pct=atr_pct, sl_price=sl_price, tp_price=tp_price,
        sl_margin_pct=round(sl_margin, 4), tp_margin_pct=round(tp_margin, 4),
        balance_fraction=min(0.15, max(0.05, _f("FUTURES_TREND_BALANCE_PCT", 0.12))),
        rsi=round(rsi, 1),
        sl_frac_designed=round(sl_frac_designed, 6),
    )
