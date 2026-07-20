from futuresbot.learning_digest import TRIAL_START, build_learning_digest


def _trade(ts_off, r, pnl, kind="WILDCARD"):
    return {"ts": TRIAL_START + ts_off, "kind": kind, "r_multiple": r, "pnl_usdt": pnl,
            "is_wildcard": True, "is_win": pnl > 0}


def test_trial_scoreboard_counts_only_convex_since_start():
    store = [
        _trade(100, 2.0, 3.0),
        _trade(200, -1.0, -1.5),
        _trade(-999, 5.0, 9.0),                      # before the trial start -> excluded
        {"ts": TRIAL_START + 300, "kind": "PMT", "r_multiple": 1.0, "pnl_usdt": 1.0},  # PMT -> excluded
    ]
    msg = build_learning_digest(store, [])
    assert "Trial: <b>2/30</b>" in msg
    assert "netR <b>+1.00</b>" in msg
    assert "exBest <b>-1.00</b>" in msg


def test_shadow_scorecard_aggregates_by_reason():
    shadow = [
        {"reject_reason": "veto:ref_not_listed", "outcome": 5.0},
        {"reject_reason": "veto:ref_not_listed", "outcome": -1.0},
        {"reject_reason": "min_vol", "outcome": None},  # unresolved
    ]
    msg = build_learning_digest([], shadow)
    assert "Shadow: 3 logged, 2 resolved" in msg
    assert "veto:ref_not_listed: n=2 cfR +4.0" in msg


def test_empty_inputs_are_graceful():
    msg = build_learning_digest([], [])
    assert "Trial: <b>0/30</b>" in msg
    assert "no OOS-consistent findings" in msg
    assert "no vetoed/near-miss" in msg
