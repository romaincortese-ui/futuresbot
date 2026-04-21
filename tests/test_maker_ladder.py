from __future__ import annotations

from futuresbot.maker_ladder import MakerLadderConfig, decide_next_action


def test_first_step_posts_maker_below_mid_for_long():
    d = decide_next_action(
        side="LONG",
        seconds_since_signal=0.0,
        best_bid=100.0,
        best_ask=100.02,
        tick_size=0.01,
        seconds_to_funding=3600.0,
        filled=False,
    )
    assert d.action == "POST_MAKER"
    assert d.step == 0
    assert d.price < (100.0 + 100.02) / 2.0  # below mid for long


def test_short_posts_above_mid():
    d = decide_next_action(
        side="SHORT",
        seconds_since_signal=0.0,
        best_bid=100.0,
        best_ask=100.02,
        tick_size=0.01,
        seconds_to_funding=3600.0,
        filled=False,
    )
    assert d.action == "POST_MAKER"
    assert d.price > (100.0 + 100.02) / 2.0


def test_reposts_with_wider_offset_after_first_wait():
    cfg = MakerLadderConfig(step_seconds=(2.0, 2.0, 1.0), tick_offsets=(1, 2, 4))
    d = decide_next_action(
        side="LONG",
        seconds_since_signal=2.5,  # past first boundary, inside second
        best_bid=100.0,
        best_ask=100.02,
        tick_size=0.01,
        seconds_to_funding=3600.0,
        filled=False,
        config=cfg,
    )
    assert d.action == "REPOST_MAKER"
    assert d.step == 1
    assert d.tick_offset == 2


def test_crosses_spread_after_ladder_exhausted():
    cfg = MakerLadderConfig(step_seconds=(2.0, 2.0, 1.0), tick_offsets=(1, 2, 4))
    d = decide_next_action(
        side="LONG",
        seconds_since_signal=6.0,  # past all three maker windows (5s total)
        best_bid=100.0,
        best_ask=100.02,
        tick_size=0.01,
        seconds_to_funding=3600.0,
        filled=False,
        config=cfg,
    )
    assert d.action == "CROSS_TAKER"
    assert d.price == 100.02  # cross into ask for long


def test_pre_funding_window_forces_immediate_cross():
    d = decide_next_action(
        side="SHORT",
        seconds_since_signal=0.1,
        best_bid=100.0,
        best_ask=100.02,
        tick_size=0.01,
        seconds_to_funding=30.0,  # inside default 90s window
        filled=False,
    )
    assert d.action == "CROSS_TAKER"
    assert d.price == 100.0  # short crosses into bid


def test_filled_short_circuits_to_wait():
    d = decide_next_action(
        side="LONG",
        seconds_since_signal=1.0,
        best_bid=100.0,
        best_ask=100.02,
        tick_size=0.01,
        seconds_to_funding=3600.0,
        filled=True,
    )
    assert d.action == "WAIT"


def test_safety_abort_on_stale_signal():
    cfg = MakerLadderConfig(max_total_seconds=10.0)
    d = decide_next_action(
        side="LONG",
        seconds_since_signal=12.0,
        best_bid=100.0,
        best_ask=100.02,
        tick_size=0.01,
        seconds_to_funding=3600.0,
        filled=False,
        config=cfg,
    )
    assert d.action == "ABORT"
