"""/why rewrite (2026-08-15, owner request).

The command used to walk the six PMT pairs and print
`diagnose_pmt_threshold_rejection` for each, while PMT entries have been blocked
by FUTURES_ENTRY_MIN_SCORE>=999 since 2026-07-13. It answered a question about a
strategy that cannot open a position and said nothing about the sleeves that
can. Each test below pins one property of the replacement.
"""
import time
from dataclasses import replace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from futuresbot.config import FuturesConfig
from futuresbot.runtime import FuturesRuntime


@pytest.fixture
def rt(tmp_path, monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    monkeypatch.setenv("FUTURES_ENTRY_MIN_SCORE", "1000")
    monkeypatch.setenv("FUTURES_WILDCARD_ENABLED", "1")
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "rt.json"),
                  status_file=str(tmp_path / "st.json"),
                  telegram_token="", telegram_chat_id="")
    return FuturesRuntime(cfg, MagicMock())


def _ticker(sym, *, amount24=50e6, hi=1.30, lo=1.0, rise=0.25):
    return {"symbol": sym, "amount24": amount24, "high24Price": hi,
            "lower24Price": lo, "riseFallRate": rise}


def _frame(n=300, start=1.0, step=1.004):
    """Steadily rising Min15 bars, closes at the high (climax guard passes)."""
    closes = [start * (step ** i) for i in range(n)]
    return pd.DataFrame({
        "open": [c / step for c in closes],
        "high": closes,
        "low": [c / step for c in closes],
        "close": closes,
        "volume": [1000.0] * (n - 1) + [9000.0],
    })


def _ctx(rt, **over):
    ctx = {
        "tickers": [], "by_symbol": {}, "majors": set(), "exclude_top": 24,
        "floor": 3e6, "min_move": 0.08, "min_roc": 0.08, "range_prefilter": True,
        "max_calm": 0.75, "slot_free": True,
    }
    ctx.update(over)
    return ctx


# --------------------------------------------------------------------------
# The defect the rewrite exists to fix
# --------------------------------------------------------------------------

def test_why_no_longer_diagnoses_the_decommissioned_pmt_pairs(rt, monkeypatch):
    """PMT cannot enter while the floor is 1000, so six PMT paragraphs are six
    answers to a question nobody asked. One line replaces them."""
    monkeypatch.setattr(rt, "_why_context", lambda: (_ for _ in ()).throw(RuntimeError("no net")))
    pmt = MagicMock(side_effect=AssertionError("PMT walk must not run when entries are blocked"))
    monkeypatch.setattr(rt, "_why_pmt_lines", pmt)
    text = rt._build_why_message()
    assert "PMT entries decommissioned" in text
    pmt.assert_not_called()


def test_why_restores_the_pmt_walk_when_entries_are_re_enabled(rt, monkeypatch):
    """The PMT diagnosis is dormant, not deleted — flipping the floor back to 0
    must bring it straight back."""
    monkeypatch.setenv("FUTURES_ENTRY_MIN_SCORE", "0")
    monkeypatch.setattr(rt, "_why_context", lambda: (_ for _ in ()).throw(RuntimeError("no net")))
    monkeypatch.setattr(rt, "_why_pmt_lines", lambda: ["🎯 <b>PMT pairs</b>", "BTC_USDT — up"])
    assert "🎯 <b>PMT pairs</b>" in rt._build_why_message()


def test_why_reports_the_convex_sleeves_not_the_pmt_slot_count(rt):
    """The old header printed the PMT max_concurrent_positions, which is the one
    number that cannot stop a trade today."""
    monkeypatch_free = rt._build_why_message
    rt._why_context = lambda: (_ for _ in ()).throw(RuntimeError("no net"))
    text = monkeypatch_free()
    assert "🎰 Slots: wildcard" in text and "squeeze" in text


# --------------------------------------------------------------------------
# Per-symbol verdicts walk the live funnel in the live order
# --------------------------------------------------------------------------

def test_verdict_majors_band_beats_the_detector(rt):
    cls, reason = rt._why_symbol_verdict("ACE_USDT", _ctx(rt, majors={"ACE_USDT"}), _frame())
    assert cls == "universe" and "majors band" in reason


def test_verdict_thin_turnover_is_reported_in_dollars(rt):
    ctx = _ctx(rt, by_symbol={"FOO_USDT": _ticker("FOO_USDT", amount24=1.2e6)})
    cls, reason = rt._why_symbol_verdict("FOO_USDT", ctx, _frame())
    assert cls == "liquidity" and "$1.2M" in reason and "$3M" in reason


def test_verdict_quiet_symbol_names_the_threshold_it_missed(rt):
    ctx = _ctx(rt, by_symbol={"FOO_USDT": _ticker("FOO_USDT", hi=1.02, lo=1.0)})
    cls, reason = rt._why_symbol_verdict("FOO_USDT", ctx, _frame())
    assert cls == "quiet" and "2%" in reason and "8%" in reason


def test_verdict_open_position_short_circuits_everything(rt):
    rt.open_positions["FOO_USDT"] = MagicMock()
    cls, reason = rt._why_symbol_verdict("FOO_USDT", _ctx(rt, majors={"FOO_USDT"}), None)
    assert cls == "open" and reason == "already open"


def test_verdict_detector_reason_is_translated_out_of_enum_jargon(rt):
    """`no_pullback_resume` is the single largest filter in the detector and it
    read as a machine enum on a phone."""
    ctx = _ctx(rt, by_symbol={"FOO_USDT": _ticker("FOO_USDT")})
    flat = _frame(step=1.0006)   # real bars, but nowhere near an 8% 3h move
    cls, reason = rt._why_symbol_verdict("FOO_USDT", ctx, flat)
    assert "_" not in reason, f"enum leaked into the message: {reason}"


def test_verdict_quiet_detector_reason_carries_the_actual_3h_move(rt):
    """'3h move too small' without the number is not a diagnosis."""
    ctx = _ctx(rt, by_symbol={"FOO_USDT": _ticker("FOO_USDT")})
    cls, reason = rt._why_symbol_verdict("FOO_USDT", ctx, _frame(step=1.0006))
    if cls == "quiet":
        assert "%" in reason and "needed" in reason


def test_verdict_no_free_slot_is_its_own_class(rt, monkeypatch):
    """slot_occupied is the sleeve's real bottleneck (11 of 23 candidates
    all-time) and must never be reported as a strategy rejection."""
    from futuresbot import wildcard as W

    sig = MagicMock(side="LONG", roc_pct=0.19, calm_ratio=0.10, symbol="FOO_USDT")
    monkeypatch.setattr(W, "detect_wildcard_signal", lambda *a, **k: sig)
    monkeypatch.setattr(W, "wildcard_long_only", lambda: False)
    ctx = _ctx(rt, by_symbol={"FOO_USDT": _ticker("FOO_USDT")}, slot_free=False)
    cls, reason = rt._why_symbol_verdict("FOO_USDT", ctx, _frame())
    assert cls == "capacity" and "slot" in reason


def test_verdict_ready_when_every_gate_passes(rt, monkeypatch):
    from futuresbot import wildcard as W

    sig = MagicMock(side="LONG", roc_pct=0.19, calm_ratio=0.10, symbol="FOO_USDT")
    monkeypatch.setattr(W, "detect_wildcard_signal", lambda *a, **k: sig)
    monkeypatch.setattr(W, "wildcard_long_only", lambda: False)
    ctx = _ctx(rt, by_symbol={"FOO_USDT": _ticker("FOO_USDT")})
    cls, reason = rt._why_symbol_verdict("FOO_USDT", ctx, _frame())
    assert cls == "ready" and "+19.0%/3h" in reason


def test_verdict_shorts_off_is_a_veto_not_a_detector_miss(rt, monkeypatch):
    from futuresbot import wildcard as W

    sig = MagicMock(side="SHORT", roc_pct=-0.19, calm_ratio=0.10, symbol="FOO_USDT")
    monkeypatch.setattr(W, "detect_wildcard_signal", lambda *a, **k: sig)
    monkeypatch.setattr(W, "wildcard_long_only", lambda: True)
    ctx = _ctx(rt, by_symbol={"FOO_USDT": _ticker("FOO_USDT")})
    cls, reason = rt._why_symbol_verdict("FOO_USDT", ctx, _frame())
    assert cls == "veto" and reason == "shorts are off"


# --------------------------------------------------------------------------
# Mover blocks
# --------------------------------------------------------------------------

def test_change_over_bars_reads_the_right_window(rt):
    f = _frame(n=300, start=1.0, step=1.01)
    c24 = rt._why_change(f, 96)
    c48 = rt._why_change(f, 192)
    assert c24 == pytest.approx(1.01 ** 96 - 1, rel=1e-6)
    assert c48 == pytest.approx(1.01 ** 192 - 1, rel=1e-6)
    assert rt._why_change(_frame(n=50), 192) is None, "short frame must not guess"


def test_mover_lines_carry_one_icon_per_gate_class(rt):
    ctx = _ctx(rt, majors={"AAA_USDT"},
               by_symbol={"BBB_USDT": _ticker("BBB_USDT", amount24=1e6)})
    picks = rt._why_pick_rows([(1.45, "AAA_USDT"), (0.31, "BBB_USDT")],
                              ctx, {"AAA_USDT": _frame(), "BBB_USDT": _frame()}, 4)
    lines = rt._why_mover_lines("📈 t", picks)
    assert lines[1].startswith("⛔") and "AAA" in lines[1]
    assert lines[2].startswith("💧") and "BBB" in lines[2]
    assert "_USDT" not in "\n".join(lines), "symbol suffix is noise on a phone"


def test_mover_lines_collapse_repeats_of_the_same_reason(rt):
    """A live run returned GPUBSC -58%, ASTEROIDBSC -36%, UPROBINHOOD -31% —
    three separate lines all saying "turnover under $3M". One line, one count."""
    thin = {s: _ticker(s, amount24=2e5) for s in ("AAA_USDT", "BBB_USDT", "CCC_USDT")}
    picks = rt._why_pick_rows(
        [(-0.58, "AAA_USDT"), (-0.36, "BBB_USDT"), (-0.31, "CCC_USDT")],
        _ctx(rt, by_symbol=thin), {}, 4)
    lines = rt._why_mover_lines("📈 t", picks)
    assert len(lines) == 2, f"expected title + one collapsed row, got {lines}"
    assert "AAA" in lines[1] and "-58%" in lines[1], "biggest mover must survive"
    assert "(+2 more)" in lines[1]
    assert "BBB" not in lines[1] and "CCC" not in lines[1]


def test_mover_lines_keep_distinct_reasons_apart(rt):
    """Collapsing must never merge two different answers."""
    ctx = _ctx(rt, majors={"AAA_USDT"},
               by_symbol={"BBB_USDT": _ticker("BBB_USDT", amount24=2e5),
                          "CCC_USDT": _ticker("CCC_USDT", amount24=2e5)})
    picks = rt._why_pick_rows(
        [(1.4, "AAA_USDT"), (0.9, "BBB_USDT"), (0.5, "CCC_USDT")], ctx, {}, 4)
    lines = rt._why_mover_lines("📈 t", picks)
    assert len(lines) == 3 and lines[1].startswith("⛔") and lines[2].startswith("💧")
    assert "(+1 more)" in lines[2]


def test_why_only_fetches_deep_frames_for_symbols_that_need_them(rt, monkeypatch):
    """The deep Min15 x 672 pull cost 18s across the whole pool on a live run.
    Only symbols that clear every ticker-level gate may pay for it."""
    tick = {"BIG_USDT": _ticker("BIG_USDT"),                      # passes: needs bars
            "THIN_USDT": _ticker("THIN_USDT", amount24=2e5),      # thin: no bars
            "CALM_USDT": _ticker("CALM_USDT", hi=1.01, lo=1.0)}   # quiet: no bars
    monkeypatch.setattr(rt, "_why_context", lambda: _ctx(
        rt, tickers=list(tick.values()), by_symbol=tick))
    asked: list[tuple] = []

    def _frames(syms, interval="Min15", bars=672):
        asked.append((interval, tuple(sorted(syms))))
        return {s: _frame() for s in syms}

    monkeypatch.setattr(rt, "_why_frames", _frames)
    monkeypatch.setattr(rt, "_is_tradeable_crypto", staticmethod(lambda s: True))
    rt._build_why_message()
    coarse = [a for a in asked if a[0] == "Min60"]
    deep = [a for a in asked if a[0] == "Min15"]
    assert coarse and len(coarse[0][1]) == 3, "all pooled symbols get the cheap frame"
    assert deep and deep[0][1] == ("BIG_USDT",), f"deep fetch overreached: {deep}"


def test_why_renders_both_mover_windows(rt, monkeypatch):
    monkeypatch.setattr(rt, "_why_context", lambda: _ctx(
        rt, tickers=[_ticker("AAA_USDT")], by_symbol={"AAA_USDT": _ticker("AAA_USDT")}))
    monkeypatch.setattr(rt, "_why_frames", lambda syms, **kw: {"AAA_USDT": _frame()})
    text = rt._build_why_message()
    assert "Top movers · 24h" in text and "Top movers · 48h" in text


def test_why_survives_a_dead_exchange(rt, monkeypatch):
    """Diagnosis is best-effort: a failed mover scan must still return the slot
    and scan context rather than raising into the Telegram handler."""
    monkeypatch.setattr(rt, "_why_context", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    text = rt._build_why_message()
    assert "Mover scan failed" in text and "🎰 Slots" in text


def test_why_surfaces_the_scan_funnel_and_top_blockers(rt, monkeypatch):
    rt._last_wildcard_scan = {
        "at": time.time() - 360, "funnel": {"in_band": 666}, "scanned": 17,
        "cands": 0, "hist": {"roc_below_min": 15, "no_pullback_resume": 2},
    }
    monkeypatch.setattr(rt, "_why_context", lambda: (_ for _ in ()).throw(RuntimeError("no net")))
    text = rt._build_why_message()
    assert "666 in-band" in text and "17 scanned" in text
    assert "🚧 Blocked:" in text
    assert "roc_below_min" not in text, "histogram keys are enums; translate them"
    assert "3h move too small ×15" in text


def test_why_flags_a_disabled_wildcard_loudly(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_ENABLED", "0")
    monkeypatch.setattr(rt, "_why_context", lambda: (_ for _ in ()).throw(RuntimeError("no net")))
    assert "Wildcard is DISABLED" in rt._build_why_message()


def test_why_stays_short_enough_for_telegram(rt, monkeypatch):
    monkeypatch.setattr(rt, "_why_context", lambda: _ctx(
        rt, tickers=[_ticker(f"S{i}_USDT") for i in range(40)],
        by_symbol={f"S{i}_USDT": _ticker(f"S{i}_USDT") for i in range(40)}))
    monkeypatch.setattr(rt, "_why_frames", lambda syms, **kw: {s: _frame() for s in syms})
    assert len(rt._build_why_message()) < 4096


# --------------------------------------------------------------------------
# riseFallRate is NOT a 24h change (2026-08-16)
# --------------------------------------------------------------------------

def test_24h_ranking_never_uses_risefallrate(rt, monkeypatch):
    """MEXC ships `riseFallRates.zone: "UTC+8"` — riseFallRate is a CALENDAR-DAY
    change anchored to Hong Kong midnight (16:00 UTC), not a rolling 24h. It
    resets to ~0 for every symbol at that hour, and the 24h list silently became
    a ranking of however many minutes had elapsed since. Measured live on
    CYS_USDT: riseFallRate +0.96% against a true rolling 24h of -38.95%."""
    tick = {"CYS_USDT": _ticker("CYS_USDT", rise=0.0096)}   # the real live value
    monkeypatch.setattr(rt, "_why_context", lambda: _ctx(
        rt, tickers=list(tick.values()), by_symbol=tick, majors={"CYS_USDT"}))
    monkeypatch.setattr(rt, "_is_tradeable_crypto", staticmethod(lambda s: True))
    # A frame that fell 39% over the trailing 24 hourly bars.
    closes = [1.1848] * 26 + [1.1848 * (1 - 0.39 * i / 24) for i in range(1, 25)]
    monkeypatch.setattr(rt, "_why_frames", lambda syms, **kw: {
        "CYS_USDT": pd.DataFrame({"open": closes, "high": closes, "low": closes,
                                  "close": closes, "volume": [1.0] * len(closes)})})
    block = rt._build_why_message().split("📈")[1].split("📉")[0]
    assert "-39%" in block, f"24h must be the rolling window, got: {block}"
    assert "+1%" not in block


def test_flat_symbols_are_not_printed_as_top_movers(rt, monkeypatch):
    """The pool is seeded partly by turnover, to catch 48h grinders. Those names
    have not moved, and one-row-per-class let a flat mega-cap take the majors
    row under a "Top movers" heading — HYPE_USDT did, at +1%."""
    picks = rt._why_pick_rows([(0.010, "HYPE_USDT"), (0.42, "AAA_USDT")],
                              _ctx(rt, majors={"HYPE_USDT", "AAA_USDT"}), {}, 4)
    assert [p[2] for p in picks] == ["AAA_USDT"], "a mover has to have moved"


def test_sub_floor_movers_get_no_dollar_claim(rt, monkeypatch):
    """The counterfactual prices a fill at the sleeve's size. On a $0.2M-turnover
    micro-cap that fill does not exist — which is why the turnover floor is
    there — so "missed $1.08" against GPUBSC was money nothing could collect."""
    tick = {"DUST_USDT": _ticker("DUST_USDT", amount24=2e5)}
    monkeypatch.setattr(rt, "_why_context", lambda: _ctx(
        rt, tickers=list(tick.values()), by_symbol=tick))
    monkeypatch.setattr(rt, "_is_tradeable_crypto", staticmethod(lambda s: True))
    monkeypatch.setattr(rt, "_why_frames", lambda syms, **kw: {"DUST_USDT": _frame()})
    priced: list[str] = []
    monkeypatch.setattr(rt, "_counterfactual_usd",
                        lambda s, *a, **k: priced.append(s) or (1, 9.99))
    text = rt._build_why_message()
    assert "DUST" in text and "under $3M" in text
    assert priced == [], "a fill that cannot be obtained must not be priced"
    assert "9.99" not in text
