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


def test_exit_kind_classification():
    from futuresbot.runtime import FuturesRuntime as R
    k = R._classify_exit_kind
    assert k(5.06) == "TP"        # NIL: full target
    assert k(4.72) == "TP"        # USOIL: TP minus fees
    assert k(-1.07) == "STOP"
    assert k(-1.65) == "STOP"     # BTW: gapped through the stop
    assert k(0.34) == "OTHER"     # ARB: neither
    assert k(2.53) == "OTHER"     # AKE: closed mid-flight
    assert k(None) is None


def test_digest_reports_tp_completion():
    from futuresbot.learning_digest import TRIAL_START, build_learning_digest
    rows = [
        {"ts": TRIAL_START + 1, "kind": "WILDCARD", "r_multiple": 5.0, "pnl_usdt": 9.0, "exit_kind": "TP"},
        {"ts": TRIAL_START + 2, "kind": "WILDCARD", "r_multiple": -1.0, "pnl_usdt": -2.0, "exit_kind": "STOP"},
        {"ts": TRIAL_START + 3, "kind": "SQUEEZE", "r_multiple": -1.0, "pnl_usdt": -2.0, "exit_kind": "STOP"},
        {"ts": TRIAL_START + 4, "kind": "WILDCARD", "r_multiple": 0.2, "pnl_usdt": 0.3, "exit_kind": "OTHER"},
    ]
    msg = build_learning_digest(rows, [])
    assert "Exits: TP <b>1</b> (25%)" in msg
    assert "stop 2" in msg and "other 1" in msg
