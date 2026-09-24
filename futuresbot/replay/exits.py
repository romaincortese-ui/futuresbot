"""ONE canonical exit resolver for replays, on the price feeds the live exits actually read.

WHY (assessment 2026-09-23, docs/DECISION_RULE.md "IMPARTIAL ASSESSMENT + REPLAY AUDIT")
  * 63 distinct exit-logic bodies existed across tools/ and wc/, none of them the bot's own code
    (wc/ASSESS/A/a01_resolvers.py). "Validated" mostly meant replay agreeing with replay.
  * They all read LAST-price wicks. Live resting orders trigger on the price type the order
    builder sets (marketdata.MexcFuturesClient._trigger_trends_for_order_side: stop lossTrend=2 =
    FAIR, target profitTrend=1 = LAST), and the software exits poll the FAIR price
    (runtime._open_position_guard_price). On last-price wicks 66 of 70 live exit types matched;
    on fair price 70 of 70. The wick bias is [-0.121, +0.061]R per fill - about +-$180/month - and
    it flips the sign of H's baseline, the trail, the breakeven stop and the early stop.

WHAT IS IMPORTED FROM THE LIVE CODE (not restated)
  * The order feeds: `live_order_feeds()` calls marketdata._trigger_trends_for_order_side.
  * The ratchet: `retain_for()` calls FuturesRuntime._trail_retain_for through a parameter shim.
  * The parameter NAMES and DEFAULTS: `LIVE_ENV_DEFAULTS` / `LIVE_FLAG_DEFAULTS`, which
    tests/test_replay_exits.py re-reads from runtime.py's source and fails on any drift.
  * The reference resolver `LiveCodeReference` drives the bot's OWN methods poll by poll
    (_convex_early_stop_exit, _convex_runner_trail_exit -> _maybe_breakeven_stop,
    _convex_time_stop_exit, _effective_stop_price) on a bare FuturesRuntime. It is slow; the
    fast resolver is tested equal to it on randomised paths, so a change to any live exit rule
    fails the suite until this module is updated.

WHAT IS MIRRORED (the live methods mutate a position, persist state and send orders, so they
cannot be called per bar in a study). Line numbers are runtime.py at commit b6374a7:
  * trail floor         _convex_runner_trail_exit  2754-2755 (arm, retain), 2782 (peak stored
                        rounded to 4 dp), 2823-2852 (floor, cost guard, cannot-trail),
                        2853-2856 (legacy giveback), 2857 (fire test: r_now <= floor)
  * early stop          _convex_early_stop_exit    2481-2492 (per-sleeve arm/window, r_now <= -arm)
  * breakeven stop      _maybe_breakeven_stop      2630-2637 (level), 2653-2665 (arm, wrong side);
                        called from inside the trail method, so FUTURES_CONVEX_RUNNER_TRAIL=0
                        switches it off too
  * time stop           _convex_time_stop_exit     2049-2060
  * poll order          _hourly_exit               2631-2636 (early, then trail, then clock)
  * sleeve gate         _is_wildcard_convex        1655-1666
  * TREND-only flags    _trail_enabled_for, _trail_arm_r_for, _breakeven_arm_r_for (EXP/T, 2026-09-23):
                        FUTURES_TREND_TRAIL_ENABLED stops the trail FIRING on TREND only - the peak and the
                        breakeven stop keep running (the switch sits below them in the trail method);
                        FUTURES_TREND_TRAIL_ARM_R / _BREAKEVEN_ARM_R override the shared arms on TREND only

THE PATH CONVENTION ON A BAR (the only modelling choice; everything else is the live rule)
Each bar is walked as four polls in R space: OPEN (t) -> ADVERSE extreme (t+20s) -> FAVOURABLE
extreme (t+40s) -> CLOSE (t+59s). The gap from the previous close to the open is a jump (a level
crossed by a jump fills at the open); the three moves inside the bar are continuous (a level
crossed fills AT the level, resting or software - the live monitor polls every second). Adverse
first is the pessimistic order every study used and the one that matched live 70/70 on fair
1m bars. A level created inside the bar (a new peak's trail floor, a breakeven armed at the
peak) can fire on the fall to the close. The 24h clock is read at OPEN and CLOSE polls only:
the extremes happen at unknown instants and would book the clock at the bar's best or worst
price. Bars that open before the fill are skipped (their range includes pre-fill prices).

Costs: net R = gross R - FUTURES_CONVEX_COST_PCT / sl_frac, the sleeve cost the trail's own
cost guard uses (0.19% round trip; within 0.03R of live fees, slightly cautious).
"""
from __future__ import annotations

import copy
import logging
import math
import os
from contextlib import contextmanager
from dataclasses import dataclass, replace
from functools import lru_cache
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Mapping

from futuresbot.marketdata import MexcFuturesClient
from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime

# ---------------------------------------------------------------------------------------------
# live parameters: names and code defaults (what the bot does when the variable is unset)
# ---------------------------------------------------------------------------------------------
LIVE_ENV_DEFAULTS: dict[str, float] = {
    "FUTURES_CONVEX_TRAIL_ARM_R": 1.0,
    "FUTURES_CONVEX_TRAIL_RETAIN_FRAC": 0.30,
    "FUTURES_CONVEX_TRAIL_GIVEBACK_R": 2.0,
    "FUTURES_CONVEX_TRAIL_RATCHET_R": 3.0,
    "FUTURES_CONVEX_TRAIL_RATCHET_RETAIN": 0.75,
    "FUTURES_CONVEX_COST_PCT": 0.190,
    "FUTURES_CONVEX_COST_FLOOR_MULT": 1.5,
    "FUTURES_CONVEX_EARLY_STOP_R": 0.0,
    "FUTURES_CONVEX_EARLY_STOP_MINUTES": 30.0,
    "FUTURES_CONVEX_BREAKEVEN_ARM_R": 0.0,
    "FUTURES_CONVEX_BREAKEVEN_COST_PCT": 0.19,
    "FUTURES_CONVEX_BREAKEVEN_SHADOW_R": 0.75,   # telemetry only: never sends an order
    "FUTURES_CONVEX_TIME_STOP_HOURS": 24.0,
}
LIVE_FLAG_DEFAULTS: dict[str, bool] = {
    "FUTURES_CONVEX_RUNNER_TRAIL": True,
    "FUTURES_WILDCARD_CONVEX_EXIT_ENABLED": False,
    "FUTURES_TREND_TRAIL_ENABLED": True,          # read on a TREND position only (_trail_enabled_for)
}
# TREND-only arm overrides (runtime._trail_arm_r_for / _breakeven_arm_r_for): read on a TREND position only,
# each falling back to the shared variable when unset, clamped at 0. name -> the shared name it falls back to.
TREND_FALLBACKS: dict[str, str] = {
    "FUTURES_TREND_TRAIL_ARM_R": "FUTURES_CONVEX_TRAIL_ARM_R",
    "FUTURES_TREND_BREAKEVEN_ARM_R": "FUTURES_CONVEX_BREAKEVEN_ARM_R",
}


def _per_sleeve(f: Any, sleeve: str, shared_name: str) -> float:
    """runtime._trail_arm_r_for / _breakeven_arm_r_for: the shared value, overridden on TREND by its
    FUTURES_TREND_ variable when that is set; clamped at 0 on every sleeve."""
    shared = f(shared_name, LIVE_ENV_DEFAULTS[shared_name])
    if sleeve == "TREND":
        name = next(k for k, v in TREND_FALLBACKS.items() if v == shared_name)
        return max(0.0, f(name, shared))
    return max(0.0, shared)
# Read as "FUTURES_" + kind + suffix, falling back to the CONVEX_ value (runtime.py 2478-2482).
PER_SLEEVE_SUFFIXES = ("_EARLY_STOP_R", "_EARLY_STOP_MINUTES")
CONVEX_SLEEVES = ("WILDCARD", "SQUEEZE", "TREND")      # _is_wildcard_convex

_TRIGGER_CODE_FEED = {1: "last", 2: "fair", 3: "index"}  # MEXC place-order docs, marketdata.py 374


def live_order_feeds(side_code: int = 1) -> tuple[str, str]:
    """(stop_feed, tp_feed) the live bracket rests on, read from the live order builder."""
    profit, loss = MexcFuturesClient._trigger_trends_for_order_side(side_code)
    return _TRIGGER_CODE_FEED[int(loss)], _TRIGGER_CODE_FEED[int(profit)]


def _parse_float(raw: Any, default: float) -> float:
    """FuturesRuntime._env_float's parse, applied to a mapping instead of os.environ."""
    try:
        if raw is None or str(raw).strip() == "":
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _parse_flag(raw: Any, default: bool) -> bool:
    """FuturesRuntime._flag's parse, applied to a mapping."""
    value = ("1" if default else "0") if raw is None or str(raw).strip() == "" else str(raw)
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class ExitPolicy:
    """The exit configuration of one position. Field defaults are the CODE defaults; use
    `from_env` for an environment and `live_at` for what was deployed at a given instant."""

    sleeve: str = "WILDCARD"
    convex: bool = False            # FUTURES_WILDCARD_CONVEX_EXIT_ENABLED (live: 1)
    trail: bool = True              # FUTURES_CONVEX_RUNNER_TRAIL
    arm_r: float = 1.0
    retain: float = 0.30
    giveback_r: float = 2.0
    ratchet_r: float = 3.0
    ratchet_retain: float = 0.75
    cost_pct: float = 0.190
    cost_floor_mult: float = 1.5
    early_stop_r: float = 0.0
    early_stop_minutes: float = 30.0
    breakeven_arm_r: float = 0.0
    breakeven_cost_pct: float = 0.19
    time_stop_hours: float = 24.0
    stop_feed: str = "fair"
    tp_feed: str = "last"
    # FUTURES_TREND_TRAIL_ENABLED; only a TREND policy reads it (always True elsewhere). Off = the trail never
    # fires, while the peak and the breakeven stop keep running - unlike `trail` (the master switch), which
    # takes the breakeven stop with it.
    sleeve_trail: bool = True

    # -- construction ---------------------------------------------------------------------
    @classmethod
    def from_env(cls, sleeve: str, env: Mapping[str, str] | None = None, *,
                 side_code: int = 1) -> "ExitPolicy":
        """Read exactly the variables the live methods read, with their clamps. env=None reads
        os.environ through the live FuturesRuntime._env_float / _flag themselves."""
        sleeve = sleeve.upper()
        if env is None:
            f = FuturesRuntime._env_float
            g = FuturesRuntime._flag
        else:
            def f(name: str, default: float) -> float:
                return _parse_float(env.get(name), default)

            def g(name: str, default: bool = False) -> bool:
                return _parse_flag(env.get(name), default)
        d = LIVE_ENV_DEFAULTS
        stop_feed, tp_feed = live_order_feeds(side_code)
        return cls(
            sleeve=sleeve,
            convex=g("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", LIVE_FLAG_DEFAULTS["FUTURES_WILDCARD_CONVEX_EXIT_ENABLED"]),
            trail=g("FUTURES_CONVEX_RUNNER_TRAIL", LIVE_FLAG_DEFAULTS["FUTURES_CONVEX_RUNNER_TRAIL"]),
            arm_r=_per_sleeve(f, sleeve, "FUTURES_CONVEX_TRAIL_ARM_R"),
            retain=f("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", d["FUTURES_CONVEX_TRAIL_RETAIN_FRAC"]),
            giveback_r=max(0.1, f("FUTURES_CONVEX_TRAIL_GIVEBACK_R", d["FUTURES_CONVEX_TRAIL_GIVEBACK_R"])),
            ratchet_r=f("FUTURES_CONVEX_TRAIL_RATCHET_R", d["FUTURES_CONVEX_TRAIL_RATCHET_R"]),
            ratchet_retain=f("FUTURES_CONVEX_TRAIL_RATCHET_RETAIN", d["FUTURES_CONVEX_TRAIL_RATCHET_RETAIN"]),
            cost_pct=f("FUTURES_CONVEX_COST_PCT", d["FUTURES_CONVEX_COST_PCT"]),
            cost_floor_mult=f("FUTURES_CONVEX_COST_FLOOR_MULT", d["FUTURES_CONVEX_COST_FLOOR_MULT"]),
            early_stop_r=f("FUTURES_" + sleeve + "_EARLY_STOP_R",
                           f("FUTURES_CONVEX_EARLY_STOP_R", d["FUTURES_CONVEX_EARLY_STOP_R"])),
            early_stop_minutes=f("FUTURES_" + sleeve + "_EARLY_STOP_MINUTES",
                                 f("FUTURES_CONVEX_EARLY_STOP_MINUTES", d["FUTURES_CONVEX_EARLY_STOP_MINUTES"])),
            breakeven_arm_r=_per_sleeve(f, sleeve, "FUTURES_CONVEX_BREAKEVEN_ARM_R"),
            breakeven_cost_pct=max(0.0, f("FUTURES_CONVEX_BREAKEVEN_COST_PCT", d["FUTURES_CONVEX_BREAKEVEN_COST_PCT"])),
            time_stop_hours=max(0.0, f("FUTURES_CONVEX_TIME_STOP_HOURS", d["FUTURES_CONVEX_TIME_STOP_HOURS"])),
            stop_feed=stop_feed,
            tp_feed=tp_feed,
            sleeve_trail=(g("FUTURES_TREND_TRAIL_ENABLED", LIVE_FLAG_DEFAULTS["FUTURES_TREND_TRAIL_ENABLED"])
                          if sleeve == "TREND" else True),
        )

    def env(self) -> dict[str, str]:
        """The environment under which the LIVE code runs this policy (every variable set)."""
        k = self.sleeve
        return {
            "FUTURES_WILDCARD_CONVEX_EXIT_ENABLED": "1" if self.convex else "0",
            "FUTURES_CONVEX_RUNNER_TRAIL": "1" if self.trail else "0",
            "FUTURES_CONVEX_TRAIL_ARM_R": repr(self.arm_r),
            "FUTURES_CONVEX_TRAIL_RETAIN_FRAC": repr(self.retain),
            "FUTURES_CONVEX_TRAIL_GIVEBACK_R": repr(self.giveback_r),
            "FUTURES_CONVEX_TRAIL_RATCHET_R": repr(self.ratchet_r),
            "FUTURES_CONVEX_TRAIL_RATCHET_RETAIN": repr(self.ratchet_retain),
            "FUTURES_CONVEX_COST_PCT": repr(self.cost_pct),
            "FUTURES_CONVEX_COST_FLOOR_MULT": repr(self.cost_floor_mult),
            "FUTURES_CONVEX_EARLY_STOP_R": "0",
            "FUTURES_CONVEX_EARLY_STOP_MINUTES": "30",
            f"FUTURES_{k}_EARLY_STOP_R": repr(self.early_stop_r),
            f"FUTURES_{k}_EARLY_STOP_MINUTES": repr(self.early_stop_minutes),
            "FUTURES_CONVEX_BREAKEVEN_ARM_R": repr(self.breakeven_arm_r),
            "FUTURES_CONVEX_BREAKEVEN_COST_PCT": repr(self.breakeven_cost_pct),
            "FUTURES_CONVEX_BREAKEVEN_SHADOW_R": "0",
            "FUTURES_CONVEX_TIME_STOP_HOURS": repr(self.time_stop_hours),
            # The TREND-only variables, on a TREND policy only (the runtime reads them nowhere else).
            **({"FUTURES_TREND_TRAIL_ENABLED": "1" if self.sleeve_trail else "0",
                "FUTURES_TREND_TRAIL_ARM_R": repr(self.arm_r),
                "FUTURES_TREND_BREAKEVEN_ARM_R": repr(self.breakeven_arm_r)} if k == "TREND" else {}),
        }

    @classmethod
    def live_at(cls, sleeve: str, side: str, t: float) -> "ExitPolicy":
        """What was DEPLOYED at epoch t for this sleeve and side (see LIVE_TIMELINE)."""
        if t < LIVE_TIMELINE[0][0]:
            raise ValueError("the deployed exit timeline is modelled from 2026-08-29 00:37Z "
                             "(retain 0.50); earlier fills ran a stack this module does not describe")
        env: dict[str, str] = {}
        for ts, change in LIVE_TIMELINE:
            if t >= ts:
                env.update(change)
        pol = cls.from_env(sleeve, env)
        if side.upper() == "SHORT" and t < SHORT_FEED_FIX_TS:
            # Before baa28b2 the order builder read the codes as directions and returned
            # (profitTrend=2, lossTrend=1) for shorts: stop on LAST, target on FAIR.
            pol = replace(pol, stop_feed="last", tp_feed="fair")
        return pol

    @classmethod
    def live_now(cls, sleeve: str, side: str = "LONG") -> "ExitPolicy":
        """Today's deployed stack: the end of LIVE_TIMELINE. The resolver's default - a study
        that forgets to pass a policy must get the live exits, not the code defaults (which have
        the convex exits switched OFF)."""
        return cls.live_at(sleeve, side, float("inf"))

    @classmethod
    def live_switches_between(cls, sleeve: str, side: str, t0: float, t1: float) -> list[float]:
        """Deployments inside (t0, t1) that changed THIS sleeve/side's policy: a position open
        across one ran two policies, which `live_at(t_entry)` cannot represent."""
        cand = sorted({ts for ts, _ in LIVE_TIMELINE} | {SHORT_FEED_FIX_TS})
        return [ts for ts in cand if t0 < ts < t1 and ts - 1 >= LIVE_TIMELINE[0][0]
                and cls.live_at(sleeve, side, ts - 1) != cls.live_at(sleeve, side, ts)]


def _utc(*a: int) -> float:
    return datetime(*a, tzinfo=timezone.utc).timestamp()


# The DEPLOYED exit configuration over time, cumulative. Sources:
#   2026-08-29 00:37Z  retain 0.30 -> 0.50, trial 18 (docs/LIVE_CONFIG.md line 9).
#   2026-09-08 18:20Z  WILDCARD early stop -0.5R / 30 min (commit 6d9fbce 18:11:52Z + env; first
#                      fire MARSCOIN 09-09 22:14Z; wc/ASSESS/A used 18:20Z, no fill in between).
#   2026-09-16 06:15Z  SHORT stop LAST -> FAIR, target FAIR -> LAST (commit baa28b2 06:13:42Z).
#   2026-09-20 10:53Z  breakeven stop at a 0.90R peak (DECISION_RULE.md: deployed 10:52:57Z).
#   The whole stack re-read from the container env 2026-09-23 (wc/ASSESS/A/env_now.txt).
LIVE_TIMELINE: tuple[tuple[float, dict[str, str]], ...] = (
    (_utc(2026, 8, 29, 0, 37), {"FUTURES_WILDCARD_CONVEX_EXIT_ENABLED": "1",
                                "FUTURES_CONVEX_TRAIL_RETAIN_FRAC": "0.50",
                                "FUTURES_TREND_EARLY_STOP_R": "0.0"}),
    (_utc(2026, 9, 8, 18, 20), {"FUTURES_WILDCARD_EARLY_STOP_R": "0.5",
                                "FUTURES_WILDCARD_EARLY_STOP_MINUTES": "30"}),
    (_utc(2026, 9, 20, 10, 53), {"FUTURES_CONVEX_BREAKEVEN_ARM_R": "0.90"}),
)
SHORT_FEED_FIX_TS = _utc(2026, 9, 16, 6, 15)


def timeline_drift(live_env: Mapping[str, str]) -> list[str]:
    """Differences between LIVE_TIMELINE's end and an exit-env snapshot taken from the container
    (tools/archive_evidence.py writes one a day). Non-empty means the owner changed an exit dial
    and LIVE_TIMELINE needs a new row - until then `live_now` replays a stack that is not live."""
    out = []
    for sleeve in ("WILDCARD", "TREND"):
        want = ExitPolicy.from_env(sleeve, live_env)
        have = ExitPolicy.live_now(sleeve)
        for name in ("convex", "trail", "arm_r", "retain", "giveback_r", "ratchet_r", "ratchet_retain",
                     "cost_pct", "cost_floor_mult", "early_stop_r", "early_stop_minutes", "breakeven_arm_r",
                     "breakeven_cost_pct", "time_stop_hours", "stop_feed", "tp_feed", "sleeve_trail"):
            a, b = getattr(have, name), getattr(want, name)
            if a != b:
                out.append(f"{sleeve}.{name}: timeline {a!r} != live {b!r}")
    return out


# ---------------------------------------------------------------------------------------------
# the rules, as pure functions of R (mirrors; see the module docstring for line numbers)
# ---------------------------------------------------------------------------------------------
@lru_cache(maxsize=256)
def _ratchet_shim(ratchet_r: float, ratchet_retain: float) -> SimpleNamespace:
    vals = {"FUTURES_CONVEX_TRAIL_RATCHET_R": ratchet_r, "FUTURES_CONVEX_TRAIL_RATCHET_RETAIN": ratchet_retain}
    return SimpleNamespace(_env_float=lambda name, default: vals.get(name, default))


def retain_for(policy: ExitPolicy, peak_r: float, base: float) -> float:
    """The LIVE FuturesRuntime._trail_retain_for, fed this policy's ratchet parameters."""
    shim = _ratchet_shim(policy.ratchet_r, policy.ratchet_retain)
    return FuturesRuntime._trail_retain_for(shim, peak_r, base)  # type: ignore[arg-type]


def cost_r(policy: ExitPolicy, sl_frac: float) -> float:
    return policy.cost_pct / 100.0 / sl_frac if sl_frac > 0 else 0.0


def trail_floor_r(policy: ExitPolicy, peak_r: float, sl_frac: float) -> float | None:
    """Exit level of the retention trail for a peak, or None when it cannot fire."""
    if not (policy.convex and policy.sleeve in CONVEX_SLEEVES and policy.trail):
        return None
    if policy.sleeve == "TREND" and not policy.sleeve_trail:
        return None                  # _trail_enabled_for: the peak and the breakeven stop still run
    if peak_r < policy.arm_r:
        return None
    if policy.retain > 0:
        level = retain_for(policy, peak_r, policy.retain) * peak_r
        if sl_frac > 0:
            level = max(level, cost_r(policy, sl_frac) * policy.cost_floor_mult)
            if level >= peak_r:
                return None                       # cannot trail profitably: SL/TP/clock only
        return level
    return peak_r - policy.giveback_r


def early_stop_live(policy: ExitPolicy, elapsed_min: float) -> float | None:
    """The early-stop level (-X R) if it is armed at this elapsed time, else None."""
    if not (policy.convex and policy.sleeve in CONVEX_SLEEVES):
        return None
    arm, window = policy.early_stop_r, policy.early_stop_minutes
    if arm <= 0 or not math.isfinite(arm) or window <= 0 or not math.isfinite(window):
        return None
    if elapsed_min < 0.0 or elapsed_min > window:
        return None
    return -arm


def breakeven_r(policy: ExitPolicy, sl_frac: float) -> float | None:
    """R of the breakeven stop price (entry +/- cost), None when the rule cannot arm."""
    if not (policy.convex and policy.sleeve in CONVEX_SLEEVES and policy.trail):
        return None                              # it lives inside the trail method
    cost = policy.breakeven_cost_pct / 100.0
    if policy.breakeven_arm_r <= 0 or cost <= 0 or sl_frac <= 0:
        return None
    return cost / sl_frac


def time_stop_s(policy: ExitPolicy) -> float | None:
    if not (policy.convex and policy.sleeve in CONVEX_SLEEVES) or policy.time_stop_hours <= 0:
        return None
    return policy.time_stop_hours * 3600.0


# ---------------------------------------------------------------------------------------------
# the resolver
# ---------------------------------------------------------------------------------------------
KIND_TO_LIVE_REASON = {
    "stop": "EXCHANGE_CLOSE", "breakeven": "EXCHANGE_CLOSE", "tp": "EXCHANGE_CLOSE",
    "trail": "CONVEX_RETENTION_TRAIL", "early": "CONVEX_EARLY_STOP", "timeout": "CONVEX_TIME_STOP",
    "open": "OPEN",
}
_POLL_OFFSETS = (0.0, 20.0, 40.0, 59.0)        # open, adverse, favourable, close (1m bars)


@dataclass(frozen=True)
class Trade:
    side: str
    entry: float
    sl: float
    tp: float | None
    t_entry: float
    sleeve: str = "WILDCARD"
    symbol: str = ""

    @property
    def s(self) -> float:
        return 1.0 if self.side.upper() == "LONG" else -1.0

    @property
    def one_r(self) -> float:
        return abs(self.entry - self.sl)

    @property
    def sl_frac(self) -> float:
        return self.one_r / self.entry if self.entry else 0.0

    def r(self, px: float) -> float:
        return (px - self.entry) * self.s / self.one_r

    def px(self, r: float) -> float:
        return self.entry + self.s * r * self.one_r


@dataclass(frozen=True)
class ExitResult:
    kind: str                    # stop | breakeven | tp | trail | early | timeout | open
    reason: str                  # the live exit_reason this kind is recorded under
    exit_ts: float | None
    exit_price: float | None     # trigger price on the feed that fired (fills are not modelled)
    gross_r: float | None
    cost_r: float
    net_r: float | None
    peak_r: float
    trough_r: float
    breakeven_armed_ts: float | None
    bars_walked: int


def _rows(bars: Any) -> list[tuple[float, float, float, float, float]]:
    if bars is None:
        return []
    if hasattr(bars, "rows"):
        bars = bars.rows()
    return [(float(t), float(o), float(h), float(l), float(c)) for t, o, h, l, c in bars]


def _bar_points(trade: Trade, o: float, h: float, l: float, c: float) -> tuple[float, float, float, float]:
    """(open, adverse, favourable, close) in R."""
    ro, rh, rl, rc = trade.r(o), trade.r(h), trade.r(l), trade.r(c)
    return ro, min(rh, rl), max(rh, rl), rc


def _cross(r0: float, r1: float, level: float, falling: bool) -> float | None:
    """Fraction of a continuous move r0 -> r1 at which `level` is first touched, else None."""
    if falling:
        if r1 > level:
            return None
        if r0 <= level:
            return 0.0
        return (r0 - level) / (r0 - r1)
    if r1 < level:
        return None
    if r0 >= level:
        return 0.0
    return (level - r0) / (r1 - r0)


def resolve_exit(trade: Trade, fair_bars: Any, last_bars: Any = None, policy: ExitPolicy | None = None, *,
                 bar_seconds: float = 60.0) -> ExitResult:
    """Walk 1m bars from the first bar that opens after the fill; return the first exit.

    fair_bars / last_bars: (t_open, open, high, low, close) rows or replay.bars.Bars. The software
    exits read FAIR; each resting order reads the feed its trigger type names (policy.stop_feed,
    policy.tp_feed). A bar missing from the resting order's feed falls back to FAIR for that bar.
    """
    pol = policy or ExitPolicy.live_now(trade.sleeve, trade.side)
    if trade.one_r <= 0 or trade.entry <= 0:
        raise ValueError("trade needs entry > 0 and a stop distance")
    fair = [b for b in _rows(fair_bars) if b[0] >= trade.t_entry]
    other = {b[0]: b for b in _rows(last_bars)}
    need_last = "last" in (pol.stop_feed, pol.tp_feed)
    if need_last and last_bars is None:
        raise ValueError(f"policy reads LAST price ({pol.stop_feed=}, {pol.tp_feed=}); pass last_bars")
    scale = bar_seconds / 60.0
    offsets = tuple(x * scale for x in _POLL_OFFSETS)
    sl_frac = trade.sl_frac
    c_r = cost_r(pol, sl_frac)
    tp_r = trade.r(trade.tp) if trade.tp else None
    be_level = breakeven_r(pol, sl_frac)
    clock = time_stop_s(pol)
    deadline = trade.t_entry + clock if clock is not None else None

    peak = 0.0
    trough = 0.0
    be_armed_ts: float | None = None
    prev = {"soft": 0.0, "stop": 0.0, "tp": 0.0}      # the fill itself: R = 0 on every feed
    walked = 0

    def done(kind: str, r: float, ts: float) -> ExitResult:
        return ExitResult(kind, KIND_TO_LIVE_REASON[kind], ts, trade.px(r), r, c_r, r - c_r, peak,
                          min(trough, r), be_armed_ts, walked)

    for t, o, h, l, c in fair:
        walked += 1
        soft = _bar_points(trade, o, h, l, c)
        feeds = {}
        for name, feed in (("stop", pol.stop_feed), ("tp", pol.tp_feed)):
            src = other.get(t) if feed == "last" else None
            feeds[name] = _bar_points(trade, *src[1:]) if src else soft
        for i in range(4):
            pt_time = t + offsets[i]
            r_soft, r_stop, r_tp = soft[i], feeds["stop"][i], feeds["tp"][i]
            jump = i == 0
            falling = i in (1, 3)
            # (1) resting orders along the move that ends at this poll
            cands: list[tuple[float, int, str, float]] = []     # (fraction, priority, kind, R)
            eff_stop = be_level if be_armed_ts is not None else -1.0
            if jump or falling:
                lam = _cross(prev["stop"], r_stop, eff_stop, True)
                if lam is not None:
                    at = r_stop if jump else eff_stop
                    kind = "breakeven" if be_armed_ts is not None else "stop"
                    cands.append((1.0 if jump else lam, 0, kind, at))
            if tp_r is not None and (jump or i == 2):
                lam = _cross(prev["tp"], r_tp, tp_r, False)
                if lam is not None:
                    cands.append((1.0 if jump else lam, 0, "tp", r_tp if jump else tp_r))
            # (2) software exits, polled on FAIR: early, then trail (the live order)
            if jump or falling:
                es = early_stop_live(pol, (pt_time - trade.t_entry) / 60.0)
                if es is not None:
                    lam = _cross(prev["soft"], r_soft, es, True)
                    if lam is not None:
                        cands.append((1.0 if jump else lam, 1, "early", r_soft if jump else es))
                fl = trail_floor_r(pol, peak, sl_frac)
                if fl is not None:
                    lam = _cross(prev["soft"], r_soft, fl, True)
                    if lam is not None:
                        cands.append((1.0 if jump else lam, 2, "trail", r_soft if jump else fl))
            if cands:
                lam, _prio, kind, r_exit = min(cands, key=lambda x: (x[0], x[1]))
                # A jump fills at the open; a continuous move at the crossing instant.
                ts = pt_time if jump else (t + offsets[i - 1] + lam * (offsets[i] - offsets[i - 1]))
                if kind in ("stop", "breakeven"):
                    trough = min(trough, r_exit)
                return done(kind, r_exit, ts)
            trough = min(trough, r_soft)
            # (3) state the trail method updates on this poll: breakeven arm, then the peak
            if pol.convex and pol.sleeve in CONVEX_SLEEVES and pol.trail:
                if (be_level is not None and be_armed_ts is None and max(peak, r_soft) >= pol.breakeven_arm_r
                        and r_soft > be_level):
                    be_armed_ts = pt_time
                if r_soft > peak:
                    peak = round(r_soft, 4)      # stored rounded, runtime.py 2782; floors derive from it
            # (4) the clock, on the open and close polls only
            if deadline is not None and i in (0, 3) and pt_time >= deadline:
                return done("timeout", r_soft, pt_time)
            prev = {"soft": r_soft, "stop": r_stop, "tp": r_tp}
    return ExitResult("open", "OPEN", None, None, None, c_r, None, peak, trough, be_armed_ts, walked)


# ---------------------------------------------------------------------------------------------
# live-record helpers (for scoring a replay against what live booked)
# ---------------------------------------------------------------------------------------------
LIVE_RULE_KIND = {"CONVEX_RETENTION_TRAIL": "trail", "CONVEX_EARLY_STOP": "early",
                  "CONVEX_TIME_STOP": "timeout", "STOP_LOSS": "stop",
                  "CONVEX_PREEMPTED": "preempt", "MANUAL_CLOSE": "manual"}


def live_exit_kind(exit_rule: str | None, gross_r: float, tp_r: float | None, be_r: float | None,
                   breakeven_live: bool) -> str:
    """Kind of a LIVE close. Exchange-side closes are all recorded EXCHANGE_CLOSE, so the stop,
    the target and the breakeven stop are told apart by where they filled (the rule used for the
    assessment's 70/70 count, wc/ASSESS/A/a03_resolve.live_kind)."""
    if exit_rule in LIVE_RULE_KIND:
        return LIVE_RULE_KIND[exit_rule]
    if tp_r is not None and abs(gross_r - tp_r) < 0.35:
        return "tp"
    if breakeven_live and be_r is not None and abs(gross_r - be_r) < 0.2:
        return "breakeven"
    if gross_r < -0.7:
        return "stop"
    return "exchange_unexplained"


# ---------------------------------------------------------------------------------------------
# the reference: the bot's own exit methods, driven poll by poll (slow; verification only)
# ---------------------------------------------------------------------------------------------
@contextmanager
def _environ(values: Mapping[str, str]):
    saved = {k: os.environ.get(k) for k in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class LiveCodeReference:
    """Resolves a trade with runtime.FuturesRuntime's own exit methods.

    Every software decision is the live code's: _convex_early_stop_exit, _convex_runner_trail_exit
    (with _maybe_breakeven_stop and _trail_retain_for inside it) and _convex_time_stop_exit, in
    _hourly_exit's order, reading the policy through the live _env_float/_flag (os.environ is set
    for the duration of a call and restored). The exchange is emulated: the resting stop sits at
    FuturesRuntime._effective_stop_price (the breakeven price once armed) on policy.stop_feed and
    the target at tp_price on policy.tp_feed. Order placement, persistence and notifications are
    stubbed out on the instance only. Where a software exit fires at the end of a continuous
    move, the crossing price is found by bisection on a copy of the position state.
    """

    def __init__(self, policy: ExitPolicy) -> None:
        self.policy = policy
        rt = object.__new__(FuturesRuntime)
        rt.config = SimpleNamespace(paper_trade=False)
        rt._save_state = lambda: None
        rt._record_activity = lambda *a, **k: None
        rt._record_r_sample = lambda *a, **k: None
        rt._maybe_record_peak_notify = lambda *a, **k: None
        rt._notify = lambda *a, **k: None
        rt._format_price = lambda x: str(x)
        rt._move_exchange_stop = lambda position, new_sl, current_price=None: True
        self._closes: list[tuple[str, float]] = []
        rt._close_position_for_exit = (
            lambda position, *, current_price, reason: self._closes.append((reason, current_price)) or True)
        self.rt = rt

    def _position(self, trade: Trade) -> FuturesPosition:
        md: dict[str, Any] = {"wildcard": 1.0, "trail_mode": "retention"}
        if trade.sleeve.upper() == "TREND":
            md["trend"] = 1.0
        elif trade.sleeve.upper() == "SQUEEZE":
            md["squeeze"] = 1.0
        md["sl_margin_pct"] = trade.one_r / trade.entry * 100.0     # leverage 1: margin = entry
        return FuturesPosition(
            symbol=trade.symbol or "REPLAY_USDT", side=trade.side.upper(), entry_price=trade.entry,
            contracts=1, contract_size=1.0, leverage=1, margin_usdt=trade.entry,
            tp_price=float(trade.tp or 0.0), sl_price=trade.sl, position_id="replay", order_id="replay",
            opened_at=datetime.fromtimestamp(trade.t_entry, timezone.utc), score=0.0, certainty=0.0,
            entry_signal=f"{trade.sleeve.upper()}_{trade.side.upper()}", metadata=md)

    def _poll(self, pos: FuturesPosition, price: float, ts: float) -> str | None:
        now = datetime.fromtimestamp(ts, timezone.utc)
        self._closes.clear()
        rt = self.rt
        if rt._convex_early_stop_exit(pos, price, now=now):
            return self._closes[-1][0]
        if rt._convex_runner_trail_exit(pos, price):
            return self._closes[-1][0]
        if rt._convex_time_stop_exit(pos, price, now=now):
            return self._closes[-1][0]
        return None

    def resolve(self, trade: Trade, fair_bars: Any, last_bars: Any = None, *,
                bar_seconds: float = 60.0) -> ExitResult:
        pol = self.policy
        rt_log = logging.getLogger(FuturesRuntime.__module__)
        was = rt_log.disabled
        rt_log.disabled = True                     # every bisection step would log a close
        try:
            with _environ(pol.env()):
                return self._resolve(trade, fair_bars, last_bars, bar_seconds)
        finally:
            rt_log.disabled = was

    def _resolve(self, trade: Trade, fair_bars: Any, last_bars: Any, bar_seconds: float) -> ExitResult:
        pol = self.policy
        pos = self._position(trade)
        s = trade.s
        other = {b[0]: b for b in _rows(last_bars)}
        offsets = tuple(x * bar_seconds / 60.0 for x in _POLL_OFFSETS)
        c_r = cost_r(pol, trade.sl_frac)
        prev_px = {"soft": trade.entry, "stop": trade.entry, "tp": trade.entry}
        trough = 0.0
        walked = 0
        be_ts: float | None = None

        def out(kind: str, px: float, ts: float) -> ExitResult:
            r = trade.r(px)
            peak = FuturesRuntime._metadata_float(pos.metadata, "convex_peak_r") or 0.0
            return ExitResult(kind, KIND_TO_LIVE_REASON[kind], ts, px, r, c_r, r - c_r, peak,
                              min(trough, r), be_ts, walked)

        def path(o, h, l, c):
            adv, fav = (l, h) if s > 0 else (h, l)
            return (o, adv, fav, c)

        for t, o, h, l, c in (b for b in _rows(fair_bars) if b[0] >= trade.t_entry):
            walked += 1
            soft = path(o, h, l, c)
            fd = {}
            for name, feed in (("stop", pol.stop_feed), ("tp", pol.tp_feed)):
                src = other.get(t) if feed == "last" else None
                fd[name] = path(*src[1:]) if src else soft
            for i in range(4):
                ts = t + offsets[i]
                jump = i == 0
                cands = []
                # exchange: resting stop (breakeven once armed) and target
                stop_px = FuturesRuntime._effective_stop_price(pos)
                sp0, sp1 = prev_px["stop"], fd["stop"][i]
                if i != 2 and (sp1 - stop_px) * s <= 0:
                    lam = 1.0 if jump else (0.0 if (sp0 - stop_px) * s <= 0 else (sp0 - stop_px) / (sp0 - sp1))
                    kind = "breakeven" if pos.metadata.get("be_stop_price") else "stop"
                    cands.append((lam, 0, kind, sp1 if jump else stop_px))
                if trade.tp and (jump or i == 2):
                    tp0, tp1 = prev_px["tp"], fd["tp"][i]
                    if (tp1 - trade.tp) * s >= 0:
                        lam = 1.0 if jump else (0.0 if (tp0 - trade.tp) * s >= 0 else (trade.tp - tp0) / (tp1 - tp0))
                        cands.append((lam, 0, "tp", tp1 if jump else trade.tp))
                # software: the live methods on a COPY, so an exit can be bisected back
                p1 = soft[i]
                snap = copy.deepcopy(pos.metadata)
                reason = self._poll(pos, p1, ts)
                if reason is not None and reason != "CONVEX_TIME_STOP":
                    kind = {"CONVEX_EARLY_STOP": "early", "CONVEX_RETENTION_TRAIL": "trail",
                            "CONVEX_RUNNER_TRAIL": "trail"}[reason]
                    px, lam = p1, 1.0
                    if not jump:
                        lo, hi = 0.0, 1.0            # fraction along prev -> p1
                        p0 = prev_px["soft"]
                        for _ in range(60):
                            mid = (lo + hi) / 2.0
                            pos.metadata = copy.deepcopy(snap)
                            if self._poll(pos, p0 + mid * (p1 - p0), ts) is not None:
                                hi = mid
                            else:
                                lo = mid
                        pos.metadata = copy.deepcopy(snap)
                        reason = self._poll(pos, p0 + hi * (p1 - p0), ts)
                        kind = {"CONVEX_EARLY_STOP": "early", "CONVEX_RETENTION_TRAIL": "trail",
                                "CONVEX_RUNNER_TRAIL": "trail", "CONVEX_TIME_STOP": "timeout"}[reason]
                        px, lam = p0 + hi * (p1 - p0), hi
                    cands.append((lam, 1, kind, px))
                if cands:
                    lam, _p, kind, px = min(cands, key=lambda x: (x[0], x[1]))
                    ets = ts if jump else t + offsets[i - 1] + lam * (offsets[i] - offsets[i - 1])
                    trough = min(trough, trade.r(px))
                    return out(kind, px, ets)
                trough = min(trough, trade.r(p1))
                if be_ts is None and pos.metadata.get("be_stop_price"):
                    be_ts = ts
                if reason == "CONVEX_TIME_STOP" and i in (0, 3):
                    return out("timeout", p1, ts)
                if reason == "CONVEX_TIME_STOP":
                    # The clock is read on open/close polls only (see the module docstring);
                    # undo this poll's state change and let the close poll take it.
                    pos.metadata = snap
                    self._poll_state_only(pos, p1, ts)
                prev_px = {"soft": p1, "stop": fd["stop"][i], "tp": fd["tp"][i]}
        peak = FuturesRuntime._metadata_float(pos.metadata, "convex_peak_r") or 0.0
        return ExitResult("open", "OPEN", None, None, None, c_r, None, peak, trough, be_ts, walked)

    def _poll_state_only(self, pos: FuturesPosition, price: float, ts: float) -> None:
        """A poll with the clock switched off: the early stop and trail update their state."""
        with _environ({"FUTURES_CONVEX_TIME_STOP_HOURS": "0"}):
            self._poll(pos, price, ts)
