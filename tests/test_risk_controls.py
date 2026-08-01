from futuresbot.risk_controls import (
    regime_size_multiplier,
    risk_capped_contracts,
    trend_efficiency,
)


def test_risk_cap_limits_loss_to_pct_of_equity():
    # BNB-style: x16 on ~$100, 1R ~ 19% of equity. Cap at 5% must shrink it.
    # entry 621.7, sl ~609 (≈ -2% price = 1R at x16 ≈ 32%/... use real stop dist)
    contracts = risk_capped_contracts(
        contracts=10_000, entry_price=621.7, sl_price=614.0,
        contract_size=0.01, equity_usdt=100.0, max_risk_pct=5.0,
    )
    # 1R loss must be <= $5 (5% of $100)
    assert contracts * 0.01 * abs(621.7 - 614.0) <= 5.0 + 1e-9
    assert contracts > 0


def test_risk_cap_returns_zero_when_min_size_too_risky():
    # A huge stop distance: even 1 contract risks more than the budget -> 0 (skip).
    contracts = risk_capped_contracts(
        contracts=5, entry_price=100.0, sl_price=50.0,
        contract_size=1.0, equity_usdt=100.0, max_risk_pct=2.0,
    )
    assert contracts == 0


def test_risk_cap_fail_open_on_degenerate_inputs():
    assert risk_capped_contracts(contracts=7, entry_price=100, sl_price=100,
                                 contract_size=1, equity_usdt=100, max_risk_pct=5) == 7
    assert risk_capped_contracts(contracts=7, entry_price=100, sl_price=99,
                                 contract_size=1, equity_usdt=100, max_risk_pct=0) == 7


def test_risk_cap_never_increases_size():
    # If the request already risks less than the cap, leave it unchanged.
    c = risk_capped_contracts(contracts=3, entry_price=100.0, sl_price=99.0,
                              contract_size=1.0, equity_usdt=100.0, max_risk_pct=5.0)
    assert c == 3


def test_trend_efficiency_clean_vs_chop():
    clean = [100 + i for i in range(25)]          # straight line up
    chop = [100 + (i % 2) for i in range(25)]      # oscillate
    assert trend_efficiency(clean) > 0.95
    assert trend_efficiency(chop) < 0.2


def test_regime_multiplier_bounds_and_monotonic():
    assert regime_size_multiplier(0.60) == 1.0          # clean trend -> full
    assert regime_size_multiplier(0.05) == 0.25         # chop -> floor
    mid = regime_size_multiplier(0.325)                  # midpoint of [0.2,0.45]
    assert 0.25 < mid < 1.0
    # monotonic increasing in efficiency
    assert regime_size_multiplier(0.30) < regime_size_multiplier(0.40)


def _rt(history, flag=True):
    from types import SimpleNamespace
    from futuresbot.runtime import FuturesRuntime
    rt = object.__new__(FuturesRuntime)
    rt.trade_history = history
    rt._flag = lambda k, default=False: flag if k == "FUTURES_CONVEX_STREAK_THROTTLE_ENABLED" else default
    rt._env_float = lambda k, d: d
    return rt


def _row(signal, pnl):
    return {"entry_signal": signal, "pnl_usdt": pnl}


def test_convex_streak_counts_any_losing_exit_reason():
    # convex server stops report EXCHANGE_CLOSE, not STOP_LOSS: a drawdown
    # protocol must count LOSSES, not exit labels.
    rt = _rt([_row("WILDCARD_LONG", -1.0), _row("SQUEEZE_LONG", -0.5), _row("WILDCARD_SHORT", -2.0)])
    assert rt._convex_loss_streak() == 3


def test_convex_streak_resets_on_a_win_and_ignores_pmt():
    rt = _rt([_row("WILDCARD_LONG", -1.0), _row("WILDCARD_LONG", +5.0), _row("SQUEEZE_LONG", -1.0)])
    assert rt._convex_loss_streak() == 1          # win breaks the older streak
    rt2 = _rt([_row("SQUEEZE_LONG", -1.0), _row("PMT_THRESHOLD_LONG", +9.0), _row("WILDCARD_LONG", -1.0)])
    assert rt2._convex_loss_streak() == 2          # PMT row skipped, not a reset


def test_streak_multiplier_halves_and_floors():
    losses = [_row("WILDCARD_LONG", -1.0)] * 6
    assert _rt(losses[:1])._convex_streak_multiplier()[0] == 1.0    # 1 loss -> untouched
    assert _rt(losses[:2])._convex_streak_multiplier()[0] == 0.5    # trigger at 2
    assert _rt(losses[:3])._convex_streak_multiplier()[0] == 0.25
    assert _rt(losses[:6])._convex_streak_multiplier()[0] == 0.25   # floored
    assert _rt(losses[:6], flag=False)._convex_streak_multiplier()[0] == 1.0  # default off


def test_tagger_surfaces_sizing_telemetry():
    # intended_margin/streak/size_efficiency were written to position metadata
    # but never copied into the feature-store row, making the undersizing
    # question unmeasurable. They must now appear on every close.
    from types import SimpleNamespace
    from futuresbot.runtime import FuturesRuntime
    rt = object.__new__(FuturesRuntime)
    pos = SimpleNamespace(metadata={
        "wildcard": 1.0, "sl_margin_pct": 15.0,
        "regime_size_multiplier": 0.25, "intended_margin_usdt": 16.0,
        "streak_multiplier": 0.5, "loss_streak_at_entry": 2.0,
    })
    trade = {"pnl_usdt": -2.0, "fees_usdt": 0.05, "pnl_pct": -15.0, "margin_usdt": 4.0,
             "entry_time": "2026-07-31T10:00:00+00:00", "exit_time": "2026-07-31T11:00:00+00:00",
             "exit_reason": "EXCHANGE_CLOSE"}
    t = rt._trade_attribution_tags(pos, trade)
    assert t["intended_margin_usdt"] == 16.0
    assert t["regime_size_mult"] == 0.25
    assert t["streak_multiplier"] == 0.5
    assert t["loss_streak_at_entry"] == 2.0
    assert t["size_efficiency"] == 0.25       # 4.0 actual / 16.0 intended
    assert t["exit_kind"] == "STOP"


def test_size_efficiency_absent_without_intended():
    from types import SimpleNamespace
    from futuresbot.runtime import FuturesRuntime
    rt = object.__new__(FuturesRuntime)
    t = rt._trade_attribution_tags(SimpleNamespace(metadata={"sl_margin_pct": 15.0}),
                                   {"pnl_usdt": 1.0, "fees_usdt": 0.0, "pnl_pct": 15.0})
    assert t["size_efficiency"] is None
