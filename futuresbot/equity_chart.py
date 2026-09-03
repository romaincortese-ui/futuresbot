"""A balance chart for /report, drawn in text.

Added 2026-09-03 at the owner's request: "the trend should be clear in one look".
Rewritten the same day, because the first version was not honest.

WHY NOT A REAL IMAGE. Telegram would render a PNG, but neither matplotlib nor
PIL is installed in the deployed image, and adding a dependency to draw a chart
is how a subsystem goes silently dead - `redis` was absent on 2026-09-02 and
took the whole crypto-event overlay with it, unnoticed for months. Block
characters need nothing and cannot fail to import.

WHY THE FIRST VERSION WAS REPLACED. It drew the BALANCE as bars growing from the
window minimum. The owner looked at it and said "big drop on day 6 and huge
climb on day 7". Both moves were real (-$8.51 then +$14.30) but they are -4.9%
and +8.9% of the account, and the picture implied far more, because a bar whose
baseline is not zero has a length that is not proportional to its value. A line
may be drawn on a truncated axis; bars may not.

Four replacement designs were built and scored by three independent judges, then
attacked by three adversarial reviewers. All three refuted the leading
pure-picture design on the same ground, and it is the ground that matters:

    ANY design that asks the reader to convert picture amplitude into dollars
    will mislead on this account, because at $170 one row of a 7-row chart is
    worth $2.50-$5.00 - one to two whole R.

Measured on that design: daily moves misread by up to 66%, the week's low
invisible because two days quantised to the same row, and a +/-$1/day sawtooth
rendering identically to a dead week.

SO THE PICTURE IS NOT THE MEASUREMENT. Bars carry sign and relative size; the
dollars are printed beside them. The reader never converts anything.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Iterable, Sequence

FLOW_JUMP = 0.20        # a >20% single-step move is treated as a cash flow
BAR_W = 4               # cells each side of the zero rule
EIGHTHS = "▏▎▍▌▋▊▉█"    # 1/8 .. 8/8, left-anchored


def daily_balances(rows: Iterable[dict], *, days: float = 7.0,
                   now_ts: float | None = None) -> list[tuple[str, float]]:
    """Last observed balance per UTC day, oldest first, gaps carried forward.

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
        except (TypeError, ValueError, AttributeError):
            continue
        # isfinite, not just a try/except: NaN passes float() and every
        # comparison against it is False, so it survives both filters below and
        # then explodes inside fromtimestamp. A reviewer found exactly this.
        if not (math.isfinite(ts) and math.isfinite(eq)):
            continue
        if ts < cut or eq <= 0:
            continue
        try:
            d = dt.datetime.fromtimestamp(ts, dt.UTC)
        except (ValueError, OSError, OverflowError):
            continue
        key = d.toordinal()
        if key not in per or ts > per[key][0]:
            per[key] = (ts, eq, d.strftime("%m-%d"))
    if not per:
        return []

    # CARRY QUIET DAYS FORWARD, and carry to TODAY rather than to the last
    # close. The feature store only holds rows for CLOSED TRADES, so a day the
    # bot took nothing produces no row; plotted as-is the axis would read
    # 28-29-31 with three adjacent entries and the drought would be invisible.
    # A bot that stopped trading three days ago would likewise draw a chart
    # ending three days ago that looked perfectly current. Silence, at either
    # end, is the signal this account most needs to see.
    lo_d = min(per)
    try:
        today = dt.datetime.fromtimestamp(now, dt.UTC).toordinal()
    except (ValueError, OSError, OverflowError):
        today = max(per)
    hi_d = max(max(per), today)
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
    """Remove cash-flow steps so the TRADING series stays comparable.

    A $900 deposit onto a $170 account is a 6x step; left in, it dwarfs every
    real trading day. Each detected step is subtracted from every later point.
    The headline still carries the real balance, and the caption names the flow.
    """
    out, shift = [], 0.0
    flows = dict(detect_flows(points))
    for i, (lbl, v) in enumerate(points):
        if i in flows:
            shift += flows[i]
        out.append((lbl, v - shift))
    return out


def _money(v: float) -> str:
    return ("%+.2f" % v) if abs(v) < 1000 else ("%+.0f" % v)


def render(points: Sequence[tuple[str, float]], *, flow_days=None,
           partial_last: bool = True) -> list[str]:
    """Each day's CHANGE against a TRUE ZERO rule, with the dollars printed.

    The baseline is real zero - no change - so bar length is genuinely
    proportional to the day's P&L, which is what a bar chart must be to be
    legitimate. Magnitude is carried by the printed number, not by the bar, so
    the reader is never asked to convert amplitude into dollars.

    A quiet day is written `flat` rather than drawn as a short bar: reviewers
    found a +/-$1/day sawtooth rendering identically to a dead week on the
    previous design, and naming the case removes the ambiguity instead of
    encoding it.
    """
    if len(points) < 2:
        return ["  (not enough history yet)"]
    deltas = [(points[i][0], points[i][1] - points[i - 1][1], points[i][1])
              for i in range(1, len(points))]
    flow_days = flow_days or set()
    # Scale off TRADING days only, so one transfer cannot flatten the real week.
    traded_mag = [abs(d) for lbl, d, _ in deltas if lbl not in flow_days]
    scale = max(traded_mag or [0.0]) or 1e-9

    lab_w = max(3, max(len(str(k)) for k, _, _ in deltas))
    blank = " " * BAR_W + "│" + " " * BAR_W
    lines = ["%s %s %8s  %s" % (str(points[0][0]).rjust(lab_w), blank,
                                "start", "%.2f" % points[0][1])]
    for i, (lbl, d, bal) in enumerate(deltas):
        tag = "now" if (i == len(deltas) - 1 and partial_last) else str(lbl)
        if lbl in flow_days:
            note, body = "transfer", blank
        else:
            cells = min(BAR_W * 8, int(round(abs(d) / scale * BAR_W * 8)))
            if abs(d) < 0.005 or cells == 0:
                note, body = "flat", blank
            else:
                full, rem = divmod(cells, 8)
                if d > 0:
                    bar = "█" * full + (EIGHTHS[rem - 1] if rem else "")
                    body = " " * BAR_W + "│" + bar.ljust(BAR_W)
                else:
                    bar = ("▐" if rem else "") + "█" * full
                    body = bar.rjust(BAR_W)[-BAR_W:] + "│" + " " * BAR_W
                note = _money(d)
        lines.append("%s %s %8s  %s" % (tag.rjust(lab_w), body, note,
                                        "%.2f" % bal))
    return lines


def balance_block(rows: Iterable[dict], *, days: float = 7.0,
                  now_ts: float | None = None) -> list[str]:
    """The whole section: headline, per-day change chart, cash flows named."""
    pts = daily_balances(rows, days=days, now_ts=now_ts)
    if len(pts) < 2:
        return []
    first, last = pts[0][1], pts[-1][1]
    flows = detect_flows(pts)
    flow_sum = sum(d for _, d in flows)
    # A deposit is not performance. Report the trading move separately so the
    # headline percentage never credits the bot with a transfer.
    traded = last - first - flow_sum
    pct = (traded / first * 100.0) if first else 0.0
    arrow = "▲" if traded > 0 else ("▼" if traded < 0 else "▬")

    out = ["%s <b>Balance, last %d days</b>  $%.2f → $%.2f"
           % (arrow, int(round(days)), first, last)]
    if flows:
        # The flow size is INFERRED from the balance step, not read from a
        # transfer ledger, so it absorbs whatever the bot earned that same day.
        # Say "~" rather than print a figure that claims to be exact.
        detail = ", ".join("%s ~$%+.0f on %s"
                           % ("deposit" if d > 0 else "withdrawal", d, pts[i][0])
                           for i, d in flows)
        out.append("<i>includes %s — traded move is $%+.2f (%+.1f%%), that "
                   "day's own P&amp;L absorbed into the transfer</i>"
                   % (detail, traded, pct))
    else:
        out.append("<i>traded move $%+.2f (%+.1f%%)</i>" % (traded, pct))
    flow_days = {pts[i][0] for i, _ in flows}
    out.append("<pre>" + "\n".join(render(pts, flow_days=flow_days)) + "</pre>")
    out.append("<i>bars are each day's P&amp;L against a true zero line; the "
               "dollars are printed, so nothing has to be judged by eye.</i>")
    return out
