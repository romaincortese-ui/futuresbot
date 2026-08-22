"""/simulation must actually RENDER.

tests/test_simulation.py covered the arithmetic thoroughly and the command still
failed live with `NameError: name 'shadow' is not defined`, because nothing ever
called the message builder. Pure-function tests cannot catch a missing import in
the caller. These render the message end to end — empty trial, closed trades, and
open positions — so that whole class of error surfaces in CI instead of Telegram.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from futuresbot.config import FuturesConfig
from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime


@pytest.fixture
def rt(tmp_path, monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    # TRIAL_START/TRIAL_LABEL are module constants computed at import time, so
    # setting the env here would not move them — patch the constants themselves.
    import futuresbot.learning_digest as ld
    monkeypatch.setattr(ld, "TRIAL_START", 1000.0)
    monkeypatch.setattr(ld, "TRIAL_LABEL", "16")
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "rt.json"),
                  status_file=str(tmp_path / "st.json"),
                  telegram_token="", telegram_chat_id="")
    r = object.__new__(FuturesRuntime)
    r.config = cfg
    r.open_positions = {}
    r._feature_rows = []
    monkeypatch.setattr(r, "_last_known_equity", lambda: 182.56)
    return r


def _row(pnl, r_mult, ts=2000.0, **kw):
    row = {"ts": ts, "kind": "WILDCARD", "pnl_usdt": pnl, "r_multiple": r_mult,
           "risk_pct_actual": 2.41, "equity_at_entry": 165.0,
           "equity_at_close_usdt": 182.56, "margin_used": 22.3, "leverage": 2,
           "sl_margin_pct": 14.54, "hold_hours": 7.0}
    row.update(kw)
    return row


def _pos(symbol="ZEC_USDT", entry=836.0, sl=805.0, mark=850.0):
    return FuturesPosition(
        symbol=symbol, side="LONG", entry_price=entry, contracts=10,
        contract_size=0.01, leverage=5, margin_usdt=6.72,
        tp_price=entry * 1.12, sl_price=sl, position_id="1", order_id="1",
        opened_at=datetime.now(timezone.utc) - timedelta(hours=1),
        score=0.0, certainty=0.0, entry_signal="TREND_LONG",
        metadata={"trend": 1.0, "sl_margin_pct": 19.4},
    )


def test_renders_with_no_trades(rt, monkeypatch):
    monkeypatch.setattr(rt, "_feature_rows_cached", lambda *a, **k: [])
    msg = rt._build_simulation_message()
    assert "Simulation" in msg and "Trial 16" in msg
    assert "nothing to simulate" in msg


def test_renders_the_balance_table(rt, monkeypatch):
    """The regression: this call path was never exercised and shipped broken."""
    monkeypatch.setattr(rt, "_feature_rows_cached",
                        lambda *a, **k: [_row(-0.76, -1.02), _row(17.94, 5.09)])
    msg = rt._build_simulation_message()
    assert "Trial 16" in msg
    assert "2 closed" in msg
    assert "netR <b>+4.07</b>" in msg
    for bal in ("$1,000", "$2,000", "$5,000", "$10,000"):
        assert bal in msg
    # capacity warning carries real numbers, not a bare caveat
    assert "notional" in msg


def test_rows_outside_the_trial_are_excluded(rt, monkeypatch):
    monkeypatch.setattr(rt, "_feature_rows_cached",
                        lambda *a, **k: [_row(99.0, 9.0, ts=500.0),   # before start
                                         _row(17.94, 5.09, ts=2000.0)])
    msg = rt._build_simulation_message()
    assert "1 closed" in msg
    assert "99" not in msg


def test_non_convex_rows_are_excluded(rt, monkeypatch):
    monkeypatch.setattr(rt, "_feature_rows_cached",
                        lambda *a, **k: [_row(0.17, 0.0, kind="PMT"),
                                         _row(17.94, 5.09)])
    msg = rt._build_simulation_message()
    assert "1 closed" in msg


def test_open_positions_are_marked_into_the_message(rt, monkeypatch):
    monkeypatch.setattr(rt, "_feature_rows_cached", lambda *a, **k: [_row(17.94, 5.09)])
    rt.open_positions = {"ZEC_USDT": _pos()}
    monkeypatch.setattr(rt, "_sleeve_kind", lambda p: "TREND")

    class _C:
        def get_fair_price(self, sym):
            return 850.0
    rt.client = _C()
    msg = rt._build_simulation_message()
    assert "open" in msg


def test_a_price_lookup_failure_does_not_break_the_message(rt, monkeypatch):
    """A Telegram command must render even when the exchange misbehaves."""
    monkeypatch.setattr(rt, "_feature_rows_cached", lambda *a, **k: [_row(17.94, 5.09)])
    rt.open_positions = {"ZEC_USDT": _pos()}
    monkeypatch.setattr(rt, "_sleeve_kind", lambda p: "TREND")

    class _C:
        def get_fair_price(self, sym):
            raise RuntimeError("exchange down")
    rt.client = _C()
    msg = rt._build_simulation_message()
    assert "Trial 16" in msg and "1 closed" in msg
