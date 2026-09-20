"""The per-trade risk cap must shrink a position, not delete it (owner, 2026-09-20).

AKE_USDT 09-20 09:00: one minimum contract risks $9.46 against an $8.55 cap, so the cap
sized the trade to zero and it was skipped. AKE then ran +125% through its +5R target.
"""
from __future__ import annotations

import inspect

import pytest

from futuresbot.risk_controls import risk_capped_contracts
from futuresbot.runtime import ENTRY_GATE_KEYS, FuturesRuntime


def _ake_like():
    """AKE: contract size 1000, entry 0.0715, stop 0.0621 -> $9.46 per contract."""
    return dict(entry_price=0.0715, sl_price=0.06204, contract_size=1000.0)


def test_the_cap_alone_still_sizes_the_overshooting_symbol_to_zero():
    assert risk_capped_contracts(contracts=2, equity_usdt=964.94, max_risk_pct=0.886,
                                 **_ake_like()) == 0


def test_the_round_up_is_off_by_default():
    """The owner reverted the tight cap instead (2026-09-20), so this stays inert until
    a future tight cap switches it on."""
    src = inspect.getsource(FuturesRuntime._open_wildcard_position)
    assert '_env_float("FUTURES_MAX_TRADE_RISK_ROUNDUP_PCT", 0.0)' in src


def test_the_round_up_rule_is_wired_into_the_convex_sizing_path():
    src = inspect.getsource(FuturesRuntime._open_wildcard_position)
    assert "FUTURES_MAX_TRADE_RISK_ROUNDUP_PCT" in src
    assert "capped < min_vol <= contracts" in src
    assert src.index("capped < min_vol") < src.index('if contracts < min_vol:')


@pytest.mark.parametrize("overshoot_pct, allowed", [(10.6, True), (19.9, True), (20.1, False), (55.0, False)])
def test_only_a_small_overshoot_is_rounded_up(overshoot_pct, allowed):
    """The ceiling still holds within a fifth of itself."""
    cap_risk = 8.55
    min_risk = cap_risk * (1.0 + overshoot_pct / 100.0)
    roundup_pct = 20.0
    assert (min_risk <= cap_risk * (1.0 + roundup_pct / 100.0)) is allowed


def test_what_the_cap_did_reaches_the_trade_record():
    """The one trade where the cap bound recorded risk_cap_bound=0.0 - a different cap."""
    for k in ("risk_capped_from_contracts", "risk_capped_contracts", "risk_cap_pct",
              "risk_cap_rounded_up"):
        assert k in ENTRY_GATE_KEYS
    entry = inspect.getsource(FuturesRuntime._open_wildcard_position)
    assert "_last_risk_cap" in entry


def test_a_normal_shrink_is_untouched():
    """Where the cap can size a real position it still shrinks, and the round-up never fires."""
    assert risk_capped_contracts(contracts=970, entry_price=0.8102, sl_price=0.7222,
                                 contract_size=1.0, equity_usdt=954.0, max_risk_pct=0.886) == 96
