"""Big-3 TREND sleeve (2026-08-20, trial 15).

Built because ETH ran +17.4%/24h on 2026-08-19 and three independent blocks kept
the bot out: the wildcard excludes majors AND hunts a 3h impulse, the squeeze
needs a coil to release, PMT is decommissioned. Each test pins one property that
gap analysis demanded.
"""
from dataclasses import replace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from futuresbot import trend as T
from futuresbot.config import FuturesConfig
from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("FUTURES_TREND_ENABLED", "1")
    monkeypatch.delenv("FUTURES_TREND_LONG_ONLY", raising=False)
    monkeypatch.delenv("FUTURES_TREND_MIN_ROC", raising=False)
    monkeypatch.delenv("FUTURES_TREND_SYMBOLS", raising=False)


@pytest.fixture
def rt(tmp_path, monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "rt.json"),
                  status_file=str(tmp_path / "st.json"),
                  telegram_token="", telegram_chat_id="")
    return FuturesRuntime(cfg, MagicMock())


def _frame(closes, high_mult=1.002, low_mult=0.998):
    return pd.DataFrame({
        "open": closes,
        "high": [c * high_mult for c in closes],
        "low": [c * low_mult for c in closes],
        "close": closes,
        "volume": [1000.0] * len(closes),
    })


def _ramp(n=200, start=100.0, total=0.10):
    """A steady climb of `total` over the whole frame."""
    step = (1 + total) ** (1 / (n - 1))
    return [start * step ** i for i in range(n)]


# --------------------------------------------------------------------------
# The detector
# --------------------------------------------------------------------------

def test_fires_on_a_sustained_24h_move_at_a_new_closing_high():
    sig = T.detect_trend_signal(_frame(_ramp(total=0.20)), "ETH_USDT")
    assert sig is not None and sig.side == "LONG"
    assert sig.sl_price < sig.entry_price < sig.tp_price


def test_fires_short_on_a_sustained_decline():
    """The operator asked for both directions: a big DROP must trigger too."""
    sig = T.detect_trend_signal(_frame(_ramp(total=-0.20)), "ETH_USDT")
    assert sig is not None and sig.side == "SHORT"
    assert sig.tp_price < sig.entry_price < sig.sl_price


def test_a_quiet_market_produces_nothing():
    r = []
    assert T.detect_trend_signal(_frame(_ramp(total=0.005)), "BTC_USDT", r) is None
    assert r == ["roc_below_min"]


def test_a_faded_move_is_refused_even_when_the_24h_return_qualifies():
    """The move must still be BEING made. A +10% run that has rolled over is a
    fade, and buying it is the failure mode the closing-extreme test exists to
    prevent."""
    # Big enough that the 24h return still clears the 4% floor AFTER the fade,
    # so the rejection can only come from the closing-extreme test.
    closes = _ramp(total=0.60)
    closes[-6:] = [c * 0.94 for c in closes[-6:]]      # roll over at the end
    r = []
    assert T.detect_trend_signal(_frame(closes), "SOL_USDT", r) is None
    assert "no_new_extreme" in r


def test_extreme_is_CLOSING_not_intraday(monkeypatch):
    """The first probe demanded the close sit within a whisker of the bar's own
    HIGH. A violent 15m bar never does, and that version filtered out the entire
    ETH move it was written to catch. A tall wick must not disqualify a new
    closing high."""
    closes = _ramp(total=0.20)
    f = _frame(closes, high_mult=1.05)                 # 5% wick above every close
    assert T.detect_trend_signal(f, "ETH_USDT") is not None


# --------------------------------------------------------------------------
# Sizing — the leverage is a consequence of a tight stop, not a risk choice
# --------------------------------------------------------------------------

def test_stop_never_exceeds_the_margin_cap():
    for total in (0.05, 0.12, 0.25, -0.25):
        sig = T.detect_trend_signal(_frame(_ramp(total=total)), "BTC_USDT")
        if sig is not None:
            assert sig.sl_margin_pct <= 20.0 + 1e-6, f"{total}: {sig.sl_margin_pct}"


def test_a_tight_atr_buys_leverage_not_extra_risk():
    """On a major the ATR is small, so the cap re-derives x5-x10. The dollar
    risk per trade is unchanged — that is the whole point."""
    sig = T.detect_trend_signal(_frame(_ramp(total=0.10)), "ETH_USDT")
    assert sig is not None
    assert sig.leverage >= 2
    assert sig.sl_margin_pct <= 20.0


def test_short_target_is_clamped_above_zero():
    """Price cannot go below zero; an unclamped 3R short target on a wide stop
    is an unreachable order."""
    sig = T.detect_trend_signal(_frame(_ramp(total=-0.30)), "SOL_USDT")
    assert sig is not None and sig.tp_price > 0


# --------------------------------------------------------------------------
# The gap this sleeve exists to close
# --------------------------------------------------------------------------

def test_no_pullback_requirement():
    """pullback-resume vetoed the ETH move seven times and its own A/B could not
    prove it pays. A one-way climb must be tradeable here."""
    assert T.detect_trend_signal(_frame(_ramp(total=0.15)), "ETH_USDT") is not None


def test_defaults_to_the_big_three():
    assert T.trend_symbols() == ("BTC_USDT", "ETH_USDT", "SOL_USDT")


def test_shorts_are_live_by_default(monkeypatch):
    """The operator asked for both directions explicitly."""
    assert T.trend_long_only() is False
    monkeypatch.setenv("FUTURES_TREND_LONG_ONLY", "1")
    assert T.trend_long_only() is True


# --------------------------------------------------------------------------
# Runtime integration
# --------------------------------------------------------------------------

def _pos(**md):
    return FuturesPosition(
        symbol="ETH_USDT", side="LONG", entry_price=100.0, contracts=1,
        contract_size=1.0, leverage=5, margin_usdt=10.0, tp_price=130.0,
        sl_price=90.0, position_id="1", order_id="1", opened_at=None,
        score=96.0, certainty=0.9, entry_signal="TREND_LONG",
        metadata={"wildcard": 1.0, "sl_margin_pct": 20.0, **md})


def test_trend_position_is_not_counted_as_a_wildcard(rt):
    """The shared entry primitive stamps wildcard=1.0 on every convex position.
    If TREND is not tested first it silently eats a wildcard slot — the exact
    defect that made a SNIPER position indistinguishable in trial 6."""
    p = _pos(trend=1.0)
    assert rt._sleeve_kind(p) == "TREND"
    rt.open_positions["ETH_USDT"] = p
    assert rt._convex_open_count("TREND") == 1
    assert rt._convex_open_count("WILDCARD") == 0


def test_trend_inherits_the_convex_exit_stack(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    assert rt._is_wildcard_convex(_pos(trend=1.0)) is True


def test_trend_losses_feed_the_cold_streak_throttle(rt):
    """A drawdown protocol that cannot see one of the live sleeves is not a
    drawdown protocol."""
    rt.trade_history.extend([
        {"entry_signal": "TREND_LONG", "pnl_usdt": -1.0},
        {"entry_signal": "TREND_SHORT", "pnl_usdt": -1.0},
    ])
    assert rt._convex_loss_streak() == 2


def test_trend_rows_are_convex_for_the_shadow_resolver():
    from futuresbot import shadow_ledger as shadow

    assert "TREND" in shadow.CONVEX_SLEEVES


def test_status_and_why_both_surface_the_trend_slot(rt, monkeypatch):
    monkeypatch.setattr(rt, "_why_context",
                        lambda: (_ for _ in ()).throw(RuntimeError("no net")))
    why = rt._build_why_message()
    assert "trend 0/1" in why and "Big-3 trend" in why


def test_trend_status_line_reports_what_the_scan_saw(rt):
    import time as _t

    rt._last_trend_scan = {"at": _t.time() - 120, "scanned": 3, "cands": 0,
                           "hist": {"roc_below_min": 3}, "lookback_h": 24, "best": None}
    text = "\n".join(rt._trend_status_lines())
    assert "3 scanned" in text and "0</b> signals" in text
    assert "24h move too small ×3" in text
    assert "roc_below_min" not in text, "enums are jargon on a phone"
