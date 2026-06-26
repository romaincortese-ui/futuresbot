"""Squeeze-breakout ("Coiled Spring") — volatility-IGNITION entry, SEPARATE from
the wildcard's momentum-CONTINUATION chase.

Thesis (see session research): we always entered LATE. This enters EARLY — the
instant a multi-bar volatility SQUEEZE (Bollinger inside Keltner, the TTM coil)
RELEASES on a volume-backed break of the coil's range. The edge is not direction
prediction (efficient/edgeless); it's (1) volatility clustering — the expansion
persists once it starts; (2) order-flow — everyone watches the same coil, so the
break triggers clustered stops/breakout entries; (3) convexity — the stop is the
coil boundary (genuinely tight), so a <50% hit rate still pays. Long-biased by
default (crypto time-series-momentum shorts get flattened by upward jumps).

Pure detection. The runtime sizes/opens/manages it and (via metadata wildcard=1)
reuses the wildcard's -20% SL cap + the convex exit. 15m bars.
"""
from __future__ import annotations

import os

import pandas as pd

from futuresbot.wildcard import WildcardSignal, _atr_pct, _f, _rsi

BB_PERIOD = 20
KC_PERIOD = 20


def squeeze_enabled() -> bool:
    raw = os.environ.get("FUTURES_SQUEEZE_ENABLED")
    return raw is not None and raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _atr_series(frame: pd.DataFrame, n: int) -> pd.Series:
    h = frame["high"].astype(float); l = frame["low"].astype(float); c = frame["close"].astype(float)
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def detect_squeeze_signal(frame: pd.DataFrame, symbol: str) -> WildcardSignal | None:
    """TTM-style squeeze release. Returns a WildcardSignal-compatible signal or None.

    Gates (completed bars, no look-ahead):
      1. COIL: Bollinger(20,k) sat INSIDE Keltner(20,mult*ATR) for >= MIN_SQUEEZE_LEN
         consecutive bars ending on the prior bar (a real multi-bar squeeze).
      2. RELEASE: the squeeze is OFF on the current bar (bands expanded).
      3. BREAK: current close breaks the coil's range (Donchian high/low over the
         squeeze window) -> that direction. Long-biased unless SHORTs are enabled.
      4. VOLUME: breakout-bar volume expansion (z >= min).
      5. NOT a vertical climax (|1-bar move| < VERT*ATR) — don't buy the spike top.
    """
    need = max(BB_PERIOD, KC_PERIOD) + 30
    if frame is None or "close" not in frame or len(frame) < need:
        return None
    c = frame["close"].astype(float); h = frame["high"].astype(float); l = frame["low"].astype(float)
    bb_k = _f("FUTURES_SQUEEZE_BB_K", 2.0)
    kc_m = _f("FUTURES_SQUEEZE_KC_MULT", 1.5)
    mid = c.rolling(BB_PERIOD).mean(); sd = c.rolling(BB_PERIOD).std()
    bb_up = mid + bb_k * sd; bb_lo = mid - bb_k * sd
    ema = _ema(c, KC_PERIOD); atr = _atr_series(frame, KC_PERIOD)
    kc_up = ema + kc_m * atr; kc_lo = ema - kc_m * atr
    squeeze_on = (bb_up < kc_up) & (bb_lo > kc_lo)
    if not bool(squeeze_on.iloc[-2]):
        return None  # the coil must be active right up to the breakout bar
    # count the coil length ending at the prior bar (excludes the breakout bar)
    coil = 0
    for i in range(2, len(squeeze_on) + 1):
        if bool(squeeze_on.iloc[-i]):
            coil += 1
        else:
            break
    min_len = int(_f("FUTURES_SQUEEZE_MIN_LEN", 6))
    if coil < min_len:
        return None

    cur = float(c.iloc[-1])
    # break/stop reference = the RECENT tight range (not the smeared full coil,
    # which can carry stale highs from before volatility collapsed).
    rb = min(coil, int(_f("FUTURES_SQUEEZE_RANGE_LB", 6)))
    coil_hi = float(h.iloc[-(rb + 1):-1].max()); coil_lo = float(l.iloc[-(rb + 1):-1].min())
    long_only = os.environ.get("FUTURES_SQUEEZE_LONG_ONLY", "1").strip().lower() in {"1", "true", "yes", "y", "on"}
    if cur > coil_hi:
        side, s = "LONG", 1
    elif cur < coil_lo and not long_only:
        side, s = "SHORT", -1
    else:
        return None  # no decisive break of the coil range

    atr_pct = _atr_pct(frame)
    if atr_pct is None or atr_pct <= 0:
        return None
    # No RSI gate: a genuine squeeze RELEASE spikes RSI on the break bar by design
    # (the coil already guarantees we were not extended). Kept only for the signal.
    rsi = _rsi(frame)
    # climax guard: don't buy a vertical blow-off bar (the spike top)
    prev = float(c.iloc[-2])
    if abs(cur / prev - 1.0) > _f("FUTURES_SQUEEZE_VERTICAL_ATR_MULT", 3.0) * atr_pct:
        return None
    # volume expansion on the breakout bar
    if "volume" in frame and len(frame) >= 22:
        v = frame["volume"].astype(float)
        b = v.iloc[-21:-1]; mu = float(b.mean()); std = float(b.std())
        if std > 0 and (float(v.iloc[-1]) - mu) / std < _f("FUTURES_SQUEEZE_MIN_VOL_Z", 1.0):
            return None

    # Stop = the coil boundary we just broke out of (structural), floored so a
    # razor-thin coil doesn't whipsaw. This is the convexity: tight, real stop.
    floor_frac = _f("FUTURES_SQUEEZE_SL_ATR_FLOOR", 0.8) * atr_pct
    if s > 0:
        sl_frac = max((cur - coil_lo) / cur, floor_frac)
    else:
        sl_frac = max((coil_hi - cur) / cur, floor_frac)
    sl_frac = min(sl_frac, _f("FUTURES_SQUEEZE_SL_ATR_CAP", 2.5) * atr_pct)  # don't let a wide coil = huge stop
    tp_r = _f("FUTURES_SQUEEZE_TP_R", 5.0)
    leverage = int(min(10.0, max(5.0, _f("FUTURES_SQUEEZE_LEVERAGE", 7.0))))
    # reuse the wildcard -20% margin SL cap: trim leverage first, then the stop.
    max_sl_margin = _f("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", 20.0)
    if max_sl_margin > 0 and sl_frac > 0:
        if sl_frac * leverage * 100.0 > max_sl_margin:
            leverage = max(1, int(max_sl_margin / (sl_frac * 100.0)))
        if sl_frac * leverage * 100.0 > max_sl_margin:
            sl_frac = max_sl_margin / 100.0 / leverage
    sl_margin = sl_frac * leverage * 100.0
    tp_margin = tp_r * sl_margin
    sl_price = cur * (1 - sl_frac) if s > 0 else cur * (1 + sl_frac)
    tp_price = cur * (1 + sl_frac * tp_r) if s > 0 else cur * (1 - sl_frac * tp_r)
    # breakout strength (used as the cross-universe ranking score), as a "roc"
    roc = (cur / coil_hi - 1.0) if s > 0 else (coil_lo / cur - 1.0)
    return WildcardSignal(
        symbol=symbol.upper(), side=side, entry_price=cur, leverage=leverage,
        roc_pct=roc, atr_pct=atr_pct, sl_price=sl_price, tp_price=tp_price,
        sl_margin_pct=round(sl_margin, 4), tp_margin_pct=round(tp_margin, 4),
        balance_fraction=min(0.15, max(0.05, _f("FUTURES_SQUEEZE_BALANCE_PCT", 0.12))),
        rsi=round(rsi, 1),
    )
