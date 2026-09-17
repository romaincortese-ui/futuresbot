import inspect

from futuresbot.runtime import FuturesRuntime

capped = FuturesRuntime._long_range_capped


def test_long_at_or_above_cap_is_refused():
    assert capped("LONG", 2.38, 2.0)
    assert capped("LONG", 2.0, 2.0)
    assert not capped("LONG", 1.99, 2.0)


def test_shorts_are_never_capped():
    assert not capped("SHORT", 2.38, 2.0)       # BR_USDT 2026-09-17 stays tradeable


def test_cap_off_and_unreadable_range_fail_open():
    assert not capped("LONG", 5.0, 0.0)
    assert not capped("LONG", 0.0, 2.0)


def test_refused_longs_are_shadow_logged_before_the_rank_loop():
    src = inspect.getsource(FuturesRuntime._maybe_scan_wildcard)
    assert 'FUTURES_WILDCARD_LONG_MAX_24H_RANGE' in src
    log_at = src.index('_shadow_log_untaken(sig, "WILDCARD", f"long_range_cap')
    assert log_at < src.index('"rank_dropped"')
