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
    msg = build_learning_digest([], shadow, trial_start=0.0)
    assert "Shadow (this trial): 3 logged, 2 resolved" in msg
    assert "veto:ref_not_listed: n=2 cfR +4.0" in msg


def test_shadow_scorecard_is_scoped_to_the_trial():
    """It read the whole file, pooling trials 4-7 — different regimes, sleeve
    configs and exit policies summed into one cfR."""
    shadow = [
        {"ts": 500.0, "reject_reason": "slot_occupied", "outcome": 5.0},   # last trial
        {"ts": 1500.0, "reject_reason": "slot_occupied", "outcome": -1.0},
    ]
    msg = build_learning_digest([], shadow, trial_start=1000.0)
    trial_line = next(l for l in msg.splitlines() if l.startswith("Shadow (this trial)"))
    assert "1 logged, 1 resolved" in trial_line
    assert "cfR -1.0" in trial_line
    assert "+4.0" not in trial_line, "the last trial's row leaked into this trial"
    # ...but it is still visible in the pooled line, labelled
    assert "pooled across trials (n=2)" in msg


def test_shadow_scorecard_reports_cost_adjusted_r():
    """cfR is fee-free by construction. On a sniper's thin stop the round trip
    is ~0.5R, which is the difference between an edge and nothing."""
    shadow = [{"ts": 1500.0, "reject_reason": "slot_occupied", "outcome": 1.0,
               "entry": 100.0, "sl": 99.63}]     # 0.37% stop -> ~0.51R cost
    msg = build_learning_digest([], shadow, trial_start=1000.0)
    assert "cfR +1.0" in msg and "net +0.5" in msg


def test_legacy_bracket_rows_are_flagged_not_silently_pooled():
    """A convex row with no exit_policy was scored on the retired 48h
    hold-to-target bracket, not the live 24h clock + retention trail."""
    shadow = [
        {"ts": 1500.0, "sleeve": "WILDCARD", "reject_reason": "slot_occupied",
         "outcome": 5.0, "entry": 100.0, "sl": 84.0},
        {"ts": 1600.0, "sleeve": "WILDCARD", "reject_reason": "slot_occupied",
         "outcome": 0.5, "entry": 100.0, "sl": 84.0, "exit_policy": "convex_v7"},
    ]
    msg = build_learning_digest([], shadow, trial_start=1000.0)
    assert "1 row(s) still scored under the retired 48h bracket" in msg


def test_empty_inputs_are_graceful():
    msg = build_learning_digest([], [])
    assert "Trial: <b>0/30</b>" in msg
    assert "no OOS-consistent findings" in msg
    assert "Shadow (this trial): 0 logged; none logged yet" in msg


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
    # A 2R-bracket sleeve (sniper) completes its target at ~+1.6R net. Scored
    # against the convex 5R those are OTHER, which mis-reads a filled target as
    # "target too demanding" in the TP-completion tripwire.
    assert k(1.72, tp_r=2.0, gross_r=2.13) == "TP"   # LINK 08-09: bracket filled
    assert k(1.60, tp_r=2.0, gross_r=2.08) == "TP"   # XRP 08-10
    assert k(1.72, gross_r=2.13) == "OTHER"          # the old, wrong reading
    assert k(-1.33, tp_r=2.0, gross_r=-1.06) == "STOP"  # HYPE: overshoot, still a stop
    # Fees alone must not manufacture a TP: SOL 08-08 paid 26% of gross and
    # still only reached +1.78R gross against a 2R target.
    assert k(1.32, tp_r=2.0, gross_r=1.78) == "OTHER"


def test_tagger_scores_exit_kind_against_the_sleeves_own_target():
    from types import SimpleNamespace
    from futuresbot.runtime import FuturesRuntime
    rt = object.__new__(FuturesRuntime)
    # LINK_USDT 2026-08-09, verbatim from the live ledger: +8.48% of margin net
    # on a 4.9171% stop = +1.72R net, +2.13R gross of a 2R bracket.
    trade = {"pnl_usdt": 0.0377, "fees_usdt": 0.0092, "pnl_pct": 8.48, "margin_usdt": 0.4596,
             "entry_time": "2026-08-09T22:53:00+00:00", "exit_time": "2026-08-09T23:30:00+00:00",
             "exit_reason": "EXCHANGE_CLOSE"}
    sniper = SimpleNamespace(metadata={"sniper": 1.0, "sl_margin_pct": 4.9171,
                                       "tp_margin_pct": 4.9171 * 2.0})
    assert rt._trade_attribution_tags(sniper, trade)["exit_kind"] == "TP"
    # Same realised R on a 5R convex sleeve is genuinely mid-flight.
    convex = SimpleNamespace(metadata={"wildcard": 1.0, "sl_margin_pct": 4.9171,
                                       "tp_margin_pct": 4.9171 * 5.0})
    assert rt._trade_attribution_tags(convex, trade)["exit_kind"] == "OTHER"
    # No tp_margin_pct (pre-2026-08 rows) falls back to the convex 5R.
    legacy = SimpleNamespace(metadata={"wildcard": 1.0, "sl_margin_pct": 4.9171})
    assert rt._trade_attribution_tags(legacy, trade)["exit_kind"] == "OTHER"


def test_digest_reports_tp_completion():
    from futuresbot.learning_digest import TRIAL_START, build_learning_digest
    rows = [
        {"ts": TRIAL_START + 1, "kind": "WILDCARD", "r_multiple": 5.0, "pnl_usdt": 9.0, "exit_kind": "TP"},
        {"ts": TRIAL_START + 2, "kind": "WILDCARD", "r_multiple": -1.0, "pnl_usdt": -2.0, "exit_kind": "STOP"},
        {"ts": TRIAL_START + 3, "kind": "SQUEEZE", "r_multiple": -1.0, "pnl_usdt": -2.0, "exit_kind": "STOP"},
        {"ts": TRIAL_START + 4, "kind": "WILDCARD", "r_multiple": 0.2, "pnl_usdt": 0.3, "exit_kind": "OTHER"},
    ]
    msg = build_learning_digest(rows, [])
    # The SQUEEZE row is excluded: trial 7 is scored on WILDCARD closes, and
    # counting squeeze made the digest disagree with /status on the same n/30.
    assert "Trial: <b>3/30</b> WC closes" in msg
    assert "Exits: TP <b>1</b> (33%)" in msg
    assert "stop 1" in msg and "other 1" in msg


# --------------------------------------------------------------------------
# resolver exit policy (2026-08-09): the replay must score the live stack
# --------------------------------------------------------------------------

def _row(**kw):
    row = {"ts": 1000, "symbol": "X_USDT", "side": "LONG", "sleeve": "WILDCARD",
           "entry": 100.0, "sl": 84.0, "tp": 180.0, "tp_r": 5.0, "outcome": None}
    row.update(kw)
    return row


def _bars(*prices, start=2000, step=900):
    """(ts, high, low) where each entry is (high, low)."""
    return [(start + i * step, hi, lo) for i, (hi, lo) in enumerate(prices)]


def test_bracket_still_rides_to_target_for_sniper():
    """SNIPER is excluded from the convex stack in the runtime, so the plain
    bracket is the RIGHT model for it — this must not change."""
    from futuresbot.shadow_ledger import resolve_outcome

    out = resolve_outcome(_row(sleeve="SNIPER_FAST"),
                          _bars((130, 128), (150, 145), (185, 180)), 9e9, convex=False)
    assert out["outcome_kind"] == "tp" and out["outcome"] == 5.0
    assert out["exit_policy"] == "bracket"


def test_convex_replay_banks_the_retention_floor_instead_of_riding_to_tp():
    """THE FIX. Same price path: the bracket credits +5R, the live stack peaks,
    fades, and banks 0.30 x peak. Every wildcard cfR in the scorecard was the
    first number when the bot would have booked the second."""
    from futuresbot.shadow_ledger import resolve_outcome

    # peaks at +2R (132), fades to +0.5R (108) -> floor 0.30 x 2.0 = +0.60R
    path = _bars((132, 130), (110, 104), (185, 180))
    bracket = resolve_outcome(_row(), path, 9e9, convex=False)
    convex = resolve_outcome(_row(), path, 9e9, convex=True)
    assert bracket["outcome"] == 5.0 and bracket["outcome_kind"] == "tp"
    assert convex["outcome_kind"] == "trail" and convex["outcome"] == 0.6
    assert convex["exit_policy"] == "convex_v7"


def test_convex_trail_does_not_arm_below_one_r():
    from futuresbot.shadow_ledger import resolve_outcome

    # peaks at +0.9R only, then fades hard to the stop
    out = resolve_outcome(_row(), _bars((114, 112), (101, 83)), 9e9, convex=True)
    assert out["outcome_kind"] == "stop" and out["outcome"] == -1.0


def test_convex_trail_ignores_a_peak_set_inside_the_same_bar():
    """Within one bar we cannot know whether the high or the low came first.
    Crediting the intrabar peak would bank a floor the trade may never have
    earned, so the floor is tested against PRIOR bars only."""
    from futuresbot.shadow_ledger import resolve_outcome

    # a single bar that both peaks at +3R and returns to +0.1R
    out = resolve_outcome(_row(), _bars((148, 101.6)), 9e9, convex=True)
    assert out is None or out["outcome_kind"] != "trail"


def test_every_resolved_row_carries_its_round_trip_cost():
    """cfR is fee-free by construction. Without the twin, a 0.37% sniper stop
    reads +1.1R when it is worth roughly nothing."""
    from futuresbot.shadow_ledger import resolve_outcome

    thin = _row(sleeve="SNIPER_FAST", entry=100.0, sl=99.63, tp=100.74, tp_r=2.0)
    out = resolve_outcome(thin, _bars((100.8, 100.5)), 9e9, convex=False)
    assert out["outcome"] == 2.0
    assert 0.50 <= out["cost_r"] <= 0.53          # 0.190% / 0.37%
    assert 1.47 <= out["outcome_net"] <= 1.50
    # a wildcard's wide stop pays almost nothing by comparison
    wide = resolve_outcome(_row(), _bars((185, 180)), 9e9, convex=False)
    assert wide["cost_r"] < 0.02


def test_legacy_rows_are_reopened_without_losing_their_outcome():
    from futuresbot.shadow_ledger import mark_for_reresolve, needs_reresolve

    legacy = _row(outcome=5.0, outcome_kind="tp")
    assert needs_reresolve(legacy) is True
    reopened = mark_for_reresolve(legacy)
    assert reopened["outcome"] is None
    assert reopened["outcome_legacy"] == 5.0 and reopened["outcome_kind_legacy"] == "tp"
    # ...and it is not reopened twice
    assert needs_reresolve({**reopened, "outcome": 0.6, "exit_policy": "convex_v7"}) is False
    # sniper rows were always scored correctly — leave them alone
    assert needs_reresolve(_row(sleeve="SNIPER_FAST", outcome=2.0)) is False
    assert needs_reresolve(_row(outcome=None)) is False


def test_kline_window_is_bounded_by_the_row_horizon_not_by_now():
    """A row re-opened by the migration can be weeks old. Fetching to `now`
    makes a capped kline response drop the OLDEST bars — the only ones that
    can resolve it."""
    import inspect

    from futuresbot.runtime import FuturesRuntime

    src = inspect.getsource(FuturesRuntime._resolve_shadow_ledger)
    assert "span_end" in src and "end=end" in src
    assert "end=int(now_ts)" not in src


def test_digest_shows_the_pooled_sample_labelled_as_such():
    """In-trial n is ~1 at a veto a week; the pooled figure is the only place
    there is any sample, so it is shown and explicitly not a verdict."""
    shadow = [
        {"ts": 500.0, "reject_reason": "slot_occupied", "outcome": 5.0},
        {"ts": 600.0, "reject_reason": "slot_occupied", "outcome": -1.0},
        {"ts": 1500.0, "reject_reason": "slot_occupied", "outcome": -1.0},
    ]
    msg = build_learning_digest([], shadow, trial_start=1000.0)
    assert "Shadow (this trial): 1 logged, 1 resolved" in msg
    assert "pooled across trials (n=3)" in msg and "not a verdict" in msg


# --------------------------------------------------------------------------
# defects found by adversarial review, 2026-08-09 — all pre-deploy
# --------------------------------------------------------------------------

def test_zero_observations_never_becomes_a_measured_outcome():
    """CRITICAL. An empty kline response is not an exception, so a re-opened row
    resolved to a fabricated `timeout 0.0` stamped convex_v7 — and since
    exit_policy was then set, needs_reresolve() froze it there, permanently
    replacing the row's real counterfactual with a zero indistinguishable from
    a measured one."""
    from futuresbot.shadow_ledger import resolve_outcome

    row = _row(ts=1000, outcome=None, outcome_legacy=5.0)
    assert resolve_outcome(row, [], 9e9, horizon_s=86400, convex=True) is None
    # bars that all predate the row are equally no observation
    assert resolve_outcome(row, _bars((150, 140), start=100), 9e9,
                           horizon_s=86400, convex=True) is None


def test_runtime_skips_a_group_with_no_bars():
    import inspect

    from futuresbot.runtime import FuturesRuntime

    src = inspect.getsource(FuturesRuntime._resolve_shadow_ledger)
    assert "if not bars:" in src, "empty kline frame must not reach the resolver"


def test_the_walk_stops_at_the_rows_own_horizon():
    """CRITICAL. horizon_s was only consulted AFTER the loop, so a 23-day-old
    row sharing a kline fetch with a fresh one was scored on bars weeks past
    its 24h clock — where a stop or a TP is near-certain."""
    from futuresbot.shadow_ledger import resolve_outcome

    # flat inside the clock, then a TP spike on day 12
    flat = [(2000 + i * 900, 101.0, 99.0) for i in range(96)]
    spike = [(1000 + 12 * 86400, 185.0, 180.0)]
    out = resolve_outcome(_row(), flat + spike, 9e9, horizon_s=86400, convex=True)
    assert out["outcome_kind"] == "timeout", "a post-clock bar produced an exit"
    assert out["outcome"] != 5.0


def test_resolver_groups_by_day_so_one_old_row_cannot_widen_the_window():
    import inspect

    from futuresbot.runtime import FuturesRuntime

    src = inspect.getsource(FuturesRuntime._resolve_shadow_ledger)
    assert "// 86400" in src, "kline window must not span an unbounded group"


def test_trail_never_books_more_than_the_trade_reached():
    """On a thin stop the cost floor can exceed the peak. Live returns False
    (`exit_level >= peak_r`); the replay was booking 1.188R on a trade whose
    maximum favourable excursion was 1.10R."""
    from futuresbot.shadow_ledger import resolve_outcome

    thin = _row(entry=100.0, sl=99.76, tp=101.2, tp_r=5.0)   # sl_frac 0.24%
    # peaks at +1.10R then returns to entry
    out = resolve_outcome(thin, _bars((100.264, 100.1), (100.0, 99.9)), 9e9,
                          horizon_s=86400, convex=True)
    assert out is None or out["outcome_kind"] != "trail"
    if out:
        assert out["outcome"] <= 1.10


def test_armed_row_banks_the_floor_not_the_stop_on_a_bar_spanning_both():
    """The floor sits ABOVE the hard stop, so price reaches it first. Testing
    the stop first booked -1R where live banks +0.35R — a 1.35R error against
    the very invariant the trail exists to enforce."""
    from futuresbot.shadow_ledger import resolve_outcome

    row = _row(entry=100.0, sl=97.0, tp=115.0, tp_r=5.0)     # 1R = 3
    out = resolve_outcome(row, _bars((103.5, 101.0), (100.5, 96.5)), 9e9,
                          horizon_s=86400, convex=True)
    assert out["outcome_kind"] == "trail"
    assert out["outcome"] > 0, "an armed trade must never book a loss"
    # ...but an UNARMED row still hits its stop, adverse-first
    unarmed = resolve_outcome(_row(entry=100.0, sl=97.0, tp=115.0),
                              _bars((101.0, 100.5), (100.5, 96.5)), 9e9,
                              horizon_s=86400, convex=True)
    assert unarmed["outcome_kind"] == "stop"


def test_timeout_marks_at_the_close_when_the_caller_supplies_one():
    from futuresbot.shadow_ledger import resolve_outcome

    row = _row(entry=100.0, sl=84.0, tp=180.0)               # 1R = 16
    with_close = resolve_outcome(row, [(2000, 110.0, 100.0, 108.0)], 9e9,
                                 horizon_s=1800, convex=True)
    assert with_close["outcome"] == 0.5                       # (108-100)/16
    midpoint = resolve_outcome(row, [(2000, 110.0, 100.0)], 9e9,
                               horizon_s=1800, convex=True)
    assert midpoint["outcome"] == 0.312                       # (105-100)/16, banker rounding


def test_the_write_path_never_drops_a_duplicate_row(tmp_path):
    """load_rows() dedupes for ANALYSIS. Writing that collapsed list back
    deletes the duplicates from the only on-disk record, including their
    distinct reject_reason."""
    import json as _json

    from futuresbot import shadow_ledger as shadow

    led = tmp_path / "l.jsonl"
    pair = {"sleeve": "SNIPER_FAST", "symbol": "S_USDT", "side": "LONG",
            "entry": 1.0, "sl": 0.9, "outcome": 1.0}
    led.write_text("\n".join(_json.dumps(r) for r in [
        {**pair, "ts": 1000, "reject_reason": "shadow_only"},
        {**pair, "ts": 1001, "reject_reason": "slot_occupied"},
    ]) + "\n", encoding="utf-8")

    assert len(shadow.load_rows(str(led))) == 1        # collapsed for analysis
    raw = shadow.load_raw(str(led))
    assert len(raw) == 2                               # both preserved on read
    shadow.rewrite(str(led), raw)
    assert len(shadow.load_raw(str(led))) == 2, "the write path lost a row"
    assert "slot_occupied" in led.read_text(encoding="utf-8")


def test_digest_does_not_claim_an_empty_ledger_when_the_trial_is_just_new():
    """It asserted "no vetoed/near-miss signals logged yet" over a ledger
    holding 34 of them, and suppressed the pooled line added for that case."""
    shadow = [{"ts": 500.0, "reject_reason": "slot_occupied", "outcome": 5.0}] * 4
    msg = build_learning_digest([], shadow, trial_start=1000.0)
    assert "no vetoed/near-miss signals logged yet" not in msg
    assert "0 logged — 4 resolved in earlier trials" in msg
    assert "pooled across trials (n=4)" in msg
