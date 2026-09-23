"""Path-faithful sizing engine: turn a stream of trades (R outcomes) into the DOLLAR path the live bot would book.

WHY. The 2026-09-23 impartial assessment graded "sizing in studies" F: every study booked a fixed stake ($23.50/R or
dial x $949 per fill) although live sizes each entry off the exchange's AVAILABLE balance at that instant, and the
available balance is cash minus the isolated margin locked by the positions already open. Measured consequences:
  - available averaged 0.926x cash (as low as 0.72x) while trades overlapped: -$7.5/mo at $949, and trade order adds
    +/-$13/mo of noise that no fixed-stake study can see;
  - variance drag at today's dials is about $22/mo; on thin edges a fixed-stake "+$X/mo" overstates the typical
    12-month result 1.8-2.6x (replay lines E +48.78 -> +20.51, V +26.22 -> -0.43, H +78.66 -> +58.77, B +90.18 -> +75.27);
  - limits DELETE trades (minimum-contract skips on a falling balance, the per-trade risk cap zeroing AKE on 09-20),
    which no replay modelled.
Lane C (wc/ASSESS/C/sim.py) rebuilt the live chain and reproduced the live cash path to -$1.85 over 151 fills (lane V
re-derived -$1.66); tests/test_replay_sizing.py keeps that reproduction as a regression test on a frozen fixture.

THE CHAIN, in the order FuturesRuntime._open_wildcard_position applies it (runtime.py: _entry_margin, then the regime
scaler, the streak throttle, integer contracts, FUTURES_MAX_TRADE_RISK_PCT via risk_controls.risk_capped_contracts,
the min_vol skip):
    base    = available = cash - margin locked by open positions        (MEXC availableBalance; 149/149 fills within 1%)
    margin  = dial(sleeve, t) x base / (stop_frac x leverage)           (_entry_margin, risk-targeted since trial 7)
    margin  = min(margin, max_margin_frac x base)                       (FUTURES_WILDCARD_MAX_MARGIN_PCT = 0.25)
    margin *= regime_mult x streak_mult                                 (inputs: recorded live, or a replay's own)
    n       = floor(margin x leverage / (entry x contract_size))        (integer contracts)
    n       = min(n, floor(cap(t) x base / (contract_size x entry x stop_frac)))   (per-trade risk cap)
    skip if n < min_vol; else margin = n x contract_size x entry / leverage, risk = margin x stop_frac x leverage
    at the close: cash += r x risk                                      (r = realised R per unit of risk TAKEN)
R is size-invariant (fees scale with notional), which is what lets one R stream be re-priced under any sizing rule.

Timestamps are epoch SECONDS. Dials and caps are FRACTIONS (0.0187 = 1.87%), never percent.
"""
from __future__ import annotations

import bisect
import math
import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

MONTH_DAYS = 30.4375   # the record's month everywhere (365.25 / 12)


def _utc(*a: int) -> float:
    return datetime(*a, tzinfo=timezone.utc).timestamp()


@dataclass(frozen=True)
class StepSchedule:
    """A setting that changed over time: `initial` until the first change, then each (ts, value) from ts onward.

    History must be priced with the dial that was LIVE at each entry. Pricing the 08-22..09-15 fills at today's 1.205%
    TREND dial, or at one constant, is exactly the "which stake was it" error the record found three times."""
    initial: float
    changes: tuple[tuple[float, float], ...] = ()

    def __post_init__(self) -> None:
        ts = [float(t) for t, _ in self.changes]
        if ts != sorted(ts):
            raise ValueError("StepSchedule changes must be in time order")

    def at(self, t: float) -> float:
        if not self.changes:
            return float(self.initial)
        k = bisect.bisect_right([c[0] for c in self.changes], float(t))
        return float(self.initial if k == 0 else self.changes[k - 1][1])

    @classmethod
    def constant(cls, value: float) -> "StepSchedule":
        return cls(float(value))


# ---- live history ------------------------------------------------------------------------------------------------
# Per-sleeve dials (FUTURES_WILDCARD_RISK_PCT / FUTURES_TREND_RISK_PCT). Valid from trial 7 (2026-08-08, risk-targeted
# sizing ON); earlier fills were sized by balance_fraction and are NOT reproduced by this chain. Where the minute of a
# change is unrecorded it is pinned from the feature store's implied dial (risk_usdt / (equity_at_entry x regime x
# streak)) and every live fill prices identically anywhere inside the bracket:
#   08-22 raise 1.87% -> 2.41%, both sleeves: last 1.87% fill 08-22 08:10Z, first 2.41% fill 08-22 12:59Z -> 12:00Z.
#   TREND halving 2.41% -> 1.205% ("the owner's 09-16 halving"): last 2.41% TREND fill 09-14 20:23Z, first 1.205%
#     09-16 09:32Z -> 09-16 00:00Z.
#   WILDCARD 2.41% -> 1.87%: owner, live 2026-09-23 18:10Z (assessment: 2.41% sat 1.3-1.55x above growth-optimal).
LIVE_DIALS: dict[str, StepSchedule] = {
    "WILDCARD": StepSchedule(0.0187, ((_utc(2026, 8, 22, 12), 0.0241), (_utc(2026, 9, 23, 18, 10), 0.0187))),
    "TREND": StepSchedule(0.0187, ((_utc(2026, 8, 22, 12), 0.0241), (_utc(2026, 9, 16), 0.01205))),
}
# FUTURES_MAX_TRADE_RISK_PCT as a fraction of AVAILABLE: the standing 5%, except the owner's 0.886% cap from
# 2026-09-19 09:43Z until trial 22F reverted it (FUTURES_TRIAL_START_TS 1789907100 = 2026-09-20 12:25Z).
LIVE_TRADE_RISK_CAP = StepSchedule(0.05, ((_utc(2026, 9, 19, 9, 43), 0.00886), (_utc(2026, 9, 20, 12, 25), 0.05)))


@dataclass(frozen=True)
class ContractSpec:
    """Exchange contract spec. contract_size <= 0 means UNKNOWN (e.g. a delisted symbol, or a replay without specs):
    the trade is then sized continuously - no integer rounding, no min_vol skip - and the result says so."""
    contract_size: float = 0.0
    min_vol: int = 1


@dataclass(frozen=True)
class Trade:
    """One fill of the stream. `r` is the realised R per unit of the risk actually taken, net of fees and funding -
    the unit every replay already produces. `stop_frac` is |entry - stop| / entry as PLACED (after any stop-margin cap),
    so stop_frac x leverage x 100 is the live sl_margin_pct. regime_mult / streak_mult are INPUTS: the recorded live
    multipliers when reproducing live, the replay's own when pricing a replay."""
    t_open: float
    t_close: float
    sleeve: str
    r: float
    stop_frac: float
    leverage: float = 1.0
    entry_price: float = 1.0
    spec: ContractSpec = ContractSpec()
    regime_mult: float = 1.0
    streak_mult: float | None = None
    symbol: str = ""
    side: str = ""

    def __post_init__(self) -> None:
        if not (self.stop_frac > 0 and self.leverage > 0):
            raise ValueError(f"trade {self.symbol or '?'} @ {self.t_open}: stop_frac and leverage must be > 0")
        if self.t_close < self.t_open:
            raise ValueError(f"trade {self.symbol or '?'} @ {self.t_open}: closes before it opens")

    @property
    def sl_margin_pct(self) -> float:
        return self.stop_frac * self.leverage * 100.0

    @classmethod
    def from_sl_margin(cls, *, sl_margin_pct: float, leverage: float, **kw: Any) -> "Trade":
        """Build from the live record's sl_margin_pct (feature store / trade_history) instead of a stop distance."""
        return cls(stop_frac=float(sl_margin_pct) / (100.0 * float(leverage)), leverage=float(leverage), **kw)


@dataclass(frozen=True)
class CapitalFlow:
    """A deposit (+) or withdrawal (-), or any cash movement outside the priced stream (e.g. the realised P&L of a
    manual/PMT fill). An explicit event, because the 09-04 +$915.72 deposit multiplied the stake ~6x just before 81
    trades averaging -0.136R: across a deposit, realised dollars mostly measure WHEN the money arrived."""
    ts: float
    amount: float
    label: str = ""


@dataclass(frozen=True)
class StreakRule:
    """runtime._convex_streak_multiplier: consecutive most-recent losing closes (pnl < 0) among the last `lookback`;
    from `n` on, size halves per extra loss, floored. Live has it OFF (FUTURES_CONVEX_STREAK_THROTTLE_ENABLED=0,
    re-enabling it REFUTED at -$30 and worse); it exists here because it WAS on for part of the 08-13.. history, where
    the reproduction reads the recorded multiplier, and so a study can price it without a 64th copy."""
    n: int = 2
    floor: float = 0.25
    lookback: int = 20

    def multiplier(self, closed_pnls: Sequence[float]) -> float:
        k = 0
        for p in reversed(list(closed_pnls)[-self.lookback:]):
            if p < 0:
                k += 1
                continue
            break
        if k < max(1, int(self.n)):
            return 1.0
        return max(min(1.0, max(0.05, self.floor)), 0.5 ** (k - int(self.n) + 1))


@dataclass(frozen=True)
class SizingConfig:
    """Which parts of the chain are on. Defaults are LIVE's; switch parts off only to measure what each is worth.

    base: 'available' (live: cash - locked margin) | 'cash' (no free-margin effect) | 'fixed' (fixed_base, the old
    study convention - kept so a study can print the comparison, never as its headline).
    streak: 'recorded' (use Trade.streak_mult, 1.0 when None) | 'dynamic' (streak_rule on the simulated closes) | 'off'."""
    dials: Mapping[str, StepSchedule] = field(default_factory=lambda: dict(LIVE_DIALS))
    max_margin_frac: float = 0.25
    trade_risk_cap: StepSchedule | None = LIVE_TRADE_RISK_CAP
    base: str = "available"
    fixed_base: float = 0.0
    integer_contracts: bool = True
    apply_regime: bool = True
    streak: str = "recorded"
    streak_rule: StreakRule = StreakRule()

    def __post_init__(self) -> None:
        if self.base not in ("available", "cash", "fixed"):
            raise ValueError(f"base must be available|cash|fixed, not {self.base!r}")
        if self.streak not in ("recorded", "dynamic", "off"):
            raise ValueError(f"streak must be recorded|dynamic|off, not {self.streak!r}")

    def dial(self, sleeve: str, t: float) -> float:
        s = self.dials.get(str(sleeve).upper())
        if s is None:
            raise KeyError(f"no dial schedule for sleeve {sleeve!r} (have {sorted(self.dials)})")
        return s.at(t)

    @classmethod
    def from_env(cls, **overrides: Any) -> "SizingConfig":
        """TODAY's live sizing as constants, read from the same env vars through the runtime's own _env_float/_flag
        helpers, so a study run with the production env prices at exactly what is live now (no history)."""
        from futuresbot.runtime import FuturesRuntime as R   # lazy: the runtime import costs ~5 s
        wc = max(0.0, R._env_float("FUTURES_WILDCARD_RISK_PCT", 0.0187))
        tr = max(0.0, R._env_float("FUTURES_TREND_RISK_PCT", 0.0)) or wc      # unset -> sleeve shares WILDCARD's dial
        cap = None
        if R._flag("FUTURES_RISK_BASED_SIZING_ENABLED", default=False):
            cap = StepSchedule.constant(R._env_float("FUTURES_MAX_TRADE_RISK_PCT", 5.0) / 100.0)
        kw: dict[str, Any] = dict(
            dials={"WILDCARD": StepSchedule.constant(wc), "TREND": StepSchedule.constant(tr)},
            max_margin_frac=max(0.01, R._env_float("FUTURES_WILDCARD_MAX_MARGIN_PCT", 0.25)),
            trade_risk_cap=cap,
            streak="dynamic" if R._flag("FUTURES_CONVEX_STREAK_THROTTLE_ENABLED", default=False) else "off",
            streak_rule=StreakRule(n=max(1, int(R._env_float("FUTURES_CONVEX_STREAK_N", 2.0))),
                                   floor=R._env_float("FUTURES_CONVEX_STREAK_FLOOR", 0.25)),
            apply_regime=R._flag("FUTURES_REGIME_SIZE_SCALER_ENABLED", default=False),
        )
        kw.update(overrides)
        return cls(**kw)


def live_config(**overrides: Any) -> SizingConfig:
    """The live chain WITH its history (dial and cap schedules): the config that reproduces the live book."""
    return replace(SizingConfig(), **overrides)


@dataclass(frozen=True)
class FillResult:
    index: int                 # position in the input stream
    trade: Trade
    taken: bool
    skip_reason: str           # '' | 'no_available' | 'min_vol' | 'zero_size'
    cash: float                # at entry
    available: float           # at entry
    margin: float
    contracts: int | None      # None when sized continuously
    risk_usdt: float           # the $ value of 1R the chain gave this fill
    pnl_usdt: float
    continuous: bool = False   # True when the spec was unknown and integer contracts could not be applied


@dataclass
class SizingResult:
    start_cash: float
    final_cash: float
    flows_total: float
    fills: list[FillResult]
    path: list[tuple[float, float]]          # (ts, cash) after every close and every flow
    max_drawdown: float                      # of realised cash, flows shifting the peak (a deposit is not a recovery)
    time_weighted_return: float              # chained across flows: a deposit does not reset or inflate it

    @property
    def pnl(self) -> float:
        """Trading dollars: final cash minus start cash minus every flow."""
        return self.final_cash - self.start_cash - self.flows_total

    @property
    def taken(self) -> list[FillResult]:
        return [f for f in self.fills if f.taken]

    @property
    def skipped(self) -> list[FillResult]:
        return [f for f in self.fills if not f.taken]


def _as_flows(flows: Iterable[Any]) -> list[CapitalFlow]:
    out = []
    for f in flows or ():
        if isinstance(f, CapitalFlow):
            out.append(f)
        elif isinstance(f, Mapping):
            out.append(CapitalFlow(float(f["ts"]), float(f["amount"]), str(f.get("label", ""))))
        else:
            out.append(CapitalFlow(float(f[0]), float(f[1]), str(f[2]) if len(f) > 2 else ""))
    return out


def _events(trades: Sequence[Trade], flows: Sequence[CapitalFlow]) -> list[tuple[float, int, int]]:
    # Same instant: flows, then closes, then opens - a close frees its margin before a same-second entry sizes,
    # which is the order the exchange applies (lane C's convention; changing it moves the reproduction).
    ev = [(f.ts, 0, i) for i, f in enumerate(flows)]
    for i, t in enumerate(trades):
        ev.append((float(t.t_open), 2, i))
        # a zero-duration fill must still open before it closes
        ev.append((float(t.t_close), 1 if t.t_close > t.t_open else 3, i))
    ev.sort()
    return ev


def _run(trades: Sequence[Trade], start_cash: float, cfg: SizingConfig, flows: Sequence[CapitalFlow],
         events: Sequence[tuple[float, int, int]],
         outcomes: Sequence[tuple[float, float, float | None]] | None = None) -> SizingResult:
    # outcomes[i] = (r, regime_mult, streak_mult) overrides trade i's outcome without rebuilding the Trade: the
    # bootstrap in compare_stakes runs this thousands of times on one timing skeleton.
    cash = float(start_cash)
    locked: dict[int, tuple[float, float]] = {}   # index -> (margin, risk)
    opened: dict[int, FillResult] = {}
    fills: list[FillResult | None] = [None] * len(trades)
    closed: list[float] = []
    path: list[tuple[float, float]] = []
    peak = cash
    mdd = 0.0
    seg_start = cash
    twr = 1.0
    for ts, kind, i in events:
        if kind == 0:
            amt = flows[i].amount
            if seg_start > 0:
                twr *= cash / seg_start
            cash += amt
            seg_start = cash
            peak = max(peak + amt, cash)
            path.append((ts, cash))
            continue
        t = trades[i]
        r_i, regime_i, streak_i = outcomes[i] if outcomes is not None else (t.r, t.regime_mult, t.streak_mult)
        if kind == 2:
            lock_total = sum(m for m, _ in locked.values())
            avail = cash - lock_total
            base = {"available": avail, "cash": cash, "fixed": cfg.fixed_base}[cfg.base]
            skip = ""
            margin = 0.0
            contracts: int | None = None
            continuous = False
            if avail <= 0 or base <= 0:
                skip = "no_available"          # live: the scan dies at zero free margin
            else:
                margin = cfg.dial(t.sleeve, t.t_open) * base / (t.stop_frac * t.leverage)
                if cfg.max_margin_frac > 0:
                    margin = min(margin, cfg.max_margin_frac * base)
                if cfg.apply_regime:
                    margin *= float(regime_i)
                if cfg.streak == "recorded":
                    margin *= float(streak_i if streak_i is not None else 1.0)
                elif cfg.streak == "dynamic":
                    margin *= cfg.streak_rule.multiplier(closed)
                cap = cfg.trade_risk_cap.at(t.t_open) if cfg.trade_risk_cap is not None else 0.0
                cs = float(t.spec.contract_size or 0.0)
                if cfg.integer_contracts and cs > 0 and t.entry_price > 0:
                    n = math.floor(margin * t.leverage / (t.entry_price * cs) + 1e-9)
                    if cap > 0:
                        risk_per_contract = cs * t.entry_price * t.stop_frac
                        n = min(n, math.floor(cap * base / risk_per_contract + 1e-9))
                    if n < int(t.spec.min_vol or 1):
                        skip = "min_vol"
                    contracts = n
                    margin = n * cs * t.entry_price / t.leverage
                else:
                    continuous = cfg.integer_contracts   # wanted integers, could not: say so
                    if cap > 0:
                        margin = min(margin, cap * base / (t.stop_frac * t.leverage))
                if not skip and margin <= 0:
                    skip = "zero_size"
            risk = margin * t.stop_frac * t.leverage if not skip else 0.0
            fr = FillResult(i, t, not skip, skip, cash, avail, margin if not skip else 0.0,
                            contracts, risk, 0.0, continuous)
            fills[i] = fr
            if not skip:
                locked[i] = (margin, risk)
                opened[i] = fr
            continue
        # close
        if i not in locked:
            continue
        _, risk = locked.pop(i)
        pnl = float(r_i) * risk
        cash += pnl
        closed.append(pnl)
        fr = opened.pop(i)
        fills[i] = replace(fr, pnl_usdt=pnl)
        path.append((ts, cash))
        peak = max(peak, cash)
        if peak > 0:
            mdd = max(mdd, (peak - cash) / peak)
    if seg_start > 0:
        twr *= cash / seg_start
    return SizingResult(float(start_cash), cash, sum(f.amount for f in flows),
                        [f for f in fills if f is not None], path, mdd, twr - 1.0)


def simulate(trades: Sequence[Trade], start_cash: float, config: SizingConfig | None = None,
             flows: Iterable[Any] = ()) -> SizingResult:
    """Run the live sizing chain over `trades` from `start_cash`, applying `flows` ((ts, amount[, label]) tuples,
    mappings or CapitalFlow) as explicit cash events. Returns every fill's size and $ and the cash path."""
    cfg = config or live_config()
    fl = _as_flows(flows)
    tr = list(trades)
    return _run(tr, start_cash, cfg, fl, _events(tr, fl))


def fixed_stake(trades: Sequence[Trade], stake_equity: float, config: SizingConfig | None = None) -> float:
    """The studies' convention: every fill books dial(sleeve, t) x stake_equity x multipliers x r, no compounding, no
    free-margin effect, no integer contracts, no skips. Reported BESIDE the compounded number, never instead of it."""
    cfg = config or live_config()
    tot = 0.0
    for t in trades:
        m = float(t.regime_mult) if cfg.apply_regime else 1.0
        if cfg.streak == "recorded" and t.streak_mult is not None:
            m *= float(t.streak_mult)
        tot += cfg.dial(t.sleeve, t.t_open) * float(stake_equity) * m * float(t.r)
    return tot


@dataclass
class StakeComparison:
    """Fixed-stake mean, compounded (actual order and bootstrap median) and intervals, side by side - the reporting
    standard from 2026-09-23 on: never headline a signed $ total whose interval straddles it without the interval."""
    n: int
    days: float
    start_cash: float
    fixed_stake_usd: float
    fixed_stake_ci: tuple[float, float]
    compounded_usd: float                  # the actual order, this history's path
    compounded_median: float               # median over outcome resamples on the same timing skeleton
    compounded_ci: tuple[float, float]
    skipped: int
    max_drawdown: float
    n_boot: int
    ci: float

    def per_month(self, usd: float) -> float:
        return usd * MONTH_DAYS / self.days if self.days > 0 else float("nan")

    def lines(self, label: str = "") -> list[str]:
        pm = self.per_month
        lo = (1.0 - self.ci) / 2 * 100
        head = f"{label}: " if label else ""
        return [
            f"{head}n={self.n} fills over {self.days:.1f} d from ${self.start_cash:,.2f} ({self.skipped} skipped by the chain)",
            f"  fixed stake  ${self.fixed_stake_usd:+9.2f}  = ${pm(self.fixed_stake_usd):+8.2f}/mo  "
            f"[{pm(self.fixed_stake_ci[0]):+.2f}, {pm(self.fixed_stake_ci[1]):+.2f}]/mo",
            f"  compounded   ${self.compounded_usd:+9.2f}  = ${pm(self.compounded_usd):+8.2f}/mo  (this order; maxDD {self.max_drawdown * 100:.1f}%)",
            f"  compounded median ${pm(self.compounded_median):+8.2f}/mo  "
            f"[{pm(self.compounded_ci[0]):+.2f}, {pm(self.compounded_ci[1]):+.2f}]/mo  "
            f"({self.ci * 100:.0f}% interval, {self.n_boot} resamples, p{lo:g}-p{100 - lo:g})",
        ]


def _pct(xs: Sequence[float], q: float) -> float:
    s = sorted(xs)
    if not s:
        return float("nan")
    k = (len(s) - 1) * q
    lo = math.floor(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def compare_stakes(trades: Sequence[Trade], start_cash: float, config: SizingConfig | None = None, *,
                   flows: Iterable[Any] = (), stake_equity: float | None = None, days: float | None = None,
                   n_boot: int = 2000, seed: int = 7, ci: float = 0.95,
                   progress: Callable[[int], None] | None = None) -> StakeComparison:
    """Price one trade stream three ways, for the side-by-side every study must now report.

    Interval method: resample each fill's OUTCOME (r with its regime/streak multipliers - the scaler's correlation with
    R is part of the outcome, +0.08 on WILDCARD since 08-08) with replacement WITHIN its sleeve, onto the fixed timing
    skeleton (same entry/exit instants, stop, leverage, contract spec, flows), and run the full chain each time. This
    keeps the concurrency and free-margin structure that makes order matter and prices edge uncertainty; it assumes
    outcomes are exchangeable within a sleeve (no serial dependence), so it is narrower than the record's weekly-block
    intervals when losses cluster. The fixed-stake interval uses the same resamples."""
    cfg = config or live_config()
    tr = sorted(trades, key=lambda t: (t.t_open, t.t_close))
    fl = _as_flows(flows)
    W = float(stake_equity if stake_equity is not None else start_cash)
    if days is None:
        days = (max(t.t_close for t in tr) - min(t.t_open for t in tr)) / 86400.0 if tr else 0.0
    ev = _events(tr, fl)
    base = _run(tr, start_cash, cfg, fl, ev)
    fx = fixed_stake(tr, W, cfg)
    rng = random.Random(seed)
    by: dict[str, list[int]] = {}
    for i, t in enumerate(tr):
        by.setdefault(t.sleeve, []).append(i)
    dials = [cfg.dial(t.sleeve, t.t_open) * W for t in tr]
    comp, fixed = [], []
    for b in range(max(0, int(n_boot))):
        oc: list[tuple[float, float, float | None]] = [(t.r, t.regime_mult, t.streak_mult) for t in tr]
        for idx in by.values():
            for i in idx:
                src = tr[idx[rng.randrange(len(idx))]]
                oc[i] = (src.r, src.regime_mult, src.streak_mult)
        comp.append(_run(tr, start_cash, cfg, fl, ev, oc).pnl)
        fs = 0.0
        for i, (r_, reg_, st_) in enumerate(oc):
            m = float(reg_) if cfg.apply_regime else 1.0
            if cfg.streak == "recorded" and st_ is not None:
                m *= float(st_)
            fs += dials[i] * m * float(r_)
        fixed.append(fs)
        if progress is not None:
            progress(b)
    q = (1.0 - ci) / 2
    return StakeComparison(
        n=len(tr), days=float(days), start_cash=float(start_cash), fixed_stake_usd=fx,
        fixed_stake_ci=(_pct(fixed, q), _pct(fixed, 1 - q)) if fixed else (fx, fx),
        compounded_usd=base.pnl, compounded_median=_pct(comp, 0.5) if comp else base.pnl,
        compounded_ci=(_pct(comp, q), _pct(comp, 1 - q)) if comp else (base.pnl, base.pnl),
        skipped=len(base.skipped), max_drawdown=base.max_drawdown, n_boot=len(comp), ci=ci)
