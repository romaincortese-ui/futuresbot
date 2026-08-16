"""Pricing the gates in dollars (2026-08-16, owner request).

The shadow ledger has always scored blocked candidates in R. R is right for a
verdict and wrong for "is this gate worth keeping", which is asked in money —
and 1R is not a constant, so an R-only scorecard hides that a -1R block on a
20%-stop candidate costs twice a -1R block on a 9%-stop one.

The number is easy to misuse, so the tests that matter most here are the ones
pinning what it must NOT do: inflate one move into many trades, or report gross
upside instead of net outcome.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from futuresbot import shadow_ledger as shadow
from futuresbot.config import FuturesConfig
from futuresbot.runtime import FuturesRuntime


@pytest.fixture
def rt(tmp_path, monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    monkeypatch.setenv("FUTURES_SHADOW_LEDGER_FILE", str(tmp_path / "shadow.jsonl"))
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "rt.json"),
                  status_file=str(tmp_path / "st.json"),
                  telegram_token="", telegram_chat_id="")
    return FuturesRuntime(cfg, MagicMock())


def _row(**over):
    row = {"ts": 1000.0, "symbol": "FOO_USDT", "side": "LONG", "sleeve": "WILDCARD",
           "reject_reason": "slot_occupied", "entry": 100.0, "sl": 90.0, "tp": 150.0,
           "leverage": 1, "sl_margin_pct": 20.0, "tp_r": 5.0, "outcome": None}
    row.update(over)
    return row


# --------------------------------------------------------------------------
# R -> $
# --------------------------------------------------------------------------

def test_one_r_scales_with_the_stop_not_just_the_balance():
    """The whole reason for pricing in dollars: two -1R blocks are not the same
    loss when their stops differ."""
    wide = shadow.one_r_usd(_row(sl_margin_pct=20.0), 100.0, 0.12)
    tight = shadow.one_r_usd(_row(sl_margin_pct=9.0), 100.0, 0.12)
    assert wide == pytest.approx(2.40)      # 100 x 0.12 x 20%
    assert tight == pytest.approx(1.08)
    assert wide > 2 * tight


def test_unresolved_rows_are_not_worth_zero():
    """A signal still in flight has no P&L. Calling it $0 would drag every
    average toward nothing and understate the gates both ways."""
    assert shadow.net_usd(_row(), 100.0) is None


def test_net_usd_uses_the_cost_inclusive_outcome():
    row = _row(outcome=5.0, outcome_net=4.8)
    assert shadow.net_usd(row, 100.0, 0.12) == pytest.approx(4.8 * 2.40)


def test_net_usd_falls_back_to_outcome_minus_cost_for_older_rows():
    row = _row(outcome=-1.0)          # written before outcome_net existed
    got = shadow.net_usd(row, 100.0, 0.12)
    assert got == pytest.approx((-1.0 - shadow.cost_r(row)) * 2.40)
    assert got < -2.40, "cost must make a stop-out worse, never better"


def test_gate_cost_buckets_by_reason_class_not_by_funding_rate():
    """`veto:crowded_longs(funding=0.104%)` and `veto:ref_not_listed` are one
    question. Keyed raw, the scorecard fragments into a bucket per rate."""
    rows = [_row(reject_reason="veto:crowded_longs(funding=0.104%)", outcome=-1.0, outcome_net=-1.02),
            _row(reject_reason="veto:ref_not_listed", outcome=-1.0, outcome_net=-1.02),
            _row(reject_reason="slot_occupied", outcome=5.0, outcome_net=4.9)]
    by = shadow.gate_cost_usd(rows, 100.0, balance_fraction=0.12)
    assert set(by) == {"veto", "slot_occupied"}
    assert by["veto"][0] == 2 and by["veto"][1] < 0
    assert by["slot_occupied"][0] == 1 and by["slot_occupied"][1] > 0


def test_gate_cost_respects_the_window():
    rows = [_row(ts=100.0, outcome=5.0, outcome_net=5.0),
            _row(ts=9_000.0, outcome=-1.0, outcome_net=-1.0)]
    by = shadow.gate_cost_usd(rows, 100.0, since_ts=5_000.0, balance_fraction=0.12)
    assert by["slot_occupied"][0] == 1 and by["slot_occupied"][1] < 0


# --------------------------------------------------------------------------
# The replay: what the detector WOULD have done
# --------------------------------------------------------------------------

def _bars(closes):
    """Bars ending NOW, like a live frame — so the 24h resolution horizon means
    what it means in production instead of every row timing out on age."""
    end = datetime.now(timezone.utc)
    idx = pd.date_range(end - timedelta(minutes=15 * (len(closes) - 1)),
                        periods=len(closes), freq="15min")
    return pd.DataFrame({"open": closes, "high": [c * 1.001 for c in closes],
                         "low": [c * 0.999 for c in closes], "close": closes,
                         "volume": [1000.0] * len(closes)}, index=idx)


def _always_signal(monkeypatch, *, side="LONG"):
    """Detector that fires on EVERY bar — the adversarial case for counting.

    Entry tracks the bar it fires on, as a real signal does; a fixed entry would
    make every trigger after the first an instant stop-out and flatter the
    de-duplication under test."""
    from futuresbot import wildcard as W

    def _fire(frame, symbol, reasons=None):
        px = float(frame["close"].iloc[-1])
        s = 1.0 if side == "LONG" else -1.0
        return MagicMock(symbol=symbol, side=side, entry_price=px,
                         sl_price=px * (1 - 0.10 * s), tp_price=px * (1 + 0.50 * s),
                         leverage=1, sl_margin_pct=20.0, roc_pct=0.20 * s, rsi=60.0)

    monkeypatch.setattr(W, "detect_wildcard_signal", _fire)


def test_replay_counts_one_trade_per_move_not_one_per_bar(rt, monkeypatch):
    """The detector fires on many adjacent bars of the same run. The bot can
    only hold one position per symbol, so a 40% move that triggers on a dozen
    consecutive bars is ONE trade — counting each trigger turns the missed
    figure into a multiple of anything reachable."""
    _always_signal(monkeypatch)
    closes = [100.0] * 200 + [100.0 - i * 0.2 for i in range(1, 101)]   # slides to the stop
    n, usd = rt._counterfactual_usd("FOO_USDT", _bars(closes), min_roc=0.0,
                                    bars_back=100, equity=100.0)
    assert 0 < n <= 8, f"100 triggers on one move became {n} trades"
    assert usd < 0, "a slide into the stop is a loss, not a missed gain"


def test_replay_prices_a_reversal_as_money_the_gate_SAVED(rt, monkeypatch):
    """The number must be able to come out negative. If blocked candidates only
    ever read positive, it is a hindsight ranking, not a measurement."""
    _always_signal(monkeypatch)
    closes = [100.0] * 200 + [80.0] * 60          # instant gap through the stop
    n, usd = rt._counterfactual_usd("FOO_USDT", _bars(closes), min_roc=0.0,
                                    bars_back=60, equity=100.0)
    assert n >= 1 and usd < 0
    assert rt._usd_tag(n, usd).startswith(" · <b>saved")


def test_replay_prices_a_runner_as_money_the_gate_COST(rt, monkeypatch):
    _always_signal(monkeypatch)
    closes = [100.0] * 200 + [200.0] * 60         # straight through the +5R target
    n, usd = rt._counterfactual_usd("FOO_USDT", _bars(closes), min_roc=0.0,
                                    bars_back=60, equity=100.0)
    assert n >= 1 and usd > 0
    assert "missed" in rt._usd_tag(n, usd)


def test_replay_ignores_a_signal_still_in_flight(rt, monkeypatch):
    """An unresolved signal has no P&L yet. Booking it now would let a symbol
    mid-move be reported as a miss it may never become."""
    _always_signal(monkeypatch)
    closes = [100.0] * 200 + [100.5] * 2          # nothing reaches stop or target
    n, usd = rt._counterfactual_usd("FOO_USDT", _bars(closes), min_roc=0.0,
                                    bars_back=3, equity=100.0)
    assert (n, usd) == (0, 0.0)


def test_replay_is_silent_on_a_symbol_that_never_triggers(rt, monkeypatch):
    from futuresbot import wildcard as W

    monkeypatch.setattr(W, "detect_wildcard_signal", lambda *a, **k: None)
    n, usd = rt._counterfactual_usd("FOO_USDT", _bars([100.0] * 300), min_roc=0.0,
                                    bars_back=96, equity=100.0)
    assert (n, usd) == (0, 0.0)


def test_replay_survives_a_frame_it_cannot_read(rt):
    assert rt._counterfactual_usd("FOO_USDT", None, min_roc=0.08,
                                  bars_back=96, equity=100.0) == (0, 0.0)


# --------------------------------------------------------------------------
# Surfaces
# --------------------------------------------------------------------------

def test_usd_tag_stays_silent_on_noise(rt):
    assert rt._usd_tag(3, 0.04) == "", "a four-cent counterfactual is not a finding"
    assert rt._usd_tag(0, 99.0) == "", "no signal means no claim"


def test_gate_cost_line_excludes_shadow_only(rt, tmp_path, monkeypatch):
    """`shadow_only` rows are the sleeve observing, not a gate refusing. Folding
    them in prices a decision nobody made."""
    import json
    import time

    path = tmp_path / "shadow.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        # Distinct geometry: load_rows collapses same-signal duplicates written
        # within 90s, which would otherwise silently drop the second row here.
        for r in (_row(ts=time.time(), reject_reason="shadow_only",
                       outcome=5.0, outcome_net=5.0),
                  _row(ts=time.time(), symbol="BAR_USDT", entry=50.0, sl=45.0,
                       reject_reason="slot_occupied", outcome=-1.0, outcome_net=-1.05)):
            fh.write(json.dumps(r) + "\n")
    monkeypatch.setattr(rt, "_last_known_equity", lambda: 100.0)
    text = "\n".join(rt._gate_cost_lines(days=7))
    assert "no free slot" in text
    assert "shadow" not in text.lower(), "observation rows must not be priced as a gate"
    assert "saved" in text, "the one real row is a loss avoided"


def test_gate_cost_line_says_so_when_there_is_nothing_to_score(rt):
    assert "nothing blocked and resolved yet" in "\n".join(rt._gate_cost_lines(days=7))


# --------------------------------------------------------------------------
# The weekly record
# --------------------------------------------------------------------------

def test_weekly_record_is_persisted_for_the_trend(rt, tmp_path, monkeypatch):
    """One figure cannot answer "is this gate drifting from protective to
    expensive". The series has to exist on disk to be read later."""
    import json
    import time

    with (tmp_path / "shadow.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_row(ts=time.time(), reject_reason="veto:ref_not_listed",
                                 outcome=-1.0, outcome_net=-1.05)) + "\n")
    monkeypatch.setattr(rt, "_last_known_equity", lambda: 100.0)
    monkeypatch.setattr(rt, "_gate_cost_history_path", lambda: tmp_path / "hist.jsonl")

    first = "\n".join(rt._record_gate_cost(7.0))
    assert "saved" in first and "external gate" in first
    assert "previous window" not in first, "nothing to compare against on run one"

    second = "\n".join(rt._record_gate_cost(7.0))
    assert "previous window" in second, "run two must compare against run one"

    rows = [json.loads(x) for x in (tmp_path / "hist.jsonl").read_text().splitlines() if x.strip()]
    assert len(rows) == 2
    assert rows[0]["resolved"] == 1 and rows[0]["net_usd"] < 0
    assert rows[0]["by_gate"]["veto"]["n"] == 1
    assert rows[0]["equity_usdt"] == 100.0, "the denominator must travel with the figure"


def test_weekly_record_states_what_the_number_is(rt, tmp_path, monkeypatch):
    """Unlabelled, this reads as 'upside we left on the table' and argues for
    deleting every gate in the stack."""
    import json
    import time

    with (tmp_path / "shadow.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_row(ts=time.time(), outcome=5.0, outcome_net=4.9)) + "\n")
    monkeypatch.setattr(rt, "_last_known_equity", lambda: 100.0)
    monkeypatch.setattr(rt, "_gate_cost_history_path", lambda: tmp_path / "hist.jsonl")
    text = "\n".join(rt._record_gate_cost(7.0))
    assert "would have fired" in text and "Negative = the gate paid for itself" in text


def test_digest_reports_gate_cost_even_when_the_forensic_walk_is_skipped(rt, monkeypatch):
    """The walk costs ~35s of klines and is skipped whenever a position is open.
    The gate scorecard is a file read, so it must survive that skip."""
    import inspect

    src = inspect.getsource(FuturesRuntime._maybe_send_learning_digest)
    assert "_record_gate_cost" in src
    walk = src.index("_missed_opportunity_lines")
    assert src.index("_record_gate_cost") > walk, "must sit after, and outside, the walk's else-branch"
    assert "missed = (missed or []) + " in src


def test_gate_parts_never_leave_the_sign_to_be_interpreted(rt):
    """"external gate -9.76" reads as a loss and means the opposite."""
    assert rt._gate_part("veto", -9.76) == "external gate saved $9.76"
    assert rt._gate_part("slot_occupied", 16.29, 17) == "no free slot cost $16.29 (n=17)"


# --------------------------------------------------------------------------
# Funding (2026-08-16)
# --------------------------------------------------------------------------

ACE = {"ts": 1786785218, "resolved_ts": 1786871618, "side": "SHORT", "symbol": "ACE_USDT",
       "sleeve": "WILDCARD", "entry": 0.20039, "sl": 0.240468, "tp": 0.100195,
       "leverage": 1, "sl_margin_pct": 20.0, "tp_r": 2.5, "outcome": 1.443,
       "outcome_net": 1.433, "outcome_kind": "timeout",
       "reject_reason": "veto:crowded_shorts(funding=-2.000%)"}
# The six settlements ACE actually crossed, off MEXC's funding history.
ACE_SETTLED = [(1786795200, -0.016517), (1786809600, -0.013514), (1786824000, -0.010258),
               (1786838400, -0.006825), (1786852800, -0.006324), (1786867200, -0.011849)]


def test_funding_is_charged_from_the_rates_that_actually_settled():
    """ACE was vetoed at a quoted -2.000% and settled between -0.63% and -1.65%
    across six 4-hourly payments. Scoring it on the veto-instant rate is a
    different number that only looked right by cancelling two errors."""
    f = shadow.funding_cost_r(ACE, ACE_SETTLED)
    assert f == pytest.approx(0.326, abs=0.005)      # 6.53% of notional / 20% stop
    assert shadow.net_r(ACE, f) == pytest.approx(1.107, abs=0.005)
    assert shadow.net_r(ACE) == pytest.approx(1.433), "no funding supplied = unchanged"


def test_a_short_paying_funding_is_worse_off_not_better():
    assert shadow.funding_cost_r(ACE, ACE_SETTLED) > 0


def test_a_short_collecting_funding_is_credited():
    """One-sided funding would just bias the measurement the other way."""
    positive = [(t, +r * -1) for t, r in ACE_SETTLED]      # flip the sign
    assert shadow.funding_cost_r(ACE, positive) < 0


def test_longs_pay_when_funding_is_positive():
    long_row = {**ACE, "side": "LONG", "sl": 0.16031}      # 20% stop the other way
    pos = [(t, 0.01) for t, _r in ACE_SETTLED]
    assert shadow.funding_cost_r(long_row, pos) > 0
    assert shadow.funding_cost_r(long_row, ACE_SETTLED) < 0


def test_a_hold_that_crosses_no_settlement_pays_nothing():
    """Most stop-outs resolve in ~2h. A pro-rata model would charge them a
    fraction of a payment that was never made."""
    quick = {**ACE, "ts": 1786795300, "resolved_ts": 1786802000}   # between settlements
    assert shadow.funding_cost_r(quick, ACE_SETTLED) == 0.0


def test_funding_falls_back_to_the_rows_own_rate_without_history():
    """Fallback must still bite — silently returning 0 would restore the bug."""
    assert shadow.funding_cost_r(ACE, None, cycle_hours=8.0) == pytest.approx(0.30, abs=0.01)
    assert shadow.funding_cost_r(ACE, None, cycle_hours=4.0) == pytest.approx(0.60, abs=0.01)


def test_funding_is_zero_when_the_row_has_no_rate_at_all():
    bare = {k: v for k, v in ACE.items() if k != "reject_reason"}
    assert shadow.funding_cost_r(bare, None) == 0.0


def test_gate_cost_prices_funding_when_given_a_lookup():
    """The whole point: the crowded-shorts scorecard must not read the veto as
    more expensive than it was."""
    without = shadow.gate_cost_usd([ACE], 140.76, balance_fraction=0.12)
    with_f = shadow.gate_cost_usd([ACE], 140.76, balance_fraction=0.12,
                                  funding_r_of=lambda r: shadow.funding_cost_r(r, ACE_SETTLED))
    assert without["veto"][1] > with_f["veto"][1]
    assert with_f["veto"][1] == pytest.approx(1.107 * 140.76 * 0.12 * 0.20, abs=0.05)


def test_digest_and_dollar_scorecards_share_one_definition_of_net():
    """They drifted once, when funding was priced in one and not the other."""
    from futuresbot import learning_digest as ld

    assert ld._net(ACE, 0.326) == pytest.approx(shadow.net_r(ACE, 0.326))


def test_funding_obeys_the_rows_own_horizon_not_its_resolved_ts():
    """XAUT_USDT carries resolved_ts 364.6h after ts under a 24h convex policy.
    Charging fifteen days of settlements against its 0.054% stop produced a
    2.29R funding bill on a row whose whole counterfactual is -0.74R. A position
    cannot pay funding after the horizon that closed it — the same clock
    resolve_outcome already enforces on the bar walk."""
    day = 86400
    row = {"ts": 1_000_000, "resolved_ts": 1_000_000 + 15 * day, "side": "LONG",
           "sleeve": "WILDCARD", "entry": 4054.3, "sl": 4052.121428571429,
           "outcome": 2.8, "outcome_net": -0.736}
    settled = [(1_000_000 + h * 3600, 5e-05) for h in range(4, 15 * 24, 4)]
    bounded = shadow.funding_cost_r(row, settled)
    unbounded = shadow.funding_cost_r(row, settled, horizon_s=15 * day)
    assert unbounded > 2.0, "guard the guard: unclamped really is that large"
    assert bounded < 0.7, f"clamped to 24h, got {bounded}"
    assert bounded == pytest.approx(6 * 5e-05 / (2.178571428571 / 4054.3), rel=0.02)


def test_sniper_rows_keep_the_bracket_horizon():
    """CONVEX_SLEEVES is the 24h clock; anything else is the plain bracket."""
    t0 = 1_000_000
    row = {"ts": t0, "resolved_ts": t0 + 10 * 86400, "side": "SHORT", "sleeve": "SNIPER",
           "entry": 100.0, "sl": 110.0, "outcome": -1.0}
    settled = [(t0 + h * 3600, -0.001) for h in range(8, 10 * 24, 8)]
    assert shadow.funding_cost_r(row, settled) > shadow.funding_cost_r(
        {**row, "sleeve": "WILDCARD"}, settled)
