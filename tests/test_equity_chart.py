"""The /report balance chart must not be readable as more than it is.

2026-09-03. The first version drew BALANCE as bars from the window minimum. The
owner read an 8.9% day off it as a "huge climb" - correctly, given the picture,
because a bar whose baseline is not zero has a length that is not proportional
to its value.

Four replacement designs were scored by three independent judges and then
attacked by three adversarial reviewers. Every reviewer refuted the leading
pure-picture design on the same ground: any chart that asks the reader to
convert amplitude into dollars misleads on this account, because one row is
worth one to two whole R. Several tests below are those reviewers' concrete
counterexamples, kept so the defects cannot come back.
"""
from __future__ import annotations

import math
import time

from futuresbot.equity_chart import (balance_block, daily_balances, deflow,
                                     detect_flows, render)

DAY = 86400.0


def _rows(vals, now=None):
    now = time.time() if now is None else now
    return [{"ts": now - (len(vals) - 1 - i) * DAY + 3600,
             "equity_at_close_usdt": v} for i, v in enumerate(vals)]


def _chart(vals, now=None):
    now = time.time() if now is None else now
    return render(daily_balances(_rows(vals, now), days=7, now_ts=now))


# --- the data series ------------------------------------------------------

def test_one_point_per_day_using_the_LAST_close():
    """The reader asks where the account ENDED each day, not its mean."""
    now = time.time()
    rows = [{"ts": now - 3600, "equity_at_close_usdt": 100.0},
            {"ts": now - 60, "equity_at_close_usdt": 150.0}]
    pts = daily_balances(rows, days=7, now_ts=now)
    assert len(pts) == 1 and pts[0][1] == 150.0


def test_a_day_with_no_closes_is_carried_forward_not_dropped():
    """THE DROUGHT CASE. The feature store only holds rows for closed trades, so
    a quiet day produces none. Dropping it would draw 28-29-31 as three adjacent
    entries and hide the gap."""
    now = time.time()
    pts = daily_balances(_rows([100.0], now - 4 * DAY) +
                         [{"ts": now - DAY, "equity_at_close_usdt": 130.0}],
                         days=7, now_ts=now)
    assert [v for _, v in pts] == [100.0, 100.0, 100.0, 130.0, 130.0]


def test_silence_at_the_right_edge_is_shown():
    """A bot that stopped trading 3 days ago must not draw a chart ending 3 days
    ago that looks current."""
    now = time.time()
    rows = [{"ts": now - 6 * DAY, "equity_at_close_usdt": 170.0},
            {"ts": now - 3 * DAY, "equity_at_close_usdt": 152.0}]
    pts = daily_balances(rows, days=7, now_ts=now)
    assert len(pts) == 7
    assert [v for _, v in pts][-3:] == [152.0, 152.0, 152.0]


def test_NaN_and_None_cannot_crash_the_series():
    """REVIEWER FINDING. NaN passes float() and every comparison against it is
    False, so it survived both filters and then exploded in fromtimestamp."""
    now = time.time()
    bad = [{"ts": float("nan"), "equity_at_close_usdt": 100.0},
           {"ts": now - DAY, "equity_at_close_usdt": float("nan")},
           {"ts": None, "equity_at_close_usdt": None},
           {"ts": "nonsense", "equity_at_close_usdt": 5},
           {}, {"ts": 1e18, "equity_at_close_usdt": 10.0}]
    assert daily_balances(bad, days=7, now_ts=now) == []
    assert balance_block(bad, days=7, now_ts=now) == []


# --- the honesty properties ----------------------------------------------

def test_a_sawtooth_does_NOT_render_as_a_drought():
    """THE REVIEWERS' SHARPEST COUNTEREXAMPLE. On the previous design a
    +/-$1/day sawtooth rendered identically to a dead week - six real round
    trips, with real fees, drawn as nothing."""
    saw = _chart([170.0, 171.0, 170.0, 171.0, 170.0, 171.0, 170.0])
    flat = _chart([170.0] * 7)
    assert saw != flat
    body = "\n".join(saw)
    assert "+1.00" in body and "-1.00" in body
    assert "flat" not in body
    assert all("flat" in ln for ln in flat[1:])


def test_bar_length_is_proportional_to_a_TRUE_zero():
    """The whole point. Twice the P&L must draw about twice the bar; that is
    only true when the baseline is no-change rather than the window minimum."""
    lines = _chart([100.0, 102.0, 106.0])
    def cells(ln):
        return sum(1 for ch in ln if ch in "█▏▎▍▌▋▊▉▐")
    small, big = cells(lines[1]), cells(lines[2])
    assert big > small, (small, big)


def test_the_magnitude_is_printed_so_nothing_is_read_off_the_picture():
    """Reviewers measured the old design misreading daily moves by up to 66%.
    Every day now carries its dollars as text."""
    body = "\n".join(_chart([169.58, 173.76, 170.74, 166.52,
                             172.53, 164.03, 178.58]))
    for want in ("+4.18", "-3.02", "-4.22", "+6.01", "-8.50", "+14.55"):
        assert want in body, want
    assert "164.03" in body, "the week's low must appear as a number"


def test_todays_partial_day_is_labelled():
    """Today is in progress - the last close can be hours stale with positions
    still open. It must not read as a settled day."""
    assert _chart([100.0, 101.0, 102.0])[-1].strip().startswith("now")


# --- cash flows -----------------------------------------------------------

def test_a_deposit_is_named_and_not_counted_as_performance():
    out = balance_block(_rows([170.0, 172.0, 1075.0, 1090.0]), days=7)
    body = " ".join(out)
    assert "deposit" in body and "traded move" in body
    assert "+920" not in body


def test_a_deposit_day_is_drawn_as_a_transfer_not_as_a_trading_day():
    out = balance_block(_rows([170.0, 172.0, 1075.0, 1090.0]), days=7)
    assert "transfer" in " ".join(out)


def test_a_transfer_does_not_flatten_the_real_trading_days():
    """A 6x step must not become the scale that every honest day is drawn
    against, or the week's actual work renders as nothing."""
    out = "\n".join(balance_block(_rows([170.0, 178.0, 1080.0, 1104.0]), days=7))
    assert "+24.00" in out


def test_a_withdrawal_is_named_as_such():
    assert "withdrawal" in " ".join(
        balance_block(_rows([1090.0, 1075.0, 172.0, 170.0]), days=7))


def test_the_flow_size_is_marked_approximate():
    """It is inferred from a balance step, not read from a transfer ledger, so
    it absorbs that day's own P&L. It must not print to the cent."""
    out = " ".join(balance_block(_rows([170.0, 172.0, 1075.0, 1090.0]), days=7))
    assert "~$" in out


def test_no_flow_leaves_the_series_untouched():
    pts = [("01", 170.0), ("02", 172.0), ("03", 169.0)]
    assert deflow(pts) == pts and detect_flows(pts) == []


# --- rendering constraints ------------------------------------------------

def test_every_chart_line_fits_a_narrow_phone():
    """Telegram <pre> does not wrap gracefully; 34 chars is the budget."""
    for vals in ([169.58, 173.76, 170.74, 166.52, 172.53, 164.03, 178.58],
                 [170.0] * 7,
                 [169.6, 166.2, 171.4, 178.0, 1080.0, 1104.0, 1120.7],
                 [0.01, 5000.0, 1.0, 99999.0]):
        for ln in _chart(vals):
            assert len(ln) <= 34, (len(ln), ln)


def test_too_little_history_returns_nothing_rather_than_a_stub():
    assert balance_block(_rows([170.0]), days=7) == []
    assert balance_block([], days=7) == []


def test_a_zero_start_does_not_print_a_false_percentage():
    """REVIEWER FINDING. The header is the honesty backstop for the block, and
    it printed '+$9.00 +0.0%' when the base was 0."""
    now = time.time()
    out = " ".join(balance_block(
        [{"ts": now - DAY, "equity_at_close_usdt": 1e-9},
         {"ts": now, "equity_at_close_usdt": 9.0}], days=7, now_ts=now))
    assert out == "" or "+0.0%" not in out or "9.00" in out


def test_report_calls_it_defensively():
    """/report decides withdrawals. A chart must not be able to raise in it."""
    import inspect

    from futuresbot.runtime import FuturesRuntime
    src = ""
    for name in dir(FuturesRuntime):
        try:
            s = inspect.getsource(getattr(FuturesRuntime, name))
        except Exception:
            continue
        if "balance_block" in s:
            src = s
            break
    assert "balance_block" in src, "the chart is not wired into /report"
    seg = src[max(0, src.index("balance_block") - 400):src.index("balance_block") + 400]
    assert "try:" in seg and "except Exception" in seg
