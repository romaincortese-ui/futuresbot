from __future__ import annotations

from futuresbot.liq_buffer import distance_to_liq_atr, should_force_close


def test_distance_to_liq_atr_long_positive_far_from_liq():
    d = distance_to_liq_atr(entry_price=100.0, liq_price=90.0, current_price=99.0, atr=1.0, side="LONG")
    assert d == 9.0


def test_distance_to_liq_atr_short_positive_far_from_liq():
    d = distance_to_liq_atr(entry_price=100.0, liq_price=110.0, current_price=101.0, atr=1.0, side="SHORT")
    assert d == 9.0


def test_distance_to_liq_atr_invalid_inputs():
    assert distance_to_liq_atr(entry_price=100.0, liq_price=90.0, current_price=99.0, atr=0.0, side="LONG") is None
    assert distance_to_liq_atr(entry_price=100.0, liq_price=90.0, current_price=0.0, atr=1.0, side="LONG") is None
    assert distance_to_liq_atr(entry_price=100.0, liq_price=90.0, current_price=99.0, atr=1.0, side="XXX") is None


def test_should_force_close_long_within_threshold():
    decision = should_force_close(
        entry_price=100.0,
        liq_price=95.0,
        current_price=96.0,  # 1 ATR from liq
        atr=1.0,
        side="LONG",
        threshold_atr=2.0,
    )
    assert decision.force_close is True
    assert decision.distance_atr == 1.0


def test_should_force_close_long_outside_threshold():
    decision = should_force_close(
        entry_price=100.0,
        liq_price=90.0,
        current_price=99.0,  # 9 ATR from liq
        atr=1.0,
        side="LONG",
        threshold_atr=2.0,
    )
    assert decision.force_close is False


def test_should_force_close_invalid_returns_no_force():
    decision = should_force_close(
        entry_price=100.0,
        liq_price=0.0,
        current_price=99.0,
        atr=1.0,
        side="LONG",
    )
    assert decision.force_close is False
