"""Stop re-placement must use the symbol's real tick (XRP, 2026-09-21).

The bot learns ticks at boot for the ACTIVE symbols only, so XRP - a TREND symbol that
is not in FUTURES_SYMBOLS - fell back to 0.01. Prices were therefore sent unsnapped and
MEXC rejected every stop re-placement with code 2015, leaving an open position with no
resting stop for 6 minutes.
"""
from __future__ import annotations

import inspect

import pytest

from futuresbot.runtime import FuturesRuntime


def _rt(tick_by_symbol=None, *, detail=None, raises=False):
    rt = object.__new__(FuturesRuntime)
    rt._env_float = lambda key, default=0.0: default
    rt._normalize_symbol_for_env = lambda s: s.upper().replace("_", "")
    rt._contract_tick_cache = dict(tick_by_symbol or {})

    class _C:
        def get_contract_detail(self, symbol):
            if raises:
                raise RuntimeError("API down")
            return detail or {}
    rt.client = _C()
    return rt


def test_the_tick_is_learned_from_the_exchange_and_cached():
    rt = _rt(detail={"symbol": "XRP_USDT", "priceUnit": 0.0001})
    assert rt._tick_size_for_symbol("XRP_USDT") == 0.0001
    assert rt._contract_tick_cache["XRP_USDT"] == 0.0001
    rt.client = None                                  # cached: no second call
    assert rt._tick_size_for_symbol("XRP_USDT") == 0.0001


def test_an_unreachable_exchange_keeps_the_old_default():
    assert _rt(raises=True)._tick_size_for_symbol("XRP_USDT") == 0.01


def test_the_live_xrp_prices_become_placeable():
    rt = _rt({"XRP_USDT": 0.0001})
    entry = 1.4373
    assert rt._snap_order_price("XRP_USDT", 1.4160756043497276, entry=entry) == pytest.approx(1.416)
    assert rt._snap_order_price("XRP_USDT", 1.5013731869508171, entry=entry) == pytest.approx(1.5014)
    for p in (1.416, 1.5014):
        assert abs(round(p / 0.0001) * 0.0001 - p) < 1e-9   # a clean multiple of the tick


def test_snapping_never_crosses_entry():
    """Rounding to nearest turned a sub-dollar short's breakeven floor into a stop 25%
    above entry on 2026-09-20. Above entry rounds up, below entry rounds down."""
    rt = _rt({"EVAA_USDT": 0.0001, "ZEC_USDT": 0.01})
    assert rt._snap_order_price("EVAA_USDT", 0.0080 * 0.9981, entry=0.0080) == pytest.approx(0.0079)
    assert rt._snap_order_price("ZEC_USDT", 1581.99 * 1.0019, entry=1581.99) == pytest.approx(1585.0, abs=0.02)
    long_be = rt._snap_order_price("ZEC_USDT", 1581.99 * 1.0019, entry=1581.99)
    assert long_be > 1581.99
    short_be = rt._snap_order_price("ZEC_USDT", 1581.99 * 0.9981, entry=1581.99)
    assert short_be < 1581.99


def test_both_re_place_paths_snap():
    for fn in (FuturesRuntime._restore_exchange_tpsl, FuturesRuntime._move_exchange_stop):
        src = inspect.getsource(fn)
        assert "_snap_order_price" in src
        assert src.index("_snap_order_price") < src.index("place_position_tpsl")
