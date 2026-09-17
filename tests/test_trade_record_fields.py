"""Four trade-record defects found by the 2026-09-17 ZEC gate review."""
import inspect
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from futuresbot import trend as T
from futuresbot.runtime import ENTRY_GATE_KEYS, FuturesRuntime


def _tags(md):
    rt = object.__new__(FuturesRuntime)
    trade = {"pnl_usdt": 1.0, "fees_usdt": 0.1, "pnl_pct": 5.0,
             "entry_time": "2026-09-16T09:32:00+00:00", "exit_time": "2026-09-16T10:02:00+00:00"}
    return rt._trade_attribution_tags(SimpleNamespace(metadata=md), trade)


def test_trend_roc_is_tagged_as_24h_not_3h():
    t = _tags({"wildcard": 1.0, "trend": 1.0, "sl_margin_pct": 20.0, "wildcard_roc_pct": 0.0447})
    assert t["entry_3h_roc_pct"] is None
    assert t["entry_24h_roc_pct"] == pytest.approx(4.47)


def test_wildcard_roc_tag_is_unchanged():
    t = _tags({"wildcard": 1.0, "sl_margin_pct": 20.0, "wildcard_roc_pct": -0.13, "majors_age_s": 1.5})
    assert t["entry_3h_roc_pct"] == 13.0 and t["entry_24h_roc_pct"] is None
    assert t["majors_age_s"] == 1.5


def test_trend_signal_carries_the_prior_closing_high():
    closes = [100.0 * (1.20 ** (1 / 199)) ** i for i in range(200)]
    frame = pd.DataFrame({"open": closes, "high": [c * 1.002 for c in closes],
                          "low": [c * 0.998 for c in closes], "close": closes, "volume": [1e3] * 200})
    sig = T.detect_trend_signal(frame, "ZEC_USDT")
    assert sig is not None
    assert sig.prior_close_extreme == pytest.approx(max(closes[-97:-1]))
    assert sig.entry_price > sig.prior_close_extreme


def test_entry_gate_values_are_stamped_and_reach_the_closed_trade():
    entry = inspect.getsource(FuturesRuntime._open_wildcard_position)
    close = inspect.getsource(FuturesRuntime._close_history_trade)
    for k in ("trend_roc_24h", "trend_prior_close_extreme", "trend_extreme_margin_pct"):
        assert f'"{k}"' in entry and k in ENTRY_GATE_KEYS
    for k in ("atr_pct", "calm_ratio", "vol_z", "range_24h", "turnover_24h_usdt"):
        assert k in ENTRY_GATE_KEYS
    assert '"entry_rsi"' in close and "ENTRY_GATE_KEYS" in close
    assert "_stamp_majors_at_entry(position.metadata)" in entry


def test_majors_are_refreshed_at_the_fill_not_served_from_a_stale_cache():
    rt = object.__new__(FuturesRuntime)
    rt.client = MagicMock()
    rt.client.get_klines = lambda *a, **k: pd.DataFrame({"close": [100.0] * 244 + [103.0] * 96})
    rt._majors_cache = (time.time() - 300.0, {"btc_24h": 0.0206})   # 5 min old, inside the 10-min TTL
    md = {"btc_24h": 0.0206}
    rt._stamp_majors_at_entry(md)
    assert md["btc_24h"] == pytest.approx(0.03)
    assert 0.0 <= md["majors_age_s"] < 5.0
    assert rt._majors_state() is rt._majors_cache[1]                 # ordinary callers still use the cache


def _rt_with_klines(frames):
    rt = object.__new__(FuturesRuntime)
    rt.client = MagicMock()
    it = iter(frames)

    def _kl(*a, **k):
        f = next(it)
        if isinstance(f, Exception):
            raise f
        return f
    rt.client.get_klines = _kl
    return rt


def test_a_failed_refresh_keeps_the_good_cache_and_stamps_nothing():
    good = {k: 0.01 for k in FuturesRuntime._MAJORS_KEYS}
    rt = _rt_with_klines([RuntimeError("429")] * 3)
    rt._majors_cache = (time.time() - 300.0, good)
    md = dict(good)                                       # the pre-order stamp, same sample
    rt._stamp_majors_at_entry(md)
    assert {k: md[k] for k in good} == good               # values unchanged
    assert md["majors_age_s"] >= 299.0                    # and the age is the sample's real age
    assert rt._majors_cache[1] is good                    # the good cache survives


def test_a_partial_refresh_never_mixes_fresh_and_stale_majors():
    good = {k: 0.01 for k in FuturesRuntime._MAJORS_KEYS}
    ok = pd.DataFrame({"close": [100.0] * 244 + [103.0] * 96})
    rt = _rt_with_klines([RuntimeError("timeout"), ok, ok])  # BTC fails, ETH/SOL succeed
    rt._majors_cache = (time.time() - 300.0, good)
    md = dict(good)
    rt._stamp_majors_at_entry(md)
    assert {k: md[k] for k in good} == good
    assert md["majors_age_s"] >= 299.0                    # honest age of the sample kept


def test_live_position_is_saved_before_the_majors_refresh():
    src = inspect.getsource(FuturesRuntime._open_wildcard_position)
    live = src[src.index("self._ensure_live_position_setup"):]
    assert live.index("self._save_state()") < live.index("self._stamp_majors_at_entry")


def test_gate_values_reach_the_feature_store_and_rank_does_not_leak_into_trend():
    assert "ENTRY_GATE_KEYS" in inspect.getsource(FuturesRuntime._close_history_trade)
    assert "ENTRY_GATE_KEYS" in inspect.getsource(FuturesRuntime._append_feature_store)
    scan = inspect.getsource(FuturesRuntime._maybe_scan_trend)
    assert "self._pending_candidate_rank = None" in scan


def test_roc_slices_only_count_wildcard_rows():
    from futuresbot.conditional_expectancy import default_conditions
    conds = default_conditions()
    assert not conds["roc>=12pct"]({"kind": "TREND", "entry_3h_roc_pct": 14.0})
    assert conds["roc>=12pct"]({"kind": "WILDCARD", "entry_3h_roc_pct": 14.0})
