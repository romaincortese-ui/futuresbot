"""A balance chart for /report, drawn in text.

Added 2026-09-03 at the owner's request: "the trend should be clear in one look".

WHY NOT A REAL IMAGE. Telegram would render a PNG, but neither matplotlib nor
PIL is installed in the deployed image, and adding a dependency to draw a chart
is how a subsystem goes silently dead - `redis` was absent on 2026-09-02 and
took the whole crypto-event overlay with it, unnoticed for months. Block
characters need nothing and cannot fail to import.

WHAT IT PLOTS. The ACCOUNT BALANCE as observed at each close
(`equity_at_close_usdt`), not the flow-adjusted trading curve. The owner asked
for the balance, so a deposit or withdrawal SHOULD appear. It is labelled rather
than hidden - an unexplained vertical step in a P&L chart is worse than no chart.

THE BASELINE IS THE WINDOW MINIMUM, NOT ZERO. On a ~$170 account a zero-based
axis compresses a week's trading into one row of pixels and shows nothing. The
axis is therefore labelled at both ends so the compression is visible: a chart
that exaggerates without saying so is a lie, one that exaggerates and labels the
range is a magnifying glass.
"""
from __future__ import annotations

import datetime as dt
from typing import Iterable, Sequence

BLOCKS = " ▁▂▃▄▅▆▇█"
COL_W = 3
FLOW_JUMP = 0.20        # a >20% single-step move is treated as a cash flow


def daily_balances(rows: Iterable[dict], *, days: float = 7.0,
                   now_ts: float | None = None) -> list[tuple[str, float]]:
    """Last observed balance per UTC day, oldest first.

    Uses the LAST close of each day rather than the mean, so the series is a
    balance history rather than a smoothed average - the reader is asking where
    the account ended each day.
    """
    import time as _t
    now = _t.time() if now_ts is None else now_ts
    cut = now - days * 86400.0
    # keyed by UTC day ORDINAL, not by an "%m-%d" string: parsing a month-day
    # without a year is ambiguous, fails on Feb 29, and changes behaviour in
    # Python 3.15. Ordinals also make the year boundary a non-event.
    per: dict[int, tuple[float, float, str]] = {}
    for r in rows:
        try:
            ts = float(r.get("ts") or 0.0)
            eq = float(r.get("equity_at_close_usdt") or 0.0)
        except (TypeError, ValueError):
            continue
        if ts < cut or eq <= 0:
            continue
        d = dt.datetime.fromtimestamp(ts, dt.UTC)
        key = d.toordinal()
        if key not in per or ts > per[key][0]:
            per[key] = (ts, eq, d.strftime("%m-%d"))
    if not per:
        return []

    # CARRY QUIET DAYS FORWARD. The feature store only holds rows for CLOSED
    # TRADES, so a day the bot took nothing produces no row. Plotted as-is the
    # axis would read 28-29-31 with three evenly spaced columns and the drought
    # would be invisible - the one thing this account most needs to see. A day
    # with no closes is a day the balance did not move, so repeat it.
    # ...and carry to TODAY, not to the last close. A bot that stopped trading
    # three days ago would otherwise draw a chart ending three days ago that
    # looks perfectly current. The silence at the RIGHT EDGE is the drought
    # signal that matters most.
    lo_d = min(per)
    hi_d = max(max(per), dt.datetime.fromtimestamp(now, dt.UTC).toordinal())
    out: list[tuple[str, float]] = []
    carry = per[lo_d][1]
    for k in range(lo_d, min(hi_d, lo_d + 400) + 1):
        if k in per:
            carry = per[k][1]
            lbl = per[k][2]
        else:
            lbl = dt.date.fromordinal(k).strftime("%m-%d")
        out.append((lbl, carry))
    return out


def detect_flows(points: Sequence[tuple[str, float]]) -> list[tuple[int, float]]:
    """(index, delta) for steps large enough to be a deposit or withdrawal."""
    out = []
    for i in range(1, len(points)):
        a, b = points[i - 1][1], points[i][1]
        if a > 0 and abs(b - a) / a >= FLOW_JUMP:
            out.append((i, b - a))
    return out


def deflow(points: Sequence[tuple[str, float]]) -> list[tuple[str, float]]:
    """Remove cash-flow steps so the TRADING curve stays visible.

    A $900 deposit onto a $170 account is a 6x step. Plotted raw it compresses
    the entire week of trading into a single row and the chart shows nothing but
    the transfer - which the reader already knows about, because they made it.
    Each detected step is subtracted from every later point, so the line becomes
    continuous and the shape is the bot's work. The headline still carries the
    real balance, and the caption names the flow.
    """
    out, shift = [], 0.0
    flows = dict(detect_flows(points))
    for i, (lbl, v) in enumerate(points):
        if i in flows:
            shift += flows[i]
        out.append((lbl, v - shift))
    return out


def render(points: Sequence[tuple[str, float]], *, height: int = 7) -> list[str]:
    """A column chart of balances. Returns lines for a Telegram <pre> block."""
    if len(points) < 2:
        return ["  (not enough history yet)"]
    vals = [v for _, v in points]
    lo, hi = min(vals), max(vals)
    span = hi - lo
    if span <= 0:                       # flat week: draw a midline, say so
        return ["  %s  flat at $%.2f" % ("─" * (COL_W * len(points)), hi)]

    # Column heights in eighths, so a 7-row chart resolves 56 levels. The floor
    # is 1, not 0: at level 0 the lowest bar draws as blank space and the day
    # vanishes from the chart entirely, which is indistinguishable from missing
    # data. Every day present in the series must be visible as a day.
    levels = [1 + int(round((v - lo) / span * (height * 8 - 2))) for v in vals]
    lab_w = max(len("$%.2f" % hi), len("$%.2f" % lo))
    lines: list[str] = []
    for row in range(height - 1, -1, -1):
        cells = []
        for lv in levels:
            filled = lv - row * 8
            if filled >= 8:
                cells.append("█" * COL_W)
            elif filled <= 0:
                cells.append(" " * COL_W)
            else:
                cells.append(BLOCKS[filled] * COL_W)
        if row == height - 1:
            lab = ("$%.2f" % hi).rjust(lab_w)
        elif row == 0:
            lab = ("$%.2f" % lo).rjust(lab_w)
        else:
            lab = " " * lab_w
        edge = "┤" if row in (0, height - 1) else "│"
        lines.append(("%s %s%s" % (lab, edge, "".join(cells))).rstrip())
    lines.append("%s └%s" % (" " * lab_w, "─" * (COL_W * len(points))))
    axis = "".join(lbl[-2:].rjust(COL_W) for lbl, _ in points)
    lines.append("%s  %s" % (" " * lab_w, axis))
    return lines


def balance_block(rows: Iterable[dict], *, days: float = 7.0,
                  now_ts: float | None = None) -> list[str]:
    """The whole section: headline, chart, and any cash flow called out."""
    pts = daily_balances(rows, days=days, now_ts=now_ts)
    if len(pts) < 2:
        return []
    first, last = pts[0][1], pts[-1][1]
    flows = detect_flows(pts)
    flow_sum = sum(d for _, d in flows)
    # A deposit is not performance. Report the trading move separately so the
    # headline percentage does not silently credit the bot with a transfer.
    traded = last - first - flow_sum
    pct = (traded / first * 100.0) if first else 0.0
    arrow = "▲" if traded > 0 else ("▼" if traded < 0 else "▬")

    head = ("%s <b>Balance, last %d days</b>  $%.2f → $%.2f"
            % (arrow, int(round(days)), first, last))
    out = [head]
    if flows:
        # The flow size is INFERRED from the balance step, not read from a
        # transfer ledger, so it absorbs whatever the bot earned or lost on the
        # same day. A $900 deposit on a day that made $2 reads as $902. Say
        # "~" rather than print a two-decimal figure that claims to be exact.
        detail = ", ".join("%s ~$%+.0f on %s" % ("deposit" if d > 0 else "withdrawal",
                                                 d, pts[i][0]) for i, d in flows)
        out.append("<i>includes %s — traded move is $%+.2f (%+.1f%%), that "
                   "day's own P&L absorbed into the transfer</i>"
                   % (detail, traded, pct))
    else:
        out.append("<i>traded move $%+.2f (%+.1f%%)</i>" % (traded, pct))
    # Plot the TRADING curve, not the transfers. A $900 deposit onto a $170
    # account compresses the whole week into one row otherwise - see deflow().
    plot = deflow(pts) if flows else pts
    out.append("<pre>" + "\n".join(render(plot)) + "</pre>")
    if flows:
        out.append("<i>chart shows the trading curve with the transfer removed; "
                   "the headline balance is the real one.</i>")
    return out
