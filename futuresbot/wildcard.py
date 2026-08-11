"""Wildcard strategy — mid-path 'meteorite' continuation, SEPARATE from PMT.

For QUIET regimes when the 6 core PMT pairs are flat: scan the broad MEXC perp
universe for a pair in an EXTREME move (|3h ROC| >= threshold) and join it
MID-FLIGHT via a pullback-resume entry with an exhaustion guard — i.e. the
acceleration phase of a parabolic move, not the start (false breakouts) and not
the vertical climax (reversal). Lower leverage (x5-10) and 10-15% of balance,
reusing the PMT stop-first bank/breakeven exits.

Forward-validated (V1 pullback-resume + exhaustion filter) on the broad universe:
+$74 / 7d (27 picks) where 'early-acceleration' (-$71) and 'ADX-mature' (-$52)
both lost. Noisy/regime-dependent (negative on some 24h stretches) -> SHADOW-only
until live-validated. Pure detection logic; the runtime opens/sizes/manages it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

# 15m bars
ROC_BARS = 12          # 3h look-back for the "extreme move"
ATR_PERIOD = 14
RSI_PERIOD = 14

# Sigma-normalised trigger (trial 6). A FIXED 8%/3h threshold is a ~1.0-sigma
# event on the band's most volatile names and a ~17-sigma event on its quietest
# — a 10-32x spread in rarity, measured across turnover rank 30-90. The sleeve
# therefore samples a completely different population per symbol while believing
# it applies one rule, and its signal is dominated by a handful of high-vol names
# where 8% is routine (BTW breached 8% on 19.2% of ALL its 3h bars).
ROC_SIGMA_LAMBDA = 0.94        # RiskMetrics EWMA
ROC_SIGMA_MIN_SAMPLES = 96     # >= 24h of trailing 3h returns before we trust it
ROC_SIGMA_FLOOR = 0.010        # a dead symbol must not trigger on 1% noise


def _f(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name)
        return float(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def wildcard_enabled() -> bool:
    return _b("FUTURES_WILDCARD_ENABLED", False)


def wildcard_max_positions() -> int:
    """Wildcard slot cap. Default 2 since 2026-07-31 (trial 4): the panel's
    pre-registered trigger was met — shadow-ledger slot_occupied n=15, netR
    +3.00 — and slot occupancy was the dominant cause of missed 7d movers
    (ON +198%, COTI +161%, MMT +113%, CAP +104%, all detected, all blocked).
    The default carries the config because env-only changes produce SKIPPED
    Railway deploys that never restart the container. Squeeze stays at 1
    (see squeeze_max_positions) — it has no such evidence."""
    try:
        return max(1, int(_f("FUTURES_WILDCARD_MAX_POSITIONS", 2)))
    except ValueError:
        return 2


def wildcard_scan_interval_seconds() -> int:
    """Trial 9: 450s, halved from 900s.

    The entry condition is TRANSIENT, and the old grid was the same order of
    magnitude as its lifetime. Measured on GUA_USDT 2026-08-10 by sampling the
    live detector every 5 minutes for 5 hours: the condition held on 3 of 60
    samples (5.0% duty cycle) in ONE unbroken 15-minute window. A 15-minute
    grid places ~1 sample in a 15-minute window, so P(seeing nothing) ~ e^-1 =
    37% per opportunity — and it saw nothing. At 450s the expected samples in
    that window is 2, so P(miss) ~ e^-2 = 13.5%.

    This buys CAPTURE, not arrival: ~63% -> ~87% of signals observed, about
    +37% more entries from the same market. Cost is 2x the kline calls."""
    return max(60, int(_f("FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS", 450)))


def wildcard_min_turnover_usdt() -> float:
    return _f("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 3_000_000.0)


def wildcard_sigma_trigger_enabled() -> bool:
    """Trial 6, default OFF. Arm only with a shadow comparison in hand.

    Pre-registration: switching this on should produce roughly 3x FEWER fires on
    roughly the SAME names (the gain measured offline came from raising the bar
    on the vol-leaders the sleeve already trades, NOT from broadening the
    universe). If shadow instead shows migration to low-vol names, the mechanism
    finding is wrong and this must be switched back off."""
    return _b("FUTURES_WILDCARD_SIGMA_TRIGGER", False)


def wildcard_long_only() -> bool:
    """Trial 6, default ON. The convex -1R/+5R design is a LONG-side design.

    A short's payoff is bounded at 1/sl_frac (price cannot go below zero), so at
    the live 3.0xATR stop a +5R short needs a ~60% collapse against a long's
    ~60% rally — 1.7x further in log space — and 21% of short signals were being
    handed a target at or below zero. Measured ladder is monotone UP in target
    for longs and monotone DOWN for shorts. Shorts are still DETECTED and shadow
    -logged so the question stays answerable; they are simply not taken."""
    return _b("FUTURES_WILDCARD_LONG_ONLY", True)


@dataclass(frozen=True, slots=True)
class WildcardSignal:
    symbol: str
    side: str               # LONG / SHORT
    entry_price: float
    leverage: int
    roc_pct: float          # the 3h extreme move that qualified it
    atr_pct: float
    sl_price: float
    tp_price: float
    sl_margin_pct: float
    tp_margin_pct: float
    balance_fraction: float
    rsi: float
    roc_z: float | None = None          # trigger in the symbol's own sigma
    sl_frac_designed: float | None = None   # pre-margin-cap stop distance


def _atr_pct(frame: pd.DataFrame) -> float | None:
    if len(frame) < ATR_PERIOD + 2:
        return None
    h = frame["high"].astype(float); l = frame["low"].astype(float); c = frame["close"].astype(float)
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = float(tr.iloc[-ATR_PERIOD:].mean())
    px = float(c.iloc[-1])
    return atr / px if px > 0 and atr > 0 else None


def _rsi(frame: pd.DataFrame) -> float:
    c = frame["close"].astype(float)
    d = c.diff().iloc[-RSI_PERIOD:]
    gain = float(d.clip(lower=0).mean()); loss = float(-d.clip(upper=0).mean())
    if loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


def _roc_sigma(frame: pd.DataFrame) -> float | None:
    """EWMA sigma of this symbol's own trailing 3h log returns.

    STRICTLY TRAILING: the final ROC_BARS returns are dropped because they
    overlap the trigger bar itself — including them would let the move being
    tested inflate its own yardstick.
    """
    c = frame["close"].astype(float)
    ratio = c / c.shift(ROC_BARS)
    r = np.log(ratio.where(ratio > 0)).dropna()
    if len(r) <= ROC_BARS:
        return None
    r = r.iloc[:-ROC_BARS]                      # drop the overlap with the trigger
    if len(r) < ROC_SIGMA_MIN_SAMPLES:
        return None
    var = r.pow(2).ewm(alpha=1.0 - ROC_SIGMA_LAMBDA, adjust=False).mean().iloc[-1]
    if not np.isfinite(var) or var <= 0:
        return None
    return max(float(var) ** 0.5, ROC_SIGMA_FLOOR)


def _rej(reasons, tag):
    if reasons is not None:
        reasons.append(tag)
    return None


def detect_wildcard_signal(frame: pd.DataFrame, symbol: str, reasons: list[str] | None = None) -> WildcardSignal | None:
    """V1 pullback-resume + exhaustion guard. Returns a signal or None.

    Gates (all on completed bars, no look-ahead):
      1. EXTREME move: |3h ROC| >= FUTURES_WILDCARD_MIN_ROC (0.08).
      2. PULLBACK-RESUME: prior bar pulled back against the move, current bar
         resumes in the move direction (flag/pennant continuation entry).
      3. EXHAUSTION GUARD: RSI has room (long<max / short>min); the current bar
         is not a climax (closed near its extreme, small adverse wick); and the
         last bar is not the vertical blow-off (|1-bar move| < 2x ATR).
      4. VOLUME: breakout-bar volume expansion (z >= min).
    """
    if frame is None or "close" not in frame or len(frame) < ROC_BARS + ATR_PERIOD + 2:
        return _rej(reasons, "short_frame")
    c = frame["close"].astype(float); h = frame["high"].astype(float); l = frame["low"].astype(float)
    cur = float(c.iloc[-1]); prev = float(c.iloc[-2]); prev2 = float(c.iloc[-3])
    base = float(c.iloc[-(ROC_BARS + 1)])
    if cur <= 0 or base <= 0:
        return _rej(reasons, "bad_price")
    roc = cur / base - 1.0
    roc_z = None
    if wildcard_sigma_trigger_enabled():
        sigma = _roc_sigma(frame)
        if sigma is None:
            return _rej(reasons, "no_roc_sigma")
        roc_z = float(np.log(cur / base)) / sigma
        if abs(roc_z) < _f("FUTURES_WILDCARD_MIN_ROC_Z", 4.0):
            return _rej(reasons, "roc_z_below_min")
    elif abs(roc) < _f("FUTURES_WILDCARD_MIN_ROC", 0.08):
        return _rej(reasons, "roc_below_min")
    side = "LONG" if roc > 0 else "SHORT"
    s = 1 if side == "LONG" else -1

    # 2. pullback-resume — the single largest filter in the detector, rejecting
    # ~76% of all trigger bars (325 of ~425 in a measured live day). It demands
    # a specific 3-bar shape (down bar, then up bar), which a random walk
    # supplies ~25% of the time. It has never been measured for value; the flag
    # exists so both arms can be replayed offline. Default unchanged.
    if _b("FUTURES_WILDCARD_REQUIRE_PULLBACK", True):
        resumed = (cur > prev) if s > 0 else (cur < prev)
        pulled_back = (prev < prev2) if s > 0 else (prev > prev2)
        if not (resumed and pulled_back):
            return _rej(reasons, "no_pullback_resume")

    # 3. exhaustion guard
    rsi = _rsi(frame)
    rsi_max = _f("FUTURES_WILDCARD_RSI_MAX", 90.0); rsi_min = _f("FUTURES_WILDCARD_RSI_MIN", 10.0)
    if (s > 0 and rsi >= rsi_max) or (s < 0 and rsi <= rsi_min):
        return _rej(reasons, "rsi_exhausted")
    bar_h = float(h.iloc[-1]); bar_l = float(l.iloc[-1]); rng = bar_h - bar_l
    if rng > 0:
        adverse_wick = ((bar_h - cur) if s > 0 else (cur - bar_l)) / rng
        if adverse_wick > _f("FUTURES_WILDCARD_MAX_WICK", 0.45):  # climax/reversal candle
            return _rej(reasons, "climax_wick")
    atr_pct = _atr_pct(frame)
    if atr_pct is None or atr_pct <= 0:
        return _rej(reasons, "no_atr")
    if abs(cur / prev - 1.0) > _f("FUTURES_WILDCARD_VERTICAL_ATR_MULT", 2.0) * atr_pct:  # vertical blow-off
        return _rej(reasons, "vertical_blowoff")

    # 4. volume expansion
    if "volume" in frame and len(frame) >= 22:
        v = frame["volume"].astype(float)
        b = v.iloc[-21:-1]; mu = float(b.mean()); sd = float(b.std())
        if sd > 0 and (float(v.iloc[-1]) - mu) / sd < _f("FUTURES_WILDCARD_MIN_VOL_Z", 1.0):
            return _rej(reasons, "low_volume_z")

    leverage = int(min(10.0, max(5.0, _f("FUTURES_WILDCARD_LEVERAGE", 7.0))))
    sl_frac = _f("FUTURES_WILDCARD_SL_ATR_MULT", 1.5) * atr_pct
    sl_frac_designed = sl_frac          # pre-cap, volatility-derived stop distance
    tp_r = _f("FUTURES_WILDCARD_TP_R", 5.0)
    # Hard cap on per-trade stop-loss (margin %). A 1.5xATR stop on a high-ATR
    # alt at x5-10 can lose 60-70% of margin (SIREN 2026-06-15 = -68.8%). Cap it
    # by trimming leverage first (preserves the ATR stop DISTANCE so the trade
    # still has room), then only tighten the stop itself if even x1 would breach.
    max_sl_margin = _f("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", 20.0)
    if max_sl_margin > 0 and sl_frac > 0:
        if sl_frac * leverage * 100.0 > max_sl_margin:
            leverage = max(1, int(max_sl_margin / (sl_frac * 100.0)))
        if sl_frac * leverage * 100.0 > max_sl_margin:  # even x1 stop too wide
            sl_frac = max_sl_margin / 100.0 / leverage
    sl_margin = sl_frac * leverage * 100.0
    tp_margin = tp_r * sl_margin
    sl_price = cur * (1 - sl_frac) if s > 0 else cur * (1 + sl_frac)
    # Target distance. Optionally anchored to the volatility-DESIGNED stop rather
    # than the margin-capped one, so the cap sizes risk without also relocating a
    # price target (it binds ~9% of signals at 3.0xATR). Default OFF: it breaks
    # the identity target == tp_r x realised-R, which every R-based report assumes.
    tp_base = sl_frac
    if _b("FUTURES_WILDCARD_TP_FROM_DESIGNED_STOP", False) and sl_frac_designed > 0:
        tp_base = sl_frac_designed
    tp_dist = tp_base * tp_r
    # SHORTS ARE BOUNDED: price cannot go below zero, so tp_dist >= 1.0 puts the
    # target at or through zero — a mathematically unreachable order. Measured at
    # the live 3.0xATR stop this hit 21% of short signals, silently converting
    # them into stop-or-nothing positions. Clamp and record it.
    if s < 0 and tp_dist >= _f("FUTURES_WILDCARD_MAX_SHORT_TP_DIST", 0.50):
        tp_dist = _f("FUTURES_WILDCARD_MAX_SHORT_TP_DIST", 0.50)
        if reasons is not None:
            reasons.append("short_tp_clamped")
    tp_price = cur * (1 + tp_dist) if s > 0 else cur * (1 - tp_dist)
    return WildcardSignal(
        symbol=symbol.upper(), side=side, entry_price=cur, leverage=leverage,
        roc_pct=roc, atr_pct=atr_pct, sl_price=sl_price, tp_price=tp_price,
        sl_margin_pct=round(sl_margin, 4), tp_margin_pct=round(tp_margin, 4),
        balance_fraction=min(0.15, max(0.05, _f("FUTURES_WILDCARD_BALANCE_PCT", 0.12))),
        rsi=round(rsi, 1),
        roc_z=(round(roc_z, 3) if roc_z is not None else None),
        sl_frac_designed=round(sl_frac_designed, 6),
    )
