import pandas as pd

from futuresbot.wildcard import detect_wildcard_signal, wildcard_enabled, wildcard_max_positions


def _frame(closes, vol_last=3000.0):
    n = len(closes)
    vols = [1000.0 + (i % 5) * 60.0 for i in range(n - 1)] + [vol_last]  # base variance so vol_z is defined
    # close near the bar high (realistic momentum bar) so the climax-wick guard passes
    return pd.DataFrame({
        "open": closes, "high": [c * 1.0008 for c in closes],
        "low": [c * 0.996 for c in closes], "close": closes, "volume": vols,
    })


def _apply(moves, base_n=28):
    closes = [1.0] * base_n; p = 1.0
    for m in moves:
        p *= (1.0 + m); closes.append(p)
    return closes


# +11% over 12 bars with retracements (RSI ~room), ending pullback then resume
_MID_LONG = [0.02, 0.02, 0.02, -0.01, 0.02, 0.02, 0.02, -0.01, 0.02, 0.02, -0.012, 0.006]


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FUTURES_WILDCARD_ENABLED", raising=False)
    assert wildcard_enabled() is False


def test_detects_pullback_resume_long():
    sig = detect_wildcard_signal(_frame(_apply(_MID_LONG)), "FOO_USDT")
    assert sig is not None and sig.side == "LONG"
    assert sig.roc_pct > 0.08 and 5 <= sig.leverage <= 10
    assert sig.sl_price < sig.entry_price < sig.tp_price
    assert 0.05 <= sig.balance_fraction <= 0.15


def test_rejects_no_extreme_move():
    assert detect_wildcard_signal(_frame([1.0 + 0.0005 * i for i in range(50)]), "FOO_USDT") is None


def test_rejects_vertical_climax():
    closes = _apply(_MID_LONG[:-2]) + [_apply(_MID_LONG[:-2])[-1] * 0.99, _apply(_MID_LONG[:-2])[-1] * 1.20]
    assert detect_wildcard_signal(_frame(closes), "FOO_USDT") is None


def test_rejects_overbought_rsi(monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_RSI_MAX", "50")
    assert detect_wildcard_signal(_frame(_apply(_MID_LONG)), "FOO_USDT") is None


def test_rejects_low_volume():
    assert detect_wildcard_signal(_frame(_apply(_MID_LONG), vol_last=950.0), "FOO_USDT") is None


def test_rejects_no_pullback():
    assert detect_wildcard_signal(_frame(_apply([0.02] * 13)), "FOO_USDT") is None


def test_max_positions_default(monkeypatch):
    monkeypatch.delenv("FUTURES_WILDCARD_MAX_POSITIONS", raising=False)
    assert wildcard_max_positions() == 1
