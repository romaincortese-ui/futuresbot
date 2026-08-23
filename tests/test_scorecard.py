"""The pre-registered weekly scorecard.

Written before the week it grades. These pin the thresholds so a future reader
cannot quietly move one after seeing a number — which is the failure mode that
left twelve trials unscored.

The /report message itself is rendered end to end here too, because
tests/test_simulation.py taught the lesson the expensive way: a thoroughly tested
pure module behind an untested call site still ships broken.
"""
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from futuresbot.config import FuturesConfig
from futuresbot.runtime import FuturesRuntime
from futuresbot.scorecard import KPI, TARGET_RISK_PCT, build_scorecard, overall


def _row(r=0.5, peak=0.5, risk=1.87, ts=2000.0, **kw):
    row = {"ts": ts, "kind": "WILDCARD", "r_multiple": r, "peak_r": peak,
           "risk_pct_actual": risk, "pnl_usdt": r * 4.0,
           "equity_at_close_usdt": 180.0, "hold_hours": 3.0}
    row.update(kw)
    return row


def _by(kpis, name):
    return next(k for k in kpis if k.name == name)


# --- integrity gates everything -------------------------------------------

def test_a_missing_ledger_row_is_bad_and_dominates_the_summary():
    kpis = build_scorecard([_row()] * 5, days=5.0, exchange_closes=7)
    assert _by(kpis, "Ledger integrity").verdict == "Bad"
    assert "INVESTIGATE" in overall(kpis)


def test_matching_counts_are_good():
    kpis = build_scorecard([_row()] * 5, days=5.0, exchange_closes=5)
    assert _by(kpis, "Ledger integrity").verdict == "Good"


def test_no_exchange_data_is_NA_not_a_pass():
    kpis = build_scorecard([_row()] * 5, days=5.0, exchange_closes=None)
    assert _by(kpis, "Ledger integrity").verdict == "NA"


def test_a_backfilled_row_also_forces_investigate():
    kpis = build_scorecard([_row(), _row(reconstructed=1)], days=2.0, exchange_closes=2)
    assert _by(kpis, "Backfilled rows").verdict == "Bad"
    assert "INVESTIGATE" in overall(kpis)


# --- the trial's own criterion ---------------------------------------------

def test_risk_at_target_is_good():
    kpis = build_scorecard([_row(risk=1.87)] * 5, days=5.0)
    assert _by(kpis, "Risk per trade").verdict == "Good"


def test_risk_still_at_the_old_level_voids_the_trial():
    """1.46% was the pre-renormalisation level. Seeing it again means the change
    did not take, whatever the P&L says."""
    kpis = build_scorecard([_row(risk=1.46)] * 5, days=5.0)
    k = _by(kpis, "Risk per trade")
    assert k.verdict == "Bad" and "VOIDS" in k.note


def test_risk_needs_three_stamped_rows_before_grading():
    kpis = build_scorecard([_row(risk=0.0)] * 5, days=5.0)
    assert _by(kpis, "Risk per trade").verdict == "NA"


# --- tail losses: the capital question -------------------------------------

def test_a_loss_beyond_minus_two_R_is_bad_even_if_it_is_the_only_one():
    kpis = build_scorecard([_row(r=0.5)] * 9 + [_row(r=-2.4)], days=7.0)
    k = _by(kpis, "Tail losses")
    assert k.verdict == "Bad" and "gap through the stop" in k.note


def test_one_ordinary_stop_is_good():
    kpis = build_scorecard([_row(r=0.5)] * 9 + [_row(r=-1.02)], days=7.0)
    assert _by(kpis, "Tail losses").verdict == "Good"


def test_several_beyond_one_R_is_bad():
    kpis = build_scorecard([_row(r=-1.3)] * 3 + [_row()] * 5, days=7.0)
    assert _by(kpis, "Tail losses").verdict == "Bad"


# --- edge, coverage, and the one-lucky-trade guard -------------------------

def test_arm_rate_is_not_graded_on_a_small_sample():
    kpis = build_scorecard([_row(peak=0.1)] * 5, days=5.0)
    assert _by(kpis, "Reached +1R").verdict == "NA"


def test_a_low_arm_rate_on_enough_closes_is_bad():
    kpis = build_scorecard([_row(peak=0.1)] * 10, days=7.0)
    assert _by(kpis, "Reached +1R").verdict == "Bad"


def test_a_healthy_arm_rate_is_good():
    kpis = build_scorecard([_row(peak=1.5)] * 3 + [_row(peak=0.2)] * 7, days=7.0)
    assert _by(kpis, "Reached +1R").verdict == "Good"      # 30%


def test_another_surge_week_is_bad_coverage():
    """The point of the week is evidence outside surge."""
    kpis = build_scorecard([_row()] * 8, days=7.0, btc_move_of=lambda ts: 0.22)
    k = _by(kpis, "Regime coverage")
    assert k.verdict == "Bad" and "teaches nothing new" in k.note


def test_flat_or_down_closes_are_good_coverage():
    kpis = build_scorecard([_row()] * 8, days=7.0, btc_move_of=lambda ts: 0.01)
    assert _by(kpis, "Regime coverage").verdict == "Good"


def test_a_week_carried_by_one_trade_fails_ex_best():
    kpis = build_scorecard([_row(r=6.0)] + [_row(r=-1.0)] * 4, days=7.0)
    assert _by(kpis, "netR ex-best").verdict == "Bad"


def test_a_broadly_positive_week_passes_ex_best():
    kpis = build_scorecard([_row(r=2.0)] + [_row(r=0.4)] * 4, days=7.0)
    assert _by(kpis, "netR ex-best").verdict == "Good"


def test_the_ratchet_is_never_graded():
    """5% of trades reach 3R — far too rare to judge on a week."""
    for rows in ([_row(peak=5.0)] * 3, [_row(peak=0.1)] * 10):
        assert _by(build_scorecard(rows, days=7.0), "Ratchet firings").verdict == "NA"


def test_a_dead_week_is_flagged_but_a_quiet_one_is_not():
    assert _by(build_scorecard([_row()] * 2, days=7.0), "Closes").verdict == "Bad"
    assert _by(build_scorecard([_row()] * 8, days=7.0), "Closes").verdict == "Good"


def test_overall_is_too_early_when_nothing_can_be_judged():
    assert "TOO EARLY" in overall(build_scorecard([], days=0.5, exchange_closes=None))


# --- the message must render ----------------------------------------------

def test_report_message_renders(tmp_path, monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    import futuresbot.learning_digest as ld
    monkeypatch.setattr(ld, "TRIAL_START", 1000.0)
    monkeypatch.setattr(ld, "TRIAL_LABEL", "16")
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "rt.json"),
                  status_file=str(tmp_path / "st.json"),
                  telegram_token="", telegram_chat_id="")
    rt = object.__new__(FuturesRuntime)
    rt.config = cfg
    monkeypatch.setattr(rt, "_last_known_equity", lambda: 178.0)
    monkeypatch.setattr(rt, "_feature_rows_cached",
                        lambda *a, **k: [_row(ts=2000.0), _row(r=-1.0, ts=3000.0)])

    class _C:
        def private_get(self, path, params=None):
            return {"data": {"resultList": []}}

        def get_klines(self, *a, **k):
            raise RuntimeError("no market data")
    rt.client = _C()
    msg = rt._build_report_message()
    assert "Report" in msg and "Trial 16" in msg
    assert "Ledger integrity" in msg and "Risk per trade" in msg
    # the lesson /pnl taught must be stated where the reader will see it
    assert "verdict" in msg.lower()


def test_report_survives_a_total_exchange_outage(tmp_path, monkeypatch):
    """A Telegram command must render even when nothing upstream answers."""
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    import futuresbot.learning_digest as ld
    monkeypatch.setattr(ld, "TRIAL_START", 1000.0)
    monkeypatch.setattr(ld, "TRIAL_LABEL", "16")
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "rt.json"),
                  status_file=str(tmp_path / "st.json"),
                  telegram_token="", telegram_chat_id="")
    rt = object.__new__(FuturesRuntime)
    rt.config = cfg
    monkeypatch.setattr(rt, "_last_known_equity", lambda: 178.0)
    monkeypatch.setattr(rt, "_feature_rows_cached", lambda *a, **k: [])

    class _Dead:
        def private_get(self, *a, **k):
            raise RuntimeError("down")

        def get_klines(self, *a, **k):
            raise RuntimeError("down")
    rt.client = _Dead()
    assert "Report" in rt._build_report_message()
