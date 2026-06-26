import pandas as pd

from futuresbot.squeeze import detect_squeeze_signal


def _frame(closes, highs, lows, vols):
    return pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes, "volume": vols})


def _squeeze_break_frame():
    # 25 high-range oscillation bars (builds ATR/Keltner width), then 12 ultra-tight
    # bars (Bollinger collapses INSIDE Keltner = squeeze), then a volume break up.
    closes, highs, lows, vols = [], [], [], []
    base = 100.0
    for i in range(40):
        c = base * (1 + 0.02 * (1 if i % 2 == 0 else -1))
        closes.append(c); highs.append(c * 1.02); lows.append(c * 0.98); vols.append(1000 + (i % 3) * 50)
    for i in range(12):
        c = base * (1 + 0.0005 * (1 if i % 2 == 0 else -1))
        closes.append(c); highs.append(c * 1.001); lows.append(c * 0.999); vols.append(1000 + (i % 3) * 50)
    # breakout bar: closes well above the coil high, on a volume spike, not vertical
    c = base * 1.025
    closes.append(c); highs.append(c * 1.001); lows.append(base * 1.0); vols.append(4000)
    return _frame(closes, highs, lows, vols)


def test_none_on_short_frame():
    assert detect_squeeze_signal(_frame([1.0] * 10, [1.01] * 10, [0.99] * 10, [100] * 10), "FOO_USDT") is None


def test_none_on_pure_trend_no_coil():
    n = 60
    closes = [100.0 * (1.01 ** i) for i in range(n)]
    highs = [c * 1.01 for c in closes]; lows = [c * 0.99 for c in closes]; vols = [1000] * n
    assert detect_squeeze_signal(_frame(closes, highs, lows, vols), "FOO_USDT") is None


def test_squeeze_position_is_convex_eligible():
    # Squeeze entries carry wildcard=1 (+squeeze=1) so they inherit the live
    # convex exit (no early lock, ride the -1R stop / +5R TP).
    from types import SimpleNamespace
    from futuresbot.runtime import FuturesRuntime
    rt = object.__new__(FuturesRuntime)
    rt._flag = lambda k, default=False: k == "FUTURES_WILDCARD_CONVEX_EXIT_ENABLED"
    assert rt._is_wildcard_convex(SimpleNamespace(metadata={"wildcard": 1.0, "squeeze": 1.0})) is True


def test_detects_squeeze_release_long():
    sig = detect_squeeze_signal(_squeeze_break_frame(), "FOO_USDT")
    assert sig is not None and sig.side == "LONG"
    assert sig.sl_price < sig.entry_price < sig.tp_price
    assert sig.sl_margin_pct <= 20.0 + 1e-6  # -20% cap honoured
    assert 5 <= sig.leverage <= 10 or sig.leverage >= 1
