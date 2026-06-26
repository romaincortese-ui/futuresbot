from futuresbot.partial_bank import partial_bank_decision


def _d(**kw):
    base = dict(gross_pnl_pct=22.0, sl_margin_pct=20.0, contracts=10, already_banked=False)
    base.update(kw)
    return partial_bank_decision(**base)


def test_banks_half_at_one_r():
    d = _d()
    assert d is not None and d.vol_to_close == 5 and d.trigger_margin_pct == 20.0


def test_no_bank_below_trigger():
    assert _d(gross_pnl_pct=19.9) is None


def test_fires_once_only():
    assert _d(already_banked=True) is None


def test_needs_two_contracts_min():
    assert _d(contracts=1) is None
    d = _d(contracts=2)
    assert d is not None and d.vol_to_close == 1  # always leaves a runner


def test_never_closes_full_position():
    d = _d(contracts=3, bank_fraction=0.9)
    assert d is not None and d.vol_to_close <= 2


def test_env_disable(monkeypatch):
    monkeypatch.setenv("FUTURES_PMT_STOP_FIRST_PARTIAL_BANK_ENABLED", "0")
    assert _d() is None


def test_custom_trigger_r(monkeypatch):
    monkeypatch.setenv("FUTURES_PMT_STOP_FIRST_PARTIAL_BANK_TRIGGER_R", "1.5")
    assert _d(gross_pnl_pct=25.0) is None      # 1.5R = 30%
    assert _d(gross_pnl_pct=31.0) is not None


def test_failopen_on_missing_data():
    assert _d(gross_pnl_pct=None) is None
    assert _d(sl_margin_pct=None) is None
    assert _d(sl_margin_pct=0.0) is None


def test_breakeven_stop_price_sides(monkeypatch):
    from futuresbot.partial_bank import breakeven_stop_price
    monkeypatch.setenv("FUTURES_PMT_BANK_BREAKEVEN_BUFFER_PCT", "0.2")
    assert abs(breakeven_stop_price(100.0, "LONG") - 100.2) < 1e-9
    assert abs(breakeven_stop_price(100.0, "SHORT") - 99.8) < 1e-9


def test_close_message_shows_partial_bank_and_total():
    from types import SimpleNamespace
    from futuresbot.runtime import FuturesRuntime
    rt = object.__new__(FuturesRuntime)
    rt._mode_label = lambda: "LIVE"
    rt._format_price = lambda p: f"{p:,.2f}"
    rt.config = SimpleNamespace(symbol="BTC_USDT")
    # banked +$3.00, runner -$0.01 -> message must show the breakdown and the +$2.99 total
    banked = {"side": "SHORT", "symbol": "BTC_USDT", "exit_reason": "STOP_LOSS",
              "entry_price": 59925.5, "exit_price": 59850.0, "pnl_usdt": 2.99, "pnl_pct": 20.0,
              "banked_pnl_usdt": 3.00, "runner_pnl_usdt": -0.01}
    msg = rt._close_message(banked)
    assert "Partial bank: <b>$+3.00</b>" in msg and "Runner: <b>$-0.01</b>" in msg
    assert "PnL (total) <b>$+2.99</b>" in msg
    # no banking -> no breakdown line, plain PnL
    plain = {"side": "LONG", "symbol": "BTC_USDT", "exit_reason": "CLOSED",
             "entry_price": 60000.0, "exit_price": 60100.0, "pnl_usdt": 1.0, "pnl_pct": 5.0}
    msg2 = rt._close_message(plain)
    assert "Partial bank" not in msg2 and "PnL <b>$+1.00</b>" in msg2
