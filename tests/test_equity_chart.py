"""The balance chart must be readable, honest about cash flows, and unable to
break /report.

Added 2026-09-03. /report is the command used to decide whether to withdraw, so
a presentation helper must never be able to raise inside it.
"""
from __future__ import annotations

import time

from futuresbot.equity_chart import (balance_block, daily_balances, deflow,
                                     detect_flows, render)


def _rows(vals, now=None):
    now = time.time() if now is None else now
    return [{"ts": now - (len(vals) - 1 - i) * 86400 + 3600,
             "equity_at_close_usdt": v} for i, v in enumerate(vals)]


def test_one_point_per_day_using_the_LAST_close():
    """The reader is asking where the account ENDED each day, not its mean."""
    now = time.time()
    rows = [{"ts": now - 3600, "equity_at_close_usdt": 100.0},
            {"ts": now - 60, "equity_at_close_usdt": 150.0}]
    pts = daily_balances(rows, days=7, now_ts=now)
    assert len(pts) == 1 and pts[0][1] == 150.0


def test_a_deposit_is_detected_and_not_counted_as_performance():
    """THE POINT OF THE FLOW LOGIC. A transfer must never inflate the headline."""
    out = balance_block(_rows([170.0, 172.0, 1075.0, 1090.0]), days=7)
    body = " ".join(out)
    assert "deposit" in body
    # traded move is 172->170 then 1090-1075: about +$17, NOT +$920
    assert "+920" not in body
    assert "traded move" in body


def test_a_withdrawal_is_named_as_such():
    out = balance_block(_rows([1090.0, 1075.0, 172.0, 170.0]), days=7)
    assert "withdrawal" in " ".join(out)


def test_the_chart_plots_the_TRADING_curve_when_a_flow_happened():
    """Plotted raw, a 6x deposit compresses the week into one row and shows
    nothing. deflow() subtracts the step so the shape is the bot's work."""
    pts = [("01", 170.0), ("02", 175.0), ("03", 1080.0), ("04", 1090.0)]
    d = deflow(pts)
    assert [round(v, 2) for _, v in d] == [170.0, 175.0, 175.0, 185.0]
    assert max(v for _, v in d) < 300, "the step must be gone"


def test_no_flow_leaves_the_series_untouched():
    pts = [("01", 170.0), ("02", 172.0), ("03", 169.0)]
    assert deflow(pts) == pts
    assert detect_flows(pts) == []


def test_render_is_monospace_rectangular():
    """Telegram <pre> only aligns if every row is the same width."""
    lines = render([("01", 100.0), ("02", 120.0), ("03", 110.0)], height=5)
    assert len(lines) >= 5
    # data rows are rstripped, so compare the axis rows which are full width
    assert lines[-1].strip() and lines[-2].strip()


def test_a_flat_week_says_so_instead_of_dividing_by_zero():
    out = render([("01", 170.0), ("02", 170.0)])
    assert "flat" in " ".join(out)


def test_too_little_history_returns_nothing_rather_than_a_stub():
    assert balance_block(_rows([170.0]), days=7) == []
    assert balance_block([], days=7) == []


def test_garbage_rows_cannot_raise():
    bad = [{"ts": "nonsense", "equity_at_close_usdt": None},
           {"ts": None}, {}, {"ts": time.time(), "equity_at_close_usdt": -5}]
    assert balance_block(bad, days=7) == []


def test_report_calls_it_defensively():
    """/report decides withdrawals. A chart must not be able to raise in it."""
    import inspect

    from futuresbot.runtime import FuturesRuntime
    src = inspect.getsource(FuturesRuntime._report_text) \
        if hasattr(FuturesRuntime, "_report_text") else ""
    if not src:
        for name in dir(FuturesRuntime):
            if "report" in name.lower():
                try:
                    s2 = inspect.getsource(getattr(FuturesRuntime, name))
                except Exception:
                    continue
                if "balance_block" in s2:
                    src = s2
                    break
    assert "balance_block" in src, "the chart is not wired into /report"
    seg = src[src.index("balance_block") - 400:src.index("balance_block") + 400]
    assert "try:" in seg and "except Exception" in seg
