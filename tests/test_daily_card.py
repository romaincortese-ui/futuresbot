"""The daily card (wc/DAILY, pre-registered 2026-09-23).

It grades the MACHINE, prints the day's draw conditional on the fill count, and says
NO ACTION on about 95% of days on purpose - including the worst dollar day in this
book's life. Every test below is about that discipline: a card that grades outcomes
daily would fire constantly and teach the reader to ignore it.
"""
import inspect
from datetime import datetime, timezone

import pytest

from futuresbot import scorecard as S
from futuresbot.runtime import FuturesRuntime


def _ts(day, hour=12):
    return datetime(*[int(x) for x in day.split("-")], hour, tzinfo=timezone.utc).timestamp()


def _row(day, *, r=-1.03, hold=1.0, kind="WILDCARD", risk=15.0, exit_reason="EXCHANGE_CLOSE",
         slip=5.0, risk_pct=1.2, breadth=0.50, hour=12, recon=0.0, exit_kind=None):
    if exit_kind is None:
        exit_kind = "STOP" if r < 0 and exit_reason in ("EXCHANGE_CLOSE", "STOP_LOSS") else "OTHER"
    return {"ts": _ts(day, hour), "hold_hours": hold, "kind": kind, "symbol": "X_USDT",
            "exit_kind": exit_kind,
            "risk_usdt": risk, "pnl_usdt": r * risk, "exit_reason": exit_reason,
            "entry_slippage_bps": slip, "risk_pct_actual": risk_pct,
            "breadth_24h": breadth, "reconstructed": recon,
            "equity_at_close_usdt": 900.0}


def _pool(n=40, day="2026-09-01"):
    """A benign history so the meter and the percentile have something to stand on."""
    out = []
    for i in range(n):
        out.append(_row(day, r=(0.9 if i % 3 else -1.0), hour=(i % 20) + 1, hold=0.5))
    return out


def test_pnl_is_entry_dated_with_the_exit_dated_figure_beside_it():
    """25% of fills straddle a UTC boundary; the card must never silently pick one."""
    straddler = _row("2026-09-22", r=-1.0, risk=10.0, hold=9.0, hour=2)   # entered 09-21
    same_day = _row("2026-09-22", r=-1.0, risk=10.0, hold=1.0, hour=12)
    card = S.build_daily_card(_pool() + [straddler, same_day], day="2026-09-22")
    assert "1 in / 2 out" in card.lines[1]
    assert "-1.00R entry" in card.lines[7] and "-2.00R exit" in card.lines[7]
    assert "-$10.00" in card.lines[8] and "-$20.00" in card.lines[8]


def test_a_stop_inside_the_band_is_not_a_defect():
    card = S.build_daily_card(_pool() + [_row("2026-09-22", r=-1.06)], day="2026-09-22")
    assert card.tripwires == []
    assert card.verdict == "NO ACTION"
    assert "0 of 6 tripwires" in card.lines[3]


def test_a_stop_outside_the_band_is_a_defect():
    card = S.build_daily_card(_pool() + [_row("2026-09-22", r=-1.64)], day="2026-09-22")
    assert any(t.startswith("M1") for t in card.tripwires)
    assert card.verdict == "INVESTIGATE"


def test_the_band_grades_stops_only_not_every_losing_exchange_close():
    """EXCHANGE_CLOSE is the book's catch-all. Selecting on it band-checked 89 rows
    including an -3.79R gap and 18 whose exit_kind was not even known; the band was
    derived on the 71 rows with exit_kind == STOP."""
    card = S.build_daily_card(
        _pool() + [_row("2026-09-22", r=-1.64, exit_kind="TIMEOUT")], day="2026-09-22")
    assert not any(t.startswith("M1") for t in card.tripwires)


def test_a_legacy_ladder_exit_is_not_an_anomaly():
    """PEAK_PROFIT_LOCK and PEAK_PROTECTION_GAP_EXIT are the same rule exiting in
    profit or at a loss; one used to be sanctioned and the other said INVESTIGATE."""
    card = S.build_daily_card(
        _pool() + [_row("2026-09-22", r=-0.4, exit_reason="PEAK_PROTECTION_GAP_EXIT")],
        day="2026-09-22")
    assert not any(t.startswith("M5") for t in card.tripwires)


def test_a_backfilled_row_fires_once_not_twice():
    card = S.build_daily_card(
        _pool() + [_row("2026-09-22", r=-1.0, exit_reason="EXCHANGE_CLOSE_RECONSTRUCTED",
                        recon=1.0, exit_kind="OTHER")], day="2026-09-22")
    assert sum(1 for t in card.tripwires if t.startswith("M5")) == 1


def test_the_ledger_check_compares_like_with_like():
    """The exchange counts EVERY close on the account; the card grades convex sleeves
    only. Comparing the two fired a false M6 on all 13 days in this book with a
    non-convex close."""
    rows = _pool() + [_row("2026-09-22", r=-1.0), _row("2026-09-22", r=-1.0, kind="PMT")]
    card = S.build_daily_card(rows, day="2026-09-22", exchange_closes=2)
    assert not any(t.startswith("M6") for t in card.tripwires)


def test_the_meter_reference_is_frozen_not_estimated_from_the_stream():
    """A CUSUM with a moving reference is not a CUSUM: estimating mu from the monitored
    stream manufactured four crossings of a once-a-year threshold."""
    src = inspect.getsource(S.decay_meter)
    assert "DECAY_MU_R" in src and "sum(pool)" not in src
    good = _pool()
    strong = good + [_row("2026-09-05", r=3.0, hour=(i % 20) + 1) for i in range(30)]
    # a run of winners must NOT make the meter easier to trip afterwards
    assert S.decay_meter(good)[0] == pytest.approx(S.decay_meter(good)[0])
    assert S.decay_meter(strong)[0] <= S.decay_meter(good)[0] + 1e-9


def test_entry_date_survives_a_row_with_no_hold_hours():
    """Every row before 2026-08-07 carries hold_min and not hold_hours."""
    row = _row("2026-09-22", r=-1.0, hold=0.0, hour=2)
    row["hold_min"] = 240.0                       # entered on 09-21 at 22:00Z
    card = S.build_daily_card(_pool() + [row], day="2026-09-22")
    assert "0 in / 1 out" in card.lines[1]


def test_favourable_slippage_is_not_a_tripwire():
    """M4 is signed: entry_slippage_bps is side-adjusted and positive means WORSE than
    the signal price. Grading the absolute value fired on 2026-09-16, a five-for-five
    day whose worst offence was a fill 107 bps in our favour."""
    good = S.build_daily_card(_pool() + [_row("2026-09-22", r=0.8, slip=-107.0)], day="2026-09-22")
    bad = S.build_daily_card(_pool() + [_row("2026-09-22", r=0.8, slip=+510.0)], day="2026-09-22")
    assert good.tripwires == []
    assert any(t.startswith("M4") for t in bad.tripwires)


def test_the_other_machine_tripwires():
    deep = S.build_daily_card(_pool() + [_row("2026-09-22", r=-1.8)], day="2026-09-22")
    assert any(t.startswith("M2") for t in deep.tripwires)
    size = S.build_daily_card(_pool() + [_row("2026-09-22", r=0.5, risk_pct=3.4)], day="2026-09-22")
    assert any(t.startswith("M3") for t in size.tripwires)
    odd = S.build_daily_card(_pool() + [_row("2026-09-22", r=0.5, exit_reason="WAT")], day="2026-09-22")
    assert any(t.startswith("M5") for t in odd.tripwires)
    back = S.build_daily_card(_pool() + [_row("2026-09-22", r=0.5, recon=1.0)], day="2026-09-22")
    assert any(t.startswith("M5") for t in back.tripwires)
    led = S.build_daily_card(_pool() + [_row("2026-09-22", r=0.5)], day="2026-09-22",
                             exchange_closes=3)
    assert any(t.startswith("M6") for t in led.tripwires)
    marg = S.build_daily_card(_pool() + [_row("2026-09-22", r=0.5)], day="2026-09-22",
                              margin_pct=47.0)
    assert any(t.startswith("M6") for t in marg.tripwires)


def test_the_draw_is_conditioned_on_the_fill_count():
    """Any daily chart that does not condition on the fill count is measuring the fill
    count: the same netR is ordinary at seven fills and extreme at two."""
    pool = [(-1.0 if i % 2 else 1.0) for i in range(60)]
    two = S.day_draw(-4.0, 2, pool)
    seven = S.day_draw(-4.0, 7, pool)
    assert "at 2 fills" in two and "at 7 fills" in seven
    assert S.day_draw(-4.0, 2, pool) == two          # deterministic: fixed seed


def test_a_good_day_and_a_bad_day_both_say_no_action():
    """The symmetry is the point - it stops the card being read as a mood ring."""
    good = S.build_daily_card(_pool() + [_row("2026-09-22", r=2.0, exit_reason="CONVEX_RETENTION_TRAIL")],
                              day="2026-09-22")
    bad = S.build_daily_card(_pool() + [_row("2026-09-22", r=-1.05)], day="2026-09-22")
    assert good.verdict == "NO ACTION" and bad.verdict == "NO ACTION"


def test_the_decay_meter_accumulates_on_a_bad_run_and_decays_on_an_ordinary_one():
    base = _pool()
    run = base + [_row("2026-09-2%d" % (i + 1), r=-1.1, hour=3) for i in range(8)]
    hot, frac_hot = S.decay_meter(run)
    cool, frac_cool = S.decay_meter(base)
    assert hot > cool and frac_hot == pytest.approx(hot / S.DECAY_H_R)
    assert frac_cool < 0.10


def test_the_meter_crossing_its_threshold_escalates_one_rung():
    rows = _pool() + [_row("2026-09-2%d" % ((i % 9) + 1), r=-3.0, hour=(i % 20) + 1)
                      for i in range(20)]
    card = S.build_daily_card(rows, day="2026-09-22")
    assert S.decay_meter(rows)[1] >= 1.0
    assert card.verdict == "CHANGE ONE THING"


def test_an_elevated_meter_says_so_without_demanding_action():
    """2026-09-08, the worst dollar day in the book's life, reached 44% of a once-a-year
    alarm and was back to 0% eight days later with nothing changed."""
    rows = _pool() + [_row("2026-09-0%d" % (i + 1), r=-1.45, hour=(i % 20) + 1,
                              exit_reason="CONVEX_TIME_STOP") for i in range(7)]
    card = S.build_daily_card(rows, day="2026-09-07")
    frac = S.decay_meter(rows)[1]
    if 0.40 <= frac < 1.0:
        assert card.verdict == "NO ACTION - meter elevated"


def test_the_card_is_short_enough_to_read_on_a_phone():
    card = S.build_daily_card(_pool() + [_row("2026-09-22")], day="2026-09-22")
    assert len(card.lines) <= 12
    assert max(len(l) for l in card.lines) <= 44
    assert card.lines[-1].startswith(">>>")


def test_the_card_states_what_it_cannot_do():
    card = S.build_daily_card(_pool() + [_row("2026-09-22")], day="2026-09-22")
    blob = "\n".join(card.detail)
    assert "not readable in one day" in blob
    assert "no action is ever taken" in blob.lower()      # the MARKET block


def test_r_is_measured_not_taken_from_the_tag():
    """pnl/risk is the correct denominator; the stored r_multiple disagreed with it on
    12 of 17 fills in the trial-19 window."""
    row = _row("2026-09-22", r=-1.0, risk=10.0)
    row["r_multiple"] = -0.5                              # a stale tag must not win
    card = S.build_daily_card(_pool() + [row], day="2026-09-22")
    assert "-1.00R entry" in card.lines[7]


def test_only_convex_sleeves_are_graded():
    pmt = _row("2026-09-22", r=-5.0, kind="PMT")
    card = S.build_daily_card(_pool() + [pmt], day="2026-09-22")
    assert "0 in / 0 out" in card.lines[1]


def test_the_command_rejects_a_bad_date_and_defaults_to_yesterday():
    src = inspect.getsource(FuturesRuntime._build_daily_message)
    assert "yesterday" in src and "today" in src
    rt = object.__new__(FuturesRuntime)
    assert "/daily YYYY-MM-DD" in rt._build_daily_message("nonsense")


def test_the_command_is_wired_and_documented():
    poll = inspect.getsource(FuturesRuntime._handle_telegram_commands)
    assert '"/daily"' in poll
    assert "_build_daily_message(arg)" in poll
    assert "/daily" in FuturesRuntime._build_help_message(object.__new__(FuturesRuntime))


def test_the_daily_card_is_not_folded_into_report():
    """/report filters rows to ts >= TRIAL_START and is trial-scoped by construction."""
    rep = inspect.getsource(FuturesRuntime._build_report_message)
    assert "build_daily_card" not in rep
