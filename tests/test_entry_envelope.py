"""FUTURES_ENTRY_ENVELOPE_ENABLED - the restricted entry area from the 84-trade study.

Owner request 2026-09-29: take only trades whose gate values sit where the study's
winners sat. The area is in-sample only; out of sample stop-losses land inside it about
as often as winners (wc/ENVELOPE/measure). These tests pin the mechanics:
  - each cell's box, inclusive at its bounds, refusing on a missing value;
  - switch off = today's decisions, input for input;
  - switch on = refuse after every other gate and before any order (and before a
    WILDCARD preemption), shadow-logged as "envelope";
  - the verdict and box values stamped on every shadow row and fill, switch on or off.
"""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

import futuresbot.runtime as R
from futuresbot import entry_envelope as E
from futuresbot import shadow_ledger
from futuresbot.config import FuturesConfig
from futuresbot.runtime import ENTRY_GATE_KEYS, FuturesRuntime
from futuresbot.wildcard import WildcardSignal

# BTC/ETH/SOL returns that sit inside every majors bound (calm score 0.6 >= 0.5165,
# ETH 12h 1% in [-0.42%, +2.96%], ETH 24h 2% <= 5.11%, SOL 72h 0% >= -2.89%).
MAJ = {"btc_12h": 0.004, "btc_24h": 0.01, "btc_72h": 0.02,
       "eth_12h": 0.01, "eth_24h": 0.02, "eth_72h": 0.03,
       "sol_12h": 0.002, "sol_24h": 0.005, "sol_72h": 0.0, "calm_score": 0.6}

# A value inside every bound of each cell; open bounds get an ordinary value.
CENTRE = {
    "TREND LONG": {"new_high_margin_pct": 0.3, "bot_eth_12h": 0.01, "bot_eth_24h": 0.02,
                   "bot_calm_score": 0.8},
    "WILDCARD LONG": {"roc3h_abs": 0.12, "rsi14": 70.0, "atr_pct": 0.03, "bot_sol_72h": 0.0},
    "WILDCARD SHORT": {"rsi14": 40.0, "range_24h": 0.5},
}


def _sig(symbol="A_USDT", side="LONG", *, roc=0.12, rsi=70.0, atr=0.03, entry=1.0, **kw):
    return WildcardSignal(symbol=symbol, side=side, entry_price=entry, leverage=5, roc_pct=roc,
                          atr_pct=atr, sl_price=entry * (0.9 if side == "LONG" else 1.1),
                          tp_price=entry * (1.5 if side == "LONG" else 0.5),
                          sl_margin_pct=50.0, tp_margin_pct=250.0, balance_fraction=0.01,
                          rsi=rsi, **kw)


# --- the frozen spec ------------------------------------------------------------------

def test_the_shipped_spec_is_the_study_area():
    """The three cells and every bound of wc/ENVELOPE/envelope/envelope.json, frozen."""
    spec = E.load_spec()
    boxes = {cell: {b["var"]: (b["lo"], b["hi"]) for b in spec[cell]}
             for cell in ("TREND LONG", "WILDCARD LONG", "WILDCARD SHORT")}
    assert boxes["TREND LONG"] == {
        "new_high_margin_pct": (0.04635, 0.67025), "bot_eth_12h": (-0.0042, pytest.approx(0.029645)),
        "bot_eth_24h": (None, 0.05108), "bot_calm_score": (0.5165, None)}
    assert boxes["WILDCARD LONG"] == {
        "roc3h_abs": (pytest.approx(0.0879815), None), "rsi14": (None, 84.35),
        "atr_pct": (None, 0.055592), "bot_sol_72h": (pytest.approx(-0.028875), None)}
    assert boxes["WILDCARD SHORT"] == {
        "rsi14": (25.0, None), "range_24h": (0.29967, pytest.approx(0.7714667468435135))}
    assert "IN-SAMPLE ONLY" in spec["_meta"]["status"]
    used = {b["var"] for cell in boxes for b in spec[cell]}
    assert used <= set(E.VARS)                      # every variable is computable


def test_the_switch_defaults_off(monkeypatch):
    monkeypatch.delenv("FUTURES_ENTRY_ENVELOPE_ENABLED", raising=False)
    assert not E.enabled()
    for off in ("", "  ", "0", "false", "no"):
        monkeypatch.setenv("FUTURES_ENTRY_ENVELOPE_ENABLED", off)
        assert not E.enabled()
    monkeypatch.setenv("FUTURES_ENTRY_ENVELOPE_ENABLED", "1")
    assert E.enabled()


# --- each cell at its bounds -----------------------------------------------------------

def _bound_cases():
    for cell, boxes in ((c, E.load_spec()[c]) for c in CENTRE):
        for b in boxes:
            for edge in ("lo", "hi"):
                if b[edge] is not None:
                    yield cell, b["var"], edge, b[edge]


@pytest.mark.parametrize("cell,var,edge,bound", list(_bound_cases()))
def test_a_value_on_the_bound_is_inside_and_just_beyond_is_out(cell, var, edge, bound):
    vals = dict(CENTRE[cell])
    assert E.evaluate(cell, vals) == (True, "inside")
    vals[var] = bound
    assert E.evaluate(cell, vals) == (True, "inside")          # inclusive
    step = max(abs(bound) * 1e-9, 1e-12)
    vals[var] = bound - step if edge == "lo" else bound + step
    ok, reason = E.evaluate(cell, vals)
    assert not ok and reason.startswith(var + ("<" if edge == "lo" else ">"))


def test_every_failure_is_named():
    ok, reason = E.evaluate("WILDCARD LONG", {**CENTRE["WILDCARD LONG"], "rsi14": 88.0,
                                              "bot_sol_72h": -0.05})
    assert not ok and reason == "rsi14>84.35;bot_sol_72h<-0.028875"


def test_a_cell_without_a_box_is_refused():
    assert E.evaluate("TREND SHORT", {"new_high_margin_pct": 0.3}) == (False, "no_box")
    assert E.evaluate("WILDCARD LONG", CENTRE["WILDCARD LONG"], spec={}) == (False, "no_box")


# --- missing values --------------------------------------------------------------------

@pytest.mark.parametrize("cell,var", [(c, v) for c in CENTRE for v in CENTRE[c]])
@pytest.mark.parametrize("bad", [None, float("nan"), "n/a"])
def test_a_missing_box_value_refuses(cell, var, bad):
    vals = {**CENTRE[cell], var: bad}
    assert E.evaluate(cell, vals) == (False, "missing:" + var)
    vals.pop(var)
    assert E.evaluate(cell, vals) == (False, "missing:" + var)


def test_calm_score_counts_only_with_all_nine_majors():
    """_majors_state computes the score from whichever majors returned, so a partial
    fetch would understate it. Missing unless all nine returns are present."""
    sig = _sig("ETH_USDT", roc=0.05, prior_close_extreme=100.0, gate_close=100.3, entry=100.3)
    assert E.candidate_values(sig, "TREND", majors=MAJ)["bot_calm_score"] == 0.6
    partial = {k: v for k, v in MAJ.items() if k != "btc_72h"}
    vals = E.candidate_values(sig, "TREND", majors=partial)
    assert vals["bot_calm_score"] is None and vals["bot_eth_12h"] == 0.01
    assert E.evaluate("TREND LONG", vals) == (False, "missing:bot_calm_score")


def test_unreadable_inputs_are_missing_not_zero():
    short = _sig(side="SHORT", roc=-0.12, rsi=40.0)
    assert E.candidate_values(short, "WILDCARD", range_24h=0.0)["range_24h"] is None
    assert E.candidate_values(short, "WILDCARD", range_24h=None)["range_24h"] is None
    assert E.candidate_values(_sig(atr=None), "WILDCARD", majors=MAJ)["atr_pct"] is None
    trend = _sig("ETH_USDT", roc=0.05, prior_close_extreme=None, entry=100.3)
    assert E.candidate_values(trend, "TREND", majors=MAJ)["new_high_margin_pct"] is None


# --- the bot's own values -----------------------------------------------------------------

def test_values_are_the_bots_own_gate_values():
    long_ = E.candidate_values(_sig(roc=0.0912, rsi=71.3, atr=0.041), "WILDCARD",
                               range_24h=0.42, majors=MAJ)
    assert long_["roc3h_abs"] == 0.0912 and long_["rsi14"] == 71.3 and long_["atr_pct"] == 0.041
    assert long_["range_24h"] == 0.42 and long_["bot_sol_72h"] == 0.0
    assert E.candidate_values(_sig(side="SHORT", roc=-0.0912), "WILDCARD")["roc3h_abs"] == 0.0912
    # TREND margin = the gate close over the prior 24h closing high, as stamped in
    # trend_extreme_margin_pct - NOT the tick the order is priced at.
    trend = _sig("ETH_USDT", roc=0.05, prior_close_extreme=100.0, gate_close=100.3, entry=101.0)
    assert E.candidate_values(trend, "TREND", majors=MAJ)["new_high_margin_pct"] == \
        pytest.approx(0.3)
    assert E.candidate_values(trend, "TREND")["rsi14"] is None     # TREND RSI is not the box's


def test_verdict_stamps_the_cell_and_only_its_box_values(monkeypatch):
    monkeypatch.delenv("FUTURES_ENTRY_ENVELOPE_ENABLED", raising=False)
    v = E.verdict(_sig(side="SHORT", roc=-0.12, rsi=40.0), "WILDCARD", range_24h=0.5,
                  majors=MAJ, majors_age_s=12.34)
    assert v == {"envelope_pass": 1.0, "envelope_cell": "WILDCARD SHORT",
                 "envelope_reason": "inside", "envelope_enabled": 0.0,
                 "envelope_rsi14": 40.0, "envelope_range_24h": 0.5,
                 "envelope_majors_age_s": 12.3}
    assert set(v) <= set(E.STAMP_KEYS)
    assert E.verdict(_sig(), "SQUEEZE") is None and E.verdict(_sig(), "SNIPER") is None


# --- the WILDCARD scan ---------------------------------------------------------------------

def _clean_env(monkeypatch, flag, **env):
    for k in [k for k in os.environ if k.startswith(
            ("FUTURES_WILDCARD_", "FUTURES_EXTERNAL_GATE", "FUTURES_ENTRY_ENVELOPE", "FUTURES_TREND_"))]:
        monkeypatch.delenv(k, raising=False)
    base = {"FUTURES_WILDCARD_ENABLED": "1", "FUTURES_WILDCARD_MAX_CALM_RATIO": "0",
            "FUTURES_WILDCARD_LONG_ONLY": "0", "FUTURES_EXTERNAL_GATE_ENABLED": "0",
            "FUTURES_TREND_ENABLED": "1", "FUTURES_TREND_LONG_ONLY": "1",
            "MEXC_API_KEY": "k", "MEXC_API_SECRET": "s"}
    if flag is not None:
        base["FUTURES_ENTRY_ENVELOPE_ENABLED"] = flag
    base.update(env)
    for k, v in base.items():
        monkeypatch.setenv(k, v)


def _runtime(tmp_path, majors):
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "rt.json"),
                  status_file=str(tmp_path / "st.json"), telegram_token="", telegram_chat_id="")
    rt = FuturesRuntime(cfg, MagicMock())
    rt._majors_sample = lambda max_age_s=None: (time.time() - 5.0, dict(majors))
    rt._shadow_ledger_path = lambda: str(tmp_path / "shadow.jsonl")
    rt._account_snapshot = lambda *a, **k: {"available_usdt": 1000.0}
    rt._get_reference_price = lambda *a, **k: 1.0
    return rt


FRAME = pd.DataFrame({"open": [1.0] * 700, "high": [1.0] * 700, "low": [1.0] * 700,
                      "close": [1.0] * 700, "volume": [1e3] * 700})


def _wc_scan(tmp_path, monkeypatch, sigs, *, flag, ranges=None, majors=MAJ, full=False,
             no_envelope=False, **env):
    """One _maybe_scan_wildcard over prebuilt signals. Returns what was opened (with the
    envelope decision handed to the fill), the shadow rows, and the preemptions."""
    _clean_env(monkeypatch, flag, **env)
    monkeypatch.setattr(R, "detect_wildcard_signal",
                        lambda frame, sym, reasons=None, min_roc=None: sigs.get(sym))
    rt = _runtime(tmp_path, majors)
    ranges = ranges or {}
    rt.client.get_all_tickers.return_value = [
        {"symbol": s, "amount24": 9e6, "riseFallRate": 0.05,
         "high24Price": 100.0 * (1 + ranges.get(s, 0.5)), "lower24Price": 100.0} for s in sigs]
    rt.client.get_klines.side_effect = lambda sym, **kw: FRAME
    for name in ("_refresh_non_crypto_universe", "_maybe_capture_news"):
        setattr(rt, name, lambda: None)
    rt._is_tradeable_crypto = lambda sym: True
    rt._major_symbols = lambda tickers, n: set()
    rt._alt_breadth = lambda *a, **k: None
    rt._record_ticker_snapshot = lambda movers: None
    rt._convex_open_count = lambda *a, **k: 3 if full else 0
    rt._preemption_possible = lambda: full
    preempted: list[str] = []
    rt._try_preempt_for = lambda sig: preempted.append(sig.symbol) or 1000.0
    opened: list[tuple] = []
    rt._open_wildcard_position = lambda sig, avail, **kw: opened.append(
        (sig.symbol, sig.side, tuple(sorted(kw.items())), rt._pending_envelope)) or True
    if no_envelope:     # the code as it was before this change
        rt._envelope_refuses = lambda sig, kind: False
        rt._envelope_verdict = lambda sig, kind: None
    rt._last_wildcard_scan_at = 0.0
    rt._maybe_scan_wildcard()
    rows = shadow_ledger.load_raw(str(tmp_path / "shadow.jsonl"))
    return rt, opened, rows, preempted


# Ranked by |roc|: A (outside, RSI 88) > B (SHORT outside, range 0.20) > C (inside).
MIXED = {"A_USDT": _sig("A_USDT", roc=0.20, rsi=88.0),
         "B_USDT": _sig("B_USDT", side="SHORT", roc=-0.15, rsi=40.0),
         "C_USDT": _sig("C_USDT", roc=0.12, rsi=70.0)}
MIXED_RANGES = {"B_USDT": 0.20}


def _decisions(opened, rows, rt):
    scan = {k: v for k, v in rt._last_wildcard_scan.items() if k != "at"}
    return ([o[:3] for o in opened],
            [(r["symbol"], r["side"], r["reject_reason"]) for r in rows], scan)


@pytest.mark.parametrize("flag", [None, "", "0", "false"])
def test_switch_off_makes_todays_decisions(tmp_path, monkeypatch, flag):
    """Same candidates, same order, same refusals, same fill as the code without the
    area - even though the top candidate sits outside it."""
    rt, opened, rows, _ = _wc_scan(tmp_path, monkeypatch, MIXED, flag=flag,
                                   ranges=MIXED_RANGES, FUTURES_WILDCARD_MAX_CANDIDATES="1")
    base_dir = tmp_path / "before"
    base_dir.mkdir()
    rt0, opened0, rows0, _ = _wc_scan(base_dir, monkeypatch, MIXED, flag=flag,
                                      ranges=MIXED_RANGES, no_envelope=True,
                                      FUTURES_WILDCARD_MAX_CANDIDATES="1")
    assert _decisions(opened, rows, rt) == _decisions(opened0, rows0, rt0)
    assert [o[0] for o in opened] == ["A_USDT"]                      # outside, still taken
    assert opened[0][3] is None                                    # nothing decided on it


def test_switch_off_never_evaluates_in_the_decision_path(tmp_path, monkeypatch):
    _clean_env(monkeypatch, "0")
    rt = _runtime(tmp_path, MAJ)
    rt._envelope_verdict = lambda sig, kind: pytest.fail("evaluated with the switch off")
    assert rt._envelope_refuses(MIXED["A_USDT"], "WILDCARD") is False


def test_switch_on_refuses_outside_and_takes_the_next_candidate(tmp_path, monkeypatch):
    rt, opened, rows, _ = _wc_scan(tmp_path, monkeypatch, MIXED, flag="1", ranges=MIXED_RANGES)
    assert [o[:2] for o in opened] == [("C_USDT", "LONG")]
    refused = [(r["symbol"], r["side"], r["envelope_reason"]) for r in rows
               if r["reject_reason"] == "envelope"]
    assert refused == [("A_USDT", "LONG", "rsi14>84.35"),
                       ("B_USDT", "SHORT", "range_24h<0.29967")]
    # The fill receives the verdict the decision was made on.
    assert opened[0][3][:3] == ("C_USDT", "LONG", "WILDCARD")
    assert opened[0][3][3]["envelope_pass"] == 1.0
    assert opened[0][3][3]["envelope_enabled"] == 1.0


@pytest.mark.parametrize("side,sig,rng,taken", [
    ("LONG", _sig(roc=0.12, rsi=70.0), 0.5, True),
    ("LONG", _sig(roc=0.085, rsi=70.0), 0.5, False),                # |3h ROC| below 8.798%
    ("LONG", _sig(roc=0.12, rsi=70.0, atr=0.06), 0.5, False),       # ATR above 5.559%
    ("SHORT", _sig(side="SHORT", roc=-0.12, rsi=40.0), 0.5, True),
    ("SHORT", _sig(side="SHORT", roc=-0.12, rsi=20.0), 0.5, False),  # RSI below 25
    ("SHORT", _sig(side="SHORT", roc=-0.12, rsi=40.0), 0.9, False),  # range above 77.1%
])
def test_switch_on_wildcard_both_sides(tmp_path, monkeypatch, side, sig, rng, taken):
    _, opened, rows, _ = _wc_scan(tmp_path, monkeypatch, {"A_USDT": sig}, flag="1",
                                  ranges={"A_USDT": rng})
    assert bool(opened) is taken
    assert [r["reject_reason"] for r in rows] == ([] if taken else ["envelope"])
    if not taken:
        assert rows[0]["envelope_cell"] == "WILDCARD " + side and rows[0]["envelope_pass"] == 0.0


def test_switch_on_missing_majors_refuse_the_long_cell_only(tmp_path, monkeypatch):
    sigs = {"A_USDT": _sig(roc=0.20), "B_USDT": _sig("B_USDT", side="SHORT", roc=-0.12, rsi=40.0)}
    _, opened, rows, _ = _wc_scan(tmp_path, monkeypatch, sigs, flag="1", majors={})
    assert [o[:2] for o in opened] == [("B_USDT", "SHORT")]        # SHORT's box has no majors
    (row,) = rows
    assert row["symbol"] == "A_USDT" and row["envelope_reason"] == "missing:bot_sol_72h"
    assert row["envelope_bot_sol_72h"] is None


def test_switch_on_an_evaluation_error_refuses(tmp_path, monkeypatch):
    _clean_env(monkeypatch, "1")
    rt = _runtime(tmp_path, MAJ)

    def boom(max_age_s=None):
        raise RuntimeError("kline outage")
    rt._majors_sample = boom
    rows: list = []
    rt._shadow_log_untaken = lambda sig, kind, reason, envelope=None: rows.append((reason, envelope))
    assert rt._envelope_refuses(_sig(), "WILDCARD") is True
    assert rows == [("envelope", {"envelope_pass": 0.0, "envelope_reason": "error",
                                  "envelope_cell": "WILDCARD LONG", "envelope_enabled": 1.0})]


def test_switch_on_refuses_before_a_preemption_evicts_anything(tmp_path, monkeypatch):
    """Slots full: an outside candidate must not cost an open position its slot."""
    sigs = {"A_USDT": _sig("A_USDT", roc=0.20, rsi=88.0), "C_USDT": _sig("C_USDT", roc=0.12)}
    _, opened, rows, preempted = _wc_scan(tmp_path, monkeypatch, sigs, flag="1", full=True)
    assert preempted == ["C_USDT"] and [o[0] for o in opened] == ["C_USDT"]
    _, opened, rows, preempted = _wc_scan(tmp_path / "x", monkeypatch,
                                          {"A_USDT": sigs["A_USDT"]}, flag="1", full=True)
    assert preempted == [] and opened == [] and rows[0]["reject_reason"] == "envelope"


def test_the_other_gates_still_run_first(tmp_path, monkeypatch):
    """The area is the LAST gate: a calm-shock refusal keeps its own reason."""
    sigs = {"A_USDT": _sig(roc=0.12, calm_ratio=0.9)}
    _, opened, rows, _ = _wc_scan(tmp_path, monkeypatch, sigs, flag="1",
                                  FUTURES_WILDCARD_MAX_CALM_RATIO="0.75")
    assert opened == [] and [r["reject_reason"] for r in rows] == ["calm_shock(0.90)"]
    assert rows[0]["envelope_pass"] == 1.0                          # stamped all the same


# --- the TREND scan -----------------------------------------------------------------------

def _trend_scan(tmp_path, monkeypatch, sigs, *, flag, majors=MAJ, no_envelope=False):
    _clean_env(monkeypatch, flag, FUTURES_TREND_SYMBOLS=",".join(sigs))
    monkeypatch.setattr(R, "detect_trend_signal", lambda frame, sym, reasons=None: sigs.get(sym))
    rt = _runtime(tmp_path, majors)
    rt.client.get_klines.side_effect = lambda sym, **kw: FRAME
    rt._convex_open_count = lambda *a, **k: 0
    rt._trend_rotation_symbol = lambda: None
    opened: list[tuple] = []
    rt._open_wildcard_position = lambda sig, avail, **kw: opened.append(
        (sig.symbol, sig.side, tuple(sorted(kw.items())), rt._pending_envelope)) or True
    if no_envelope:
        rt._envelope_refuses = lambda sig, kind: False
        rt._envelope_verdict = lambda sig, kind: None
    rt._last_trend_scan_at = 0.0
    rt._maybe_scan_trend()
    return rt, opened, shadow_ledger.load_raw(str(tmp_path / "shadow.jsonl"))


def _tsig(symbol, gate, roc):
    return _sig(symbol, roc=roc, rsi=60.0, atr=0.01, entry=gate, prior_close_extreme=100.0,
                gate_close=gate)


# ZEC's new high is 0.8% over the prior closing high (outside 0.67%); XRP's 0.3% (inside).
TREND_MIX = {"ZEC_USDT": _tsig("ZEC_USDT", 100.8, 0.09), "XRP_USDT": _tsig("XRP_USDT", 100.3, 0.05)}


@pytest.mark.parametrize("flag", [None, "0"])
def test_trend_switch_off_makes_todays_decisions(tmp_path, monkeypatch, flag):
    _, opened, rows = _trend_scan(tmp_path, monkeypatch, TREND_MIX, flag=flag)
    (tmp_path / "b").mkdir()
    _, opened0, rows0 = _trend_scan(tmp_path / "b", monkeypatch, TREND_MIX, flag=flag,
                                    no_envelope=True)
    assert [o[:3] for o in opened] == [o[:3] for o in opened0] == \
        [("ZEC_USDT", "LONG", (("kind", "TREND"), ("veto_checked", True)))]
    assert rows == rows0 == []


def test_trend_switch_on_refuses_outside_and_takes_inside(tmp_path, monkeypatch):
    _, opened, rows = _trend_scan(tmp_path, monkeypatch, TREND_MIX, flag="1")
    assert [o[:2] for o in opened] == [("XRP_USDT", "LONG")]
    assert opened[0][3][3]["envelope_new_high_margin_pct"] == pytest.approx(0.3)
    (row,) = rows
    assert (row["symbol"], row["reject_reason"], row["envelope_cell"]) == \
        ("ZEC_USDT", "envelope", "TREND LONG")
    assert row["envelope_reason"] == "new_high_margin_pct>0.67025"
    assert row["envelope_new_high_margin_pct"] == pytest.approx(0.8)


@pytest.mark.parametrize("majors,reason", [
    ({**MAJ, "eth_12h": 0.035}, "bot_eth_12h>0.029645"),
    ({**MAJ, "eth_24h": 0.06}, "bot_eth_24h>0.05108"),
    ({**MAJ, "calm_score": 0.4}, "bot_calm_score<0.5165"),
    ({k: v for k, v in MAJ.items() if k != "sol_12h"}, "missing:bot_calm_score"),
])
def test_trend_switch_on_market_conditions(tmp_path, monkeypatch, majors, reason):
    _, opened, rows = _trend_scan(tmp_path, monkeypatch, {"XRP_USDT": TREND_MIX["XRP_USDT"]},
                                  flag="1", majors=majors)
    assert opened == [] and [r["envelope_reason"] for r in rows] == [reason]


# --- telemetry, switch on or off -------------------------------------------------------------

def test_every_shadow_row_carries_the_verdict_with_the_switch_off(tmp_path, monkeypatch):
    rt, opened, rows, _ = _wc_scan(tmp_path, monkeypatch, MIXED, flag="0",
                                   ranges=MIXED_RANGES, FUTURES_WILDCARD_MAX_CANDIDATES="1")
    assert {r["reject_reason"] for r in rows} == {"rank_dropped"}
    by = {r["symbol"]: r for r in rows}
    assert by["B_USDT"]["envelope_pass"] == 0.0 and by["B_USDT"]["envelope_enabled"] == 0.0
    assert by["B_USDT"]["envelope_range_24h"] == pytest.approx(0.20)
    assert by["C_USDT"]["envelope_pass"] == 1.0 and by["C_USDT"]["envelope_rsi14"] == 70.0
    assert by["C_USDT"]["envelope_bot_sol_72h"] == 0.0
    assert by["C_USDT"]["envelope_majors_age_s"] == pytest.approx(5.0, abs=1.0)


def test_other_sleeves_are_not_stamped(tmp_path, monkeypatch):
    _clean_env(monkeypatch, "1")
    rt = _runtime(tmp_path, MAJ)
    rt._shadow_log_untaken(_sig(), "SQUEEZE", "slot_occupied")
    (row,) = shadow_ledger.load_raw(str(tmp_path / "shadow.jsonl"))
    assert not any(k.startswith("envelope_") for k in row)


def _paper_open(tmp_path, monkeypatch, sig, kind, flag, **env):
    _clean_env(monkeypatch, flag, FUTURES_PAPER_TRADE="1", **env)
    rt = _runtime(tmp_path, MAJ)
    assert rt.config.paper_trade
    rt.client.get_contract_detail.return_value = {"contractSize": 0.001, "minVol": 1}
    rt._entry_margin = lambda *a, **k: 20.0
    rt._convex_streak_multiplier = lambda: (1.0, 0)
    rt._notify = lambda *a, **k: None
    rt._entry_message = lambda position: ""
    rt._wildcard_attribution = {sig.symbol: {"range_24h": 0.5}}
    if flag == "1":
        assert rt._envelope_refuses(sig, kind) is False
    else:
        assert rt._envelope_refuses(sig, kind) is False and rt._pending_envelope is None
    assert rt._open_wildcard_position(sig, 1000.0, kind=kind, veto_checked=True)
    return rt, rt.open_positions[sig.symbol].metadata


@pytest.mark.parametrize("flag", ["0", "1"])
def test_every_fill_carries_the_verdict(tmp_path, monkeypatch, flag):
    _, md = _paper_open(tmp_path, monkeypatch, _sig(roc=0.12), "WILDCARD", flag)
    assert md["envelope_pass"] == 1.0 and md["envelope_cell"] == "WILDCARD LONG"
    assert md["envelope_enabled"] == (1.0 if flag == "1" else 0.0)
    assert (md["envelope_roc3h_abs"], md["envelope_rsi14"], md["envelope_atr_pct"],
            md["envelope_bot_sol_72h"]) == (0.12, 70.0, 0.03, 0.0)


def test_a_trend_fill_carries_its_own_cell(tmp_path, monkeypatch):
    _, md = _paper_open(tmp_path, monkeypatch, _tsig("XRP_USDT", 100.3, 0.05), "TREND", "0")
    assert md["envelope_cell"] == "TREND LONG" and md["envelope_pass"] == 1.0
    assert md["envelope_new_high_margin_pct"] == pytest.approx(md["trend_extreme_margin_pct"],
                                                               abs=1e-4)
    assert md["envelope_bot_calm_score"] == 0.6


def test_the_fill_stamps_the_decision_not_a_recomputation(tmp_path, monkeypatch):
    """Switch on, the fill carries the verdict the order was allowed on, even if the
    majors sample refreshes in between (a preemption can take seconds)."""
    sig = _sig(roc=0.12)
    _clean_env(monkeypatch, "1", FUTURES_PAPER_TRADE="1")
    rt = _runtime(tmp_path, MAJ)
    rt.client.get_contract_detail.return_value = {"contractSize": 0.001, "minVol": 1}
    rt._entry_margin = lambda *a, **k: 20.0
    rt._convex_streak_multiplier = lambda: (1.0, 0)
    rt._notify = lambda *a, **k: None
    rt._entry_message = lambda position: ""
    assert rt._envelope_refuses(sig, "WILDCARD") is False
    rt._majors_sample = lambda max_age_s=None: (time.time(), {**MAJ, "sol_72h": -0.2})
    assert rt._open_wildcard_position(sig, 1000.0, veto_checked=True)
    md = rt.open_positions[sig.symbol].metadata
    assert md["envelope_bot_sol_72h"] == 0.0 and md["envelope_pass"] == 1.0
    assert rt._pending_envelope is None                              # consumed


def test_the_verdict_reaches_the_trade_record_and_feature_store(tmp_path, monkeypatch):
    assert set(E.STAMP_KEYS) <= set(ENTRY_GATE_KEYS)
    _clean_env(monkeypatch, "0")
    rt = _runtime(tmp_path, MAJ)
    rt._feature_store_path = tmp_path / "fs.jsonl"
    md = {"sl_margin_pct": 50.0, "envelope_pass": 0.0, "envelope_cell": "WILDCARD LONG",
          "envelope_reason": "rsi14>84.35", "envelope_enabled": 0.0, "envelope_rsi14": 88.0}
    pos = SimpleNamespace(metadata=md, entry_signal="WILDCARD_LONG", contracts=1,
                          contract_size=1.0, entry_price=1.0)
    rt._append_feature_store({"entry_signal": "WILDCARD_LONG", "symbol": "A_USDT",
                              "exit_time": "2026-09-29T10:00:00+00:00"}, pos)
    row = json.loads((tmp_path / "fs.jsonl").read_text().splitlines()[-1])
    assert (row["envelope_pass"], row["envelope_cell"], row["envelope_rsi14"]) == \
        (0.0, "WILDCARD LONG", 88.0)
    assert row["envelope_bot_sol_72h"] is None


def test_refusals_are_priced_in_the_gate_cost_report():
    """Refused rows resolve like every other shadow row, so the report prices the area."""
    assert FuturesRuntime._GATE_COST_LABELS["envelope"] == "restricted area"
