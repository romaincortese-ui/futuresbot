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
