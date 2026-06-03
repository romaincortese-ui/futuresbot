import pandas as pd

from futuresbot.spot_regime import spot_regime_label


def _frame_with_tail(prices: list[float]) -> pd.DataFrame:
    frame = pd.DataFrame({"close": prices})
    frame["high"] = frame["close"] + 0.1
    frame["low"] = frame["close"] - 0.1
    return frame


def test_spot_regime_ema_gap_forces_bearish_label(monkeypatch):
    monkeypatch.setenv("FUTURES_REGIME_TREND_GAP", "0.015")
    frame = _frame_with_tail([100.0] * 80 + [100.0 + (96.0 - 100.0) * index / 59 for index in range(60)])

    assert spot_regime_label(frame) == "BEAR"


def test_spot_regime_ema_gap_override_can_be_disabled(monkeypatch):
    monkeypatch.setenv("FUTURES_REGIME_TREND_GAP", "0")
    frame = _frame_with_tail([100.0] * 80 + [100.0 + (96.0 - 100.0) * index / 59 for index in range(60)])

    assert spot_regime_label(frame) == "SIDEWAYS"


def test_spot_regime_ema_gap_requires_persistence(monkeypatch):
    monkeypatch.setenv("FUTURES_REGIME_TREND_GAP", "0.015")
    monkeypatch.setenv("FUTURES_REGIME_TREND_GAP_LOOKBACK_BARS", "1")
    prices = [100.0] * 80 + [100.0 + (94.0 - 100.0) * index / 59 for index in range(60)] + [94.4]
    frame = _frame_with_tail(prices)

    assert spot_regime_label(frame) == "SIDEWAYS"