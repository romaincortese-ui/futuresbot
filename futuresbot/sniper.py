"""Sniper sleeve — short-horizon continuation on LIQUID pairs. SHADOW-ONLY.

The convex sleeves hunt small caps for rare +5R runners. The Sniper is the
opposite trade: take a significant, recent, directional move on a DEEP book and
ask for a modest +2R/+3R, on the reasoning that a liquid instrument in motion
tends to keep going for a while, and that a smaller target is actually reachable.

Three design facts, each forced by evidence rather than preference:

1. LEVERAGE IS AN OUTPUT, NOT AN INPUT. The -20%-of-margin cap means
   ``sl_frac * leverage * 100 <= 20``. Asking for 25x IS asking for a 0.8% stop.
   Measured 4h ranges are BTC 0.84% / ETH 1.17% / SOL 1.03%, so a 0.8% stop sits
   INSIDE one typical 4h bar — noise would take it out before direction did. So
   the stop is set from realised range first and leverage falls out of the cap.

2. THE TARGET IS +3R, NOT +5R. Trial 4 measured a 9.1% TP-completion rate at
   +5R against a 16.7% break-even. Break-even at 3:1 is 25%; at 2:1 it is 33%.
   A reachable target beats a flattering one.

3. A COST-DRAG GATE, NOT JUST A MARGIN FLOOR. ``cost_drag = (2*fee + slip)/sl_frac``
   — leverage cancels. The XAU_USDT squeeze trade had a 0.28% stop; fees were
   286% of gross and it lost -3.79R in 60 seconds. That is arithmetic, not bad
   luck, and it is checked here directly rather than via a margin proxy.

The bot's previous majors sleeve (PMT, 15-24x) lost 2.52R over 12 trades — but
its four winners cluster at +0.38/+0.39/+0.42/+0.44R, the signature of exit
machinery banking winners at ~+0.4R rather than of a market that failed to move.
That evidence is CONFOUNDED, so this sleeve runs convex (resting stop + resting
TP, no locks/trails/banks) and shadow-only until it has its own record.

Pure detection. The runtime owns universe selection, sizing and execution.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

from futuresbot.wildcard import WildcardSignal

# 15m bars
MOVE_BARS = 48          # 12h look-back for "a significant recent move"
CONFIRM_BARS = 4        # 1h of confirmation that it has not already turned
RANGE_BLOCK = 16        # 16 x 15m = one 4h block, for the realised-range stop
RANGE_BLOCKS = 12       # median over the last 12 blocks (~2 days)
RSI_PERIOD = 14

# MEXC taker fee, one way. Round trip is 2x this.
TAKER_FEE = 0.0008


def _f(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name)
        return float(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def sniper_enabled() -> bool:
    return _b("FUTURES_SNIPER_ENABLED", False)


def sniper_shadow_only() -> bool:
    """Default TRUE. The sleeve must earn live capital, not be granted it."""

    return _b("FUTURES_SNIPER_SHADOW_ONLY", True)


def sniper_max_positions() -> int:
    return max(1, int(_f("FUTURES_SNIPER_MAX_POSITIONS", 1)))


def sniper_scan_interval_seconds() -> int:
    """Outer guard only — the real cadence is per-variant (see scan_interval_s).

    Must be no slower than the fastest active variant, or the per-variant timers
    never get a chance to fire.
    """

    fastest = min((v.scan_interval_s for v in active_variants()), default=3600)
    return max(60, int(_f("FUTURES_SNIPER_SCAN_INTERVAL_SECONDS", fastest)))


def sniper_rearm_seconds() -> float:
    """Per (symbol, side) cooldown between logged signals.

    A 12h continuation re-qualifies on almost every subsequent bar, so without
    a re-arm the shadow ledger fills with dozens of copies of one setup and
    every count computed from it is inflated.
    """

    return max(0.0, _f("FUTURES_SNIPER_REARM_HOURS", 12.0)) * 3600.0


def sniper_min_turnover_usdt() -> float:
    """Liquidity floor. Far above the wildcard's $3M — this sleeve exists
    BECAUSE deep books make tight stops and modest targets viable."""

    return _f("FUTURES_SNIPER_MIN_TURNOVER_USDT", 50_000_000.0)


def sniper_universe() -> tuple[str, ...]:
    """Explicit allow-list, empty means 'any symbol passing the turnover floor'.

    An explicit list is the safer default while the sleeve is unproven: it makes
    the tested population and the traded population the same set.
    """

    raw = os.environ.get("FUTURES_SNIPER_SYMBOLS", "")
    return tuple(s.strip().upper() for s in raw.split(",") if s.strip())


def sniper_excluded_prefixes() -> tuple[str, ...]:
    """Categories to refuse regardless of turnover.

    XAU/XAG/USOIL and friends are synthetic commodity perps on MEXC: thin,
    gappy, and the source of the worst trade in trial 4 (XAU -3.79R in 60s on a
    0.28% stop). They are excluded by CATEGORY because a turnover filter did
    not catch them — XAUT_USDT clears $26M/24h with a 0.18% 4h range, i.e. a
    68% cost drag.

    Matched at either END of the base ticker, not exact: a live scan let XAUT
    and SILVER through a nominal "XAU" exclusion, and tokenised equities land as
    a suffix (SNDKSTOCK). Those gap across equity-market closes, which is the
    same tight-stop killer as the commodity synthetics.
    """

    raw = os.environ.get(
        "FUTURES_SNIPER_EXCLUDE",
        "XAU,XAG,GOLD,SILVER,USOIL,UKOIL,NGAS,STOCK",
    )
    return tuple(s.strip().upper() for s in raw.split(",") if s.strip())


def symbol_allowed(symbol: str) -> bool:
    sym = symbol.upper()
    base = sym.replace("_USDT", "")
    if any(base.startswith(p) or base.endswith(p) for p in sniper_excluded_prefixes()):
        return False
    universe = sniper_universe()
    return (sym in universe) if universe else True


@dataclass(frozen=True, slots=True)
class SniperVariant:
    """One Sniper configuration. Several run side by side in shadow.

    The point of separating these is that "how fast is the signal" and "how wide
    is the stop" are INDEPENDENT choices, and conflating them is what produced
    the first version. You can have a 30-minute signal; you cannot have a
    30-minute stop, because a 0.36% stop on BTC hands ~50% of every 1R to fees.
    """

    name: str
    interval: str            # kline granularity the scan fetches
    move_bars: int           # look-back for "a significant move", in bars
    confirm_bars: int
    range_block: int         # bars per block for the realised-range stop
    range_blocks: int = 12
    sl_range_mult: float = 1.5
    trigger_mult: float = 2.0    # required move, as a multiple of the range block
    min_move: float = 0.015
    min_sl_pct: float = 1.5      # stop-width floor, % of price
    max_cost_drag: float = 0.20
    tp_r: float = 3.0
    max_leverage: int = 13
    resolve_interval: str = "Min15"   # granularity the shadow resolver replays
    resolve_horizon_h: float = 48.0
    economically_viable: bool = True  # False = signal study only, see FAST
    # Scan cadence MUST track the look-back. A 30-minute signal scanned hourly is
    # invisible: measured on real data, FAST would have fired 47 times in 30h but
    # an hourly scan samples ~1/60th of the windows, so the expected catch was
    # 0.8 — and we logged 0. Rule of thumb: >=6 samples per look-back window.
    scan_interval_s: int = 3600
    rearm_h: float = 12.0             # must exceed the hold, or one impulse logs twice

    @property
    def bars_needed(self) -> int:
        """Bars the scan must fetch.

        Must cover BOTH the look-back AND enough blocks for a stable range
        median — `realised_range_pct` returns None below `range_block * 2`, and
        a median over 2 blocks is noise. FAST_TRIGGER (6-bar look-back, 48-bar
        block) is dominated entirely by the second term; sizing this as
        move_bars + range_block returned `no_range` on every symbol.
        """

        return max(self.move_bars + 2, self.range_block * min(self.range_blocks, 6))


# Today's shipped behaviour: 12h look-back, 4h-range stop, hours-to-days hold.
SWING = SniperVariant(
    name="SWING", interval="Min15", move_bars=48, confirm_bars=4, range_block=16,
)

# Option #2 — FAST TRIGGER, SLOW STOP. Detects a 30-minute impulse but sizes the
# stop off the 4h range, so it is cost-viable at taker fees TODAY (BTC ~1.14%
# stop, ~16% drag). The trade resolves over hours, not minutes. Requiring a 30min
# move >= 1.0x the 4h range makes this a dislocation detector: it should fire
# rarely, and that is the intended behaviour rather than a bug.
FAST_TRIGGER = SniperVariant(
    name="FAST_TRIGGER", interval="Min5", move_bars=6, confirm_bars=2,
    range_block=48, trigger_mult=1.0, min_move=0.006,
    resolve_interval="Min5", resolve_horizon_h=24.0,
    scan_interval_s=300, rearm_h=6.0,     # 30min look-back -> 6 samples per window
)

# Option #3 — GENUINELY FAST. 30-minute look-back, 30-minute-range stop, ~30min
# hold. NOT economically viable at taker fees: a 0.36% BTC stop is ~50% cost
# drag, worse than PMT (which ran ~0.6% stops and lost 63% of gross to fees).
# It runs with the cost gates DISABLED on purpose, because shadow counterfactuals
# are fee-free: this variant measures ONLY whether a 30-minute impulse continues.
# A positive result here does NOT imply live profitability — it would additionally
# require maker execution at a maker rate nobody has verified (MEXC's API claims
# makerFeeRate=0 while misreporting the taker rate by 4x).
FAST = SniperVariant(
    name="FAST", interval="Min1", move_bars=30, confirm_bars=5, range_block=30,
    trigger_mult=2.0, min_move=0.002, min_sl_pct=0.0, max_cost_drag=1.0,
    tp_r=2.0, resolve_interval="Min1", resolve_horizon_h=6.0,
    economically_viable=False,
    scan_interval_s=300, rearm_h=2.0,     # ~30min hold -> 2h re-arm is 4x the hold
)

VARIANTS: dict[str, SniperVariant] = {v.name: v for v in (SWING, FAST_TRIGGER, FAST)}


def active_variants() -> tuple[SniperVariant, ...]:
    raw = os.environ.get("FUTURES_SNIPER_VARIANTS", "SWING")
    picked = [VARIANTS[n.strip().upper()] for n in raw.split(",")
              if n.strip().upper() in VARIANTS]
    return tuple(picked) or (SWING,)


def _rej(reasons, tag):
    if reasons is not None:
        reasons.append(tag)
    return None


def realised_range_pct(frame: pd.DataFrame, *, block: int = RANGE_BLOCK, blocks: int = RANGE_BLOCKS) -> float | None:
    """Median (high-low)/close over recent N-bar blocks — a 4h 'how far does
    this thing normally travel' measure.

    Preferred over a 15m ATR because the stop has to survive HOURS of holding,
    and a 15m ATR flatters the answer by roughly 5x.
    """

    if frame is None or len(frame) < block * 2:
        return None
    highs = frame["high"].astype(float); lows = frame["low"].astype(float); closes = frame["close"].astype(float)
    out: list[float] = []
    n = len(frame)
    for i in range(n - block, max(n - block * (blocks + 1), -1), -block):
        hi = float(highs.iloc[i:i + block].max())
        lo = float(lows.iloc[i:i + block].min())
        cl = float(closes.iloc[i + block - 1])
        if cl > 0 and hi > lo:
            out.append((hi - lo) / cl)
    if not out:
        return None
    out.sort()
    return out[len(out) // 2]


def _rsi(frame: pd.DataFrame) -> float:
    c = frame["close"].astype(float)
    d = c.diff().iloc[-RSI_PERIOD:]
    gain = float(d.clip(lower=0).mean()); loss = float(-d.clip(upper=0).mean())
    if loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


# Slippage assumption. Deliberately LOWER than the wildcard's: this sleeve only
# trades books above FUTURES_SNIPER_MIN_TURNOVER_USDT, where 1-2bps is realistic.
# Using the small-cap 5bps figure here would refuse BTC itself — measured BTC 4h
# range 0.84% -> 1.26% stop -> 16.7% drag at 5bps, over a 15% budget.
DEFAULT_SLIPPAGE = 0.0002


def cost_drag(sl_frac: float, *, fee: float = TAKER_FEE, slippage: float = DEFAULT_SLIPPAGE) -> float:
    """Fraction of 1R consumed by a round trip. Leverage cancels — this is why
    a thin stop is unwinnable no matter how the position is sized."""

    return (2.0 * fee + slippage) / sl_frac if sl_frac > 0 else float("inf")


def detect_sniper_signal(frame: pd.DataFrame, symbol: str,
                         reasons: list[str] | None = None,
                         variant: SniperVariant = SWING) -> WildcardSignal | None:
    """Continuation on a liquid pair after a significant recent move.

    Gates, all on completed bars:
      1. MOVE: |12h ROC| >= FUTURES_SNIPER_MIN_MOVE (0.02).
      2. NOT ALREADY EXHAUSTED: the move has not retraced most of itself, and
         RSI still has room in the direction of travel.
      3. CONFIRMATION: the last CONFIRM_BARS still favour the move direction —
         "confirmed over a short amount of time" rather than caught mid-reversal.
      4. NOT A BLOW-OFF: the newest bar is not a vertical climax.
      5. COST: round-trip cost must not exceed FUTURES_SNIPER_MAX_COST_DRAG of 1R.
    """

    if not symbol_allowed(symbol):
        return _rej(reasons, "symbol_excluded")
    need = variant.bars_needed
    if frame is None or "close" not in frame or len(frame) < need:
        return _rej(reasons, "short_frame")

    c = frame["close"].astype(float)
    h = frame["high"].astype(float); l = frame["low"].astype(float)
    cur = float(c.iloc[-1])
    base = float(c.iloc[-(variant.move_bars + 1)])
    if cur <= 0 or base <= 0:
        return _rej(reasons, "bad_price")

    rng_pct = realised_range_pct(frame, block=variant.range_block, blocks=variant.range_blocks)
    if rng_pct is None or rng_pct <= 0:
        return _rej(reasons, "no_range")

    # 1. SIGNIFICANT move — measured in the symbol's OWN volatility, not as a
    #    flat percentage. A flat 2% is 1.79x BTC's 4h range but only 0.24x
    #    BEAT's, so a flat threshold fires 3x more often on high-ATR names and
    #    they monopolise the slots: measured, BTC/ETH/SOL win just 4.8% of slots
    #    in a 30-pair universe under a flat rule. That silently turns a
    #    liquid-majors sleeve into an altcoin sleeve.
    #    The trigger multiple must EXCEED the stop multiple (1.5), or the stop
    #    ends up wider than the move that triggered it.
    roc = cur / base - 1.0
    trigger = max(
        _f("FUTURES_SNIPER_MIN_MOVE", variant.min_move),
        _f("FUTURES_SNIPER_TRIGGER_ATR_MULT", variant.trigger_mult) * rng_pct,
    )
    if abs(roc) < trigger:
        return _rej(reasons, "move_below_min")
    side = "LONG" if roc > 0 else "SHORT"
    s = 1 if side == "LONG" else -1

    # 2. still in force: price should sit near the extreme of the move, not have
    #    round-tripped back to where it started.
    window = c.iloc[-(variant.move_bars + 1):]
    hi_w = float(window.max()); lo_w = float(window.min())
    span = hi_w - lo_w
    if span <= 0:
        return _rej(reasons, "flat_window")
    pos = (cur - lo_w) / span              # 1.0 = at the top of the window
    hold = _f("FUTURES_SNIPER_MIN_EXTREME_POS", 0.6)
    if (s > 0 and pos < hold) or (s < 0 and pos > 1.0 - hold):
        return _rej(reasons, "move_retraced")

    rsi = _rsi(frame)
    if s > 0 and rsi >= _f("FUTURES_SNIPER_RSI_MAX", 82.0):
        return _rej(reasons, "rsi_exhausted")
    if s < 0 and rsi <= _f("FUTURES_SNIPER_RSI_MIN", 18.0):
        return _rej(reasons, "rsi_exhausted")

    # 3. short-window confirmation
    recent = float(c.iloc[-1]) / float(c.iloc[-(variant.confirm_bars + 1)]) - 1.0
    if (s > 0 and recent <= 0) or (s < 0 and recent >= 0):
        return _rej(reasons, "not_confirmed")

    # 4. blow-off guard
    last_move = abs(cur / float(c.iloc[-2]) - 1.0)
    if last_move > _f("FUTURES_SNIPER_VERTICAL_MULT", 0.5) * rng_pct:
        return _rej(reasons, "vertical_blowoff")
    bar_h = float(h.iloc[-1]); bar_l = float(l.iloc[-1]); bar_rng = bar_h - bar_l
    if bar_rng > 0:
        adverse_wick = ((bar_h - cur) if s > 0 else (cur - bar_l)) / bar_rng
        if adverse_wick > _f("FUTURES_SNIPER_MAX_WICK", 0.5):
            return _rej(reasons, "climax_wick")

    # ---- geometry: stop first, leverage second -----------------------------
    sl_frac = _f("FUTURES_SNIPER_SL_RANGE_MULT", variant.sl_range_mult) * rng_pct
    tp_r = _f("FUTURES_SNIPER_TP_R", variant.tp_r)

    # 5. cost gate — the XAU lesson, applied to the stop DISTANCE not the margin.
    # 20% budget => a ~0.9% minimum viable stop. Refuses the XAU pattern (0.28%
    # stop = 64% drag) while admitting BTC (1.26% stop = 14% drag). At the budget
    # a +3R gross target nets roughly +2.4R.
    drag = cost_drag(sl_frac, slippage=_f("FUTURES_SNIPER_SLIPPAGE", DEFAULT_SLIPPAGE))
    if drag > _f("FUTURES_SNIPER_MAX_COST_DRAG", variant.max_cost_drag):
        return _rej(reasons, "fee_doomed")

    # A minimum stop WIDTH is the same rule as a maximum leverage (20/1.5 = 13x)
    # and the same rule as the cost budget. It is what actually kills the XAU
    # class: XAU is turnover rank 4 with a 0.07bp spread — one of the deepest
    # books MEXC lists — but its 4h range is 0.67%, so any percentage stop is
    # small in absolute terms and the fixed fee dominates it. The failure mode
    # is "thin stop on a LOW-VOLATILITY instrument", not "thin book".
    min_sl_pct = _f("FUTURES_SNIPER_MIN_SL_PRICE_PCT", variant.min_sl_pct) / 100.0
    if sl_frac < min_sl_pct:
        return _rej(reasons, "stop_too_thin")

    max_sl_margin = _f("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", 20.0)
    lev_cap = int(_f("FUTURES_SNIPER_MAX_LEVERAGE", variant.max_leverage))
    leverage = max(1, min(lev_cap, int(max_sl_margin / (sl_frac * 100.0)))) if sl_frac > 0 else 1
    if leverage < int(_f("FUTURES_SNIPER_MIN_LEVERAGE", 3)):
        # Too volatile for this sleeve: the stop the range demands would need
        # leverage below the point where the trade is worth the fees.
        return _rej(reasons, "too_volatile_for_leverage")
    sl_margin = sl_frac * leverage * 100.0

    sl_price = cur * (1 - sl_frac) if s > 0 else cur * (1 + sl_frac)
    tp_price = cur * (1 + sl_frac * tp_r) if s > 0 else cur * (1 - sl_frac * tp_r)
    return WildcardSignal(
        symbol=symbol.upper(), side=side, entry_price=cur, leverage=leverage,
        roc_pct=roc, atr_pct=rng_pct, sl_price=sl_price, tp_price=tp_price,
        sl_margin_pct=round(sl_margin, 4), tp_margin_pct=round(tp_r * sl_margin, 4),
        balance_fraction=min(0.20, max(0.05, _f("FUTURES_SNIPER_BALANCE_PCT", 0.12))),
        rsi=round(rsi, 1),
    )
