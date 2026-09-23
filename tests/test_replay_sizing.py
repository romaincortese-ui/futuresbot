"""futuresbot.replay.sizing - the live sizing chain as a pure function of a trade stream.

The headline test reproduces the LIVE book: 151 WILDCARD+TREND fills 2026-08-13..09-23 (frozen from exchange position
history in tests/fixtures/replay_live_book_0813_0923.json) priced from the exchange cash at the window start must end
on the exchange's cash. Lane C got -$1.85, lane V -$1.66; a regression past $3 means the chain no longer is live's."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from futuresbot.replay.sizing import (
    LIVE_DIALS,
    LIVE_TRADE_RISK_CAP,
    CapitalFlow,
    ContractSpec,
    SizingConfig,
    StepSchedule,
    StreakRule,
    Trade,
    _utc,
    compare_stakes,
    fixed_stake,
    live_config,
    simulate,
)

FIXTURE = Path(__file__).parent / "fixtures" / "replay_live_book_0813_0923.json"


def _fixture():
    d = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cols = d["columns"]
    rows = [dict(zip(cols, r)) for r in d["trades"]]
    trades = [Trade.from_sl_margin(sl_margin_pct=x["sl_margin_pct"], leverage=x["leverage"], t_open=x["t_open"],
                                   t_close=x["t_close"], sleeve=x["sleeve"], r=x["r"], entry_price=x["entry_price"],
                                   spec=ContractSpec(x["contract_size"], x["min_vol"]), regime_mult=x["regime_mult"],
                                   streak_mult=x["streak_mult"], symbol=x["symbol"], side=x["side"]) for x in rows]
    return d, rows, trades


def _risk_share_within(res, rows, tol=0.05):
    rel = [f.risk_usdt / x["live_risk_usdt"] - 1 for f, x in zip(res.fills, rows) if f.taken and x["live_risk_usdt"]]
    return sum(1 for v in rel if abs(v) <= tol) / len(rel)


def _t(t0, t1, r=1.0, sleeve="WILDCARD", stop=0.05, lev=2.0, **kw):
    return Trade(t_open=float(t0), t_close=float(t1), sleeve=sleeve, r=r, stop_frac=stop, leverage=lev, **kw)


FLAT = SizingConfig(dials={"WILDCARD": StepSchedule.constant(0.02), "TREND": StepSchedule.constant(0.01)},
                    trade_risk_cap=None, integer_contracts=False, max_margin_frac=0.0)


# ---- the live book ---------------------------------------------------------------------------------------------------
def test_reproduces_the_live_book_to_within_three_dollars():
    """If the chain stops matching live cash over 151 real fills, every compounded study built on it is pricing a
    different account. The fixture is exchange truth; lanes C and V both landed within $2."""
    d, rows, trades = _fixture()
    assert len(trades) == 151
    res = simulate(trades, d["start_cash"], live_config(), flows=d["flows"])
    assert abs(res.final_cash - d["end_cash"]) <= 3.0
    assert not res.skipped
    assert _risk_share_within(res, rows) >= 145 / 151      # measured 148/151


def test_every_live_component_is_needed_to_reproduce_live():
    """Guards the THRESHOLDS in acceptance.py: dropping the recorded streak multiplier (on for part of this window)
    costs -$14, dropping integer contracts leaves only ~77% of fills within 5% of live's 1R. If a refactor silently
    drops either, the headline test alone might not notice; these do."""
    d, rows, trades = _fixture()
    no_streak = simulate(trades, d["start_cash"], live_config(streak="off"), flows=d["flows"])
    assert no_streak.final_cash - d["end_cash"] < -10.0
    no_gran = simulate(trades, d["start_cash"], live_config(integer_contracts=False), flows=d["flows"])
    assert _risk_share_within(no_gran, rows) < 0.90


def test_live_dial_schedule_prices_history_with_the_dial_live_at_entry():
    """08-22 raise, the TREND halving and the owner's 2026-09-23 18:10Z WILDCARD cut to 1.87% must all price at the
    dial that was live at the entry instant, not at today's dial."""
    wc, tr = LIVE_DIALS["WILDCARD"], LIVE_DIALS["TREND"]
    assert wc.at(_utc(2026, 8, 22, 8)) == 0.0187 and wc.at(_utc(2026, 8, 22, 13)) == 0.0241
    assert wc.at(_utc(2026, 9, 23, 18, 9)) == 0.0241 and wc.at(_utc(2026, 9, 23, 18, 10)) == 0.0187
    assert tr.at(_utc(2026, 9, 14, 21)) == 0.0241 and tr.at(_utc(2026, 9, 16, 9, 32)) == 0.01205
    assert LIVE_TRADE_RISK_CAP.at(_utc(2026, 9, 19, 12)) == 0.00886
    assert LIVE_TRADE_RISK_CAP.at(_utc(2026, 9, 20, 12, 25)) == 0.05


def test_step_schedule_rejects_unordered_changes():
    """An out-of-order schedule would price a fill with a dial from the wrong side of a change, silently."""
    with pytest.raises(ValueError):
        StepSchedule(0.01, ((200.0, 0.02), (100.0, 0.03)))


# ---- the chain, piece by piece -----------------------------------------------------------------------------------------
def test_available_is_cash_minus_margin_locked_by_open_positions():
    """The free-margin effect every fixed-stake study missed: a second entry while the first is open sizes off
    cash - locked margin, not off cash."""
    a = _t(0, 100)          # margin = 0.02 x 1000 / (0.05 x 2) = 200, risk 20
    b = _t(50, 150)
    res = simulate([a, b], 1000.0, FLAT)
    fa, fb = res.fills
    assert fa.margin == pytest.approx(200.0) and fa.risk_usdt == pytest.approx(20.0)
    assert fb.available == pytest.approx(800.0)
    assert fb.risk_usdt == pytest.approx(16.0)           # 0.02 x 800
    assert res.final_cash == pytest.approx(1036.0)


def test_close_frees_margin_before_a_same_second_entry():
    """Same instant: the close books first, then the entry sizes on the freed balance (lane C's order)."""
    res = simulate([_t(0, 100, r=1.0), _t(100, 200, r=0.0)], 1000.0, FLAT)
    assert res.fills[1].available == pytest.approx(1020.0)


def test_zero_duration_fill_opens_before_it_closes():
    """A fill that opens and closes in the same second must still book its P&L and release its margin; ordering
    closes first would have locked its margin for the rest of the path."""
    res = simulate([_t(10, 10, r=-1.0), _t(20, 30, r=0.0)], 1000.0, FLAT)
    assert res.fills[0].pnl_usdt == pytest.approx(-20.0)
    assert res.fills[1].available == pytest.approx(980.0)


def test_margin_cap_binds_on_a_tight_stop():
    """FUTURES_WILDCARD_MAX_MARGIN_PCT: a 0.5% stop at 1x wants 4x the balance as margin; the cap holds it to 25%."""
    cfg = SizingConfig(dials={"WILDCARD": StepSchedule.constant(0.02)}, trade_risk_cap=None, integer_contracts=False)
    f = simulate([_t(0, 1, stop=0.005, lev=1.0)], 1000.0, cfg).fills[0]
    assert f.margin == pytest.approx(250.0)
    assert f.risk_usdt == pytest.approx(1.25)


def test_regime_scaler_is_an_input_and_scales_the_stake():
    res = simulate([_t(0, 1, regime_mult=0.5)], 1000.0, FLAT)
    assert res.fills[0].risk_usdt == pytest.approx(10.0)
    off = simulate([_t(0, 1, regime_mult=0.5)], 1000.0, SizingConfig(**{**FLAT.__dict__, "apply_regime": False}))
    assert off.fills[0].risk_usdt == pytest.approx(20.0)


def test_integer_contracts_round_down_and_min_vol_skips():
    """A falling balance deletes trades through the minimum contract (8 such skips in 30 days live); no replay modelled
    it. 1 contract of this spec needs $50 margin; $2,000 x 2% / 0.1 = $400 -> 8 contracts."""
    cfg = SizingConfig(dials={"WILDCARD": StepSchedule.constant(0.02)}, trade_risk_cap=None, max_margin_frac=0.0)
    spec = ContractSpec(contract_size=10.0, min_vol=1)
    ok = simulate([_t(0, 1, entry_price=10.0, spec=spec)], 2000.0, cfg).fills[0]
    assert ok.contracts == 8 and ok.margin == pytest.approx(400.0)
    small = simulate([_t(0, 1, entry_price=10.0, spec=spec)], 200.0, cfg).fills[0]    # wants $40 < one contract
    assert not small.taken and small.skip_reason == "min_vol"


def test_per_trade_risk_cap_zeroes_a_trade_like_ake_on_0920():
    """AKE_USDT 2026-09-20: 2 contracts wanted, one contract of size 1000 risks $9.46 against an $8.55 cap (0.886% of
    ~$965) -> sized to ZERO. The chain must reproduce the deletion, not a shrink."""
    spec = ContractSpec(contract_size=1000.0, min_vol=1)
    ake = Trade(t_open=_utc(2026, 9, 20, 9), t_close=_utc(2026, 9, 20, 18), sleeve="WILDCARD", r=5.0, stop_frac=0.0946,
                leverage=2.0, entry_price=0.1, spec=spec)
    capped = simulate([ake], 965.0, live_config()).fills[0]
    assert not capped.taken and capped.skip_reason == "min_vol"
    uncapped = simulate([ake], 965.0, live_config(trade_risk_cap=None)).fills[0]
    assert uncapped.taken and uncapped.contracts == 2


def test_flows_are_explicit_and_time_weighted_return_ignores_the_deposit():
    """A deposit moves the stake, not the trading result: pnl excludes it, and the time-weighted return is the
    product of the trades' returns whatever the deposit size (the record's 'judge trials in TWR' rule)."""
    trades = [_t(0, 10, r=1.0), _t(20, 30, r=1.0)]
    for dep in (0.0, 1000.0, 9000.0):
        res = simulate(trades, 1000.0, FLAT, flows=[CapitalFlow(15.0, dep, "deposit")] if dep else [])
        assert res.time_weighted_return == pytest.approx(1.02 * 1.02 - 1)
        assert res.pnl == pytest.approx(20.0 + 0.02 * (1020.0 + dep))
    assert simulate(trades, 1000.0, FLAT, flows=[(15.0, 1000.0)]).flows_total == 1000.0


def test_drawdown_is_not_reset_by_a_deposit():
    """A deposit after a loss must not read as a recovery: the peak shifts with the flow."""
    res = simulate([_t(0, 10, r=-5.0), _t(20, 30, r=0.0)], 1000.0, FLAT, flows=[(15.0, 5000.0)])
    assert res.max_drawdown == pytest.approx(0.10)


def test_dynamic_streak_rule_matches_the_runtime_throttle():
    """runtime._convex_streak_multiplier: halves per loss from the n-th, floored at 0.25, restored by a win."""
    rule = StreakRule(n=2, floor=0.25)
    assert [rule.multiplier([-1.0] * k) for k in range(6)] == [1.0, 1.0, 0.5, 0.25, 0.25, 0.25]
    assert rule.multiplier([-1.0, -1.0, 2.0]) == 1.0
    cfg = SizingConfig(**{**FLAT.__dict__, "streak": "dynamic"})
    res = simulate([_t(0, 1, r=-1.0), _t(2, 3, r=-1.0), _t(4, 5, r=0.0)], 1000.0, cfg)
    assert res.fills[2].risk_usdt == pytest.approx(0.5 * 0.02 * res.fills[2].available)


def test_unknown_contract_spec_is_sized_continuously_and_flagged():
    """A delisted symbol has no spec; the fill is still priced, but the result must say integer sizing was skipped."""
    f = simulate([_t(0, 1, entry_price=0.0)], 1000.0, live_config()).fills[0]
    assert f.taken and f.continuous and f.contracts is None


def test_trade_rejects_a_missing_stop():
    with pytest.raises(ValueError):
        _t(0, 1, stop=0.0)


# ---- fixed stake vs compounded, side by side -----------------------------------------------------------------------------
def test_fixed_stake_and_compounded_side_by_side_on_sequential_trades():
    """For trades one after another at a fixed fraction, compounded wealth is the product - the identity the record
    uses; fixed stake is the sum. Both must come out of one call with an interval."""
    rs = [1.0, -1.0, 2.0, -1.0, 0.5]
    trades = [_t(10 * i, 10 * i + 5, r=r) for i, r in enumerate(rs)]
    cmp = compare_stakes(trades, 1000.0, FLAT, n_boot=200, seed=3, days=30.4375)
    assert cmp.fixed_stake_usd == pytest.approx(sum(0.02 * 1000.0 * r for r in rs))
    assert cmp.compounded_usd == pytest.approx(1000.0 * (math.prod(1 + 0.02 * r for r in rs) - 1))
    assert cmp.compounded_ci[0] <= cmp.compounded_median <= cmp.compounded_ci[1]
    assert cmp.fixed_stake_ci[0] <= cmp.fixed_stake_usd <= cmp.fixed_stake_ci[1]
    assert cmp.per_month(cmp.fixed_stake_usd) == pytest.approx(cmp.fixed_stake_usd)
    lines = "\n".join(cmp.lines("t"))
    assert "fixed stake" in lines and "compounded median" in lines


def test_compare_stakes_is_reproducible_and_resamples_within_sleeve():
    """Same seed, same interval; and a sleeve made only of winners can never draw a loser from the other sleeve."""
    trades = [_t(10 * i, 10 * i + 5, r=1.0, sleeve="TREND") for i in range(10)]
    trades += [_t(10 * i + 1, 10 * i + 6, r=-1.0) for i in range(10)]
    a = compare_stakes(trades, 1000.0, FLAT, n_boot=100, seed=5)
    b = compare_stakes(trades, 1000.0, FLAT, n_boot=100, seed=5)
    assert a.compounded_ci == b.compounded_ci
    assert a.fixed_stake_ci[0] == pytest.approx(a.fixed_stake_ci[1])     # nothing to resample within a sleeve
    assert fixed_stake(trades, 1000.0, FLAT) == pytest.approx(10 * 10.0 - 10 * 20.0)


def test_from_env_reads_todays_live_sizing(monkeypatch):
    """A study run under the production env must price at what is live now, read through the runtime's helpers."""
    for k, v in {"FUTURES_WILDCARD_RISK_PCT": "0.0187", "FUTURES_TREND_RISK_PCT": "0.01205",
                 "FUTURES_RISK_BASED_SIZING_ENABLED": "1", "FUTURES_MAX_TRADE_RISK_PCT": "5",
                 "FUTURES_WILDCARD_MAX_MARGIN_PCT": "0.25", "FUTURES_REGIME_SIZE_SCALER_ENABLED": "1",
                 "FUTURES_CONVEX_STREAK_THROTTLE_ENABLED": "0"}.items():
        monkeypatch.setenv(k, v)
    cfg = SizingConfig.from_env()
    assert cfg.dial("WILDCARD", 0) == 0.0187 and cfg.dial("TREND", 0) == 0.01205
    assert cfg.trade_risk_cap is not None and cfg.trade_risk_cap.at(0) == pytest.approx(0.05)
    assert cfg.apply_regime and cfg.streak == "off" and cfg.max_margin_frac == 0.25
    monkeypatch.delenv("FUTURES_TREND_RISK_PCT")
    assert SizingConfig.from_env().dial("TREND", 0) == 0.0187          # unset -> shares WILDCARD's dial, as live
