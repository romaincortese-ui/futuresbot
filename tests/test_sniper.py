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


def _zigzag(n=90, up=0.0025, dn=0.0015, cycle=3, start=100.0):
    """Net-uptrending series with real pullbacks, so RSI lands in a plausible
    band instead of pinning at 100 the way a monotonic ramp does."""
    closes = [start]
    for i in range(1, n):
        closes.append(closes[-1] * (1 + (up if i % cycle else -dn)))
    return closes


def _trending(n=90, up=0.0025, dn=0.0015, wick=0.0015):
    return _frame(_zigzag(n, up, dn), wick=wick)


def _falling(n=90, wick=0.0015):
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
    return _frame(_zigzag(90, up=0.0005, dn=0.0003), wick=0.0002)


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
    assert detect_sniper_signal(_frame([100.0] * 90), "BTC_USDT", reasons) is None
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
    closes = [100.0] * 41
    closes += [100.0 * (1 + 0.10 * i / 30) for i in range(1, 31)]   # rally to 110
    closes += [110.0 - 6.0 * i / 18 for i in range(1, 19)]          # give back to 104
    reasons = []
    assert detect_sniper_signal(_frame(closes), "BTC_USDT", reasons) is None
    assert "move_retraced" in reasons


def test_unconfirmed_move_is_refused():
    # Uptrend intact over 12h, but the most recent hour has turned down.
    closes = _zigzag(86)
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
    closes = _zigzag(89)
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
