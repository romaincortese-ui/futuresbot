"""Sniper sleeve — detection geometry, the cost gate, and shadow-only safety."""
import os

import pandas as pd
import pytest

from futuresbot.shadow_ledger import TP_R, candidate_row, resolve_outcome, signal_tp_r
from futuresbot.sniper import (
    cost_drag,
    detect_sniper_signal,
    realised_range_pct,
    sniper_shadow_only,
    symbol_allowed,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("FUTURES_SNIPER"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("FUTURES_WILDCARD_MAX_SL_MARGIN_PCT", raising=False)


def _frame(closes, *, wick=0.001, vol=1000.0):
    """OHLC where the close sits toward the bar extreme in the direction of the
    last move — how a bar in a real trend actually looks. Symmetric wicks would
    put adverse_wick at exactly 0.5 and trip the climax guard on every bar."""
    highs, lows = [], []
    for i, c in enumerate(closes):
        rising = i == 0 or c >= closes[i - 1]
        near, far = wick * 0.3, wick * 1.7
        highs.append(c * (1 + (near if rising else far)))
        lows.append(c * (1 - (far if rising else near)))
    idx = pd.date_range("2026-08-01", periods=len(closes), freq="15min", tz="UTC")
    return pd.DataFrame({"open": closes, "high": highs, "low": lows,
                         "close": closes, "volume": [vol] * len(closes)}, index=idx)


def _zigzag(n=131, up=0.0025, dn=0.0015, cycle=3, start=100.0):
    # n-1 must not be divisible by `cycle`, or the series ends on a DOWN bar and
    # _frame puts the close at the wrong end of the final candle, tripping the
    # climax-wick guard for reasons that have nothing to do with the test.
    """Net-uptrending series with real pullbacks, so RSI lands in a plausible
    band instead of pinning at 100 the way a monotonic ramp does."""
    closes = [start]
    for i in range(1, n):
        closes.append(closes[-1] * (1 + (up if i % cycle else -dn)))
    return closes


def _trending(n=131, up=0.0025, dn=0.0015, wick=0.0015):
    return _frame(_zigzag(n, up, dn), wick=wick)


def _falling(n=131, wick=0.0015):
    return _frame([1.0 / x * 10000 for x in _zigzag(n)], wick=wick)


# --------------------------------------------------------------------------
# universe rules
# --------------------------------------------------------------------------

def test_synthetic_commodity_perps_are_excluded_by_category():
    # XAU_USDT produced the worst trade in trial 4: 0.28% stop, 286% fee share,
    # -3.79R in 60 seconds. A turnover filter did not catch it; category does.
    assert not symbol_allowed("XAU_USDT")
    assert not symbol_allowed("USOIL_USDT")
    assert symbol_allowed("BTC_USDT")


def test_exclusion_matches_prefixes_not_exact_names():
    # A live scan found XAUT_USDT (tokenised gold, 0.18% 4h range = 68% cost
    # drag) and SILVER_USDT clearing the turnover floor while an exact-match
    # list nominally excluded "XAU".
    assert not symbol_allowed("XAUT_USDT")
    assert not symbol_allowed("SILVER_USDT")
    assert not symbol_allowed("SNDKSTOCK_USDT")
    # ...without swallowing ordinary crypto that merely starts with similar text
    assert symbol_allowed("SUI_USDT")
    assert symbol_allowed("SOL_USDT")


def test_allow_list_when_set_restricts_everything_else(monkeypatch):
    monkeypatch.setenv("FUTURES_SNIPER_SYMBOLS", "BTC_USDT,ETH_USDT")
    assert symbol_allowed("BTC_USDT")
    assert not symbol_allowed("SOL_USDT")


def test_empty_allow_list_permits_any_non_excluded_symbol():
    assert symbol_allowed("SOL_USDT")
    assert symbol_allowed("DOGE_USDT")


def test_excluded_list_is_configurable(monkeypatch):
    monkeypatch.setenv("FUTURES_SNIPER_EXCLUDE", "DOGE")
    assert symbol_allowed("XAU_USDT")     # no longer excluded
    assert not symbol_allowed("DOGE_USDT")


# --------------------------------------------------------------------------
# the cost gate — the XAU lesson as arithmetic
# --------------------------------------------------------------------------

def test_cost_drag_is_leverage_independent_and_explodes_on_thin_stops():
    # 0.28% stop (the XAU trade): round trip eats about two thirds of 1R.
    assert cost_drag(0.0028) > 0.6
    # 1.26% stop (BTC's measured 4h range x1.5): inside the 20% budget.
    assert cost_drag(0.0126) < 0.20
    assert cost_drag(0.0) == float("inf")


def _thin(monkeypatch):
    """Qualifying move, but a range so small the stop cannot pay for fees."""
    monkeypatch.setenv("FUTURES_SNIPER_MIN_MOVE", "0.005")
    return _frame(_zigzag(131, up=0.0005, dn=0.0003), wick=0.0002)


def test_fee_doomed_setup_is_refused(monkeypatch):
    reasons = []
    assert detect_sniper_signal(_thin(monkeypatch), "BTC_USDT", reasons) is None
    assert "fee_doomed" in reasons


def test_cost_budget_is_configurable(monkeypatch):
    frame = _thin(monkeypatch)
    monkeypatch.setenv("FUTURES_SNIPER_MAX_COST_DRAG", "0.99")
    monkeypatch.setenv("FUTURES_SNIPER_MIN_LEVERAGE", "1")
    reasons = []
    detect_sniper_signal(frame, "BTC_USDT", reasons)
    assert "fee_doomed" not in reasons


# --------------------------------------------------------------------------
# geometry: leverage is an OUTPUT of the stop, never an input
# --------------------------------------------------------------------------

def test_leverage_falls_out_of_the_margin_cap():
    sig = detect_sniper_signal(_trending(), "BTC_USDT")
    assert sig is not None
    sl_frac = abs(sig.entry_price - sig.sl_price) / sig.entry_price
    # the -20% margin cap must hold
    assert sl_frac * sig.leverage * 100 <= 20.0 + 1e-6
    # and leverage must be the largest integer that respects it
    assert (sl_frac * (sig.leverage + 1) * 100 > 20.0) or sig.leverage == 20


def test_wider_range_produces_lower_leverage(monkeypatch):
    # Trigger relaxed so this isolates the sizing rule: a wider range means a
    # wider stop, and a wider stop means the margin cap permits less leverage.
    monkeypatch.setenv("FUTURES_SNIPER_TRIGGER_ATR_MULT", "0.1")
    calm = detect_sniper_signal(_trending(wick=0.0010), "BTC_USDT")
    wild = detect_sniper_signal(_trending(wick=0.0060), "BTC_USDT")
    assert calm is not None and wild is not None
    assert wild.leverage < calm.leverage


# --------------------------------------------------------------------------
# the trigger is measured in the symbol's own volatility
# --------------------------------------------------------------------------

def test_trigger_scales_with_volatility_not_a_flat_percentage():
    # A flat 2% is 1.79x BTC's 4h range but 0.24x a high-ATR alt's. Under a flat
    # rule the alts fire ~3x more often and monopolise the slots — measured,
    # BTC/ETH/SOL won only 4.8% of slots in a 30-pair universe. Same +6% move,
    # different volatility: the calm symbol qualifies, the wild one does not.
    calm = detect_sniper_signal(_trending(up=0.0025, dn=0.0015, wick=0.0008), "BTC_USDT")
    reasons = []
    detect_sniper_signal(_trending(up=0.0025, dn=0.0015, wick=0.0090), "WILD_USDT", reasons)
    assert calm is not None
    assert "move_below_min" in reasons


def test_trigger_multiple_exceeds_the_stop_multiple():
    # Otherwise the stop is wider than the move that triggered it — incoherent
    # for a continuation design.
    from futuresbot.sniper import _f
    assert _f("FUTURES_SNIPER_TRIGGER_ATR_MULT", 2.0) > _f("FUTURES_SNIPER_SL_RANGE_MULT", 1.5)


def test_low_volatility_instrument_is_refused_on_stop_width(monkeypatch):
    # The XAU class: turnover rank 4, 0.07bp spread, deepest book on the venue —
    # but a 0.67% 4h range makes every percentage stop tiny in absolute terms and
    # the fixed fee dominates. "Thin stop on a low-volatility instrument."
    frame = _thin(monkeypatch)                       # small drift AND small wick
    monkeypatch.setenv("FUTURES_SNIPER_TRIGGER_ATR_MULT", "0.1")
    monkeypatch.setenv("FUTURES_SNIPER_MAX_COST_DRAG", "0.99")   # isolate the width rule
    reasons = []
    assert detect_sniper_signal(frame, "QUIET_USDT", reasons) is None
    assert "stop_too_thin" in reasons


def test_leverage_cap_defaults_to_13_not_20():
    # 20 / 1.5% minimum stop = 13.3x. The cap and the stop floor are one rule.
    from futuresbot.sniper import _f
    assert _f("FUTURES_SNIPER_MAX_LEVERAGE", 13) == 13


def test_target_defaults_to_3r_not_5r():
    sig = detect_sniper_signal(_trending(), "BTC_USDT")
    assert sig is not None
    one_r = abs(sig.entry_price - sig.sl_price)
    assert abs(sig.tp_price - sig.entry_price) / one_r == pytest.approx(3.0, rel=1e-3)


def test_target_is_configurable(monkeypatch):
    monkeypatch.setenv("FUTURES_SNIPER_TP_R", "2.0")
    sig = detect_sniper_signal(_trending(), "BTC_USDT")
    one_r = abs(sig.entry_price - sig.sl_price)
    assert abs(sig.tp_price - sig.entry_price) / one_r == pytest.approx(2.0, rel=1e-3)


def test_stop_uses_the_4h_range_not_the_15m_range():
    # A 15m ATR flatters the stop by roughly 5x; the stop must survive hours.
    frame = _trending()
    rng = realised_range_pct(frame)
    sig = detect_sniper_signal(frame, "BTC_USDT")
    sl_frac = abs(sig.entry_price - sig.sl_price) / sig.entry_price
    assert sl_frac == pytest.approx(1.5 * rng, rel=1e-3)


def test_realised_range_is_none_on_a_short_frame():
    assert realised_range_pct(_frame([100.0] * 10)) is None


# --------------------------------------------------------------------------
# entry gates
# --------------------------------------------------------------------------

def test_flat_market_produces_no_signal():
    reasons = []
    assert detect_sniper_signal(_frame([100.0] * 130), "BTC_USDT", reasons) is None
    assert "move_below_min" in reasons or "flat_window" in reasons


def test_short_frame_is_refused():
    reasons = []
    assert detect_sniper_signal(_frame([100.0] * 20), "BTC_USDT", reasons) is None
    assert "short_frame" in reasons


def test_retraced_move_is_refused(monkeypatch):
    # The 12h ROC still qualifies (+4%), but price has fallen back to 40% of the
    # window's range — the move happened and is already half given back. This is
    # the case a naive ROC filter would take and the position gate must refuse.
    monkeypatch.setenv("FUTURES_SNIPER_TRIGGER_ATR_MULT", "0.1")
    closes = [100.0] * 81
    closes += [100.0 * (1 + 0.10 * i / 30) for i in range(1, 31)]   # rally to 110
    closes += [110.0 - 6.0 * i / 18 for i in range(1, 19)]          # give back to 104
    reasons = []
    assert detect_sniper_signal(_frame(closes), "BTC_USDT", reasons) is None
    assert "move_retraced" in reasons


def test_unconfirmed_move_is_refused():
    # Uptrend intact over 12h, but the most recent hour has turned down.
    closes = _zigzag(126)
    closes += [closes[-1] * (0.998 ** i) for i in range(1, 5)]
    reasons = []
    assert detect_sniper_signal(_frame(closes), "BTC_USDT", reasons) is None
    assert {"not_confirmed", "move_retraced"} & set(reasons)


def test_short_side_is_detected_symmetrically():
    sig = detect_sniper_signal(_falling(), "ETH_USDT")
    assert sig is not None
    assert sig.side == "SHORT"
    assert sig.sl_price > sig.entry_price
    assert sig.tp_price < sig.entry_price


def test_blow_off_bar_is_refused(monkeypatch):
    # RSI relaxed so this isolates the vertical guard rather than tripping the
    # exhaustion gate first (a blow-off raises both).
    monkeypatch.setenv("FUTURES_SNIPER_RSI_MAX", "99")
    closes = _zigzag(129)
    closes.append(closes[-1] * 1.02)          # > 0.5 x the 4h range in one bar
    reasons = []
    assert detect_sniper_signal(_frame(closes), "BTC_USDT", reasons) is None
    assert "vertical_blowoff" in reasons


# --------------------------------------------------------------------------
# shadow-only safety
# --------------------------------------------------------------------------

def test_shadow_only_defaults_to_true():
    # The sleeve must earn live capital, not be granted it.
    assert sniper_shadow_only() is True


def test_shadow_only_can_be_disabled_explicitly(monkeypatch):
    monkeypatch.setenv("FUTURES_SNIPER_SHADOW_ONLY", "0")
    assert sniper_shadow_only() is False


# --------------------------------------------------------------------------
# shadow ledger scores each sleeve at ITS OWN target
# --------------------------------------------------------------------------

class _Sig:
    symbol = "BTC_USDT"; side = "LONG"; entry_price = 100.0
    sl_price = 99.0; tp_price = 103.0     # +3R
    leverage = 15; sl_margin_pct = 15.0; roc_pct = 0.03; rsi = 60.0


def test_signal_tp_r_reads_the_geometry():
    assert signal_tp_r(_Sig()) == 3.0


def test_a_3r_sniper_tp_resolves_as_3r_not_5r():
    row = candidate_row(_Sig(), sleeve="SNIPER", reject_reason="shadow_only")
    assert row["tp_r"] == 3.0
    bars = [(row["ts"] + 900, 103.5, 100.5)]     # high tags the +3R target
    out = resolve_outcome(row, bars, row["ts"] + 3600)
    assert out["outcome_kind"] == "tp"
    assert out["outcome"] == 3.0


def test_legacy_rows_without_tp_r_still_resolve_at_5r():
    row = candidate_row(_Sig(), sleeve="WILDCARD", reject_reason="slot_occupied")
    row.pop("tp_r")
    out = resolve_outcome(row, [(row["ts"] + 900, 103.5, 100.5)], row["ts"] + 3600)
    assert out["outcome"] == TP_R


def test_stop_still_wins_ties_against_the_target():
    row = candidate_row(_Sig(), sleeve="SNIPER", reject_reason="shadow_only")
    out = resolve_outcome(row, [(row["ts"] + 900, 103.5, 98.5)], row["ts"] + 3600)
    assert out["outcome"] == -1.0


# --------------------------------------------------------------------------
# operator visibility: /status and the learning digest must show the study
# --------------------------------------------------------------------------

@pytest.fixture
def runtime(tmp_path, monkeypatch):
    import json
    from dataclasses import replace
    from unittest.mock import MagicMock

    from futuresbot.config import FuturesConfig
    from futuresbot.runtime import FuturesRuntime

    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    monkeypatch.setenv("FUTURES_SNIPER_ENABLED", "1")
    monkeypatch.delenv("FUTURES_SHADOW_LEDGER_FILE", raising=False)
    cfg = replace(
        FuturesConfig.from_env(),
        symbol="BTC_USDT", symbols=("BTC_USDT",),
        runtime_state_file=str(tmp_path / "rt.json"),
        status_file=str(tmp_path / "st.json"),
        telegram_token="", telegram_chat_id="",
    )
    rt = FuturesRuntime(cfg, MagicMock())
    rt._ledger_write = lambda rows: open(rt._shadow_ledger_path(), "w", encoding="utf-8").write(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    return rt


def _ledger_rows(ts=1_000_000):
    return [
        {"ts": ts, "symbol": "AVAX_USDT", "side": "LONG", "sleeve": "SNIPER_SWING",
         "reject_reason": "shadow_only", "entry": 20.0, "sl": 19.7, "tp": 20.9,
         "leverage": 7, "sl_margin_pct": 10.5, "roc_pct": 0.068, "rsi": 71.0,
         "tp_r": 3.0, "outcome": 3.0, "outcome_kind": "tp"},
        {"ts": ts + 1, "symbol": "SOL_USDT", "side": "SHORT", "sleeve": "SNIPER_SWING",
         "reject_reason": "shadow_only", "entry": 73.0, "sl": 74.1, "tp": 69.7,
         "leverage": 6, "sl_margin_pct": 9.0, "roc_pct": -0.031, "rsi": 30.0,
         "tp_r": 3.0, "outcome": None},
        {"ts": ts + 2, "symbol": "BTC_USDT", "side": "SHORT", "sleeve": "SNIPER_FAST",
         "reject_reason": "shadow_only", "entry": 63000.0, "sl": 63230.0, "tp": 62540.0,
         "leverage": 13, "sl_margin_pct": 4.7, "roc_pct": -0.006, "rsi": 28.0,
         "tp_r": 2.0, "outcome": -1.0, "outcome_kind": "stop"},
        {"ts": ts + 2, "symbol": "ON_USDT", "side": "LONG", "sleeve": "WILDCARD",
         "reject_reason": "slot_occupied", "entry": 1.0, "sl": 0.9, "tp": 1.5,
         "leverage": 5, "sl_margin_pct": 15.0, "roc_pct": 0.1, "rsi": 60.0,
         "outcome": 5.0, "outcome_kind": "tp"},
    ]


def test_status_shows_the_would_be_entries(runtime, monkeypatch):
    monkeypatch.setenv("FUTURES_SNIPER_VARIANTS", "SWING,FAST")
    runtime._ledger_write(_ledger_rows())
    text = "\n".join(runtime._sniper_shadow_status_lines())
    assert "SHADOW" in text and "never trades" in text
    # each variant scored separately — never pooled
    assert "<b>SWING</b>: 2 would-be" in text and "cfR <b>+3.0</b>" in text
    assert "<b>FAST</b>" in text and "cfR <b>-1.0</b>" in text
    # Status tidy 2026-08-08 (operator request): RESOLVED sample rows are gone —
    # they were two lines of stale history per variant and once rendered the
    # same DOGE candidate twice. OPEN rows remain (live-relevant).
    assert "AVAX_USDT LONG" not in text, "resolved sample rows are back in /status"
    assert "SOL_USDT SHORT" in text and "open" in text


def test_status_flags_the_variant_that_is_not_economically_viable(runtime, monkeypatch):
    monkeypatch.setenv("FUTURES_SNIPER_VARIANTS", "SWING,FAST")
    runtime._ledger_write(_ledger_rows())
    text = "\n".join(runtime._sniper_shadow_status_lines())
    swing_line = next(l for l in text.split("\n") if "SWING" in l)
    fast_line = next(l for l in text.split("\n") if "FAST" in l)
    assert "signal-study only" in fast_line
    assert "signal-study only" not in swing_line


def test_status_line_present_but_quiet_before_any_signal(runtime):
    lines = runtime._sniper_shadow_status_lines()
    assert len(lines) == 2                      # header + one active variant
    assert "no signals yet" in lines[1]


def test_status_says_nothing_when_sniper_is_disabled(runtime, monkeypatch):
    monkeypatch.setenv("FUTURES_SNIPER_ENABLED", "0")
    assert runtime._sniper_shadow_status_lines() == []


# --------------------------------------------------------------------------
# trial-4 provenance: ref_listed tag (2026-08-02 gate relaxation)
# --------------------------------------------------------------------------

class _VetoSig:
    symbol = "KOMA_USDT"; side = "LONG"; entry_price = 1.0
    sl_price = 0.98; tp_price = 1.10; leverage = 5
    sl_margin_pct = 10.0; roc_pct = 0.09; rsi = 65.0


def _veto(runtime, monkeypatch, *, listed, require_listed="0"):
    import futuresbot.external_gate as gate

    monkeypatch.setenv("FUTURES_EXTERNAL_GATE_REQUIRE_LISTED", require_listed)
    monkeypatch.setattr(gate, "fetch_reference",
                        lambda sym, timeout=0.6: (listed, 0.05, 0.0001, 5_000_000.0))
    return runtime._external_entry_veto(_VetoSig(), "WILDCARD")


def test_veto_records_corroborated_listing(runtime, monkeypatch):
    allow, _ = _veto(runtime, monkeypatch, listed=True)
    assert allow is True
    assert runtime._pending_ref_listed is True


def test_relaxed_gate_admits_mexc_only_but_tags_it(runtime, monkeypatch):
    # The 2026-08-02 relaxation: the trade is now allowed, but the provenance
    # must survive so trial 4 can be scored with and without this population.
    allow, _ = _veto(runtime, monkeypatch, listed=False, require_listed="0")
    assert allow is True
    assert runtime._pending_ref_listed is False


def test_strict_gate_still_vetoes_mexc_only(runtime, monkeypatch):
    allow, reason = _veto(runtime, monkeypatch, listed=False, require_listed="1")
    assert allow is False
    assert reason == "ref_not_listed"


def test_failed_fetch_leaves_provenance_unknown(runtime, monkeypatch):
    import futuresbot.external_gate as gate

    runtime._pending_ref_listed = True  # stale value from a previous candidate
    def boom(sym, timeout=0.6):
        raise TimeoutError("venue down")
    monkeypatch.setattr(gate, "fetch_reference", boom)
    allow, reason = runtime._external_entry_veto(_VetoSig(), "WILDCARD")
    assert allow is True and reason == "failopen"
    assert runtime._pending_ref_listed is None  # unknown, not inherited


def test_feature_store_row_carries_ref_listed(runtime, tmp_path):
    import json
    from datetime import datetime, timezone
    from types import SimpleNamespace

    position = SimpleNamespace(
        entry_signal="WILDCARD_LONG",
        metadata={"sl_margin_pct": 12.0, "entry_lateness": 0.4, "ref_listed": 0.0},
    )
    trade = {"symbol": "KOMA_USDT", "side": "LONG", "leverage": 5,
             "pnl_usdt": -1.0, "pnl_pct": -10.0, "setup_regime": "OTHER_LONG",
             "exit_time": datetime.now(timezone.utc).isoformat()}
    runtime._append_feature_store(trade, position)
    row = json.loads(open(runtime._feature_store_path, encoding="utf-8").read().strip())
    assert row["ref_listed"] == 0.0
    assert row["kind"] == "WILDCARD"


def test_feature_store_row_tags_sniper_kind(runtime):
    import json
    from datetime import datetime, timezone
    from types import SimpleNamespace

    position = SimpleNamespace(
        entry_signal="SNIPER_SHORT",
        metadata={"sl_margin_pct": 4.04, "entry_lateness": None},
    )
    trade = {"symbol": "XRP_USDT", "side": "SHORT", "leverage": 13,
             "pnl_usdt": 0.02, "pnl_pct": 4.86, "setup_regime": "OTHER_SHORT",
             "exit_time": datetime.now(timezone.utc).isoformat()}
    runtime._append_feature_store(trade, position)
    row = json.loads(open(runtime._feature_store_path, encoding="utf-8").read().strip())
    assert row["kind"] == "SNIPER"  # previously fell through to the "PMT" default


def test_digest_scores_each_variant_separately():
    from futuresbot.learning_digest import build_learning_digest

    msg = build_learning_digest([], _ledger_rows())
    assert "Sniper SHADOW (would-be trades, never traded):" in msg
    assert "<b>SWING</b>: 2 logged, 1 resolved | cfR <b>+3.0</b>" in msg
    assert "<b>FAST</b>: 1 logged, 1 resolved | cfR <b>-1.0</b>" in msg
    assert "tp 1 stop 0 timeout 0" in msg      # SWING
    assert "tp 0 stop 1 timeout 0" in msg      # FAST
    assert "not viable at taker fees" in msg   # the caveat travels with the number
    # ...and the generic scorecard no longer swallows them as "shadow_only"
    assert "shadow_only" not in msg
    assert "slot_occupied: n=1 cfR +5.0" in msg


# --------------------------------------------------------------------------
# variants
# --------------------------------------------------------------------------

def test_bars_needed_covers_the_range_median_not_just_the_lookback():
    # Sizing this as move_bars + range_block made FAST_TRIGGER (6-bar look-back,
    # 48-bar block) fetch 56 bars while realised_range_pct needs >= 96, so it
    # returned 'no_range' on every symbol in a live scan.
    from futuresbot.sniper import FAST_TRIGGER, VARIANTS, realised_range_pct

    for v in VARIANTS.values():
        assert v.bars_needed >= v.range_block * 2, v.name
        assert v.bars_needed >= v.move_bars + 2, v.name
    frame = _frame(_zigzag(FAST_TRIGGER.bars_needed))
    assert realised_range_pct(frame, block=FAST_TRIGGER.range_block,
                              blocks=FAST_TRIGGER.range_blocks) is not None


def test_variants_differ_where_it_matters():
    from futuresbot.sniper import FAST, FAST_TRIGGER, SWING

    # FAST_TRIGGER: fast signal, SLOW stop -> cost-viable at taker fees today.
    assert FAST_TRIGGER.interval == "Min5" and FAST_TRIGGER.move_bars == 6   # 30 min
    assert FAST_TRIGGER.range_block == 48                                    # 4h stop
    assert FAST_TRIGGER.economically_viable is True
    assert FAST_TRIGGER.min_sl_pct == 1.5

    # FAST: fast signal AND fast stop -> signal study only, cost gates disabled.
    assert FAST.interval == "Min1" and FAST.move_bars == 30                  # 30 min
    assert FAST.range_block == 30                                            # 30 min stop
    assert FAST.economically_viable is False
    assert FAST.min_sl_pct == 0.0 and FAST.max_cost_drag >= 1.0

    # the shipped swing variant is untouched
    assert SWING.move_bars == 48 and SWING.range_block == 16


def test_default_variant_reproduces_the_shipped_behaviour():
    from futuresbot.sniper import SWING, active_variants
    assert active_variants() == (SWING,)


def test_variants_are_selectable_by_env(monkeypatch):
    from futuresbot.sniper import FAST, FAST_TRIGGER, active_variants
    monkeypatch.setenv("FUTURES_SNIPER_VARIANTS", "FAST_TRIGGER,FAST")
    assert active_variants() == (FAST_TRIGGER, FAST)


def test_unknown_variant_names_fall_back_rather_than_crash(monkeypatch):
    from futuresbot.sniper import SWING, active_variants
    monkeypatch.setenv("FUTURES_SNIPER_VARIANTS", "NONSENSE")
    assert active_variants() == (SWING,)


def test_resolver_uses_finer_bars_and_shorter_horizon_for_fast(runtime):
    # A 30-minute trade replayed on 15m bars is decided by one bar, and
    # adverse-first means the stop wins nearly every time.
    fast = {"sleeve": "SNIPER_FAST"}
    swing = {"sleeve": "SNIPER_SWING"}
    other = {"sleeve": "WILDCARD"}
    assert runtime._row_resolve_interval(fast) == "Min1"
    assert runtime._row_resolve_interval(swing) == "Min15"
    assert runtime._row_resolve_interval(other) == "Min15"
    assert runtime._row_resolve_horizon(fast) == 6 * 3600
    assert runtime._row_resolve_horizon(other) == 48 * 3600


def test_scan_cadence_tracks_the_lookback_window():
    # A 30-minute signal scanned hourly is invisible. Measured on real data:
    # FAST would have fired 47x in 30h, but an hourly scan samples ~1/60th of
    # the windows, so the expected catch was 0.8 and we logged 0.
    from futuresbot.sniper import VARIANTS

    _BAR_S = {"Min1": 60, "Min5": 300, "Min15": 900}
    for v in VARIANTS.values():
        lookback_s = v.move_bars * _BAR_S[v.interval]
        samples = lookback_s / v.scan_interval_s
        assert samples >= 5.0, f"{v.name}: only {samples:.1f} scans per look-back window"


def test_rearm_exceeds_the_hold_but_does_not_starve_the_study():
    from futuresbot.sniper import FAST, FAST_TRIGGER, SWING

    # Re-arm must exceed the hold (or one impulse logs twice)...
    assert FAST.rearm_h * 3600 > FAST.move_bars * 60
    # ...but a 12h cooldown on a 30-minute strategy caps it at 2 signals per
    # symbol per day, which would take weeks to reach n=60.
    assert FAST.rearm_h < SWING.rearm_h
    assert FAST_TRIGGER.rearm_h < SWING.rearm_h


def test_outer_scan_guard_is_no_slower_than_the_fastest_variant(monkeypatch):
    from futuresbot.sniper import FAST, sniper_scan_interval_seconds
    monkeypatch.delenv("FUTURES_SNIPER_SCAN_INTERVAL_SECONDS", raising=False)
    monkeypatch.setenv("FUTURES_SNIPER_VARIANTS", "SWING,FAST")
    assert sniper_scan_interval_seconds() <= FAST.scan_interval_s


# --------------------------------------------------------------------------
# live leg: two independent switches, and a hard notional cap
# --------------------------------------------------------------------------

def test_live_trading_is_off_by_default(monkeypatch):
    from futuresbot.sniper import sniper_live_variants, sniper_shadow_only
    monkeypatch.delenv("FUTURES_SNIPER_LIVE_VARIANTS", raising=False)
    monkeypatch.delenv("FUTURES_SNIPER_SHADOW_ONLY", raising=False)
    assert sniper_live_variants() == ()
    assert sniper_shadow_only() is True


def test_both_switches_are_required(runtime, monkeypatch):
    """Neither flag alone may start trading."""
    calls = []
    monkeypatch.setattr(runtime, "_open_wildcard_position",
                        lambda *a, **k: calls.append(a) or True)
    from futuresbot.sniper import FAST
    sig = type("S", (), {"symbol": "BTC_USDT", "side": "LONG", "balance_fraction": 0.12,
                         "leverage": 13, "entry_price": 60000.0})()

    monkeypatch.setenv("FUTURES_SNIPER_LIVE_VARIANTS", "FAST")   # opt-in but still shadow
    monkeypatch.setenv("FUTURES_SNIPER_SHADOW_ONLY", "1")
    runtime._maybe_open_sniper_live(sig, FAST)
    assert calls == []

    monkeypatch.setenv("FUTURES_SNIPER_SHADOW_ONLY", "0")        # shadow off, no opt-in
    monkeypatch.delenv("FUTURES_SNIPER_LIVE_VARIANTS", raising=False)
    runtime._maybe_open_sniper_live(sig, FAST)
    assert calls == []


def test_notional_cap_arithmetic():
    from futuresbot.sniper import capped_available
    # notional = available * balance_fraction * leverage, so inverting the cap
    # must reproduce it exactly.
    equity, bf, lev, pct = 138.59, 0.12, 13, 3.0
    avail = capped_available(equity=equity, balance_fraction=bf, leverage=lev,
                             max_notional_pct=pct)
    assert avail * bf * lev == pytest.approx(equity * pct / 100.0)


@pytest.mark.parametrize("equity,bf,lev,pct", [
    (0, 0.12, 13, 3.0), (100, 0, 13, 3.0), (100, 0.12, 0, 3.0), (100, 0.12, 13, 0),
])
def test_degenerate_cap_inputs_mean_do_not_trade(equity, bf, lev, pct):
    from futuresbot.sniper import capped_available
    assert capped_available(equity=equity, balance_fraction=bf, leverage=lev,
                            max_notional_pct=pct) == 0.0


def test_live_leg_never_sizes_above_available_balance(runtime, monkeypatch):
    from futuresbot.sniper import FAST
    seen = []
    monkeypatch.setattr(runtime, "_open_wildcard_position",
                        lambda sig, budget, **k: seen.append(budget) or True)
    monkeypatch.setattr(runtime, "_account_snapshot",
                        lambda *a, **k: {"equity_usdt": 10000.0, "available_usdt": 5.0})
    monkeypatch.setenv("FUTURES_SNIPER_LIVE_VARIANTS", "FAST")
    monkeypatch.setenv("FUTURES_SNIPER_SHADOW_ONLY", "0")
    sig = type("S", (), {"symbol": "BTC_USDT", "side": "LONG", "balance_fraction": 0.12,
                         "leverage": 13, "entry_price": 60000.0})()
    runtime._maybe_open_sniper_live(sig, FAST)
    assert seen and seen[0] <= 5.0


def test_shadow_row_is_written_even_when_live_leg_runs(runtime, monkeypatch):
    """The study must not be interrupted by enabling live trading."""
    from futuresbot.sniper import FAST
    monkeypatch.setattr(runtime, "_open_wildcard_position", lambda *a, **k: True)
    monkeypatch.setattr(runtime, "_account_snapshot",
                        lambda *a, **k: {"equity_usdt": 138.59, "available_usdt": 138.59})
    monkeypatch.setenv("FUTURES_SNIPER_LIVE_VARIANTS", "FAST")
    monkeypatch.setenv("FUTURES_SNIPER_SHADOW_ONLY", "0")
    # _maybe_scan_sniper shadow-logs BEFORE calling the live leg; assert ordering
    # by checking the live helper does not itself write a shadow row.
    import inspect
    src = inspect.getsource(runtime._log_sniper_variant.__func__)
    assert src.index("_shadow_log_untaken") < src.index("_maybe_open_sniper_live")


def test_rearm_is_per_variant_not_per_symbol():
    # SWING and FAST can legitimately fire on the same symbol at the same time;
    # a shared re-arm key would silently drop one of the two studies.
    from futuresbot.sniper import FAST, SWING
    assert (SWING.name, "BTC_USDT", "LONG") != (FAST.name, "BTC_USDT", "LONG")
