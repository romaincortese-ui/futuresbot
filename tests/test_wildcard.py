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


def test_available_slots_excludes_wildcard():
    # PMT slot count must exclude wildcard positions (separate slot).
    import os
    os.environ.setdefault("USE_FUTURES_PMT_STRATEGY", "1")
    from types import SimpleNamespace
    from futuresbot.runtime import FuturesRuntime
    rt = object.__new__(FuturesRuntime)
    rt.config = SimpleNamespace(max_concurrent_positions=2)
    pmt = SimpleNamespace(metadata={"pmt_stop_first": 1.0})
    wc = SimpleNamespace(metadata={"wildcard": 1.0})
    rt.open_positions = {"BTC_USDT": pmt, "FOO_USDT": wc}
    # 2 positions total, but only 1 is PMT -> 1 PMT slot still free
    assert rt._available_slots() == 1
    assert rt._wildcard_open_count() == 1


def test_sl_margin_capped_at_20(monkeypatch):
    # A wide ATR stop on a volatile alt must never lose more than the cap
    # (SIREN 2026-06-15 lost -68.8%). Force a wide stop and assert the cap holds.
    monkeypatch.setenv("FUTURES_WILDCARD_SL_ATR_MULT", "8.0")
    sig = detect_wildcard_signal(_frame(_apply(_MID_LONG)), "FOO_USDT")
    assert sig is not None
    assert sig.sl_margin_pct <= 20.0 + 1e-6   # never beyond the -20% cap
    assert sig.leverage >= 1
    # the cap is honoured by trimming leverage, not by leaving sl_margin huge
    assert sig.sl_price < sig.entry_price < sig.tp_price


def test_sl_margin_cap_is_configurable(monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_SL_ATR_MULT", "8.0")
    monkeypatch.setenv("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", "10.0")
    sig = detect_wildcard_signal(_frame(_apply(_MID_LONG)), "FOO_USDT")
    assert sig is not None and sig.sl_margin_pct <= 10.0 + 1e-6


def test_wildcard_convex_exit_skips_partial_bank():
    # Option A: with the convex flag on, a wildcard position must NOT partial-bank
    # at +1R (it rides the full runner). PMT positions are unaffected (no wildcard key).
    from types import SimpleNamespace
    from futuresbot.runtime import FuturesRuntime
    rt = object.__new__(FuturesRuntime)
    rt._flag = lambda k, default=False: k == "FUTURES_WILDCARD_CONVEX_EXIT_ENABLED"
    pos = SimpleNamespace(contracts=100, symbol="FOO_USDT")
    # wildcard + flag -> gate returns False even at a banked-worthy +1R gain
    assert rt._maybe_partial_bank(pos, current_price=1.0, gross_pnl_pct=99.0, metadata={"wildcard": 1.0}) is False


def test_wildcard_convex_skips_profit_and_micro_locks():
    # Convex wildcards must skip BOTH discretionary profit-locks so the runner
    # rides the -1R stop / +5R TP. micro_lock was the real +0.5R clipper (the
    # base profit_lock is already off in prod). PMT positions are NOT convex.
    from types import SimpleNamespace
    from futuresbot.runtime import FuturesRuntime
    rt = object.__new__(FuturesRuntime)
    rt._flag = lambda k, default=False: k == "FUTURES_WILDCARD_CONVEX_EXIT_ENABLED"
    wc = SimpleNamespace(metadata={"wildcard": 1.0})
    assert rt._is_wildcard_convex(wc) is True
    assert rt._profit_lock_exit(wc, 1.0) is False
    assert rt._micro_lock_exit(wc, 1.0) is False
    # PMT (no wildcard key) is not convex, so it is not short-circuited by the gate
    assert rt._is_wildcard_convex(SimpleNamespace(metadata={"pmt_stop_first": 1.0})) is False
    # convex gate also requires the flag to be on
    rt._flag = lambda k, default=False: False
    assert rt._is_wildcard_convex(wc) is False


def test_per_sleeve_convex_slots():
    # Slots are per-sleeve: an open WILDCARD must not block SQUEEZE, and vice
    # versa (the single shared slot sat occupied ~69% of a 21d window).
    from types import SimpleNamespace
    from futuresbot.runtime import FuturesRuntime
    rt = object.__new__(FuturesRuntime)
    wc = SimpleNamespace(metadata={"wildcard": 1.0})
    sq = SimpleNamespace(metadata={"wildcard": 1.0, "squeeze": 1.0})
    pmt = SimpleNamespace(metadata={"pmt_stop_first": 1.0})
    rt.open_positions = {"A_USDT": wc, "B_USDT": sq, "C_USDT": pmt}
    assert rt._convex_open_count("WILDCARD") == 1
    assert rt._convex_open_count("SQUEEZE") == 1
    rt.open_positions = {"B_USDT": sq}
    assert rt._convex_open_count("WILDCARD") == 0  # squeeze open leaves wildcard slot free


def test_wildcard_rank_prefers_deep_pullback():
    # A deep-pullback (lateness 0.50-0.70) candidate outranks a bigger-ROC
    # extreme-chase; among same-class candidates, |roc| decides. Never gates.
    from types import SimpleNamespace
    from futuresbot.runtime import FuturesRuntime
    k = FuturesRuntime._wildcard_rank_key
    deep_small = k(SimpleNamespace(roc_pct=0.09), 0.60)
    chase_big = k(SimpleNamespace(roc_pct=0.30), 1.00)
    assert deep_small > chase_big
    assert k(SimpleNamespace(roc_pct=0.30), 0.60) > deep_small  # same class -> roc
    assert k(SimpleNamespace(roc_pct=0.30), None) == (0, 0.30)  # unknown lateness = not deep


def test_engine_has_lateness_conditions():
    from futuresbot.conditional_expectancy import default_conditions
    conds = default_conditions()
    row = {"entry_lateness": 0.95}
    assert conds["stalled_reclaim(lat 0.85-0.99)"](row) is True
    assert conds["at_extreme(lat>=0.99)"]({"entry_lateness": 0.995}) is True
    assert conds["deep_pullback(lat 0.50-0.70)"]({"entry_lateness": 0.6}) is True
    assert conds["deep_pullback(lat 0.50-0.70)"]({"entry_lateness": None}) is False


def test_top_turnover_symbols_band():
    from futuresbot.runtime import FuturesRuntime
    tickers = [
        {"symbol": "BTC_USDT", "amount24": 900e6},
        {"symbol": "ETH_USDT", "amount24": 500e6},
        {"symbol": "AKE_USDT", "amount24": 37e6},
        {"symbol": "TINY_USDT", "amount24": 4e6},
        {"symbol": "BTC_USD", "amount24": 999e9},  # non-USDT ignored
    ]
    majors = FuturesRuntime._top_turnover_symbols(tickers, 2)
    assert majors == {"BTC_USDT", "ETH_USDT"}
    assert FuturesRuntime._top_turnover_symbols(tickers, 0) == set()


def test_trade_attribution_tags():
    # Stage-1 tagger: deterministic conditional features for win/loss study.
    from types import SimpleNamespace
    from futuresbot.runtime import FuturesRuntime
    rt = object.__new__(FuturesRuntime)
    pos = SimpleNamespace(metadata={"wildcard": 1.0, "sl_margin_pct": 20.0, "wildcard_roc_pct": 0.13})
    trade = {"pnl_usdt": 2.0, "fees_usdt": 0.2, "pnl_pct": 10.0,
             "entry_time": "2026-06-25T10:00:00+00:00", "exit_time": "2026-06-25T10:30:00+00:00",
             "exit_reason": "trail"}
    t = rt._trade_attribution_tags(pos, trade)
    assert t["is_win"] is True and t["is_wildcard"] is True
    assert t["entry_3h_roc_pct"] == 13.0
    assert t["r_multiple"] == 0.5          # pnl_pct 10 / sl_margin 20
    assert t["hold_min"] == 30.0
    assert rt._trade_attribution_tags(SimpleNamespace(metadata={}), {}) == {} or isinstance(rt._trade_attribution_tags(SimpleNamespace(metadata={}), {}), dict)


def test_regime_trim_conditions_read_recorded_multiplier():
    # The scaler's multiplier is now recorded in metadata -> the tagger's
    # regime_size_mult column is real, so these conditions can actually fire.
    from futuresbot.conditional_expectancy import default_conditions
    conds = default_conditions()
    assert conds["regime_trimmed(mult<1)"]({"regime_size_mult": 0.32}) is True
    assert conds["regime_trimmed(mult<1)"]({"regime_size_mult": 1.0}) is False
    assert conds["regime_trimmed_hard(<0.5)"]({"regime_size_mult": 0.32}) is True
    assert conds["regime_trimmed_hard(<0.5)"]({"regime_size_mult": 0.75}) is False
    # missing column must not fabricate a trim
    assert conds["regime_trimmed(mult<1)"]({}) is False
