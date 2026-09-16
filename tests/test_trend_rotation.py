"""The rotating TREND universe slot: ETH/XRP/ZEC plus one coin, re-picked every 48h.

Shipped 2026-09-16 as a TRIAL after three pre-registered universe studies. The
measured cell is "list + 1, 48h, shared slots": +$50.6/month [-$0.2, +$102.7].
These tests pin the properties that make it safe to run with real money:
  - OFF by default, and the static list is the fallback on every failure;
  - the pick is held for its whole window and survives a restart;
  - a rotated-out symbol is never force-closed;
  - the liquidity and history floors actually exclude the thin pump names that
    made the earlier monthly-rotation study unfillable.
"""
from __future__ import annotations

import math
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from futuresbot import trend_rotation as rot
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import build_contract_frame
from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime


def _cand(symbol, *, vol=1.0, mom=0.1, attn=1.5, t30=50e6, t7=50e6, days=200.0):
    return rot.Candidate(symbol=symbol, vol_7d=vol, mom=mom, attn=attn,
                         turnover_30d=t30, turnover_7d=t7, history_days=days)


# --- the ranking rule --------------------------------------------------------

def test_rank_pick_takes_the_best_average_rank():
    cands = [
        _cand("A_USDT", vol=2.0, mom=0.50, attn=3.0),   # ranks 1,1,1 -> 1.00
        _cand("B_USDT", vol=1.9, mom=0.40, attn=2.0),   # ranks 2,2,2 -> 2.00
        _cand("C_USDT", vol=0.5, mom=0.05, attn=1.0),
    ]
    pick = rot.rank_pick(cands)
    assert pick.symbol == "A_USDT"
    assert pick.score == pytest.approx(1.0)
    assert pick.pool_size == 3


def test_no_single_metric_decides_the_pick():
    """The highest volatility name loses to the one that ranks well on all three."""
    cands = [
        _cand("VOLONLY_USDT", vol=9.0, mom=-0.20, attn=0.5),   # 1,3,3 -> 2.33
        _cand("BALANCED_USDT", vol=2.0, mom=0.30, attn=2.0),   # 2,1,1 -> 1.33
        _cand("QUIET_USDT", vol=1.0, mom=0.10, attn=1.0),      # 3,2,2 -> 2.33
    ]
    assert rot.rank_pick(cands).symbol == "BALANCED_USDT"


def test_thin_and_young_names_are_excluded():
    cands = [
        _cand("PUMP_USDT", vol=9.0, mom=2.0, attn=9.0, t7=400_000, t30=400_000),  # too thin
        _cand("NEW_USDT", vol=8.0, mom=1.5, attn=8.0, days=20.0),                 # too young
        _cand("LIQUID_USDT", vol=1.2, mom=0.10, attn=1.2),
    ]
    pick = rot.rank_pick(cands)
    assert pick.symbol == "LIQUID_USDT"
    assert pick.pool_size == 1


def test_pool_is_capped_by_turnover_rank():
    cands = [_cand(f"S{i}_USDT", vol=1.0 + i / 100, mom=0.01 * i, attn=1.0, t30=1e6 * (100 - i))
             for i in range(60)]
    pool = rot.eligible(cands, min_turnover=0.0, min_days=0.0, top_n=40)
    assert len(pool) == 40
    assert pool[0].turnover_30d > pool[-1].turnover_30d


def test_empty_pool_returns_no_pick():
    assert rot.rank_pick([]) is None
    assert rot.rank_pick([_cand("THIN_USDT", t7=1.0, t30=1.0)]) is None


# --- metrics from bars -------------------------------------------------------

def _hourly_rows(hours=1600, *, drift=0.001, turnover=5e6, start_ts=1_700_000_000):
    rows = []
    price = 100.0
    for i in range(hours):
        price *= math.exp(drift + (0.002 if i % 3 == 0 else -0.0015))
        rows.append((start_ts + i * 3600, price, turnover / 24.0))
    return rows


def test_metrics_measure_what_the_rule_says():
    rows = _hourly_rows()
    c = rot.metrics_from_hourly("X_USDT", rows, window_hours=48)
    assert c is not None
    assert c.history_days == pytest.approx((len(rows) - 1) / 24.0, rel=1e-6)
    expected_mom = rows[-1][1] / rows[-49][1] - 1.0
    assert c.mom == pytest.approx(expected_mom, rel=1e-9)
    assert c.turnover_30d == pytest.approx(5e6, rel=1e-6)
    assert c.attn == pytest.approx(1.0, rel=1e-6)
    assert c.vol_7d > 0


def test_metrics_refuse_a_short_history():
    assert rot.metrics_from_hourly("X_USDT", _hourly_rows(20), window_hours=48) is None


# --- runtime wiring ----------------------------------------------------------

class _Client:
    def __init__(self, tickers=None, frames=None, raise_on_klines=False):
        self._tickers = tickers or []
        self._frames = frames or {}
        self.raise_on_klines = raise_on_klines
        self.kline_calls: list[str] = []

    def get_all_tickers(self):
        return self._tickers

    def get_klines(self, symbol, *, interval="Min15", start=None, end=None):
        self.kline_calls.append(symbol)
        if self.raise_on_klines:
            raise RuntimeError("kline outage")
        return self._frames.get(symbol, pd.DataFrame())

    def get_account_asset(self, currency: str = "USDT"):
        return {"availableBalance": "1000", "equity": "1000"}

    def get_updates(self, *, offset=None, limit: int = 5, timeout: int = 0):
        return []


def _frame(rows, *, drop_amount: bool = False):
    """Build the frame the way production does: through build_contract_frame on a
    MEXC-shaped payload. A fixture that hand-rolls the columns tests nothing about
    the adapter that actually runs."""
    payload = {"data": {
        "time": [int(r[0]) for r in rows],
        "open": [r[1] for r in rows],
        "high": [r[1] for r in rows],
        "low": [r[1] for r in rows],
        "close": [r[1] for r in rows],
        "vol": [r[2] / max(r[1], 1e-9) for r in rows],      # contracts, as MEXC sends
        "amount": [r[2] for r in rows],                      # quote turnover, USDT
    }}
    if drop_amount:
        payload["data"].pop("amount")
    return build_contract_frame(payload)


def _runtime(tmp_path, client) -> FuturesRuntime:
    config = replace(
        FuturesConfig.from_env(),
        symbol="BTC_USDT", symbols=("BTC_USDT",),
        runtime_state_file=str(tmp_path / "state.json"),
        status_file=str(tmp_path / "status.json"),
        telegram_token="token", telegram_chat_id="1",
    )
    runtime = FuturesRuntime(config, client)
    runtime._notify = lambda message, parse_mode="HTML": None
    return runtime


def _live_like_client():
    tickers = [
        {"symbol": "HOT_USDT", "amount24": 90e6},
        {"symbol": "MILD_USDT", "amount24": 70e6},
        {"symbol": "THIN_USDT", "amount24": 5e6},
        {"symbol": "ETH_USDT", "amount24": 900e6},        # static, must be skipped
        {"symbol": "TESLASTOCK_USDT", "amount24": 500e6},  # not crypto, must be skipped
    ]
    frames = {
        "HOT_USDT": _frame(_hourly_rows(drift=0.004, turnover=90e6)),
        "MILD_USDT": _frame(_hourly_rows(drift=0.0005, turnover=70e6)),
        "THIN_USDT": _frame(_hourly_rows(drift=0.01, turnover=200_000)),
    }
    return _Client(tickers=tickers, frames=frames)


def test_rotation_is_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("FUTURES_TREND_ROTATION_ENABLED", raising=False)
    runtime = _runtime(tmp_path, _live_like_client())
    assert runtime._trend_rotation_symbol() is None
    assert runtime.client.kline_calls == []


def test_pick_skips_static_and_non_crypto_and_thin_names(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_TREND_ROTATION_ENABLED", "1")
    monkeypatch.setenv("FUTURES_TREND_SYMBOLS", "ETH_USDT,XRP_USDT,ZEC_USDT")
    client = _live_like_client()
    runtime = _runtime(tmp_path, client)

    symbol = runtime._trend_rotation_symbol()

    assert symbol == "HOT_USDT"
    assert "ETH_USDT" not in client.kline_calls
    assert "TESLASTOCK_USDT" not in client.kline_calls
    assert runtime._trend_rotation["symbol"] == "HOT_USDT"


def test_pick_is_held_for_its_window_and_survives_a_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_TREND_ROTATION_ENABLED", "1")
    client = _live_like_client()
    runtime = _runtime(tmp_path, client)
    first = runtime._trend_rotation_symbol()
    calls_after_first = len(client.kline_calls)

    assert runtime._trend_rotation_symbol() == first
    assert len(client.kline_calls) == calls_after_first          # no re-pick inside the window

    reloaded = _runtime(tmp_path, _live_like_client())            # same state file
    assert reloaded._trend_rotation.get("symbol") == first
    assert reloaded._trend_rotation_symbol() == first
    assert reloaded.client.kline_calls == []


def test_expired_window_re_picks(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_TREND_ROTATION_ENABLED", "1")
    runtime = _runtime(tmp_path, _live_like_client())
    runtime._trend_rotation_symbol()
    runtime._trend_rotation["until"] = time.time() - 1.0
    runtime.client.kline_calls.clear()

    assert runtime._trend_rotation_symbol() == "HOT_USDT"
    assert runtime.client.kline_calls                              # it did re-rank


def test_outage_holds_the_previous_pick_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_TREND_ROTATION_ENABLED", "1")
    runtime = _runtime(tmp_path, _live_like_client())
    first = runtime._trend_rotation_symbol()

    runtime._trend_rotation["until"] = time.time() - 1.0
    runtime.client = _Client(tickers=[], frames={}, raise_on_klines=True)
    assert runtime._trend_rotation_symbol() == first               # held, not dropped


def test_no_history_and_no_previous_pick_falls_back_to_the_static_list(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_TREND_ROTATION_ENABLED", "1")
    runtime = _runtime(tmp_path, _Client(tickers=[], frames={}))
    assert runtime._trend_rotation_symbol() is None


def test_turning_rotation_off_clears_the_pick(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_TREND_ROTATION_ENABLED", "1")
    runtime = _runtime(tmp_path, _live_like_client())
    assert runtime._trend_rotation_symbol() == "HOT_USDT"
    monkeypatch.setenv("FUTURES_TREND_ROTATION_ENABLED", "0")
    assert runtime._trend_rotation_symbol() is None
    assert runtime._trend_rotation == {}


def test_a_held_position_is_never_force_closed_by_a_rotation(tmp_path, monkeypatch):
    """The scan only ADDS symbols; exits are owned by the position's own rules."""
    monkeypatch.setenv("FUTURES_TREND_ROTATION_ENABLED", "1")
    runtime = _runtime(tmp_path, _live_like_client())
    runtime._trend_rotation_symbol()
    position = FuturesPosition(
        symbol="HOT_USDT", side="LONG", entry_price=100.0, contracts=1, contract_size=1.0,
        leverage=5, margin_usdt=20.0, tp_price=115.0, sl_price=95.0, position_id="1", order_id="1",
        opened_at=datetime.now(timezone.utc) - timedelta(minutes=5), score=96.0, certainty=0.9,
        entry_signal="TREND_LONG", metadata={"wildcard": 1.0, "trend": 1.0},
    )
    runtime.open_positions["HOT_USDT"] = position

    runtime._trend_rotation["until"] = time.time() - 1.0
    runtime._trend_rotation_symbol()                               # rotates: HOT is held, so skipped

    assert runtime.open_positions["HOT_USDT"] is position
    assert runtime._trend_rotation.get("symbol") != "HOT_USDT"


# --- regressions from the pre-deploy review ----------------------------------

def test_turnover_is_quote_currency_not_contracts():
    """`vol x close` is contracts x price: wrong by contractSize, which spans 1e-4
    to 1e7 across MEXC perps. Without `amount` there is no candidate at all."""
    rows = _hourly_rows(turnover=8e6)
    frame = _frame(rows)
    assert "amount" in frame
    built = FuturesRuntime._hourly_rows_for_rotation(frame)
    assert built
    assert built[0][2] == pytest.approx(8e6 / 24.0, rel=1e-6)
    assert FuturesRuntime._hourly_rows_for_rotation(_frame(rows, drop_amount=True)) == []


def test_a_frame_without_amount_still_serves_every_other_scan():
    """The adapter change must not delete bars for the sleeves that never read it."""
    frame = _frame(_hourly_rows(60), drop_amount=True)
    assert len(frame) == 60
    assert {"open", "high", "low", "close", "volume"} <= set(frame.columns)


def _sparse_rows(prints=60, *, span_days=62.0, start_ts=1_700_000_000, turnover=3e6):
    step = span_days * 86400 / max(1, prints - 1)
    rows, price = [], 100.0
    for i in range(prints):
        price *= 1.04
        rows.append((start_ts + i * step, price, turnover))
    return rows


def test_a_sparse_tape_cannot_win_on_a_60_day_span():
    """60 prints over 62 days used to rank first on all three metrics."""
    sparse = rot.metrics_from_hourly("DEAD_USDT", _sparse_rows(), window_hours=48)
    assert sparse is None
    live = rot.metrics_from_hourly("LIQUID_USDT", _hourly_rows(1600, turnover=40e6), window_hours=48)
    assert live is not None


def test_daily_turnover_is_bucketed_by_calendar_day_not_by_row_count():
    """A tape quoting every second hour used to report 2x its real daily turnover."""
    rows = [(r[0], r[1], r[2]) for i, r in enumerate(_hourly_rows(2400, turnover=6e6)) if i % 2 == 0]
    c = rot.metrics_from_hourly("GAPPY_USDT", rows, window_hours=48)
    assert c is not None
    assert c.turnover_30d == pytest.approx(3e6, rel=0.05)     # half the bars, half the day


def test_momentum_uses_wall_clock_hours_not_bar_count():
    rows = [(r[0], r[1], r[2]) for i, r in enumerate(_hourly_rows(2400)) if i % 2 == 0]
    c = rot.metrics_from_hourly("GAPPY_USDT", rows, window_hours=48)
    assert c is not None
    cutoff = rows[-1][0] - 48 * 3600
    base = next(px for ts, px, _a in reversed(rows) if ts <= cutoff)
    assert c.mom == pytest.approx(rows[-1][1] / base - 1.0, rel=1e-9)


def test_cold_start_failure_backs_off_instead_of_retrying_every_scan(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_TREND_ROTATION_ENABLED", "1")
    client = _Client(tickers=[], frames={})
    runtime = _runtime(tmp_path, client)

    assert runtime._trend_rotation_symbol() is None
    until = float(runtime._trend_rotation.get("until") or 0.0)
    assert until > time.time()                                   # a retry window was persisted

    runtime.client = _live_like_client()
    assert runtime._trend_rotation_symbol() is None               # still backing off
    assert runtime.client.kline_calls == []


def test_corrupt_rotation_state_cannot_kill_the_sleeve(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_TREND_ROTATION_ENABLED", "1")
    runtime = _runtime(tmp_path, _live_like_client())
    runtime._trend_rotation = FuturesRuntime._coerce_rotation_state({"symbol": "FOO_USDT", "until": "soon"})
    assert runtime._trend_rotation == {}
    assert runtime._trend_rotation_symbol() == "HOT_USDT"        # re-picks instead of raising
    assert runtime._trend_status_lines()                          # and the status line renders


def test_delisting_and_paused_contracts_are_not_pickable(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_TREND_ROTATION_ENABLED", "1")
    client = _live_like_client()
    client.get_all_contract_details = lambda: [
        {"symbol": "HOT_USDT", "state": 1},                      # paused / pre-delisting
        {"symbol": "MILD_USDT", "state": 0},
    ]
    runtime = _runtime(tmp_path, client)
    assert runtime._trend_rotation_symbol() == "MILD_USDT"


def test_the_rotating_symbol_reaches_the_trend_detector(tmp_path, monkeypatch):
    """The three lines that put the pick in front of detect_trend_signal."""
    monkeypatch.setenv("FUTURES_TREND_ROTATION_ENABLED", "1")
    monkeypatch.setenv("FUTURES_TREND_ENABLED", "1")
    monkeypatch.setenv("FUTURES_TREND_SYMBOLS", "ETH_USDT,XRP_USDT,ZEC_USDT")
    client = _live_like_client()
    runtime = _runtime(tmp_path, client)
    runtime._account_snapshot = lambda *a, **k: {"available_usdt": 500.0}
    runtime._trend_rotation_symbol()                              # fix the pick first
    client.kline_calls.clear()
    runtime._last_trend_scan_at = 0.0

    runtime._maybe_scan_trend()

    scanned = [s for s in client.kline_calls]
    assert "HOT_USDT" in scanned
    assert {"ETH_USDT", "XRP_USDT", "ZEC_USDT"} <= set(scanned)
    assert scanned.count("HOT_USDT") == 1                         # never duplicated
    assert runtime._last_trend_scan.get("rotating") == "HOT_USDT"


def test_scan_falls_back_to_the_static_list_when_rotation_is_off(tmp_path, monkeypatch):
    monkeypatch.delenv("FUTURES_TREND_ROTATION_ENABLED", raising=False)
    monkeypatch.setenv("FUTURES_TREND_ENABLED", "1")
    monkeypatch.setenv("FUTURES_TREND_SYMBOLS", "ETH_USDT,XRP_USDT,ZEC_USDT")
    client = _live_like_client()
    runtime = _runtime(tmp_path, client)
    runtime._account_snapshot = lambda *a, **k: {"available_usdt": 500.0}
    runtime._last_trend_scan_at = 0.0

    runtime._maybe_scan_trend()

    assert set(client.kline_calls) == {"ETH_USDT", "XRP_USDT", "ZEC_USDT"}
