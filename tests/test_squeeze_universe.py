"""The squeeze sleeve traded tokenised equities and commodities (fixed 2026-08-21).

Every other sleeve screens its universe through `_is_tradeable_crypto`, which
exists precisely because tokenised equities gap across market closes and
weekends — the one hazard an ATR-derived stop cannot price. `_maybe_scan_squeeze`
never called it: it gated on the `_USDT` suffix and the turnover floor alone.

That is how the squeeze came to hold XAU_USDT and USOIL_USDT. Its live record
(n=13, +$1.17) is therefore drawn from a universe the strategy was never
designed for.

These pin the filter itself rather than the scan loop, so they stay meaningful
if the loop is refactored.
"""
import pytest

from futuresbot.runtime import FuturesRuntime


@pytest.mark.parametrize("symbol", [
    "XAU_USDT",      # gold — actually held live
    "USOIL_USDT",    # crude — actually held live
    "SPX500_USDT",
    "JP225_USDT",
    "SPY_USDT",
    "SOXL_USDT",
])
def test_non_crypto_perps_are_rejected(symbol):
    assert FuturesRuntime._is_tradeable_crypto(symbol) is False


@pytest.mark.parametrize("symbol", ["BTC_USDT", "ETH_USDT", "SOL_USDT",
                                    "ORDI_USDT", "GALA_USDT", "ZEC_USDT"])
def test_crypto_perps_still_pass(symbol):
    assert FuturesRuntime._is_tradeable_crypto(symbol) is True


def test_squeeze_scan_applies_the_crypto_filter():
    """The scan loop must consult the filter, not just the suffix and turnover.

    Guards against the exact regression: a reader adding a universe branch that
    checks `endswith("_USDT")` and stops there.
    """
    import inspect

    src = inspect.getsource(FuturesRuntime._maybe_scan_squeeze)
    assert "_is_tradeable_crypto" in src, (
        "the squeeze scan dropped its crypto filter again")


def test_exchange_tags_close_the_gap_the_static_list_could_not():
    """MEXC's own conceptPlate tags, not a hand-kept blocklist.

    An audit on 2026-08-21 found 68 non-crypto perps passing the static
    NON_CRYPTO_BASES filter — the leveraged equity ETFs, FX and commodities.
    TESLA_USDT is the canonical one: it is a tokenised equity that no name rule
    in the list matched.
    """
    from futuresbot import universe

    universe._EXCHANGE_NON_CRYPTO.clear()
    assert FuturesRuntime._is_tradeable_crypto("TESLA_USDT") is True   # the gap

    n = universe.refresh_non_crypto_universe([
        {"symbol": "TESLA_USDT", "conceptPlate": ["mc-trade-zone-stock",
                                                  "mc-trade-zone-tradfi"]},
        {"symbol": "TQQQ_USDT", "conceptPlate": ["mc-trade-zone-tradfi"]},
        {"symbol": "EUR_USDT", "conceptPlate": ["mc-trade-zone-forex"]},
        {"symbol": "COPPER_USDT", "conceptPlate": ["mc-trade-zone-metalsfutures"]},
        {"symbol": "SPK_USDT", "conceptPlate": []},
        {"symbol": "HOODRAT_USDT", "conceptPlate": ["mc-trade-zone-MEME"]},
    ])
    assert n == 4
    for sym in ("TESLA_USDT", "TQQQ_USDT", "EUR_USDT", "COPPER_USDT"):
        assert FuturesRuntime._is_tradeable_crypto(sym) is False
    # names a keyword rule would false-positive on must survive
    for sym in ("SPK_USDT", "HOODRAT_USDT"):
        assert FuturesRuntime._is_tradeable_crypto(sym) is True
    universe._EXCHANGE_NON_CRYPTO.clear()


def test_empty_refresh_leaves_the_previous_universe_standing():
    """A failed or empty fetch must not silently reopen the gate."""
    from futuresbot import universe

    universe._EXCHANGE_NON_CRYPTO.clear()
    universe.refresh_non_crypto_universe(
        [{"symbol": "TESLA_USDT", "conceptPlate": ["mc-trade-zone-tradfi"]}])
    assert universe.refresh_non_crypto_universe([]) == 1
    assert universe.refresh_non_crypto_universe(None) == 1
    assert FuturesRuntime._is_tradeable_crypto("TESLA_USDT") is False
    universe._EXCHANGE_NON_CRYPTO.clear()
