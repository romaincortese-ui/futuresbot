"""Trial 24 - the random-direction strategy (FUTURES_RANDOM_MODE_ENABLED).

Frozen definition: wc/RANDOM/PREREG.md (sha256 29fabd853a4f5d77...). These tests pin:
  - the switch (C26: blank reads as unset = off) and that OFF is today's behaviour;
  - tick timing (00:00Z / 12:00Z, 15-minute grace) and once-only processing across restarts;
  - bucket order TREND -> WILDCARD-long -> WILDCARD-short, slots TREND 2 / WILDCARD 3 shared,
    the book AT the tick, held-symbol skip to the next best, the detector-then-fallback ranking;
  - the coin: fair, from os.urandom, never a seeded PRNG;
  - the order for the coin's side (TREND SHORT included) and the live exits on it;
  - a min-volume refusal leaving the slot empty until the next tick;
  - telemetry on positions, the trade record, the feature store, the shadow ledger, the journal;
  - the ported ranking against the backtest's own tick_candidates.json (fixture);
  - trial 25 (wc/TRIAL25/PREREG.md, sha256 23840ce65807b549...): the settings that choose the
    configuration (defaults = trial 24; 6h / natural / TREND stop 3.5; invalid values refused
    with an alert; PREREG tag per combination) and the logging they add.
"""
from __future__ import annotations

import inspect
import json
import math
import os
import random
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

import futuresbot.runtime as R
from futuresbot import random_mode as RM
from futuresbot import shadow_ledger
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime
from futuresbot.wildcard import WildcardSignal, detect_wildcard_signal

FIXTURE = Path(__file__).parent / "fixtures" / "random_mode_ticks.json"
T = int(datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc).timestamp())       # a 12:00Z tick

# The live detector / sizing / exit values (wc/RANDOM common.DETECTOR_ENV + exit_env.json).
LIVE_ENV = {
    "FUTURES_WILDCARD_ENABLED": "1", "FUTURES_TREND_ENABLED": "1",
    "FUTURES_WILDCARD_LEVERAGE": "5", "FUTURES_WILDCARD_SL_ATR_MULT": "3.0",
    "FUTURES_WILDCARD_TP_R": "5.0", "FUTURES_WILDCARD_MAX_SL_MARGIN_PCT": "20",
    "FUTURES_WILDCARD_MAX_SHORT_TP_DIST": "0.50", "FUTURES_WILDCARD_MIN_ROC": "0.08",
    "FUTURES_WILDCARD_REQUIRE_PULLBACK": "1", "FUTURES_WILDCARD_RSI_MAX": "90",
    "FUTURES_WILDCARD_RSI_MIN": "10", "FUTURES_WILDCARD_MAX_WICK": "0.45",
    "FUTURES_WILDCARD_VERTICAL_ATR_MULT": "2.0", "FUTURES_WILDCARD_MIN_VOL_Z": "1.0",
    "FUTURES_TREND_MIN_ROC": "0.04", "FUTURES_TREND_LOOKBACK_HOURS": "24",
    "FUTURES_TREND_LEVERAGE_MAX": "10", "FUTURES_TREND_SL_ATR_MULT": "3.0",
    "FUTURES_TREND_MAX_SL_MARGIN_PCT": "20", "FUTURES_TREND_TP_R": "3.0",
    "FUTURES_TREND_MAX_SHORT_TP_DIST": "0.50", "FUTURES_TREND_LONG_ONLY": "1",
    "FUTURES_TREND_SYMBOLS": "ETH_USDT,XRP_USDT,ZEC_USDT",
    "FUTURES_TREND_MAX_POSITIONS": "2", "FUTURES_WILDCARD_MAX_POSITIONS": "3",
    "FUTURES_WILDCARD_RISK_PCT": "0.01205", "FUTURES_TREND_RISK_PCT": "0.01205",
    "FUTURES_RISK_BASED_SIZING_ENABLED": "1", "FUTURES_MAX_TRADE_RISK_PCT": "5",
    "FUTURES_REGIME_SIZE_SCALER_ENABLED": "1", "FUTURES_REGIME_EFF_WINDOW": "24",
    "FUTURES_REGIME_EFF_LO": "0.20", "FUTURES_REGIME_EFF_HI": "0.45",
    "FUTURES_REGIME_FLOOR_MULT": "0.50", "FUTURES_TREND_FLAGGED_TP_R": "1.0",
    "FUTURES_WILDCARD_CONVEX_EXIT_ENABLED": "1", "FUTURES_CONVEX_TIME_STOP_HOURS": "24",
    "FUTURES_CONVEX_BREAKEVEN_ARM_R": "0.90", "FUTURES_CONVEX_TRAIL_RETAIN_FRAC": "0.50",
    "FUTURES_WILDCARD_EARLY_STOP_R": "0.5", "FUTURES_WILDCARD_EARLY_STOP_MINUTES": "30",
    "FUTURES_TREND_EARLY_STOP_R": "0.0", "FUTURES_CONVEX_STREAK_THROTTLE_ENABLED": "0",
    "FUTURES_EXTERNAL_GATE_ENABLED": "0", "FUTURES_ENTRY_ENVELOPE_ENABLED": "1",
    "MEXC_API_KEY": "k", "MEXC_API_SECRET": "s",
}


@pytest.fixture
def live_env(monkeypatch):
    for k in [k for k in os.environ if k.startswith("FUTURES_")]:
        monkeypatch.delenv(k, raising=False)
    for k, v in LIVE_ENV.items():
        monkeypatch.setenv(k, v)
    return monkeypatch


def _on(monkeypatch, on=True):
    monkeypatch.setenv("FUTURES_RANDOM_MODE_ENABLED", "1" if on else "0")


class FakeClient:
    """The exchange calls the entry and exit paths make; records every order."""

    def __init__(self, prices, *, min_vol=1, contract_size=1.0, max_lev=50, available=1000.0):
        self.prices = dict(prices)
        self.min_vol, self.contract_size, self.max_lev = min_vol, contract_size, max_lev
        self.available = available
        self.orders, self.tpsl, self.cancels, self.leverage = [], [], [], []
        self.positions: dict[str, dict] = {}
        self.klines: dict[str, pd.DataFrame] = {}

    def get_ticker(self, symbol):
        return {"lastPrice": self.prices.get(symbol, 0.0)}

    def get_fair_price(self, symbol):
        return self.prices.get(symbol, 0.0)

    def get_contract_detail(self, symbol):
        return {"contractSize": self.contract_size, "minVol": self.min_vol, "maxLeverage": self.max_lev}

    def get_account_asset(self, currency="USDT"):
        return {"availableBalance": str(self.available), "equity": str(self.available)}

    def change_position_mode(self, mode):
        return {}

    def change_leverage(self, **kw):
        self.leverage.append(kw)
        return {}

    def place_order(self, **kw):
        self.orders.append(kw)
        self.positions[kw["symbol"]] = {"positionType": 1 if kw["side"] == 1 else 2,
                                        "holdVol": kw["vol"], "positionId": str(900 + len(self.orders)),
                                        "holdAvgPrice": self.prices[kw["symbol"]]}
        return {"orderId": "O%d" % len(self.orders)}

    def get_order(self, order_id):
        return {}

    def get_open_positions(self, symbol=None, **kw):
        return [self.positions[symbol]] if symbol in self.positions else []

    def cancel_all_tpsl(self, **kw):
        self.cancels.append(kw)
        return {"success": True}

    def place_position_tpsl(self, **kw):
        self.tpsl.append(kw)
        return {"success": True}

    def get_klines(self, symbol, interval="Min15", start=None, end=None):
        return self.klines[symbol]

    def get_updates(self, **kw):
        return []


def _rt(tmp_path, client, *, paper=False) -> FuturesRuntime:
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "state.json"), status_file=str(tmp_path / "st.json"),
                  telegram_token="", telegram_chat_id="", paper_trade=paper, margin_budget_usdt=1000.0)
    rt = FuturesRuntime(cfg, client)
    rt._notify = lambda *a, **k: None
    rt._notify_once = lambda *a, **k: None
    rt._majors_sample = lambda max_age_s=None: (time.time(), {})
    rt._shadow_ledger_path = lambda: str(tmp_path / "shadow.jsonl")
    rt._feature_store_path = tmp_path / "features.jsonl"
    return rt


def _frame(closes, *, end_tick=T, vol=1000.0) -> pd.DataFrame:
    """15m bars whose last bar opens at end_tick - 900 (i.e. all closed by end_tick)."""
    n = len(closes)
    t = [end_tick - 900 * (n - i) for i in range(n)]
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999, "close": c,
                         "volume": [vol] * n},
                        index=pd.to_datetime(np.asarray(t, dtype=np.int64), unit="s", utc=True))


def _cand(sym, bucket, value, *, status="fallback", gate=100.0, atr=0.01, det=None, amount=5e6,
          rng=0.30):
    key = RM.KEY[bucket]
    row = {"symbol": sym, "usable": True, key: value, "gate_close": gate, "atr_pct": atr,
           "status": status, "detector": det, "reject": None if det else "roc_below_min",
           "calm_ratio": 0.4}
    if bucket != "TREND":
        row["ticker"] = {"range24": rng, "amount24": amount, "source": "ticker"}
    return row


def _plan(buckets: dict, *, frames=None, btc=False, tick=T) -> dict:
    fr = {"WILDCARD": {}, "TREND": {}}
    for b, cands in buckets.items():
        for c in cands:
            fr[RM.SLEEVE[b]].setdefault(c["symbol"], (frames or {}).get(c["symbol"])
                                        if frames else _frame(np.linspace(95, 100, 120)))
    return {"tick": tick, "buckets": dict(buckets), "frames": fr,
            "universe": [[c["symbol"], 0.3, 5e6] for b in ("WC_LONG", "WC_SHORT")
                         for c in buckets.get(b, [])],
            "unusable": [], "trend_symbols": [c["symbol"] for c in buckets.get("TREND", [])],
            "btc_flag": {"flagged": btc, "trend_flag": 1.0 if btc else 0.0}}


def _pos(sym, sleeve="WILDCARD", side="LONG", *, opened=None, md=None, entry=100.0, sl=None, tp=None,
         lev=5, contracts=10):
    sl = sl if sl is not None else (entry * 0.97 if side == "LONG" else entry * 1.03)
    tp = tp if tp is not None else (entry * 1.15 if side == "LONG" else entry * 0.85)
    meta = {"wildcard": 1.0, "sl_margin_pct": abs(entry - sl) / entry * lev * 100.0}
    if sleeve == "TREND":
        meta["trend"] = 1.0
    meta.update(md or {})
    return FuturesPosition(symbol=sym, side=side, entry_price=entry, contracts=contracts,
                           contract_size=1.0, leverage=lev,
                           margin_usdt=contracts * entry / lev, tp_price=tp, sl_price=sl,
                           position_id="7", order_id="1",
                           opened_at=opened or datetime.now(timezone.utc) - timedelta(minutes=5),
                           score=96.0, certainty=0.9, entry_signal=f"{sleeve}_{side}", metadata=meta)


# =====================================================================================
# the switch
# =====================================================================================

@pytest.mark.parametrize("raw,on", [(None, False), ("", False), ("   ", False), ("0", False),
                                    ("false", False), ("no", False), ("off", False),
                                    ("1", True), ("true", True), (" on ", True), ("YES", True)])
def test_the_switch_reads_blank_as_unset_c26(monkeypatch, raw, on):
    monkeypatch.delenv("FUTURES_RANDOM_MODE_ENABLED", raising=False)
    if raw is not None:
        monkeypatch.setenv("FUTURES_RANDOM_MODE_ENABLED", raw)
    assert RM.enabled() is on


# =====================================================================================
# tick timing and once-only processing
# =====================================================================================

def _ts(*a):
    return int(datetime(*a, tzinfo=timezone.utc).timestamp())


def test_ticks_are_0000z_and_1200z():
    assert RM.tick_at(_ts(2026, 10, 1, 0, 0, 30)) == _ts(2026, 10, 1, 0, 0)
    assert RM.tick_at(_ts(2026, 10, 1, 11, 59, 59)) == _ts(2026, 10, 1, 0, 0)
    assert RM.tick_at(_ts(2026, 10, 1, 12, 0, 0)) == _ts(2026, 10, 1, 12, 0)
    assert RM.next_tick(_ts(2026, 10, 1, 12, 0, 0)) == _ts(2026, 10, 2, 0, 0)
    assert RM.next_tick(_ts(2026, 10, 1, 23, 59, 59)) == _ts(2026, 10, 2, 0, 0)


def test_a_tick_is_due_once_and_only_inside_its_grace():
    assert RM.TICK_GRACE_SECONDS == 900
    assert RM.due_tick(T + 1, None) == T
    assert RM.due_tick(T + 900, None) == T
    assert RM.due_tick(T + 901, None) is None                    # too late: wait for the next
    assert RM.due_tick(T + 30, T) is None                        # already processed
    assert RM.due_tick(T + 30, T - 43200) == T
    assert RM.due_tick(T + 43200 + 5, T) == T + 43200
    assert RM.due_tick(T + 30, "garbage") == T


def _tick_runtime(tmp_path, live_env, calls, *, select=None):
    _on(live_env)
    rt = _rt(tmp_path, MagicMock())
    state_path = tmp_path / "state.json"

    def fake_select(tick, cfg=None):
        calls.append(("select", tick))
        if select is not None:
            return select(tick)
        return {"tick": tick, "buckets": {}, "frames": {}, "universe": [], "unusable": [],
                "trend_symbols": [], "btc_flag": None}

    def fake_execute(plan):
        # the tick must already be on disk when the first order could go out
        on_disk = json.loads(state_path.read_text(encoding="utf-8"))
        calls.append(("execute", plan["tick"], on_disk["random_mode"]["last_tick"]))
        return [{"bucket": "TREND", "decision": "opened", "symbol": "ETH_USDT", "side": "SHORT"}]

    rt._random_tick_select = fake_select
    rt._random_tick_execute = fake_execute
    return rt


def test_a_tick_is_processed_once_even_across_restarts(tmp_path, live_env):
    calls: list = []
    clock = {"now": T + 30}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    rt = _tick_runtime(tmp_path, live_env, calls)
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"]
    assert calls[1] == ("execute", T, T), "marked on disk BEFORE the first order"
    clock["now"] = T + 90
    rt._maybe_random_tick()                                  # same process, same tick
    assert len(calls) == 2
    rt2 = _tick_runtime(tmp_path, live_env, calls)           # restart, same state file
    clock["now"] = T + 120
    rt2._maybe_random_tick()
    assert len(calls) == 2, "a restart must not process a processed tick"
    clock["now"] = T + 43200 + 3                              # the next tick runs
    rt2._maybe_random_tick()
    assert calls[-1] == ("execute", T + 43200, T + 43200)
    journal = [json.loads(x) for x in (tmp_path / "futures_random_ticks.jsonl").read_text().splitlines()]
    assert [j["tick"] for j in journal] == [T, T + 43200]


def test_a_restart_inside_the_grace_still_processes_the_tick_and_after_it_waits(tmp_path, live_env):
    calls: list = []
    clock = {"now": T + 14 * 60}                             # restarted 14 min after the tick
    live_env.setattr(R.time, "time", lambda: clock["now"])
    rt = _tick_runtime(tmp_path, live_env, calls)
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"]
    calls.clear()
    (tmp_path / "late").mkdir()
    clock["now"] = T + 16 * 60                               # 16 min: too late for this tick
    rt = _tick_runtime(tmp_path / "late", live_env, calls)
    rt._maybe_random_tick()
    assert calls == []
    clock["now"] = T + 43200 + 1
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"] and calls[1][1] == T + 43200


def test_a_failed_selection_is_not_marked_and_is_retried(tmp_path, live_env):
    calls: list = []
    clock = {"now": T + 20}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    state = {"fail": True}

    def select(tick):
        if state["fail"]:
            raise RuntimeError("ticker down")
        return {"tick": tick, "buckets": {}, "frames": {}, "universe": [], "unusable": [],
                "trend_symbols": [], "btc_flag": None}
    rt = _tick_runtime(tmp_path, live_env, calls, select=select)
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select"] and not rt._random_mode_state
    state["fail"] = False
    clock["now"] = T + 80
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "select", "execute"]


def test_paused_ticks_are_not_processed_but_resume_inside_the_grace_runs_it(tmp_path, live_env):
    calls: list = []
    clock = {"now": T + 20}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    rt = _tick_runtime(tmp_path, live_env, calls)
    rt._paused = True
    rt._maybe_random_tick()
    assert calls == []
    assert "paused" in rt._random_mode_status_line()
    rt._paused = False
    clock["now"] = T + 300
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"]


def test_the_tick_waits_for_positions_the_backtest_closes_at_it(tmp_path, live_env):
    """A position opened at the tick 24h ago is closed AT this tick by the backtest; live
    closes it on its fill clock a little later. The tick waits (bounded), then runs."""
    calls: list = []
    clock = {"now": T + 2}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    rt = _tick_runtime(tmp_path, live_env, calls)
    due = _pos("OLD_USDT", md={"random_tick_ts": float(T - 86400)},
               opened=datetime.fromtimestamp(T - 86400 + 40, timezone.utc))
    rt.open_positions = {"OLD_USDT": due}
    rt._maybe_random_tick()
    assert calls == [] and rt._random_tick_pending == T
    assert rt._random_mode_sleep_seconds(300) <= 5
    assert "waiting on a 24h clock" in rt._random_mode_status_line()
    rt.open_positions = {}                                     # its clock fired
    clock["now"] = T + 45
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"] and rt._random_tick_pending is None
    # bounded: a close that never lands does not cost the tick
    calls.clear()
    (tmp_path / "b").mkdir()
    rt = _tick_runtime(tmp_path / "b", live_env, calls)
    rt.open_positions = {"OLD_USDT": due}
    clock["now"] = T + RM.TICK_DEFER_SECONDS + 1
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"]
    # a position opened 12h ago is NOT due
    calls.clear()
    (tmp_path / "c").mkdir()
    rt = _tick_runtime(tmp_path / "c", live_env, calls)
    rt.open_positions = {"MID_USDT": _pos("MID_USDT", md={"random_tick_ts": float(T - 43200)})}
    clock["now"] = T + 2
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"]


def test_the_cycle_sleep_lands_on_the_tick_only_when_on(tmp_path, live_env):
    rt = _rt(tmp_path, MagicMock())
    live_env.setattr(R.time, "time", lambda: T - 100.5)
    _on(live_env, False)
    assert rt._random_mode_sleep_seconds(300) == 300
    _on(live_env, True)
    assert rt._random_mode_sleep_seconds(300) == 102          # wakes 1 s after the tick
    assert rt._random_mode_sleep_seconds(60) == 60


# =====================================================================================
# buckets, slots, held, fallback
# =====================================================================================

def _exec(rt, plan, live_env, coins=None):
    """_random_tick_execute with _random_open stubbed: records (bucket, symbol, rank, coin)."""
    drawn: list[int] = []
    seq = iter(coins or [0, 1, 0, 1, 0, 1])

    def coin():
        c = next(seq)
        drawn.append(c)
        return c
    live_env.setattr(RM, "coin", coin)
    opened: list = []

    def fake_open(plan_, bucket, cand, rank_, field, coin_, held):
        opened.append((bucket, cand["symbol"], rank_, coin_, tuple(held)))
        sleeve = RM.SLEEVE[bucket]
        rt.open_positions[cand["symbol"]] = _pos(cand["symbol"], sleeve, RM.coin_side(coin_))
        return {"bucket": bucket, "decision": "opened", "symbol": cand["symbol"]}
    rt._random_open = fake_open
    rows: list = []
    rt._random_record = lambda plan_, bucket, cand, rank_, field, held, decision, **k: rows.append(
        (bucket, cand["symbol"], decision))
    decisions = rt._random_tick_execute(plan)
    return opened, drawn, decisions, rows


def _three_buckets():
    return {"TREND": [_cand("ETH_USDT", "TREND", 0.05), _cand("XRP_USDT", "TREND", 0.02)],
            "WC_LONG": [_cand("L1_USDT", "WC_LONG", 0.30), _cand("L2_USDT", "WC_LONG", 0.20)],
            "WC_SHORT": [_cand("S1_USDT", "WC_SHORT", -0.30), _cand("S2_USDT", "WC_SHORT", -0.20)]}


def test_bucket_order_is_trend_then_wildcard_long_then_short_one_coin_each(tmp_path, live_env):
    _on(live_env)
    rt = _rt(tmp_path, MagicMock())
    opened, drawn, decisions, _ = _exec(rt, _plan(_three_buckets()), live_env, coins=[1, 0, 1])
    assert [(o[0], o[1], o[2], o[3]) for o in opened] == [
        ("TREND", "ETH_USDT", 1, 1), ("WC_LONG", "L1_USDT", 1, 0), ("WC_SHORT", "S1_USDT", 1, 1)]
    assert drawn == [1, 0, 1]
    assert [d["decision"] for d in decisions] == ["opened"] * 3


@pytest.mark.parametrize("trend_open,wc_open,expect", [
    (2, 0, ["slot_full", "opened", "opened"]),
    (1, 2, ["opened", "opened", "slot_full"]),     # the third WILDCARD slot goes to WC_LONG
    (0, 3, ["opened", "slot_full", "slot_full"]),
    (0, 1, ["opened", "opened", "opened"]),
])
def test_slots_trend_2_wildcard_3_shared(tmp_path, live_env, trend_open, wc_open, expect):
    _on(live_env)
    rt = _rt(tmp_path, MagicMock())
    for i in range(trend_open):
        rt.open_positions[f"T{i}_USDT"] = _pos(f"T{i}_USDT", "TREND")
    for i in range(wc_open):
        rt.open_positions[f"W{i}_USDT"] = _pos(f"W{i}_USDT")
    opened, drawn, decisions, rows = _exec(rt, _plan(_three_buckets()), live_env)
    assert [d["decision"] for d in decisions] == expect
    assert len(drawn) == expect.count("opened"), "no coin is drawn for a full sleeve"
    assert [r for r in rows if r[2] == "slot_full"] == [
        (b, c, "slot_full") for b, c, e in zip(("TREND", "WC_LONG", "WC_SHORT"),
                                               ("ETH_USDT", "L1_USDT", "S1_USDT"), expect)
        if e == "slot_full"]


def test_the_book_is_the_book_at_the_tick(tmp_path, live_env):
    """Closed after the tick (the tick ran late): still occupies its slot and its symbol.
    A tick-opened position whose 24h clock from its own tick ended at this tick: does not."""
    _on(live_env)
    rt = _rt(tmp_path, MagicMock())
    iso = lambda ts: datetime.fromtimestamp(ts, timezone.utc).isoformat()  # noqa: E731
    rt.trade_history = [
        # open at the tick, stopped 20 s after it -> held at the tick
        {"symbol": "L1_USDT", "sleeve": "WILDCARD", "entry_time": iso(T - 3600), "exit_time": iso(T + 20)},
        {"symbol": "W2_USDT", "sleeve": "WILDCARD", "entry_time": iso(T - 7200), "exit_time": iso(T + 25)},
        # the 24h clock of a position opened at the previous-day tick, recorded 30 s late
        {"symbol": "S1_USDT", "sleeve": "WILDCARD", "entry_time": iso(T - 86400 + 30),
         "exit_time": iso(T + 30), "random_tick_ts": float(T - 86400)},
        # closed before the tick
        {"symbol": "ETH_USDT", "sleeve": "TREND", "entry_time": iso(T - 9000), "exit_time": iso(T - 60)},
    ]
    rt.open_positions["W3_USDT"] = _pos("W3_USDT")
    held, count = rt._random_book_at(T)
    assert held == {"L1_USDT", "W2_USDT", "W3_USDT"}
    assert count == {"TREND": 0, "WILDCARD": 3}
    _, _, decisions, _ = _exec(rt, _plan(_three_buckets()), live_env)
    assert [d["decision"] for d in decisions] == ["opened", "slot_full", "slot_full"]


def test_held_symbols_are_skipped_for_the_next_best(tmp_path, live_env):
    _on(live_env)
    rt = _rt(tmp_path, MagicMock())
    rt.open_positions["L1_USDT"] = _pos("L1_USDT")             # held from an earlier tick
    buckets = _three_buckets()
    buckets["WC_SHORT"] = [_cand("L2_USDT", "WC_SHORT", -0.4), _cand("S2_USDT", "WC_SHORT", -0.2)]
    opened, drawn, decisions, rows = _exec(rt, _plan(buckets), live_env)
    # WC_LONG: L1 held -> L2 at rank 2; WC_SHORT: L2 was opened at THIS tick -> S2 at rank 2
    assert [(o[0], o[1], o[2], o[4]) for o in opened] == [
        ("TREND", "ETH_USDT", 1, ()), ("WC_LONG", "L2_USDT", 2, ("L1_USDT",)),
        ("WC_SHORT", "S2_USDT", 2, ("L2_USDT",))]
    assert ("WC_LONG", "L1_USDT", "held") in rows and ("WC_SHORT", "L2_USDT", "held") in rows
    assert [d["decision"] for d in decisions] == ["opened", "held", "opened", "held", "opened"]


def test_an_empty_list_draws_no_coin(tmp_path, live_env):
    _on(live_env)
    rt = _rt(tmp_path, MagicMock())
    b = _three_buckets()
    b["WC_SHORT"] = []
    _, drawn, decisions, _ = _exec(rt, _plan(b), live_env)
    assert decisions[-1]["decision"] == "no_candidate" and len(drawn) == 2


def test_a_switched_off_sleeve_has_no_bucket(tmp_path, live_env):
    _on(live_env)
    rt = _rt(tmp_path, MagicMock())
    b = _three_buckets()
    del b["TREND"]
    _, _, decisions, _ = _exec(rt, _plan(b), live_env)
    assert decisions[0]["decision"] == "sleeve_disabled"


def _row(sym, roc, side=None, usable=True, key="roc3h"):
    return {"symbol": sym, "usable": usable, key: roc,
            "detector": {"side": side} if side else None}


def test_detector_passes_rank_first_then_the_fallback():
    rows = [_row("A", 0.30), _row("B", 0.09, "LONG"), _row("C", -0.25), _row("D", -0.10, "SHORT"),
            _row("E", 0.50, usable=False), _row("F", 0.12, "LONG")]
    longs, shorts = RM.rank_wildcard(rows)
    assert [(r["symbol"], r["status"]) for r in longs] == [
        ("F", "pass"), ("B", "pass"), ("A", "fallback"), ("D", "fallback"), ("C", "fallback")]
    assert [(r["symbol"], r["status"]) for r in shorts] == [
        ("D", "pass"), ("C", "fallback"), ("B", "fallback"), ("F", "fallback"), ("A", "fallback")]
    # no pass at all: pure fallback by the bucket's own ROC (the 163-of-168 case)
    longs, shorts = RM.rank_wildcard([_row("A", 0.30), _row("C", -0.25), _row("G", 0.01)])
    assert [r["symbol"] for r in longs] == ["A", "G", "C"] and {r["status"] for r in longs} == {"fallback"}
    assert [r["symbol"] for r in shorts] == ["C", "G", "A"]
    trend = RM.rank_trend([_row("ETH", 0.02, key="roc24h"), _row("XRP", 0.05, "LONG", key="roc24h"),
                           _row("ZEC", 0.09, "SHORT", key="roc24h")])
    assert [(r["symbol"], r["status"]) for r in trend] == [
        ("XRP", "pass"), ("ZEC", "fallback"), ("ETH", "fallback")]      # a SHORT signal is not a pass
    assert len(RM.rank_wildcard([_row(f"S{i}", i / 100) for i in range(30)])[0]) == RM.TOP_N


def test_the_universe_filter_is_the_prereg_one():
    tickers = [
        {"symbol": "A_USDT", "amount24": 3e6, "r": 0.50},
        {"symbol": "B_USDT", "amount24": 1.9e6, "r": 0.50},     # under $2M
        {"symbol": "C_USDT", "amount24": 9e6, "r": 0.069},       # under 7%
        {"symbol": "D_USDT", "amount24": 9e6, "r": 0.07},        # exactly 7%: in
        {"symbol": "ETH_USDT", "amount24": 9e9, "r": 0.20},      # majors band
        {"symbol": "XAU_USDT", "amount24": 9e6, "r": 0.20},      # not crypto
        {"symbol": "HELD_USDT", "amount24": 4e6, "r": 0.90},     # held: still in the universe
        {"symbol": "X_BTC", "amount24": 9e6, "r": 0.9},
    ]
    uni = RM.universe(tickers, majors={"ETH_USDT"}, tradeable=FuturesRuntime._is_tradeable_crypto,
                      range_of=lambda t: t["r"])
    assert [s for s, _ in uni] == ["HELD_USDT", "A_USDT", "D_USDT"]
    assert uni[1][1] == {"range24": 0.50, "amount24": 3e6, "source": "ticker"}
    assert RM.UNIVERSE_MIN_TURNOVER == 2_000_000.0 and RM.UNIVERSE_MIN_RANGE == 0.07
    assert RM.MAJORS_BAND == 24


def test_only_bars_closed_before_the_tick_are_read():
    closes = list(np.linspace(1.0, 1.2, 60))
    fr = _frame(closes)
    late = pd.concat([fr, _frame([5.0, 5.0], end_tick=T + 1800)])   # bars at T and T+900
    a = RM.wildcard_row("A_USDT", fr, T)
    b = RM.wildcard_row("A_USDT", late, T)
    assert a["usable"] and a == b and a["gate_close"] == pytest.approx(1.2)
    stale = RM.wildcard_row("A_USDT", fr.iloc[:-1], T)               # last bar opens at T-1800
    assert stale["usable"] is False and stale["why"] == "stale_or_missing_bar"
    assert RM.wildcard_row("A_USDT", None, T)["why"] == "kline_error"
    assert RM.trend_row("ETH_USDT", _frame(closes[:50]), T)["why"] == "short_frame"


def _select_runtime(tmp_path, live_env, *, fail=()):
    _on(live_env)
    client = FakeClient({})
    up = [100.0] * 300 + list(np.linspace(100, 112, 100))       # +11.6% in 24h, at the high
    down = [100.0] * 300 + list(np.linspace(100, 80, 100))
    flat = [100.0] * 400
    after = lambda fr: pd.concat([fr, _frame([1.0, 1.0], end_tick=T + 1800)])  # noqa: E731
    client.klines = {"UP_USDT": after(_frame(up)), "DN_USDT": after(_frame(down)),
                     "FL_USDT": after(_frame(flat)), "ETH_USDT": after(_frame(up)),
                     "XRP_USDT": after(_frame(down)), "ZEC_USDT": after(_frame(flat)),
                     "BTC_USDT": after(_frame(list(np.linspace(100, 101, 700))))}
    real = client.get_klines

    def get_klines(symbol, **kw):
        if symbol in fail:
            raise RuntimeError("timeout")
        return real(symbol, **kw)
    client.get_klines = get_klines
    client.get_all_tickers = lambda: [
        {"symbol": s, "amount24": 5e6, "high24Price": 130.0, "lower24Price": 100.0}
        for s in ("UP_USDT", "DN_USDT", "FL_USDT", "ETH_USDT")]
    rt = _rt(tmp_path, client)
    rt._refresh_non_crypto_universe = lambda: None
    rt._major_symbols = lambda tickers, n: {"ETH_USDT"}
    rt._trend_rotation_symbol = lambda: None
    return rt


def test_the_selection_reads_the_ticker_and_the_bars_closed_by_the_tick(tmp_path, live_env):
    rt = _select_runtime(tmp_path, live_env)
    plan = rt._random_tick_select(T)
    assert sorted(s for s, _r, _a in plan["universe"]) == ["DN_USDT", "FL_USDT", "UP_USDT"]
    assert [c["symbol"] for c in plan["buckets"]["WC_LONG"]] == ["UP_USDT", "FL_USDT", "DN_USDT"]
    assert [c["symbol"] for c in plan["buckets"]["WC_SHORT"]] == ["DN_USDT", "FL_USDT", "UP_USDT"]
    assert [c["symbol"] for c in plan["buckets"]["TREND"]] == ["ETH_USDT", "ZEC_USDT", "XRP_USDT"]
    assert plan["buckets"]["TREND"][0]["status"] == "pass"           # +12%/24h at a new closing high
    assert plan["buckets"]["WC_LONG"][0]["gate_close"] == pytest.approx(112.0)   # not the 1.0 after the tick
    assert plan["trend_symbols"] == ["ETH_USDT", "XRP_USDT", "ZEC_USDT"]
    assert plan["btc_flag"]["flagged"] is False
    assert len(plan["frames"]["WILDCARD"]["UP_USDT"]) == RM.WC_BARS


def test_a_kline_outage_fails_the_selection_so_the_tick_is_retried(tmp_path, live_env):
    rt = _select_runtime(tmp_path, live_env, fail=("UP_USDT", "DN_USDT", "ETH_USDT"))
    with pytest.raises(RuntimeError, match="klines unavailable"):
        rt._random_tick_select(T)
    (tmp_path / "one").mkdir()
    rt = _select_runtime(tmp_path / "one", live_env, fail=("FL_USDT",))
    plan = rt._random_tick_select(T)                                   # one symbol lost: proceed
    assert {"symbol": "FL_USDT", "why": "kline_error"} in plan["unusable"]
    assert "FL_USDT" not in [c["symbol"] for c in plan["buckets"]["WC_LONG"]]


# =====================================================================================
# the coin
# =====================================================================================

def test_the_coin_is_fair():
    n = 40_000
    ones = sum(RM.coin() for _ in range(n))
    z = (ones - n / 2) / math.sqrt(n / 4)
    assert abs(z) < 4.5, z                         # P(false alarm) ~ 7e-6
    pairs = [RM.coin() * 2 + RM.coin() for _ in range(8000)]
    counts = np.bincount(pairs, minlength=4)
    chi2 = float(((counts - 2000) ** 2 / 2000).sum())
    assert chi2 < 30.0, counts                     # 3 dof; P(false alarm) < 1e-5
    assert {RM.coin_side(0), RM.coin_side(1)} == {"LONG", "SHORT"} and RM.coin_side(0) == "LONG"


def test_the_coin_is_os_urandom_and_never_a_seeded_prng(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the coin read a PRNG")
    for name in ("random", "getrandbits", "randint", "randrange", "choice", "seed"):
        monkeypatch.setattr(random, name, boom)
    for name in ("default_rng", "random", "randint", "rand", "choice"):
        monkeypatch.setattr(np.random, name, boom)
    draws = [RM.coin() for _ in range(64)]
    assert set(draws) <= {0, 1}
    monkeypatch.undo()
    # the source IS os.urandom: its low bit
    for byte, want in ((b"\x00", 0), (b"\x01", 1), (b"\xfe", 0), (b"\xff", 1)):
        monkeypatch.setattr(RM.os, "urandom", lambda n, _b=byte: _b)
        assert RM.coin() == want
    monkeypatch.undo()
    # seeding every PRNG in the process does not repeat it
    random.seed(7)
    np.random.seed(7)
    a = [RM.coin() for _ in range(64)]
    random.seed(7)
    np.random.seed(7)
    b = [RM.coin() for _ in range(64)]
    assert a != b
    src = inspect.getsource(RM.coin)
    assert "os.urandom(1)" in src and "numpy" not in src.split('"""')[-1]


# =====================================================================================
# the order for the coin's side; TREND SHORT end to end
# =====================================================================================

def test_the_signal_is_the_detectors_own_arithmetic_on_its_natural_side(live_env):
    """A passing detector signal and build_signal on the same inputs agree exactly."""
    closes = [100.0] * 108
    for i in range(12):                        # -1.5% / +3% zigzag: +9.1% in 3h, a pull-back then a resume
        closes.append(closes[-1] * (0.985 if i % 2 == 0 else 1.03))
    fr = _frame(closes)
    fr["volume"] = [1000.0, 1100.0] * 59 + [1000.0, 5000.0]
    fr["high"] = fr["close"]
    fr["low"] = fr["close"] * 0.97
    reasons: list[str] = []
    sig = detect_wildcard_signal(fr, "A_USDT", reasons)
    assert sig is not None and sig.side == "LONG", reasons
    mine = RM.build_signal(symbol="A_USDT", sleeve="WILDCARD", side="LONG", ref_price=sig.entry_price,
                           atr_pct=sig.atr_pct, roc_pct=sig.roc_pct, rsi=sig.rsi)
    for f in ("leverage", "sl_price", "tp_price", "sl_margin_pct", "tp_margin_pct", "balance_fraction",
              "sl_frac_designed"):
        assert getattr(mine, f) == pytest.approx(getattr(sig, f), rel=1e-12), f


@pytest.mark.parametrize("sleeve,side,atr,lev,sl,tp", [
    # TREND: 3 x 1% = 3% stop, x10 trims to x6 (18% of margin), 3R target
    ("TREND", "LONG", 0.01, 6, 97.0, 109.0),
    ("TREND", "SHORT", 0.01, 6, 103.0, 91.0),
    # WILDCARD: 3 x 5% = 15% stop, x5 trims to x1, 5R = 75%; a short's target clamps at 50%
    ("WILDCARD", "LONG", 0.05, 1, 85.0, 175.0),
    ("WILDCARD", "SHORT", 0.05, 1, 115.0, 50.0),
    # tight stop: x5 kept
    ("WILDCARD", "SHORT", 0.004, 5, 101.2, 94.0),
])
def test_the_order_geometry_for_each_side(live_env, sleeve, side, atr, lev, sl, tp):
    sig = RM.build_signal(symbol="A_USDT", sleeve=sleeve, side=side, ref_price=100.0, atr_pct=atr,
                          roc_pct=0.1, rsi=50.0)
    assert sig.side == side and sig.leverage == lev
    assert sig.sl_price == pytest.approx(sl) and sig.tp_price == pytest.approx(tp)
    assert sig.sl_margin_pct <= 20.0 + 1e-9
    # the exchange's own maximum caps the sleeve's leverage, as in the backtest
    capped = RM.build_signal(symbol="A_USDT", sleeve=sleeve, side=side, ref_price=100.0, atr_pct=atr,
                             roc_pct=0.1, rsi=50.0, exch_max_leverage=1)
    assert capped.leverage == 1


def _trend_short_runtime(tmp_path, live_env, *, btc=False, paper=False):
    _on(live_env)
    client = FakeClient({"ETH_USDT": 100.0, "BTC_USDT": 60000.0})
    rt = _rt(tmp_path, client, paper=paper)
    rt._btc_flag_asof = (T, btc, {"trend_flag": 1.0 if btc else 0.0, "trend_flag_btc_24h": 0.004,
                                  "trend_flag_btc_72h": 0.06, "trend_flag_btc_168h": 0.08,
                                  "trend_flag_dist_7d_high": -0.02})
    return rt, client


def test_a_trend_short_opens_end_to_end(tmp_path, live_env):
    rt, client = _trend_short_runtime(tmp_path, live_env)
    cand = _cand("ETH_USDT", "TREND", 0.05, status="pass", gate=99.0, atr=0.01,
                 det={"side": "LONG", "roc_pct": 0.05, "prior_close_extreme": 98.0, "leverage": 10})
    plan = _plan({"TREND": [cand]})
    d = rt._random_open(plan, "TREND", cand, 1, 1, 1, [])
    assert d["decision"] == "opened" and d["side"] == "SHORT" and d["natural_side"] == "LONG"
    (order,) = client.orders
    assert order["side"] == 3, "open SHORT"
    assert order["leverage"] == 6
    assert order["stop_loss_price"] == pytest.approx(103.0)      # 3 x ATR above the reference
    assert order["take_profit_price"] == pytest.approx(91.0)     # 3R below
    # the resting stop triggers on FAIR price, the target on last (both sides alike)
    assert MexcFuturesClient._trigger_trends_for_order_side(3) == (1, 2)
    pos = rt.open_positions["ETH_USDT"]
    assert pos.side == "SHORT" and pos.entry_signal == "TREND_SHORT"
    assert rt._sleeve_kind(pos) == "TREND" and rt._is_wildcard_convex(pos)
    md = pos.metadata
    assert md["random_bucket"] == "TREND" and md["random_coin"] == 1.0 and md["random_side"] == "SHORT"
    assert md["random_natural_side"] == "LONG" and md["random_fallback"] == 0.0
    assert md["random_tick_ts"] == float(T) and md["random_prereg"] == RM.PREREG_TAG
    assert md["trend"] == 1.0 and md["trend_flag"] == 0.0
    # sized as today: 1R = 1.205% of available x regime (1.0 here), integer contracts
    assert md["risk_usdt_intended"] == pytest.approx(0.01205 * 1000.0, rel=1e-6)
    assert order["vol"] == 4 and md["risk_usdt"] == pytest.approx(12.0)
    assert md["regime_size_multiplier"] == pytest.approx(md["random_regime_mult"])


def test_a_flagged_tick_caps_the_trend_short_target_at_1r(tmp_path, live_env):
    rt, client = _trend_short_runtime(tmp_path, live_env, btc=True)
    cand = _cand("ETH_USDT", "TREND", 0.02, atr=0.01)
    rt._random_open(_plan({"TREND": [cand]}, btc=True), "TREND", cand, 1, 1, 1, [])
    (order,) = client.orders
    assert order["take_profit_price"] == pytest.approx(97.0)     # 1R below a 103 stop
    assert rt.open_positions["ETH_USDT"].metadata["trend_flag_tp_capped"] == 1.0


def test_a_trend_short_runs_the_live_exits(tmp_path, live_env):
    """Breakeven at 0.90R moves the resting stop below entry; the retention trail closes a
    2R peak at 1R; the 24h clock closes it; no early stop on TREND (it is WILDCARD-only)."""
    rt, client = _trend_short_runtime(tmp_path, live_env)
    closed: list = []
    rt._close_position_for_exit = lambda p, current_price, reason: closed.append(
        (p.symbol, reason, current_price)) or True
    opened_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    pos = _pos("ETH_USDT", "TREND", "SHORT", entry=100.0, sl=103.0, tp=91.0, lev=6, opened=opened_at)
    rt.open_positions = {"ETH_USDT": pos}
    # no early stop on TREND: -0.6R at minute 10
    assert rt._convex_early_stop_exit(pos, 101.8) is False and closed == []
    # breakeven: fair peak 0.92R -> resting stop to entry - costs, below entry for a short
    assert rt._convex_runner_trail_exit(pos, 97.25) is False
    (moved,) = client.tpsl
    assert moved["stop_loss_price"] == pytest.approx(99.81) and moved["side"] == "SHORT"
    assert moved["take_profit_price"] == pytest.approx(91.0)
    assert pos.metadata["be_stop_price"] == pytest.approx(99.81) and pos.sl_price == 103.0
    assert rt._effective_stop_price(pos) == pytest.approx(99.81)       # what a re-placed bracket uses
    # trail: peak 2R (94), back to 1R (97) -> floor 0.5 x 2R = 1R -> close
    assert rt._convex_runner_trail_exit(pos, 94.0) is False            # new peak 2R
    assert rt._convex_runner_trail_exit(pos, 96.8) is False and not closed   # 1.07R: above the floor
    assert rt._convex_runner_trail_exit(pos, 97.5) is True             # 0.83R: through 0.5 x 2R
    assert closed[-1][:2] == ("ETH_USDT", "CONVEX_RETENTION_TRAIL")
    # the 24h clock
    closed.clear()
    pos2 = _pos("XRP_USDT", "TREND", "SHORT", entry=2.0, sl=2.06, tp=1.82, lev=6,
                opened=datetime.now(timezone.utc) - timedelta(hours=24, seconds=1))
    assert rt._convex_time_stop_exit(pos2, 2.01) is True and closed[-1][1] == "CONVEX_TIME_STOP"
    pos3 = _pos("XRP_USDT", "TREND", "SHORT", entry=2.0, sl=2.06, tp=1.82, lev=6,
                opened=datetime.now(timezone.utc) - timedelta(hours=23, minutes=59))
    assert rt._convex_time_stop_exit(pos3, 2.01) is False


def test_a_wildcard_short_and_long_open_on_the_coins_side(tmp_path, live_env):
    _on(live_env)
    client = FakeClient({"L1_USDT": 2.0, "S1_USDT": 0.5})
    rt = _rt(tmp_path, client)
    long_bucket = _cand("L1_USDT", "WC_LONG", 0.3, gate=2.0, atr=0.02)
    short_bucket = _cand("S1_USDT", "WC_SHORT", -0.3, gate=0.5, atr=0.02)
    plan = _plan({"WC_LONG": [long_bucket], "WC_SHORT": [short_bucket]})
    d1 = rt._random_open(plan, "WC_LONG", long_bucket, 1, 1, 1, [])      # coin 1 -> SHORT
    d2 = rt._random_open(plan, "WC_SHORT", short_bucket, 1, 1, 0, [])    # coin 0 -> LONG
    assert (d1["decision"], d1["side"], d2["decision"], d2["side"]) == ("opened", "SHORT", "opened", "LONG")
    o1, o2 = client.orders
    # 3 x 2% = 6% stop: x5 -> 30% of margin -> trimmed to x3 (18%); 5R = 30%
    assert (o1["side"], o1["leverage"]) == (3, 3)
    assert o1["stop_loss_price"] == pytest.approx(2.0 * 1.06) and o1["take_profit_price"] == pytest.approx(2.0 * 0.70)
    assert (o2["side"], o2["leverage"]) == (1, 3)
    assert o2["stop_loss_price"] == pytest.approx(0.5 * 0.94) and o2["take_profit_price"] == pytest.approx(0.5 * 1.30)
    for sym, side in (("L1_USDT", "SHORT"), ("S1_USDT", "LONG")):
        p = rt.open_positions[sym]
        assert p.side == side and rt._sleeve_kind(p) == "WILDCARD"
        assert p.metadata["turnover_24h_usdt"] == 5e6 and p.metadata["range_24h"] == 0.30
    # the early stop is live on WILDCARD, both sides: -0.6R inside 30 minutes closes it
    closed: list = []
    rt._close_position_for_exit = lambda p, current_price, reason: closed.append(reason) or True
    p = rt.open_positions["L1_USDT"]
    adverse = p.entry_price + 0.6 * abs(p.sl_price - p.entry_price)
    assert rt._convex_early_stop_exit(p, adverse) is True and closed == ["CONVEX_EARLY_STOP"]


def test_a_min_volume_refusal_leaves_the_slot_empty_until_the_next_tick(tmp_path, live_env):
    _on(live_env)
    client = FakeClient({"BTW_USDT": 0.05, "L2_USDT": 1.0, "S1_USDT": 1.0}, min_vol=1)
    rt = _rt(tmp_path, client, paper=True)
    real_detail = client.get_contract_detail
    client.get_contract_detail = lambda s: ({"contractSize": 100.0, "minVol": 10_000, "maxLeverage": 50}
                                            if s == "BTW_USDT" else real_detail(s))
    buckets = {"TREND": [],
               "WC_LONG": [_cand("BTW_USDT", "WC_LONG", 0.4, gate=0.05), _cand("L2_USDT", "WC_LONG", 0.2, gate=1.0)],
               "WC_SHORT": [_cand("S1_USDT", "WC_SHORT", -0.3, gate=1.0)]}
    live_env.setattr(RM, "coin", lambda: 0)
    decisions = rt._random_tick_execute(_plan(buckets))
    assert [(d["bucket"], d["decision"], d.get("symbol")) for d in decisions] == [
        ("TREND", "no_candidate", None), ("WC_LONG", "min_vol", "BTW_USDT"), ("WC_SHORT", "opened", "S1_USDT")]
    assert "L2_USDT" not in rt.open_positions, "no next-best retry at the same tick"
    rows = shadow_ledger.load_raw(str(tmp_path / "shadow.jsonl"))
    assert [r["reject_reason"] for r in rows] == ["random_tick:min_vol", "random_tick:opened"]
    assert "min_vol_skip" not in {r["reject_reason"] for r in rows}
    # the slot was left empty: the next tick fills it
    buckets2 = {"TREND": [], "WC_LONG": [_cand("L2_USDT", "WC_LONG", 0.2, gate=1.0)], "WC_SHORT": []}
    decisions = rt._random_tick_execute(_plan(buckets2, tick=T + 43200))
    assert decisions[1]["decision"] == "opened" and len(rt.open_positions) == 2


# =====================================================================================
# switch OFF = today; ON = the scans open nothing
# =====================================================================================

def _sig(symbol="A_USDT", side="LONG", roc=0.12, entry=1.0):
    return WildcardSignal(symbol=symbol, side=side, entry_price=entry, leverage=5, roc_pct=roc,
                          atr_pct=0.03, sl_price=entry * (0.9 if side == "LONG" else 1.1),
                          tp_price=entry * (1.5 if side == "LONG" else 0.5), sl_margin_pct=50.0,
                          tp_margin_pct=250.0, balance_fraction=0.12, rsi=60.0)


def _scan(tmp_path, live_env, flag, *, sleeve="WILDCARD", full=False, twice=False):
    live_env.setenv("FUTURES_ENTRY_ENVELOPE_ENABLED", "0")
    live_env.setenv("FUTURES_WILDCARD_MAX_CALM_RATIO", "0")
    live_env.setenv("FUTURES_WILDCARD_LONG_ONLY", "0")
    if flag is None:
        live_env.delenv("FUTURES_RANDOM_MODE_ENABLED", raising=False)
    else:
        live_env.setenv("FUTURES_RANDOM_MODE_ENABLED", flag)
    sigs = {"A_USDT": _sig("A_USDT", roc=0.20), "B_USDT": _sig("B_USDT", "SHORT", roc=-0.15)}
    live_env.setattr(R, "detect_wildcard_signal", lambda frame, sym, reasons=None, min_roc=None: sigs.get(sym))
    live_env.setattr(R, "detect_trend_signal", lambda frame, sym, reasons=None:
                     _sig(sym, roc=0.06, entry=100.0) if sym == "ETH_USDT" else None)
    rt = _rt(tmp_path, MagicMock())
    rt.client.get_all_tickers.return_value = [
        {"symbol": s, "amount24": 9e6, "riseFallRate": 0.05, "high24Price": 150.0, "lower24Price": 100.0}
        for s in sigs]
    flat = pd.DataFrame({"open": [1.0] * 700, "high": [1.0] * 700, "low": [1.0] * 700,
                         "close": [1.0] * 700, "volume": [1e3] * 700})
    rt.client.get_klines.side_effect = lambda sym, **kw: flat
    for name in ("_refresh_non_crypto_universe", "_maybe_capture_news"):
        setattr(rt, name, lambda: None)
    rt._is_tradeable_crypto = lambda sym: True
    rt._major_symbols = lambda tickers, n: set()
    rt._alt_breadth = lambda *a, **k: None
    rt._record_ticker_snapshot = lambda movers: None
    rt._account_snapshot = lambda *a, **k: {"available_usdt": 1000.0}
    rt._get_reference_price = lambda *a, **k: 1.0
    rt._convex_open_count = lambda *a, **k: 3 if full else 0
    rt._trend_rotation_symbol = lambda: None
    rt._preemption_possible = lambda: full
    preempted: list = []
    rt._try_preempt_for = lambda sig: preempted.append(sig.symbol) or 1000.0
    opened: list = []
    rt._open_wildcard_position = lambda sig, avail, **kw: opened.append((sig.symbol, sig.side)) or True
    for _ in range(2 if twice else 1):
        if sleeve == "WILDCARD":
            rt._last_wildcard_scan_at = 0.0
            rt._maybe_scan_wildcard()
        else:
            rt._last_trend_scan_at = 0.0
            rt._maybe_scan_trend()
    rows = shadow_ledger.load_raw(str(tmp_path / "shadow.jsonl"))
    return opened, [(r["symbol"], r["reject_reason"]) for r in rows], preempted


@pytest.mark.parametrize("flag", [None, "", "  ", "0", "false"])
@pytest.mark.parametrize("sleeve", ["WILDCARD", "TREND"])
def test_switch_off_the_scans_make_todays_decisions(tmp_path, live_env, flag, sleeve):
    opened, rows, _ = _scan(tmp_path, live_env, flag, sleeve=sleeve)
    assert opened == ([("A_USDT", "LONG")] if sleeve == "WILDCARD" else [("ETH_USDT", "LONG")])
    assert not any("random" in r for _s, r in rows)
    # slots full: today's preemption still runs
    if sleeve == "WILDCARD":
        (tmp_path / "full").mkdir()
        opened, rows, preempted = _scan(tmp_path / "full", live_env, flag, full=True)
        assert preempted == ["A_USDT"] and opened == [("A_USDT", "LONG")]


@pytest.mark.parametrize("sleeve", ["WILDCARD", "TREND"])
def test_switch_on_the_scans_open_nothing_and_log_the_pick_once_per_tick(tmp_path, live_env, sleeve):
    opened, rows, preempted = _scan(tmp_path, live_env, "1", sleeve=sleeve, full=True, twice=True)
    assert opened == [] and preempted == []
    want = "A_USDT" if sleeve == "WILDCARD" else "ETH_USDT"
    assert rows == [(want, "random_mode")]


def test_switch_on_no_other_entry_path_can_open(tmp_path, live_env):
    _on(live_env)
    client = FakeClient({"A_USDT": 1.0})
    rt = _rt(tmp_path, client, paper=True)
    for kind in ("WILDCARD", "TREND", "SQUEEZE", "SNIPER"):
        assert rt._open_wildcard_position(_sig(), 1000.0, kind=kind) is False
    assert rt.open_positions == {} and client.orders == []
    _on(live_env, False)
    assert rt._open_wildcard_position(_sig(), 1000.0) is True       # off: today's path


def test_switch_off_nothing_new_is_written_or_run(tmp_path, live_env):
    _on(live_env, False)
    rt = _rt(tmp_path, MagicMock())
    rt._random_tick_select = lambda tick: pytest.fail("ran with the switch off")
    live_env.setattr(R.time, "time", lambda: T + 5)
    rt._maybe_random_tick()
    rt._save_state()
    assert "random_mode" not in json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert rt._random_mode_status_line() is None
    assert rt._random_entry_line({"wildcard": 1.0}) == ""
    src = inspect.getsource(FuturesRuntime.run)
    assert "and not random_mode.enabled()" in src, "the PMT path must be shut while the mode is on"
    assert src.index("self._maybe_random_tick()") < src.index("signal = self._fetch_signal()")


def test_the_status_line_names_the_mode(tmp_path, live_env):
    _on(live_env)
    rt = _rt(tmp_path, MagicMock())
    live_env.setattr(R.time, "time", lambda: T + 3600)
    rt._random_mode_state = {"last_tick": T, "summary": {"opened": 2}}
    line = rt._random_mode_status_line()
    assert "RANDOM MODE" in line and "trial 24" in line and "coin flip" in line
    assert "opened <b>2</b>" in line and "next 00:00Z" in line
    assert "_random_mode_status_line()" in inspect.getsource(FuturesRuntime._build_status_message)


# =====================================================================================
# telemetry
# =====================================================================================

def test_every_decision_and_position_carries_the_tick_telemetry(tmp_path, live_env):
    _on(live_env)
    client = FakeClient({"ETH_USDT": 100.0, "L2_USDT": 1.0, "S1_USDT": 1.0, "L1_USDT": 1.0})
    rt = _rt(tmp_path, client, paper=True)
    rt._btc_flag_asof = (T, False, {"trend_flag": 0.0})
    rt.open_positions["L1_USDT"] = _pos("L1_USDT")
    rt.open_positions["W9_USDT"] = _pos("W9_USDT")             # 2 of 3 WILDCARD slots used
    buckets = {"TREND": [_cand("ETH_USDT", "TREND", 0.03)],
               "WC_LONG": [_cand("L1_USDT", "WC_LONG", 0.4, gate=1.0), _cand("L2_USDT", "WC_LONG", 0.2, gate=1.0)],
               "WC_SHORT": [_cand("S1_USDT", "WC_SHORT", -0.3, gate=1.0, status="pass",
                                  det={"side": "SHORT", "vol_z": 2.5})]}
    coins = iter([1, 0, 0])
    live_env.setattr(RM, "coin", lambda: next(coins))
    decisions = rt._random_tick_execute(_plan(buckets))
    assert [(d["bucket"], d["decision"]) for d in decisions] == [
        ("TREND", "opened"), ("WC_LONG", "held"), ("WC_LONG", "opened"), ("WC_SHORT", "slot_full")]
    md = rt.open_positions["L2_USDT"].metadata
    want = {"random_mode": 1.0, "random_bucket": "WC_LONG", "random_rank": 2.0, "random_field": 2.0,
            "random_status": "fallback", "random_fallback": 1.0, "random_key_value": 0.2,
            "random_natural_side": "LONG", "random_coin": 0.0, "random_side": "LONG",
            "random_held_skipped": 1.0, "random_held_symbols": "L1_USDT", "random_decision": "opened",
            "random_tick_ts": float(T), "random_turnover_24h": 5e6, "random_range_24h": 0.30,
            "candidate_rank": 2.0, "candidate_field": 2.0}
    assert {k: md[k] for k in want} == want
    assert set(RM.STAMP_KEYS) <= set(md)
    # shadow ledger: one row per decision, with the telemetry
    rows = shadow_ledger.load_raw(str(tmp_path / "shadow.jsonl"))
    assert [(r["sleeve"], r["symbol"], r["side"], r["reject_reason"]) for r in rows] == [
        ("TREND", "ETH_USDT", "SHORT", "random_tick:opened"),
        ("WILDCARD", "L1_USDT", "LONG", "random_tick:held"),
        ("WILDCARD", "L2_USDT", "LONG", "random_tick:opened"),
        ("WILDCARD", "S1_USDT", "SHORT", "random_tick:slot_full")]
    assert rows[3]["random_coin"] is None and rows[3]["random_status"] == "pass"
    assert rows[0]["random_coin"] == 1.0 and rows[0]["random_natural_side"] == "LONG"
    # the trade record and the feature store on close
    pos = rt.open_positions["L2_USDT"]
    assert rt._close_position_for_exit(pos, current_price=1.05, reason="CONVEX_TIME_STOP")
    trade = rt.trade_history[-1]
    feat = [json.loads(x) for x in (tmp_path / "features.jsonl").read_text().splitlines()][-1]
    for rec in (trade, feat):
        assert rec["random_bucket"] == "WC_LONG" and rec["random_coin"] == 0.0
        assert rec["random_tick_ts"] == float(T) and rec["random_fallback"] == 1.0
    assert feat["kind"] == "WILDCARD"


def test_records_of_other_positions_are_unchanged(tmp_path, live_env):
    _on(live_env, False)
    rt = _rt(tmp_path, FakeClient({"A_USDT": 1.0}), paper=True)
    pos = _pos("A_USDT")
    rt.open_positions["A_USDT"] = pos
    rt._close_position_for_exit(pos, current_price=1.0, reason="X")
    feat = json.loads((tmp_path / "features.jsonl").read_text().splitlines()[-1])
    assert not any(k.startswith("random_") for k in list(rt.trade_history[-1]) + list(feat))


def test_the_journal_has_the_ranked_lists_and_every_decision(tmp_path, live_env):
    _on(live_env)
    rt = _rt(tmp_path, MagicMock())
    live_env.setattr(R.time, "time", lambda: T + 9)
    plan = _plan(_three_buckets())
    rt._random_tick_select = lambda tick, cfg=None: plan
    rt._random_tick_execute = lambda p: [{"bucket": "TREND", "decision": "opened", "symbol": "ETH_USDT",
                                          "side": "SHORT", "coin": 1}]
    rt._maybe_random_tick()
    (row,) = [json.loads(x) for x in (tmp_path / "futures_random_ticks.jsonl").read_text().splitlines()]
    assert row["tick"] == T and row["tick_utc"] == "2026-10-02T12:00:00Z" and row["prereg"] == RM.PREREG_TAG
    assert [c["symbol"] for c in row["buckets"]["WC_LONG"]] == ["L1_USDT", "L2_USDT"]
    assert row["decisions"][0]["coin"] == 1
    assert rt._random_mode_state["summary"] == {"opened": 1, "decisions": ["TREND:opened ETH_USDT SHORT"]}


def test_tick_decisions_do_not_read_as_scan_skips_or_gate_costs(tmp_path, live_env):
    _on(live_env)
    rt = _rt(tmp_path, MagicMock())
    shadow_ledger.append_row(str(tmp_path / "shadow.jsonl"), shadow_ledger.candidate_row(
        _sig(), sleeve="WILDCARD", reject_reason="random_tick:opened"))
    assert rt._last_wildcard_reject() is None
    assert "by.pop(\"random_tick\", None)" in inspect.getsource(FuturesRuntime._gate_cost_lines)


# =====================================================================================
# live-time inputs: the regime scaler and the BTC flag as of the tick
# =====================================================================================

def test_the_regime_scaler_reads_the_closes_it_is_given(tmp_path, live_env):
    rt = _rt(tmp_path, MagicMock())
    closes = list(np.linspace(100, 101, 30)) + [100.5, 100.2, 100.9, 100.1]
    rt.client.get_klines.return_value = pd.DataFrame({"close": closes})
    fetched = rt._regime_size_multiplier("A_USDT")
    rt.client.get_klines.side_effect = AssertionError("must not fetch")
    assert rt._regime_size_multiplier("A_USDT", closes=closes) == fetched


def test_the_btc_flag_as_of_the_tick_reads_only_bars_closed_by_it(tmp_path, live_env):
    client = FakeClient({})
    rt = _rt(tmp_path, client)
    closes = list(np.linspace(100, 112, 700))                   # +12% over the week, at the high
    fr = _frame(closes)
    late = pd.concat([fr, _frame([50.0, 50.0, 50.0], end_tick=T + 2700)])   # bars after the tick
    client.klines["BTC_USDT"] = late
    flagged, fields = rt._btc_exhaustion_flag(asof=T)
    assert flagged is True and fields["trend_flag_dist_7d_high"] == 0.0
    assert getattr(rt, "_btc_flag_cache", None) is None, "the 10-minute cache is untouched"
    client.klines["BTC_USDT"] = None                              # cached per tick
    assert rt._btc_exhaustion_flag(asof=T)[0] is True


# =====================================================================================
# the ported ranking against the backtest's own candidate lists
# =====================================================================================

def _fixture_frames(tick_row):
    out = {}
    for sym, b in tick_row["bars"].items():
        rows = b["ohlcv"]
        t = [b["t0"] + 900 * i for i in range(len(rows))]
        a = np.asarray(rows, dtype=float)
        out[sym] = pd.DataFrame({"open": a[:, 0], "high": a[:, 1], "low": a[:, 2], "close": a[:, 3],
                                 "volume": a[:, 4]},
                                index=pd.to_datetime(np.asarray(t, dtype=np.int64), unit="s", utc=True))
    return out


def _close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return a == pytest.approx(b, rel=1e-12, abs=1e-15)


@pytest.mark.parametrize("idx", [0, 1, 2])
def test_the_live_ranking_reproduces_the_backtests_lists(tmp_path, live_env, idx):
    """wc/RANDOM/build/tick_candidates.json, three past ticks: a WILDCARD-short detector pass
    (MAGMA, a symbol the live bot held), a WILDCARD-long pass (AIN), a TREND pass (NEAR, BTC
    flagged). Every listed row: order, pass/fallback, ROC, gate close, ATR, detector verdict,
    regime multiplier, leverage and stop as placed. PARITY.md runs all 56 ticks."""
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    tick = fx["ticks"][idx]
    T0 = tick["tick"]
    frames = _fixture_frames(tick)
    full = set(tick["full_bars"])
    wc_syms = {e["symbol"] for b in ("WC_LONG", "WC_SHORT") for e in tick["expected"][b]}
    wc = [RM.wildcard_row(s, frames[s], T0) for s in sorted(wc_syms)]
    longs, shorts = RM.rank_wildcard(wc)
    trend = RM.rank_trend([RM.trend_row(s, frames[s], T0) for s in tick["trend_symbols"]])
    rt = _rt(tmp_path, MagicMock())
    for bucket, mine in (("TREND", trend), ("WC_LONG", longs), ("WC_SHORT", shorts)):
        exp = tick["expected"][bucket]
        key = RM.KEY[bucket]
        assert [r["symbol"] for r in mine] == [e["symbol"] for e in exp], bucket
        for r, e in zip(mine, exp):
            assert r["status"] == e["status"]
            assert ((r.get("detector") or {}).get("side"), r.get("reject")) == (e["detector_side"], e["reject"])
            for f in (key, "gate_close", "atr_pct"):
                assert _close(r[f], e[f]), (bucket, r["symbol"], f)
            if r["symbol"] in full and bucket != "TREND":
                assert _close(r["calm_ratio"], e["calm_ratio"])
            fr = RM.completed(frames[r["symbol"]], T0, 400)
            assert rt._regime_size_multiplier(r["symbol"], closes=list(fr["close"])) == \
                pytest.approx(e["regime_mult"], rel=1e-12)
            for side in ("LONG", "SHORT"):
                sig = RM.signal_for(r, bucket=bucket, side=side, ref_price=r["gate_close"], frame=fr,
                                    exch_max_leverage=e["exch_max_leverage"])
                assert sig.leverage == e["leverage"]
                assert abs(sig.sl_price - r["gate_close"]) / r["gate_close"] == \
                    pytest.approx(e["sl_frac_placed"], rel=1e-9)
    first = {b: tick["expected"][b][0] for b in ("TREND", "WC_LONG", "WC_SHORT")}
    assert any(v["status"] == "pass" for v in first.values())


# =====================================================================================
# trial 25 (wc/TRIAL25/PREREG.md sha256 23840ce65807b549...): the settings that choose the
# configuration - FUTURES_RANDOM_TICK_HOURS, FUTURES_RANDOM_SIDE_MODE,
# FUTURES_RANDOM_WC_MIN_TURNOVER (+ FUTURES_TREND_SL_ATR_MULT) - read once per tick
# =====================================================================================

T25_ENV = {"FUTURES_RANDOM_TICK_HOURS": "6", "FUTURES_RANDOM_SIDE_MODE": "natural",
           "FUTURES_TREND_SL_ATR_MULT": "3.5"}
NEW_VARS = ("FUTURES_RANDOM_TICK_HOURS", "FUTURES_RANDOM_SIDE_MODE", "FUTURES_RANDOM_WC_MIN_TURNOVER")


def _t25(monkeypatch, **extra):
    for k, v in {**T25_ENV, **extra}.items():
        monkeypatch.setenv(k, v)


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_defaults_are_trial_24(live_env, raw):
    live_env.delenv("FUTURES_TREND_SL_ATR_MULT", raising=False)
    for k in NEW_VARS:
        if raw is None:
            live_env.delenv(k, raising=False)
        else:
            live_env.setenv(k, raw)
    cfg = RM.config()
    assert cfg.valid and cfg.errors == ()
    assert (cfg.tick_hours, cfg.side_mode, cfg.trend_sl_mult, cfg.wc_min_turnover) == (12, "coin", 3.0, 2e6)
    assert cfg.tick_seconds == RM.TICK_SECONDS == 43200
    assert cfg.prereg == RM.PREREG_TAG == "29fabd853a4f5d77" and cfg.trial == "trial 24"
    assert cfg.fields() == {"random_tick_hours": 12.0, "random_side_mode": "coin",
                            "random_trend_sl_mult": 3.0, "random_wc_min_turnover": 2e6}
    # the same values written literally are trial 24 too (the REVERT procedure)
    for k, v in (("FUTURES_RANDOM_TICK_HOURS", "12"), ("FUTURES_RANDOM_SIDE_MODE", "coin"),
                 ("FUTURES_TREND_SL_ATR_MULT", "3.0"), ("FUTURES_RANDOM_WC_MIN_TURNOVER", "2000000")):
        live_env.setenv(k, v)
    assert RM.config() == cfg


def test_the_trial_25_configuration_and_the_prereg_tags(live_env):
    _t25(live_env)
    cfg = RM.config()
    assert cfg.valid and (cfg.tick_hours, cfg.side_mode, cfg.trend_sl_mult, cfg.wc_min_turnover) == \
        (6, "natural", 3.5, 2e6)
    assert cfg.prereg == RM.PREREG25_TAG == "23840ce65807b549" and cfg.trial == "trial 25"
    assert RM.PREREG25_SHA256.startswith(RM.PREREG25_TAG) and len(RM.PREREG25_SHA256) == 64
    assert "06:00Z" in cfg.describe() and "natural" in cfg.describe() and "3.5x" in cfg.describe()
    live_env.setenv("FUTURES_TREND_SL_ATR_MULT", "3.50")
    live_env.setenv("FUTURES_RANDOM_SIDE_MODE", " natural ")             # surrounding spaces ignored
    live_env.setenv("FUTURES_RANDOM_WC_MIN_TURNOVER", "2e6")
    assert RM.config().prereg == RM.PREREG25_TAG


@pytest.mark.parametrize("hours,mode,sl,turn", [
    ("6", "coin", "3.0", None), ("12", "natural", "3.5", None), ("6", "natural", "3.0", None),
    ("12", "coin", "3.5", None), ("6", "natural", "3.5", "10000000"), ("12", "coin", "3.0", "10000000"),
])
def test_any_other_valid_combination_is_unregistered(live_env, hours, mode, sl, turn):
    live_env.setenv("FUTURES_RANDOM_TICK_HOURS", hours)
    live_env.setenv("FUTURES_RANDOM_SIDE_MODE", mode)
    live_env.setenv("FUTURES_TREND_SL_ATR_MULT", sl)
    if turn:
        live_env.setenv("FUTURES_RANDOM_WC_MIN_TURNOVER", turn)
    cfg = RM.config()
    assert cfg.valid and cfg.prereg == RM.UNREGISTERED == "unregistered" and cfg.trial == "UNREGISTERED"


@pytest.mark.parametrize("name,raw", [
    ("FUTURES_RANDOM_TICK_HOURS", "8"), ("FUTURES_RANDOM_TICK_HOURS", "6.0"),
    ("FUTURES_RANDOM_TICK_HOURS", "6h"), ("FUTURES_RANDOM_TICK_HOURS", "0"),
    ("FUTURES_RANDOM_TICK_HOURS", "24"), ("FUTURES_RANDOM_SIDE_MODE", "random"),
    ("FUTURES_RANDOM_SIDE_MODE", "natual"), ("FUTURES_RANDOM_SIDE_MODE", "0"),
    ("FUTURES_RANDOM_SIDE_MODE", "Natural"), ("FUTURES_RANDOM_SIDE_MODE", "NATURAL"),
    ("FUTURES_RANDOM_SIDE_MODE", " Natural "), ("FUTURES_RANDOM_SIDE_MODE", "Coin"),
    ("FUTURES_RANDOM_WC_MIN_TURNOVER", "abc"), ("FUTURES_RANDOM_WC_MIN_TURNOVER", "-1"),
    ("FUTURES_RANDOM_WC_MIN_TURNOVER", "0"), ("FUTURES_RANDOM_WC_MIN_TURNOVER", "nan"),
    ("FUTURES_RANDOM_WC_MIN_TURNOVER", "inf"), ("FUTURES_RANDOM_WC_MIN_TURNOVER", "2M"),
    ("FUTURES_TREND_SL_ATR_MULT", "3.5x"), ("FUTURES_TREND_SL_ATR_MULT", "abc"),
    ("FUTURES_TREND_SL_ATR_MULT", "3,5"), ("FUTURES_TREND_SL_ATR_MULT", "0"),
    ("FUTURES_TREND_SL_ATR_MULT", "-1"), ("FUTURES_TREND_SL_ATR_MULT", "nan"),
    ("FUTURES_TREND_SL_ATR_MULT", "inf"),
])
def test_an_invalid_value_is_refused_never_a_silent_fallback(tmp_path, live_env, name, raw):
    live_env.setenv(name, raw)
    cfg = RM.config()
    assert not cfg.valid and len(cfg.errors) == 1 and name in cfg.errors[0] and repr(raw.strip()) in cfg.errors[0]
    # the due tick is not processed, not marked, and the owner is alerted (once per tick)
    calls: list = []
    clock = {"now": T + 30}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    rt = _tick_runtime(tmp_path, live_env, calls)
    sent: list = []
    rt._notify_once = lambda key, msg, **k: sent.append((key, msg))
    rt._maybe_random_tick()
    clock["now"] = T + 60
    rt._maybe_random_tick()
    assert calls == [] and not rt._random_mode_state
    assert not (tmp_path / "futures_random_ticks.jsonl").exists()
    assert [k for k, _m in sent] == [f"random_config_invalid_{T}"] * 2       # cooldown is per key
    assert "NOT processed" in sent[0][1] and name in sent[0][1]
    line = rt._random_mode_status_line()
    assert "invalid settings" in line and "NOT processed" in line and name in line
    # the boot log alerts too
    sent.clear()
    rt._random_mode_boot_log()
    assert [k for k, _m in sent] == ["random_config_invalid_boot"]
    # fixed (or blanked = the default) -> the tick runs again, still inside its grace
    live_env.setenv(name, "")
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"]


def test_an_invalid_tick_hours_value_is_checked_and_alerted_at_every_6h_tick(tmp_path, live_env):
    """An invalid cadence is checked on the finest allowed grid: 06:00Z and 18:00Z alert
    too (never processed), and the cycle sleep lands just after them."""
    live_env.setenv("FUTURES_RANDOM_TICK_HOURS", "8")
    assert not RM.config().valid and RM.config().tick_seconds == 6 * 3600
    for t6 in (T - 6 * 3600, T + 6 * 3600):                        # 06:00Z and 18:00Z
        calls: list = []
        clock = {"now": t6 + 30}
        live_env.setattr(R.time, "time", lambda: clock["now"])
        (tmp_path / str(t6)).mkdir()
        rt = _tick_runtime(tmp_path / str(t6), live_env, calls)
        sent: list = []
        rt._notify_once = lambda key, msg, **k: sent.append((key, msg))
        rt._maybe_random_tick()
        assert calls == [] and not rt._random_mode_state
        assert [k for k, _m in sent] == [f"random_config_invalid_{t6}"]
        clock["now"] = t6 - 100.5
        assert rt._random_mode_sleep_seconds(300) == 102


def test_an_unregistered_combination_still_runs_with_an_alert(tmp_path, live_env):
    live_env.setenv("FUTURES_RANDOM_SIDE_MODE", "natural")              # 12h / natural / 3.0
    calls: list = []
    live_env.setattr(R.time, "time", lambda: T + 30)
    rt = _tick_runtime(tmp_path, live_env, calls)
    sent: list = []
    rt._notify_once = lambda key, msg, **k: sent.append((key, msg))
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"]
    assert [k for k, _m in sent] == [f"random_config_unregistered_{T}"]
    (row,) = [json.loads(x) for x in (tmp_path / "futures_random_ticks.jsonl").read_text().splitlines()]
    assert row["prereg"] == "unregistered" and row["random_side_mode"] == "natural"
    sent.clear()
    rt._random_mode_boot_log()
    assert [k for k, _m in sent] == ["random_config_unregistered_boot"]
    # registered configurations raise no alert
    for env in ({"FUTURES_RANDOM_SIDE_MODE": ""}, T25_ENV):
        for k, v in env.items():
            live_env.setenv(k, v)
        sent.clear()
        rt._random_mode_boot_log()
        assert sent == []


def test_6h_ticks_are_0000z_0600z_1200z_1800z():
    s6 = 6 * 3600
    assert RM.tick_at(_ts(2026, 10, 1, 5, 59, 59), s6) == _ts(2026, 10, 1, 0, 0)
    assert RM.tick_at(_ts(2026, 10, 1, 6, 0, 0), s6) == _ts(2026, 10, 1, 6, 0)
    assert RM.tick_at(_ts(2026, 10, 1, 17, 59, 59), s6) == _ts(2026, 10, 1, 12, 0)
    assert RM.tick_at(_ts(2026, 10, 1, 18, 0, 1), s6) == _ts(2026, 10, 1, 18, 0)
    assert RM.next_tick(_ts(2026, 10, 1, 6, 0, 0), s6) == _ts(2026, 10, 1, 12, 0)
    assert RM.next_tick(_ts(2026, 10, 1, 23, 59, 59), s6) == _ts(2026, 10, 2, 0, 0)
    day = _ts(2026, 10, 2)
    assert {RM.tick_at(day + m * 60, s6) for m in range(0, 1440, 7)} == {day + h * 3600 for h in (0, 6, 12, 18)}
    # the 15-minute grace is unchanged
    t6 = _ts(2026, 10, 2, 6, 0)
    assert RM.due_tick(t6 + 900, t6 - s6, tick_seconds=s6) == t6
    assert RM.due_tick(t6 + 901, t6 - s6, tick_seconds=s6) is None
    assert RM.due_tick(t6 + 30, t6, tick_seconds=s6) is None
    assert RM.due_tick(t6 + 30, None) is None                    # 12h: 06:00Z is no tick


def test_6h_ticks_run_at_0600z_and_1800z_with_the_same_grace_and_wait(tmp_path, live_env):
    t6 = T + 6 * 3600                                             # 2026-10-02 18:00Z
    calls: list = []
    clock = {"now": t6 + 30}
    live_env.setattr(R.time, "time", lambda: clock["now"])
    rt = _tick_runtime(tmp_path, live_env, calls)
    rt._maybe_random_tick()                                       # 12h (default): nothing at 18:00Z
    assert calls == []
    _t25(live_env)
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"] and calls[1][1:] == (t6, t6)
    (row,) = [json.loads(x) for x in (tmp_path / "futures_random_ticks.jsonl").read_text().splitlines()]
    assert row["tick_utc"] == "2026-10-02T18:00:00Z" and row["prereg"] == RM.PREREG25_TAG
    clock["now"] = t6 + 120
    rt._maybe_random_tick()
    assert len(calls) == 2, "once only"
    # 16 minutes late: skipped, as at 12h
    calls.clear()
    (tmp_path / "late").mkdir()
    rt = _tick_runtime(tmp_path / "late", live_env, calls)
    clock["now"] = t6 + 16 * 60
    rt._maybe_random_tick()
    assert calls == []
    # the 24h-clock wait: a position its own tick opened 24h ago holds the tick (bounded)
    (tmp_path / "w").mkdir()
    rt = _tick_runtime(tmp_path / "w", live_env, calls)
    rt.open_positions = {"OLD_USDT": _pos("OLD_USDT", md={"random_tick_ts": float(t6 - 86400)},
                                          opened=datetime.fromtimestamp(t6 - 86400 + 40, timezone.utc))}
    clock["now"] = t6 + 2
    rt._maybe_random_tick()
    assert calls == [] and rt._random_tick_pending == t6
    clock["now"] = t6 + RM.TICK_DEFER_SECONDS + 1
    rt._maybe_random_tick()
    assert [c[0] for c in calls] == ["select", "execute"]
    # the cycle sleep lands 1 s after 06:00Z / 18:00Z only at 6h
    rt2 = _rt(tmp_path / "w", MagicMock())
    clock["now"] = t6 - 100.5
    assert rt2._random_mode_sleep_seconds(300) == 102
    for k in T25_ENV:
        live_env.delenv(k)
    assert rt2._random_mode_sleep_seconds(300) == 300


def test_natural_side_per_bucket_and_no_coin_is_drawn(tmp_path, live_env):
    _on(live_env)
    _t25(live_env)

    def no_coin():
        raise AssertionError("a coin was drawn in natural mode")
    live_env.setattr(RM, "coin", no_coin)
    live_env.setattr(RM.os, "urandom", lambda n: no_coin())
    client = FakeClient({"ETH_USDT": 100.0, "L1_USDT": 1.0, "S1_USDT": 1.0})
    rt = _rt(tmp_path, client, paper=True)
    rt._btc_flag_asof = (T, False, {"trend_flag": 0.0})
    buckets = {"TREND": [_cand("ETH_USDT", "TREND", -0.03)],          # falling: still LONG
               "WC_LONG": [_cand("L1_USDT", "WC_LONG", -0.1, gate=1.0)],
               "WC_SHORT": [_cand("S1_USDT", "WC_SHORT", 0.2, gate=1.0)]}
    plan = _plan(buckets)
    plan["config"] = RM.config()
    decisions = rt._random_tick_execute(plan)
    assert [(d["bucket"], d["decision"], d["side"], d["coin"]) for d in decisions] == [
        ("TREND", "opened", "LONG", None), ("WC_LONG", "opened", "LONG", None),
        ("WC_SHORT", "opened", "SHORT", None)]
    for sym, side in (("ETH_USDT", "LONG"), ("L1_USDT", "LONG"), ("S1_USDT", "SHORT")):
        md = rt.open_positions[sym].metadata
        assert rt.open_positions[sym].side == side
        assert md["random_coin"] is None and md["random_side"] == side == md["random_natural_side"]
        assert md["random_side_mode"] == "natural" and md["random_prereg"] == RM.PREREG25_TAG
        assert (md["random_tick_hours"], md["random_trend_sl_mult"], md["random_wc_min_turnover"]) == \
            (6.0, 3.5, 2e6)
        assert "natural side → <b>%s</b>" % side in rt._random_entry_line(md)
    assert RM.side_for("WC_SHORT", "natural", None) == "SHORT" and RM.side_for("TREND", "coin", 1) == "SHORT"


def test_coin_mode_still_draws_one_coin_per_decided_position(tmp_path, live_env):
    _on(live_env)
    rt = _rt(tmp_path, MagicMock())
    plan = _plan(_three_buckets())
    plan["config"] = RM.config()
    opened, drawn, _d, _r = _exec(rt, plan, live_env, coins=[1, 1, 0])
    assert drawn == [1, 1, 0] and [o[3] for o in opened] == [1, 1, 0]
    assert plan["config"].prereg == RM.PREREG_TAG


def test_trend_stop_3_5_atr_and_the_r_based_levels(tmp_path, live_env):
    """FUTURES_TREND_SL_ATR_MULT=3.5: the stop is 3.5 x ATR14% from the reference, the
    20%-of-margin rule trims leverage, the target is 3R (1R when BTC is flagged) of the
    wider stop, 1R in $ is unchanged (fewer contracts), and the live exits measure R from
    the placed stop, so breakeven arms at 0.90 x the 3.5% distance. WILDCARD stays 3.0."""
    live_env.setenv("FUTURES_TREND_SL_ATR_MULT", "3.5")
    sig = RM.build_signal(symbol="ETH_USDT", sleeve="TREND", side="LONG", ref_price=100.0, atr_pct=0.01,
                          roc_pct=0.05, rsi=50.0)
    assert sig.leverage == 5                                  # 3.5% x 10 = 35% -> x5 (17.5%)
    assert sig.sl_price == pytest.approx(96.5) and sig.tp_price == pytest.approx(110.5)
    assert sig.sl_frac_designed == pytest.approx(0.035) and sig.sl_margin_pct == pytest.approx(17.5)
    wc = RM.build_signal(symbol="A_USDT", sleeve="WILDCARD", side="LONG", ref_price=100.0, atr_pct=0.01,
                         roc_pct=0.1, rsi=50.0)
    assert wc.sl_price == pytest.approx(97.0)                 # WILDCARD: 3.0 x ATR, unchanged
    # end to end, natural side, through the live entry
    _t25(live_env)
    rt, client = _trend_short_runtime(tmp_path, live_env)
    cand = _cand("ETH_USDT", "TREND", 0.05, gate=99.0, atr=0.01)
    plan = _plan({"TREND": [cand]})
    plan["config"] = RM.config()
    d = rt._random_open(plan, "TREND", cand, 1, 1, None, [])
    assert d["decision"] == "opened" and d["side"] == "LONG" and d["coin"] is None
    (order,) = client.orders
    assert order["side"] == 1 and order["leverage"] == 5
    assert order["stop_loss_price"] == pytest.approx(96.5) and order["take_profit_price"] == pytest.approx(110.5)
    pos = rt.open_positions["ETH_USDT"]
    md = pos.metadata
    assert md["risk_usdt_intended"] == pytest.approx(0.01205 * 1000.0, rel=1e-6)   # 1R $ unchanged
    assert order["vol"] == 3 and md["risk_usdt"] == pytest.approx(10.5)             # 12.05 / 3.5 -> 3
    assert md["random_trend_sl_mult"] == 3.5 and md["random_prereg"] == RM.PREREG25_TAG
    # breakeven at 0.90R of the 3.5% stop: 103.1 (0.886R) does not arm it (it would at 3.0x)
    assert rt._convex_runner_trail_exit(pos, 103.1) is False and client.tpsl == []
    assert rt._convex_runner_trail_exit(pos, 103.2) is False                      # 0.914R: arms
    (moved,) = client.tpsl
    assert 100.0 < moved["stop_loss_price"] < 100.5 and moved["take_profit_price"] == pytest.approx(110.5)
    # a flagged tick caps the target at 1R of the wider stop
    (tmp_path / "f").mkdir()
    rt, client = _trend_short_runtime(tmp_path / "f", live_env, btc=True)
    plan = _plan({"TREND": [cand]}, btc=True)
    plan["config"] = RM.config()
    rt._random_open(plan, "TREND", cand, 1, 1, None, [])
    (order,) = client.orders
    assert order["take_profit_price"] == pytest.approx(103.5)


def test_the_wildcard_turnover_floor_is_the_setting(tmp_path, live_env):
    tickers = [{"symbol": "A_USDT", "amount24": 3e6, "r": 0.5}, {"symbol": "B_USDT", "amount24": 1.2e7, "r": 0.5},
               {"symbol": "C_USDT", "amount24": 1e7, "r": 0.5}]
    kw = dict(majors=set(), tradeable=FuturesRuntime._is_tradeable_crypto, range_of=lambda t: t["r"])
    assert [s for s, _ in RM.universe(tickers, **kw)] == ["C_USDT", "B_USDT", "A_USDT"]
    assert [s for s, _ in RM.universe(tickers, min_turnover=1e7, **kw)] == ["C_USDT", "B_USDT"]
    # the runtime applies the tick's setting (every ticker carries $5M)
    for i, (raw, want) in enumerate((("", 3), ("5000000", 3), ("6000000", 0))):
        live_env.setenv("FUTURES_RANDOM_WC_MIN_TURNOVER", raw)
        (tmp_path / str(i)).mkdir()
        rt = _select_runtime(tmp_path / str(i), live_env)
        plan = rt._random_tick_select(T)
        assert len(plan["universe"]) == want and plan["config"].wc_min_turnover == float(raw or 2e6)


def test_the_journal_logs_the_full_ranking_trend_turnover_and_the_configuration(tmp_path, live_env):
    rt = _select_runtime(tmp_path, live_env)
    _t25(live_env)
    plan = rt._random_tick_select(T)
    for b in ("TREND", "WC_LONG", "WC_SHORT"):
        assert plan["buckets"][b] == plan["buckets_all"][b][:RM.TOP_N]
    eth = next(c for c in plan["buckets"]["TREND"] if c["symbol"] == "ETH_USDT")
    assert eth["ticker"] == {"range24": pytest.approx(0.30), "amount24": 5e6, "source": "ticker"}
    # journal only: a TREND position's stamps keep trial 24's (WILDCARD-only) ticker fields
    st = RM.stamp(tick=T, bucket="TREND", cand=eth, rank_=1, field=3, side="LONG", coin_=None,
                  ref_price=100.0, universe_n=3, held=[], cfg=plan["config"])
    assert st["random_turnover_24h"] is None and st["random_range_24h"] is None
    rt._random_journal(plan, [{"bucket": "TREND", "decision": "opened"}], T + 1)
    (row,) = [json.loads(x) for x in (tmp_path / "futures_random_ticks.jsonl").read_text().splitlines()]
    assert row["prereg"] == RM.PREREG25_TAG
    assert (row["random_tick_hours"], row["random_side_mode"], row["random_trend_sl_mult"],
            row["random_wc_min_turnover"]) == (6.0, "natural", 3.5, 2e6)
    assert [c["symbol"] for c in row["buckets_all"]["WC_LONG"]] == ["UP_USDT", "FL_USDT", "DN_USDT"]
    trend_eth = next(c for c in row["buckets"]["TREND"] if c["symbol"] == "ETH_USDT")
    assert trend_eth["ticker"]["amount24"] == 5e6 and trend_eth["ticker"]["range24"] == pytest.approx(0.30)
    # what it wrote before is all still there
    assert {"tick", "tick_utc", "prereg", "started_at", "done_at", "universe_n", "universe", "trend_symbols",
            "btc_flag", "unusable", "buckets", "decisions"} <= set(row)
    # the full ranking: every usable row, its first 10 = the top-10 list
    rows = [_row(f"S{i}_USDT", i / 100) for i in range(30)]
    full_l, full_s = RM.rank_wildcard(rows, top_n=None)
    top_l, top_s = RM.rank_wildcard(rows)
    assert len(full_l) == 30 and full_l[:RM.TOP_N] == top_l and full_s[:RM.TOP_N] == top_s


def test_every_stamp_carries_the_tick_configuration(tmp_path, live_env):
    assert {"random_tick_hours", "random_side_mode", "random_trend_sl_mult",
            "random_wc_min_turnover"} <= set(RM.STAMP_KEYS)
    _on(live_env)
    client = FakeClient({"L1_USDT": 1.0})
    rt = _rt(tmp_path, client, paper=True)
    live_env.setattr(RM, "coin", lambda: 0)
    plan = _plan({"WC_LONG": [_cand("L1_USDT", "WC_LONG", 0.3, gate=1.0)]})
    plan["config"] = RM.config()
    rt._random_tick_execute(plan)
    md = rt.open_positions["L1_USDT"].metadata
    assert (md["random_prereg"], md["random_tick_hours"], md["random_side_mode"], md["random_trend_sl_mult"],
            md["random_wc_min_turnover"], md["random_coin"]) == (RM.PREREG_TAG, 12.0, "coin", 3.0, 2e6, 0.0)
    assert "coin 0 → <b>LONG</b>" in rt._random_entry_line(md)
    rows = shadow_ledger.load_raw(str(tmp_path / "shadow.jsonl"))
    assert rows[-1]["random_side_mode"] == "coin" and rows[-1]["random_tick_hours"] == 12.0
    pos = rt.open_positions["L1_USDT"]
    assert rt._close_position_for_exit(pos, current_price=1.05, reason="CONVEX_TIME_STOP")
    feat = [json.loads(x) for x in (tmp_path / "features.jsonl").read_text().splitlines()][-1]
    for rec in (rt.trade_history[-1], feat):
        assert rec["random_side_mode"] == "coin" and rec["random_trend_sl_mult"] == 3.0


def test_the_status_line_prints_the_effective_values(tmp_path, live_env):
    _on(live_env)
    rt = _rt(tmp_path, MagicMock())
    live_env.setattr(R.time, "time", lambda: T + 3600)
    line = rt._random_mode_status_line()
    assert "trial 24" in line and "00:00Z / 12:00Z" in line and "coin flip" in line
    assert "every 12h · coin · TREND stop 3x ATR · WILDCARD turnover ≥ $2,000,000 · PREREG 29fabd853a4f5d77" in line
    _t25(live_env)
    line = rt._random_mode_status_line()
    assert "trial 25" in line and "00:00Z / 06:00Z / 12:00Z / 18:00Z" in line and "natural side" in line
    assert "every 6h · natural · TREND stop 3.5x ATR" in line and "PREREG 23840ce65807b549" in line
    assert "next 18:00Z" in line                                    # 13:00Z now: the next 6h tick
