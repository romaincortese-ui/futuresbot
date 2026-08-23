"""The gate scorecard counted the same missed move many times.

A blocked mover keeps re-signalling every scan while it runs, and each fire was
scored as an independent missed trade. Over 7 days to 2026-08-22 the
slot_occupied bucket held ELEVEN rows that were THREE moves — four BTC fires in
92 minutes, two ETH, five XRP inside 70 minutes — each credited a full +3.0R, as
though five separate XRP longs could have run at once.

That read -$71.04 against roughly -$16 of real opportunity and produced the
headline "gates cost $53.30" on a week when the gates themselves SAVED $17.74.

The live book allows one position per symbol. The scorecard now applies the same
rule. Reporting only — no order path reads this.
"""
import pytest

from futuresbot.shadow_ledger import dedupe_by_occupancy, gate_cost_usd


def _r(ts, symbol, outcome=3.0, reason="slot_occupied", resolved_ts=None, **kw):
    row = {"ts": ts, "symbol": symbol, "reject_reason": reason, "outcome": outcome,
           "side": "LONG", "entry": 100.0, "sl": 85.0, "tp": 145.0, "tp_r": 3.0,
           "sleeve": "WILDCARD", "sl_margin_pct": 18.0,
           "resolved_ts": ts + 3600 if resolved_ts is None else resolved_ts}
    row.update(kw)
    return row


def test_a_resignalling_move_counts_once():
    """The XRP case: five fires inside 70 minutes on one move."""
    rows = [_r(0, "XRP_USDT", resolved_ts=7200),
            _r(960, "XRP_USDT", resolved_ts=7200),
            _r(2160, "XRP_USDT", resolved_ts=7200),
            _r(4020, "XRP_USDT", resolved_ts=7200),
            _r(4200, "XRP_USDT", resolved_ts=7200)]
    kept = dedupe_by_occupancy(rows)
    assert len(kept) == 1
    assert kept[0]["ts"] == 0          # the one you would actually have taken


def test_a_genuinely_new_move_after_the_first_resolved_still_counts():
    rows = [_r(0, "XRP_USDT", resolved_ts=3600),
            _r(7200, "XRP_USDT", resolved_ts=10800)]
    assert len(dedupe_by_occupancy(rows)) == 2


def test_different_symbols_are_independent():
    rows = [_r(0, "BTC_USDT", resolved_ts=7200),
            _r(60, "ETH_USDT", resolved_ts=7200),
            _r(120, "XRP_USDT", resolved_ts=7200)]
    assert len(dedupe_by_occupancy(rows)) == 3


def test_different_reasons_are_independent():
    """A symbol blocked by two different gates is two separate facts."""
    rows = [_r(0, "BTC_USDT", resolved_ts=7200),
            _r(60, "BTC_USDT", reason="veto:ref_not_listed", resolved_ts=7200)]
    assert len(dedupe_by_occupancy(rows)) == 2


def test_reason_class_is_what_groups_not_the_full_string():
    """veto:crowded_shorts(funding=-0.24%) and veto:ref_not_listed are one class,
    matching how gate_cost_usd buckets them."""
    rows = [_r(0, "BTC_USDT", reason="veto:crowded_shorts(funding=-0.24%)", resolved_ts=7200),
            _r(60, "BTC_USDT", reason="veto:ref_not_listed", resolved_ts=7200)]
    assert len(dedupe_by_occupancy(rows)) == 1


def test_rows_without_a_resolution_are_kept():
    """Errs toward the old behaviour rather than silently discarding evidence."""
    rows = [_r(0, "XRP_USDT", resolved_ts=0), _r(60, "XRP_USDT", resolved_ts=0)]
    assert len(dedupe_by_occupancy(rows)) == 2


def test_unsorted_input_is_handled():
    rows = [_r(4200, "XRP_USDT", resolved_ts=7200), _r(0, "XRP_USDT", resolved_ts=7200)]
    kept = dedupe_by_occupancy(rows)
    assert len(kept) == 1 and kept[0]["ts"] == 0


def test_the_scorecard_stops_multiplying_one_move():
    """End to end: the same move five times must not cost five times as much."""
    one = gate_cost_usd([_r(0, "XRP_USDT", resolved_ts=7200)], 180.0)
    five = gate_cost_usd([_r(0, "XRP_USDT", resolved_ts=7200),
                          _r(960, "XRP_USDT", resolved_ts=7200),
                          _r(2160, "XRP_USDT", resolved_ts=7200),
                          _r(4020, "XRP_USDT", resolved_ts=7200),
                          _r(4200, "XRP_USDT", resolved_ts=7200)], 180.0)
    assert five == one
    assert five["slot_occupied"][0] == 1


def test_losers_are_not_deduped_away_either():
    """The dedupe must not quietly improve the number by dropping bad outcomes —
    the ETH pair in the live case were both -1R."""
    rows = [_r(0, "ETH_USDT", outcome=-1.0, resolved_ts=7200),
            _r(1800, "ETH_USDT", outcome=-1.0, resolved_ts=7200)]
    got = gate_cost_usd(rows, 180.0)
    assert got["slot_occupied"][0] == 1
    assert got["slot_occupied"][1] < 0      # still recorded as a saving
