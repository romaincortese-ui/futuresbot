from __future__ import annotations

from futuresbot.session_leverage import classify_session, session_policy


def test_classify_session_covers_24_hours():
    assert classify_session(2) == "ASIA"
    assert classify_session(7) == "LONDON"
    assert classify_session(12) == "LONDON"
    assert classify_session(13) == "OVERLAP"
    assert classify_session(15) == "OVERLAP"
    assert classify_session(16) == "US"
    assert classify_session(20) == "US"
    assert classify_session(23) == "ASIA"


def test_session_policy_asia_caps_leverage_low():
    policy = session_policy(3, full_leverage_cap=10, asia_leverage_cap=5)
    assert policy.session == "ASIA"
    assert policy.leverage_cap == 5
    assert policy.score_threshold_bump == 0.0


def test_session_policy_london_full_leverage():
    policy = session_policy(9, full_leverage_cap=10, asia_leverage_cap=5)
    assert policy.session == "LONDON"
    assert policy.leverage_cap == 10


def test_session_policy_event_window_bumps_us_threshold():
    policy = session_policy(17, full_leverage_cap=10, is_event_window=True, event_score_bump=12.0)
    assert policy.session == "US"
    assert policy.score_threshold_bump == 12.0


def test_session_policy_event_window_ignored_in_asia():
    policy = session_policy(3, is_event_window=True, event_score_bump=12.0)
    assert policy.score_threshold_bump == 0.0
