"""Trials 24 and 25: the random-tick strategy, live (FUTURES_RANDOM_MODE_ENABLED, default OFF).

THE FROZEN DEFINITIONS. Two registered configurations; which one a tick runs is read from
four settings ONCE per tick (`config()`), and every position and tick-journal row is
stamped with the effective values and the tag of the PREREG they match:
  - TRIAL 24 = wc/RANDOM/PREREG.md (sha256 29fabd853a4f5d77...) with the interpretations
    its backtest had to choose (wc/RANDOM/build/DEVIATIONS.md): ticks every 12h
    (00:00Z, 12:00Z), side by a fair coin, TREND stop 3.0 x ATR14%, WILDCARD ticker 24h
    turnover >= $2M. FUTURES_RANDOM_TICK_HOURS=12, FUTURES_RANDOM_SIDE_MODE=coin,
    FUTURES_TREND_SL_ATR_MULT=3.0, FUTURES_RANDOM_WC_MIN_TURNOVER=2000000 - also what
    unset or blank settings give.
  - TRIAL 25 = wc/TRIAL25/PREREG.md (sha256 23840ce65807b549...; rank 2 of wc/OPTIMUM,
    `6h|NNN|liq0|3.5`): ticks every 6h (00:00Z, 06:00Z, 12:00Z, 18:00Z), natural side
    for every bucket (TREND LONG, WILDCARD-long LONG, WILDCARD-short SHORT; no coin),
    TREND stop 3.5 x ATR14%, WILDCARD turnover >= $2M. Everything else as trial 24.
  - Any other valid combination runs, stamped "unregistered", and the owner is alerted;
    an invalid value stops the ticks (not processed) and alerts - never a silent fallback.
This module is the backtest's selection code moved into the package: `wildcard_row`,
`trend_row` and `rank` are ports of wc/RANDOM/build/_scripts/b02_candidates.py, line for
line, and `build_signal` is the detectors' own stop / leverage / target arithmetic
(wildcard.py, trend.py) applied to the side the tick chose instead of the detector's.

What one tick does (the runtime drives it, see FuturesRuntime._maybe_random_tick):
  - at every tick of the cadence, using only 15m bars CLOSED before the tick;
  - three buckets, in this order: TREND, WILDCARD-long, WILDCARD-short;
  - each bucket ranks its candidates (detector passes first, then the fallback by the
    bucket's own ROC), skips symbols already held, and opens at most ONE position if
    its sleeve has a free slot (TREND 2, WILDCARD 3 shared by both WILDCARD buckets);
  - the direction is a fair coin from os.urandom (side mode coin), or the bucket's
    natural side (side mode natural, no coin drawn);
  - sizing and exits are the live ones, unchanged (a TREND stop multiple moves 1R's
    price distance; every R-based level follows it).
Runtime-level gates the backtest did NOT apply (calm-ratio cap, long 24h-range cap,
external listing veto, entry envelope, lateness re-ranking, preemption) are not applied.

Pure helpers: no I/O, no clock reads except where a function says so.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

import pandas as pd

from futuresbot.trend import detect_trend_signal
from futuresbot.wildcard import (
    WildcardSignal,
    _atr_pct,
    _b,
    _f,
    _rsi,
    calm_ratio,
    detect_wildcard_signal,
)

PREREG_SHA256 = "29fabd853a4f5d77526a544f528692c733e55d8b667f24e119c6a095bf9d94b6"
PREREG_TAG = PREREG_SHA256[:16]                                    # trial 24
PREREG25_SHA256 = "23840ce65807b549a406a531c0b05d4b677ead981c84ad0c8fc4f5ecc4a8e89f"
PREREG25_TAG = PREREG25_SHA256[:16]                                # trial 25
UNREGISTERED = "unregistered"

# ---- the frozen definition ---------------------------------------------------------
TICK_SECONDS = 12 * 3600            # default (trial 24): 00:00Z and 12:00Z (the epoch is 00:00Z, 43200 | 86400)
TICK_HOURS_ALLOWED = (12, 6)        # FUTURES_RANDOM_TICK_HOURS; 6 = 00:00Z, 06:00Z, 12:00Z, 18:00Z
SIDE_MODES = ("coin", "natural")    # FUTURES_RANDOM_SIDE_MODE
BAR_SECONDS = 900                   # 15m bars
# A tick is processed by the first cycle after it. A restart (or a pause) that lands
# within this grace still processes the tick once; later than that the tick is skipped
# and the bot waits for the next one, because the entry would no longer be "at the tick"
# - the backtest filled at the next 1m open after it.
TICK_GRACE_SECONDS = 15 * 60
# The longest a tick waits for positions the backtest would already have closed at it
# (24h clock from the tick 24h earlier; live measures the clock from the fill, a few
# seconds to minutes later). Kept inside the grace so a stuck close cannot lose the tick.
TICK_DEFER_SECONDS = 10 * 60

BUCKETS = ("TREND", "WC_LONG", "WC_SHORT")                   # PREREG's listed order
SLEEVE = {"TREND": "TREND", "WC_LONG": "WILDCARD", "WC_SHORT": "WILDCARD"}
NATURAL = {"TREND": "LONG", "WC_LONG": "LONG", "WC_SHORT": "SHORT"}
KEY = {"TREND": "roc24h", "WC_LONG": "roc3h", "WC_SHORT": "roc3h"}

# WILDCARD universe (PREREG): USDT perps outside the top-24 turnover majors band,
# 24h turnover >= $2M, 24h range >= 7%. Fixed here, not read from the scan's env; the
# turnover floor is the default of FUTURES_RANDOM_WC_MIN_TURNOVER.
MAJORS_BAND = 24
UNIVERSE_MIN_TURNOVER = 2_000_000.0
UNIVERSE_MIN_RANGE = 0.07

WC_BARS = 200                        # b02: 200 completed 15m bars per WILDCARD symbol
TREND_BARS = 400                     # b02: 400 completed 15m bars per TREND symbol
TOP_N = 10                           # b02 keeps the top 10 of each bucket

# Metadata keys a tick stamps on a position; copied by name to the closed trade record
# and the feature-store row (only when present, so every other row is unchanged).
STAMP_KEYS = (
    "random_mode", "random_prereg", "random_tick_ts", "random_tick_utc", "random_bucket",
    "random_rank", "random_field", "random_status", "random_fallback", "random_key_value",
    "random_gate_close", "random_atr_pct", "random_calm_ratio", "random_detector_side",
    "random_detector_reject", "random_natural_side", "random_coin", "random_side",
    "random_ref_price", "random_regime_mult", "random_universe_n", "random_held_skipped",
    "random_held_symbols", "random_btc_flag", "random_turnover_24h", "random_range_24h",
    "random_decision", "random_tick_hours", "random_side_mode", "random_trend_sl_mult",
    "random_wc_min_turnover",
)

# (tick hours, side mode, TREND stop multiple, WILDCARD turnover floor) -> the PREREG tag.
REGISTERED = {
    (12, "coin", 3.0, 2_000_000.0): PREREG_TAG,
    (6, "natural", 3.5, 2_000_000.0): PREREG25_TAG,
}
TRIAL_OF_TAG = {PREREG_TAG: "trial 24", PREREG25_TAG: "trial 25"}


def enabled() -> bool:
    """FUTURES_RANDOM_MODE_ENABLED. Default OFF; empty or whitespace reads as unset (C26)."""
    return _b("FUTURES_RANDOM_MODE_ENABLED", False)


# ---- the tick's configuration (read once per tick) ---------------------------------------

@dataclass(frozen=True)
class TickConfig:
    """The settings one tick runs with. `errors` non-empty = invalid: the tick is not
    processed (the fields then hold the defaults and must not be traded on; an invalid
    FUTURES_RANDOM_TICK_HOURS holds 6, the finest allowed cadence, so every tick either
    cadence could have is checked and alerted)."""
    tick_hours: int = 12
    side_mode: str = "coin"
    trend_sl_mult: float = 3.0
    wc_min_turnover: float = UNIVERSE_MIN_TURNOVER
    errors: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def tick_seconds(self) -> int:
        return int(self.tick_hours) * 3600

    @property
    def prereg(self) -> str:
        """The tag of the PREREG this combination is, else "unregistered"."""
        key = (int(self.tick_hours), self.side_mode, float(self.trend_sl_mult), float(self.wc_min_turnover))
        return REGISTERED.get(key, UNREGISTERED)

    @property
    def trial(self) -> str:
        return TRIAL_OF_TAG.get(self.prereg, "UNREGISTERED")

    def fields(self) -> dict[str, Any]:
        """The effective values as stamped on positions, shadow rows and journal rows."""
        return {"random_tick_hours": float(self.tick_hours), "random_side_mode": self.side_mode,
                "random_trend_sl_mult": float(self.trend_sl_mult),
                "random_wc_min_turnover": float(self.wc_min_turnover)}

    def describe(self) -> str:
        """One line: the effective values (boot log, /status, alerts)."""
        hours = " / ".join(f"{h:02d}:00Z" for h in range(0, 24, int(self.tick_hours)))
        return (f"ticks every {int(self.tick_hours)}h ({hours}), side {self.side_mode}, "
                f"TREND stop {float(self.trend_sl_mult):g}x ATR, WILDCARD turnover >= "
                f"${float(self.wc_min_turnover):,.0f}, PREREG {self.prereg}")


def _setting(name: str) -> str | None:
    """The raw value, stripped; None when unset or blank (blank reads as unset, C26)."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip()


def config() -> TickConfig:
    """FUTURES_RANDOM_TICK_HOURS (12 | 6, default 12), FUTURES_RANDOM_SIDE_MODE (coin |
    natural, default coin), FUTURES_RANDOM_WC_MIN_TURNOVER (> 0, default 2000000) and the
    TREND stop multiple the order uses (FUTURES_TREND_SL_ATR_MULT, default 3.0, read as
    trend.py reads it; a set value that is not a number > 0 is an error here). Unset or
    blank = the default; surrounding spaces are ignored; values are case-sensitive. Any
    other value is an error: the caller does not process the tick and alerts. Never a
    silent fallback."""
    errors: list[str] = []
    hours = 12
    raw = _setting("FUTURES_RANDOM_TICK_HOURS")
    if raw is not None:
        if raw in tuple(str(h) for h in TICK_HOURS_ALLOWED):
            hours = int(raw)
        else:
            hours = min(TICK_HOURS_ALLOWED)    # checked (and alerted) at every 6h tick
            errors.append(f"FUTURES_RANDOM_TICK_HOURS={raw!r} (allowed: 12, 6)")
    mode = "coin"
    raw = _setting("FUTURES_RANDOM_SIDE_MODE")
    if raw is not None:
        if raw in SIDE_MODES:
            mode = raw
        else:
            errors.append(f"FUTURES_RANDOM_SIDE_MODE={raw!r} (allowed: coin, natural)")
    turnover = UNIVERSE_MIN_TURNOVER
    raw = _setting("FUTURES_RANDOM_WC_MIN_TURNOVER")
    if raw is not None:
        try:
            val = float(raw)
        except ValueError:
            val = float("nan")
        if math.isfinite(val) and val > 0:
            turnover = val
        else:
            errors.append(f"FUTURES_RANDOM_WC_MIN_TURNOVER={raw!r} (a number > 0)")
    raw = _setting("FUTURES_TREND_SL_ATR_MULT")
    if raw is not None:
        try:
            val = float(raw)
        except ValueError:
            val = float("nan")
        if not (math.isfinite(val) and val > 0):
            errors.append(f"FUTURES_TREND_SL_ATR_MULT={raw!r} (a number > 0)")
    return TickConfig(tick_hours=hours, side_mode=mode,
                      trend_sl_mult=float(_sleeve_params("TREND")["sl_mult"]),
                      wc_min_turnover=turnover, errors=tuple(errors))


# ---- time ------------------------------------------------------------------------------

def tick_at(now: float, tick_seconds: int = TICK_SECONDS) -> int:
    """The latest tick boundary at or before `now` (12h: 00:00Z / 12:00Z; 6h: also
    06:00Z / 18:00Z - both divide the day, so every tick is on the UTC clock)."""
    return int(float(now) // int(tick_seconds)) * int(tick_seconds)


def next_tick(now: float, tick_seconds: int = TICK_SECONDS) -> int:
    return tick_at(now, tick_seconds) + int(tick_seconds)


def due_tick(now: float, last_tick: float | None, grace: float = TICK_GRACE_SECONDS,
             tick_seconds: int = TICK_SECONDS) -> int | None:
    """The tick to process now, or None.

    A tick is due once: when it is later than the last processed tick and no more than
    `grace` seconds old. The caller persists the tick before its first order, so a
    restart can never process it twice."""
    tick = tick_at(now, tick_seconds)
    try:
        last = None if last_tick is None else float(last_tick)
    except (TypeError, ValueError):
        last = None
    if last is not None and tick <= last:
        return None
    if float(now) - tick > float(grace):
        return None
    return tick


def utc(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- bars ------------------------------------------------------------------------------

def _open_times(frame: pd.DataFrame) -> list[int]:
    idx = frame.index
    if isinstance(idx, pd.DatetimeIndex):
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        return [int(pd.Timestamp(x).timestamp()) for x in idx]
    return [int(x) for x in frame["t"]]


def completed(frame: pd.DataFrame | None, tick: int, n: int) -> pd.DataFrame | None:
    """The last `n` 15m bars CLOSED by `tick` (open <= tick - 900), oldest first.

    Filters on the bar's own open time, never on the clock, so a tick processed minutes
    late still reads exactly the bars the backtest read."""
    if frame is None:
        return None
    if len(frame) == 0:
        return frame
    times = _open_times(frame)
    keep = [t <= int(tick) - BAR_SECONDS for t in times]
    out = frame[keep]
    return out.iloc[-int(n):] if n > 0 else out


def _last_open(frame: pd.DataFrame) -> int | None:
    if frame is None or len(frame) == 0:
        return None
    return _open_times(frame.iloc[-1:])[0]


def turnover24(frame: pd.DataFrame) -> float | None:
    """Sum of the last 96 completed bars' quote turnover (`amount`), the slippage-band
    input the backtest recorded; None when the kline payload carried no `amount`."""
    if frame is None or "amount" not in frame or len(frame) == 0:
        return None
    vals = pd.to_numeric(frame["amount"].iloc[-96:], errors="coerce")
    return float(vals.fillna(0.0).sum())


_OHLCV = ["open", "high", "low", "close", "volume"]


# ---- candidate rows (ports of b02_candidates.wc_row / trend_row) -----------------------

def wildcard_row(symbol: str, frame: pd.DataFrame | None, tick: int,
                 ticker: dict | None = None) -> dict[str, Any]:
    """One WILDCARD universe symbol at `tick`: 3h ROC, the detector's verdict and the
    values the backtest recorded. `frame` is any 15m frame covering the tick (the
    forming bar and anything later are dropped here)."""
    row: dict[str, Any] = {"symbol": symbol, "ticker": ticker}
    if frame is None:
        row.update({"usable": False, "why": "kline_error"})
        return row
    fr = completed(frame, tick, WC_BARS)
    last = _last_open(fr)
    if last is None or last != int(tick) - BAR_SECONDS:
        row.update({"usable": False, "why": "stale_or_missing_bar", "last_bar": utc(last)})
        return row
    c = fr["close"].astype(float).values
    roc3 = float(c[-1] / c[-13] - 1.0) if len(c) >= 13 and c[-13] > 0 else None
    reasons: list[str] = []
    sig = detect_wildcard_signal(fr[_OHLCV], symbol, reasons)
    atr = _atr_pct(fr)
    row.update({
        "usable": roc3 is not None, "why": None if roc3 is not None else "short_frame",
        "roc3h": roc3, "gate_close": float(c[-1]), "atr_pct": atr, "n_bars": len(fr),
        "detector": None if sig is None else {
            "side": sig.side, "roc_pct": sig.roc_pct, "rsi": sig.rsi, "vol_z": sig.vol_z,
            "calm_ratio": sig.calm_ratio, "leverage": sig.leverage,
            "sl_margin_pct": sig.sl_margin_pct},
        "reject": reasons[-1] if (sig is None and reasons) else None,
        "calm_ratio": calm_ratio(fr),
        "turnover24_mx": turnover24(fr),
    })
    return row


def trend_row(symbol: str, frame: pd.DataFrame | None, tick: int) -> dict[str, Any]:
    """One TREND symbol at `tick`: 24h ROC and the TREND detector's verdict."""
    row: dict[str, Any] = {"symbol": symbol}
    if frame is None:
        row.update({"usable": False, "why": "kline_error"})
        return row
    fr = completed(frame, tick, TREND_BARS)
    last = _last_open(fr)
    if last is None or last != int(tick) - BAR_SECONDS:
        row.update({"usable": False, "why": "stale_or_missing_bar"})
        return row
    c = fr["close"].astype(float).values
    roc24 = float(c[-1] / c[-97] - 1.0) if len(c) >= 97 else None
    reasons: list[str] = []
    sig = detect_trend_signal(fr[_OHLCV], symbol, reasons)
    row.update({
        "usable": roc24 is not None, "why": None if roc24 is not None else "short_frame",
        "roc24h": roc24, "gate_close": float(c[-1]), "atr_pct": _atr_pct(fr), "n_bars": len(fr),
        "detector": None if sig is None else {
            "side": sig.side, "roc_pct": sig.roc_pct,
            "prior_close_extreme": sig.prior_close_extreme, "leverage": sig.leverage},
        "reject": reasons[-1] if (sig is None and reasons) else None,
        "turnover24_mx": turnover24(fr),
    })
    return row


def rank(rows: Iterable[dict], key: str, passing: Callable[[dict], bool], desc: bool,
         top_n: int | None = TOP_N) -> list[dict]:
    """b02_candidates.rank: passing candidates by `key`, then the rest of the usable
    universe by the same key (the PREREG fallback); each tagged pass / fallback.
    top_n None = every usable row (the journal's full ranking; its first TOP_N rows are
    the top_n=TOP_N list exactly)."""
    ok = [r for r in rows if r.get("usable")]
    p = sorted([r for r in ok if passing(r)], key=lambda r: r[key], reverse=desc)
    rest = sorted([r for r in ok if not passing(r)], key=lambda r: r[key], reverse=desc)
    out: list[dict] = []
    for r, flag in [(r, "pass") for r in p] + [(r, "fallback") for r in rest]:
        out.append(dict(r, status=flag))
        if top_n is not None and len(out) >= top_n:
            break
    return out


def _detector_side(row: dict) -> str | None:
    det = row.get("detector")
    return det.get("side") if isinstance(det, dict) else None


def rank_wildcard(rows: list[dict], top_n: int | None = TOP_N) -> tuple[list[dict], list[dict]]:
    """(WILDCARD-long list, WILDCARD-short list): LONG passes by +3h ROC (largest
    first), SHORT passes by 3h ROC (most negative first), each followed by the rest."""
    longs = rank(rows, "roc3h", lambda r: _detector_side(r) == "LONG", True, top_n)
    shorts = rank(rows, "roc3h", lambda r: _detector_side(r) == "SHORT", False, top_n)
    return longs, shorts


def rank_trend(rows: list[dict], top_n: int | None = TOP_N) -> list[dict]:
    """TREND list: passing = a LONG TREND signal (24h ROC >= 4% and a new 24h closing
    high), by 24h ROC; else the highest 24h ROC (fallback)."""
    return rank(rows, "roc24h", lambda r: _detector_side(r) == "LONG", True, top_n)


# ---- the WILDCARD universe at the tick ----------------------------------------------------

def universe(tickers: Iterable[dict], *, majors: set[str], tradeable: Callable[[str], bool],
             range_of: Callable[[dict], float],
             min_turnover: float = UNIVERSE_MIN_TURNOVER) -> list[tuple[str, dict]]:
    """(symbol, ticker values) for every crypto USDT perp outside the majors band with
    24h turnover >= `min_turnover` ($2M unless FUTURES_RANDOM_WC_MIN_TURNOVER says
    otherwise) and 24h range >= 7%, widest range first (the scan's order).

    HELD SYMBOLS ARE INCLUDED. The scan journal the backtest read drops symbols the bot
    holds, and DEVIATIONS.md D2 added them back when they pass the same filters; read
    off the ticker directly they are simply never removed. Holding is handled at pick
    time (next best), exactly as the backtest's simulator did."""
    out: list[tuple[float, str, dict]] = []
    for t in tickers:
        sym = str(t.get("symbol") or "")
        if not sym.endswith("_USDT") or not tradeable(sym) or sym in majors:
            continue
        try:
            turn = float(t.get("amount24") or 0.0)
        except (TypeError, ValueError):
            continue
        rng = float(range_of(t) or 0.0)
        if turn >= float(min_turnover) and rng >= UNIVERSE_MIN_RANGE:
            out.append((rng, sym, {"range24": rng, "amount24": turn, "source": "ticker"}))
    out.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [(sym, tk) for _rng, sym, tk in out]


# ---- the coin ----------------------------------------------------------------------------

def coin() -> int:
    """One fair coin: 0 = LONG, 1 = SHORT.

    The low bit of one byte from os.urandom, the operating system's CSPRNG. Every bit of
    a uniform byte is a fair bit, so this is exactly 50/50. It never touches the
    `random` module or numpy, so no seed anywhere in the process can make it
    predictable or repeat it."""
    return os.urandom(1)[0] & 1


def coin_side(c: int) -> str:
    return "LONG" if int(c) == 0 else "SHORT"


def side_for(bucket: str, side_mode: str, coin_: int | None) -> str:
    """The side a bucket's pick trades: the coin's (side mode coin) or the bucket's
    natural side (side mode natural, where no coin is drawn)."""
    if side_mode == "natural":
        return NATURAL[bucket]
    return coin_side(coin_)


# ---- the signal for the chosen side -------------------------------------------------------

def _sleeve_params(sleeve: str) -> dict[str, Any]:
    """The detector's own parameters, read from the same variables with the same
    defaults as wildcard.detect_wildcard_signal / trend.detect_trend_signal."""
    if sleeve == "TREND":
        return {"leverage": int(min(20.0, max(1.0, _f("FUTURES_TREND_LEVERAGE_MAX", 10.0)))),
                "sl_mult": _f("FUTURES_TREND_SL_ATR_MULT", 3.0),
                "tp_r": _f("FUTURES_TREND_TP_R", 3.0),
                "max_sl_margin": _f("FUTURES_TREND_MAX_SL_MARGIN_PCT", 20.0),
                "max_short": _f("FUTURES_TREND_MAX_SHORT_TP_DIST", 0.50),
                "tp_from_designed": False,
                "balance_fraction": min(0.15, max(0.05, _f("FUTURES_TREND_BALANCE_PCT", 0.12)))}
    return {"leverage": int(min(10.0, max(5.0, _f("FUTURES_WILDCARD_LEVERAGE", 7.0)))),
            "sl_mult": _f("FUTURES_WILDCARD_SL_ATR_MULT", 1.5),
            "tp_r": _f("FUTURES_WILDCARD_TP_R", 5.0),
            "max_sl_margin": _f("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", 20.0),
            "max_short": _f("FUTURES_WILDCARD_MAX_SHORT_TP_DIST", 0.50),
            "tp_from_designed": _b("FUTURES_WILDCARD_TP_FROM_DESIGNED_STOP", False),
            "balance_fraction": min(0.15, max(0.05, _f("FUTURES_WILDCARD_BALANCE_PCT", 0.12)))}


def prior_close_extreme(frame: pd.DataFrame | None, side: str) -> float | None:
    """The prior 24h closing high (LONG) / low (SHORT) before the last completed bar,
    as trend.detect_trend_signal records it. Telemetry only."""
    if frame is None or len(frame) < 97:
        return None
    window = frame["close"].astype(float).iloc[-97:-1]
    return float(window.max() if side == "LONG" else window.min())


def build_signal(*, symbol: str, sleeve: str, side: str, ref_price: float, atr_pct: float,
                 roc_pct: float, rsi: float, gate_close: float | None = None,
                 exch_max_leverage: float | None = None, calm: float | None = None,
                 vol_z: float | None = None, prior_extreme: float | None = None) -> WildcardSignal:
    """The order the bot sends for `side`, priced at `ref_price`.

    Stop 3 x ATR14% (the sleeve's SL_ATR_MULT) from the reference on the chosen side;
    the 20%-of-margin leverage rule (trim leverage first, tighten the stop only if even
    x1 would breach); target TP_R x the stop as placed (WILDCARD 5R, TREND 3R; the BTC
    exhaustion cap to 1R is applied by the runtime afterwards), a short's target
    distance clamped at 50%. The exchange's maximum leverage caps the sleeve's, as in
    the backtest's leverage rule. Same arithmetic, same rounding, as the detectors."""
    if ref_price is None or float(ref_price) <= 0:
        raise ValueError("no reference price")
    if atr_pct is None or not math.isfinite(float(atr_pct)) or float(atr_pct) <= 0:
        raise ValueError("no ATR")
    side = str(side).upper()
    if side not in ("LONG", "SHORT"):
        raise ValueError(f"bad side {side!r}")
    p = _sleeve_params(sleeve)
    s = 1 if side == "LONG" else -1
    cur = float(ref_price)
    leverage = int(p["leverage"])
    try:
        if exch_max_leverage and float(exch_max_leverage) > 0:
            leverage = max(1, min(leverage, int(float(exch_max_leverage))))
    except (TypeError, ValueError):
        pass
    sl_frac = float(p["sl_mult"]) * float(atr_pct)
    sl_frac_designed = sl_frac
    tp_r = float(p["tp_r"])
    max_sl_margin = float(p["max_sl_margin"])
    if max_sl_margin > 0 and sl_frac > 0:
        if sl_frac * leverage * 100.0 > max_sl_margin:
            leverage = max(1, int(max_sl_margin / (sl_frac * 100.0)))
        if sl_frac * leverage * 100.0 > max_sl_margin:
            sl_frac = max_sl_margin / 100.0 / leverage
    sl_margin = sl_frac * leverage * 100.0
    tp_margin = tp_r * sl_margin
    sl_price = cur * (1 - sl_frac) if s > 0 else cur * (1 + sl_frac)
    tp_base = sl_frac
    if p["tp_from_designed"] and sl_frac_designed > 0:
        tp_base = sl_frac_designed
    tp_dist = tp_base * tp_r
    if s < 0 and tp_dist >= float(p["max_short"]):
        tp_dist = float(p["max_short"])
    tp_price = cur * (1 + tp_dist) if s > 0 else cur * (1 - tp_dist)
    return WildcardSignal(
        symbol=symbol.upper(), side=side, entry_price=cur, leverage=leverage,
        roc_pct=float(roc_pct or 0.0), atr_pct=float(atr_pct), sl_price=sl_price,
        tp_price=tp_price, sl_margin_pct=round(sl_margin, 4), tp_margin_pct=round(tp_margin, 4),
        balance_fraction=float(p["balance_fraction"]), rsi=round(float(rsi or 0.0), 1),
        sl_frac_designed=round(sl_frac_designed, 6),
        calm_ratio=(round(float(calm), 3) if calm is not None else None),
        vol_z=(round(float(vol_z), 3) if vol_z is not None else None),
        prior_close_extreme=prior_extreme,
        gate_close=(float(gate_close) if gate_close is not None else None),
    )


def signal_for(cand: dict, *, bucket: str, side: str, ref_price: float,
               frame: pd.DataFrame | None, exch_max_leverage: float | None = None) -> WildcardSignal:
    """build_signal from a ranked candidate row and its completed frame."""
    sleeve = SLEEVE[bucket]
    det = cand.get("detector") if isinstance(cand.get("detector"), dict) else {}
    rsi = _rsi(frame) if frame is not None and len(frame) > 1 else 0.0
    return build_signal(
        symbol=cand["symbol"], sleeve=sleeve, side=side, ref_price=ref_price,
        atr_pct=cand.get("atr_pct"), roc_pct=cand.get(KEY[bucket]) or 0.0, rsi=rsi,
        gate_close=cand.get("gate_close"), exch_max_leverage=exch_max_leverage,
        calm=cand.get("calm_ratio") if sleeve == "WILDCARD" else None,
        vol_z=det.get("vol_z") if det else None,
        prior_extreme=prior_close_extreme(frame, side) if sleeve == "TREND" else None)


def stamp(*, tick: int, bucket: str, cand: dict, rank_: int, field: int, side: str,
          coin_: int | None, ref_price: float | None, universe_n: int,
          held: list[str], regime_mult: float | None = None,
          btc_flag: bool | None = None, decision: str | None = None,
          cfg: TickConfig | None = None) -> dict[str, Any]:
    """The telemetry one bucket decision carries (metadata, trade record, feature
    store, shadow ledger). Missing readings stay None rather than 0.0. `cfg` is the
    tick's configuration (read from the environment when not given)."""
    cfg = cfg if cfg is not None else config()
    # The ticker turnover / range stamped are the WILDCARD universe's, as in trial 24; a TREND
    # row's ticker values go to the tick journal only (compact), so its stamps are unchanged.
    tk = cand.get("ticker") if isinstance(cand.get("ticker"), dict) and SLEEVE[bucket] == "WILDCARD" else {}
    det_side = _detector_side(cand)
    out = {
        "random_mode": 1.0, "random_prereg": cfg.prereg,
        "random_tick_ts": float(tick), "random_tick_utc": utc(tick),
        "random_bucket": bucket, "random_rank": float(rank_), "random_field": float(field),
        "random_status": cand.get("status"),
        "random_fallback": 1.0 if cand.get("status") == "fallback" else 0.0,
        "random_key_value": cand.get(KEY[bucket]),
        "random_gate_close": cand.get("gate_close"), "random_atr_pct": cand.get("atr_pct"),
        "random_calm_ratio": cand.get("calm_ratio"),
        "random_detector_side": det_side or "", "random_detector_reject": cand.get("reject") or "",
        "random_natural_side": NATURAL[bucket],
        "random_coin": (float(coin_) if coin_ is not None else None),
        "random_side": side, "random_ref_price": ref_price,
        "random_regime_mult": regime_mult, "random_universe_n": float(universe_n),
        "random_held_skipped": float(len(held)), "random_held_symbols": ",".join(held),
        "random_btc_flag": (None if btc_flag is None else (1.0 if btc_flag else 0.0)),
        "random_turnover_24h": tk.get("amount24"), "random_range_24h": tk.get("range24"),
        "random_decision": decision,
        **cfg.fields(),
    }
    return out


def compact(cand: dict, bucket: str) -> dict[str, Any]:
    """A ranked candidate as the tick journal stores it."""
    return {"symbol": cand.get("symbol"), "status": cand.get("status"),
            KEY[bucket]: cand.get(KEY[bucket]), "gate_close": cand.get("gate_close"),
            "atr_pct": cand.get("atr_pct"), "detector_side": _detector_side(cand),
            "reject": cand.get("reject"), "calm_ratio": cand.get("calm_ratio"),
            "turnover24_mx": cand.get("turnover24_mx"), "ticker": cand.get("ticker")}
