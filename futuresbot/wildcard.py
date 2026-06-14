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

import pandas as pd

# 15m bars
ROC_BARS = 12          # 3h look-back for the "extreme move"
ATR_PERIOD = 14
RSI_PERIOD = 14


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
    try:
        return max(1, int(_f("FUTURES_WILDCARD_MAX_POSITIONS", 1)))
    except ValueError:
        return 1


def wildcard_scan_interval_seconds() -> int:
    return max(60, int(_f("FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS", 900)))  # 15m default


def wildcard_min_turnover_usdt() -> float:
    return _f("FUTURES_WILDCARD_MIN_TURNOVER_USDT", 3_000_000.0)


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


def detect_wildcard_signal(frame: pd.DataFrame, symbol: str) -> WildcardSignal | None:
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
        return None
    c = frame["close"].astype(float); h = frame["high"].astype(float); l = frame["low"].astype(float)
    cur = float(c.iloc[-1]); prev = float(c.iloc[-2]); prev2 = float(c.iloc[-3])
    base = float(c.iloc[-(ROC_BARS + 1)])
    if cur <= 0 or base <= 0:
        return None
    roc = cur / base - 1.0
    if abs(roc) < _f("FUTURES_WILDCARD_MIN_ROC", 0.08):
        return None
    side = "LONG" if roc > 0 else "SHORT"
    s = 1 if side == "LONG" else -1

    # 2. pullback-resume
    resumed = (cur > prev) if s > 0 else (cur < prev)
    pulled_back = (prev < prev2) if s > 0 else (prev > prev2)
    if not (resumed and pulled_back):
        return None

    # 3. exhaustion guard
    rsi = _rsi(frame)
    rsi_max = _f("FUTURES_WILDCARD_RSI_MAX", 90.0); rsi_min = _f("FUTURES_WILDCARD_RSI_MIN", 10.0)
    if (s > 0 and rsi >= rsi_max) or (s < 0 and rsi <= rsi_min):
        return None
    bar_h = float(h.iloc[-1]); bar_l = float(l.iloc[-1]); rng = bar_h - bar_l
    if rng > 0:
        adverse_wick = ((bar_h - cur) if s > 0 else (cur - bar_l)) / rng
        if adverse_wick > _f("FUTURES_WILDCARD_MAX_WICK", 0.45):  # climax/reversal candle
            return None
    atr_pct = _atr_pct(frame)
    if atr_pct is None or atr_pct <= 0:
        return None
    if abs(cur / prev - 1.0) > _f("FUTURES_WILDCARD_VERTICAL_ATR_MULT", 2.0) * atr_pct:  # vertical blow-off
        return None

    # 4. volume expansion
    if "volume" in frame and len(frame) >= 22:
        v = frame["volume"].astype(float)
        b = v.iloc[-21:-1]; mu = float(b.mean()); sd = float(b.std())
        if sd > 0 and (float(v.iloc[-1]) - mu) / sd < _f("FUTURES_WILDCARD_MIN_VOL_Z", 1.0):
            return None

    leverage = int(min(10.0, max(5.0, _f("FUTURES_WILDCARD_LEVERAGE", 7.0))))
    sl_frac = _f("FUTURES_WILDCARD_SL_ATR_MULT", 1.5) * atr_pct
    tp_r = _f("FUTURES_WILDCARD_TP_R", 5.0)
    sl_margin = sl_frac * leverage * 100.0
    tp_margin = tp_r * sl_margin
    sl_price = cur * (1 - sl_frac) if s > 0 else cur * (1 + sl_frac)
    tp_price = cur * (1 + sl_frac * tp_r) if s > 0 else cur * (1 - sl_frac * tp_r)
    return WildcardSignal(
        symbol=symbol.upper(), side=side, entry_price=cur, leverage=leverage,
        roc_pct=roc, atr_pct=atr_pct, sl_price=sl_price, tp_price=tp_price,
        sl_margin_pct=round(sl_margin, 4), tp_margin_pct=round(tp_margin, 4),
        balance_fraction=min(0.15, max(0.05, _f("FUTURES_WILDCARD_BALANCE_PCT", 0.12))),
        rsi=round(rsi, 1),
    )
