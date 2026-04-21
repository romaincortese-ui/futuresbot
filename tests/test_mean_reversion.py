from __future__ import annotations

import pandas as pd

from futuresbot.mean_reversion import score_mean_reversion_setup


def _build_frame(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.0005 for c in closes],
            "low": [c * 0.9995 for c in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
        }
    )


def test_short_signal_on_upper_band_spike():
    # 40 bars of small oscillation near 100, then final 5 bars rip to 115
    # -> price >> 2*sigma upper band AND RSI > 72.
    closes = [100.0, 100.2, 99.8, 100.1, 99.9] * 8  # 40 flat bars
    closes += [102.0, 106.0, 110.0, 113.0, 115.0]   # 5 spike bars
    sig = score_mean_reversion_setup(_build_frame(closes))
    assert sig is not None
    assert sig.side == "SHORT"
    assert sig.tp_price < sig.entry_price
    assert sig.sl_price > sig.entry_price


def test_long_signal_on_lower_band_spike():
    closes = [100.0, 100.2, 99.8, 100.1, 99.9] * 8
    closes += [98.0, 94.0, 90.0, 87.0, 85.0]
    sig = score_mean_reversion_setup(_build_frame(closes))
    assert sig is not None
    assert sig.side == "LONG"
    assert sig.tp_price > sig.entry_price
    assert sig.sl_price < sig.entry_price


def test_no_signal_in_flat_market():
    closes = [100.0, 100.1, 99.95, 100.05, 99.98] * 12
    assert score_mean_reversion_setup(_build_frame(closes)) is None


def test_returns_none_with_insufficient_history():
    assert score_mean_reversion_setup(_build_frame([1.0] * 5)) is None
