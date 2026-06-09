from futuresbot.oi_signal import oi_price_confirmation, pct_change


def test_confirmed_when_oi_rises_with_favourable_move():
    s = oi_price_confirmation(oi_change_pct=2.0, price_move_pct=1.0)
    assert s.state == "CONFIRMED" and s.score_adj > 0


def test_divergent_when_oi_falls_on_favourable_move():
    s = oi_price_confirmation(oi_change_pct=-2.0, price_move_pct=1.0)
    assert s.state == "DIVERGENT" and s.score_adj < 0


def test_neutral_when_oi_flat():
    assert oi_price_confirmation(oi_change_pct=0.1, price_move_pct=1.0).state == "NEUTRAL"


def test_neutral_when_move_flat():
    assert oi_price_confirmation(oi_change_pct=5.0, price_move_pct=0.0).state == "NEUTRAL"


def test_failopen_on_missing_data():
    assert oi_price_confirmation(None, 1.0).state == "NEUTRAL"
    assert oi_price_confirmation(2.0, None).state == "NEUTRAL"


def test_pct_change():
    assert round(pct_change(110, 100), 6) == 10.0
    assert pct_change(100, None) is None
    assert pct_change(100, 0) is None
