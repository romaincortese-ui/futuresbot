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
