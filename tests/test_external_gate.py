from futuresbot.external_gate import (
    decide_cross_exchange,
    decide_funding_crowding,
    okx_inst,
    perp_symbol,
)


def test_symbol_mapping():
    assert perp_symbol("BTC_USDT") == "BTCUSDT"
    assert okx_inst("BTC_USDT") == "BTC-USDT-SWAP"


def test_cross_exchange_vetoes_mexc_only():
    # not listed on the reference venue -> veto (require_listed)
    assert decide_cross_exchange(0.10, 0.0, False, require_listed=True)[0] is False
    # not listed but not required -> allow
    assert decide_cross_exchange(0.10, 0.0, False, require_listed=False)[0] is True


def test_cross_exchange_small_move_only_needs_listing():
    # squeeze-style (small/zero mexc move): listed is enough, no corroboration needed
    assert decide_cross_exchange(0.0, 0.0, True)[0] is True


def test_cross_exchange_big_move_requires_corroboration():
    # MEXC +10%, reference flat -> MEXC-only pump -> veto
    assert decide_cross_exchange(0.10, 0.005, True, min_corroboration=0.4)[0] is False
    # MEXC +10%, reference +6% same direction -> corroborated -> allow
    assert decide_cross_exchange(0.10, 0.06, True, min_corroboration=0.4)[0] is True
    # opposite direction -> veto
    assert decide_cross_exchange(0.10, -0.08, True)[0] is False


def test_funding_crowding():
    # crowded longs: long into very positive funding -> veto
    assert decide_funding_crowding("LONG", 0.0015, max_abs=0.001)[0] is False
    # crowded shorts: short into very negative funding -> veto
    assert decide_funding_crowding("SHORT", -0.0015, max_abs=0.001)[0] is False
    # benign funding -> allow
    assert decide_funding_crowding("LONG", 0.0002, max_abs=0.001)[0] is True
    # no funding data -> allow (fail-open)
    assert decide_funding_crowding("LONG", None, max_abs=0.001)[0] is True
