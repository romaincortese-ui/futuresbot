from __future__ import annotations

from futuresbot.portfolio_var import (
    PositionWeight,
    check_new_position,
    portfolio_vol,
)


def test_single_position_vol_matches_asset_vol():
    # 100% of NAV in one symbol -> portfolio vol == that symbol's vol.
    vols = {"BTC_USDT": 0.80}
    corr: dict[tuple[str, str], float] = {}
    v = portfolio_vol(
        positions=[PositionWeight(symbol="BTC_USDT", signed_notional_usdt=1000.0)],
        nav_usdt=1000.0,
        annualised_vol=vols,
        correlation=corr,
    )
    assert abs(v - 0.80) < 1e-9


def test_correlated_longs_raise_portfolio_vol():
    vols = {"BTC_USDT": 0.8, "ETH_USDT": 0.9}
    corr = {("BTC_USDT", "ETH_USDT"): 0.85}
    two = portfolio_vol(
        positions=[
            PositionWeight("BTC_USDT", 500.0),
            PositionWeight("ETH_USDT", 500.0),
        ],
        nav_usdt=1000.0,
        annualised_vol=vols,
        correlation=corr,
    )
    one = portfolio_vol(
        positions=[PositionWeight("BTC_USDT", 500.0)],
        nav_usdt=1000.0,
        annualised_vol=vols,
        correlation=corr,
    )
    # Two correlated longs of half-size each have higher vol than a single
    # half-size long, because their correlated variances add up.
    assert two > one


def test_opposing_legs_reduce_portfolio_vol():
    vols = {"BTC_USDT": 0.8, "ETH_USDT": 0.8}
    corr = {("BTC_USDT", "ETH_USDT"): 0.9}
    hedged = portfolio_vol(
        positions=[
            PositionWeight("BTC_USDT", +500.0),
            PositionWeight("ETH_USDT", -500.0),
        ],
        nav_usdt=1000.0,
        annualised_vol=vols,
        correlation=corr,
    )
    outright = portfolio_vol(
        positions=[
            PositionWeight("BTC_USDT", +500.0),
            PositionWeight("ETH_USDT", +500.0),
        ],
        nav_usdt=1000.0,
        annualised_vol=vols,
        correlation=corr,
    )
    assert hedged < outright


def test_check_new_position_accepts_under_cap():
    vols = {"BTC_USDT": 0.6}
    res = check_new_position(
        existing=[],
        candidate=PositionWeight("BTC_USDT", 100.0),
        nav_usdt=1000.0,
        annualised_vol=vols,
        correlation={},
        cap_vol=0.08,
    )
    # 100/1000 * 0.6 = 0.06 < 0.08 cap
    assert res.accepted is True


def test_check_new_position_rejects_over_cap():
    vols = {"BTC_USDT": 0.8, "ETH_USDT": 0.9}
    corr = {("BTC_USDT", "ETH_USDT"): 0.9}
    res = check_new_position(
        existing=[PositionWeight("BTC_USDT", 500.0)],
        candidate=PositionWeight("ETH_USDT", 500.0),
        nav_usdt=1000.0,
        annualised_vol=vols,
        correlation=corr,
        cap_vol=0.08,
    )
    assert res.accepted is False
    assert res.portfolio_vol_annualised > 0.08
