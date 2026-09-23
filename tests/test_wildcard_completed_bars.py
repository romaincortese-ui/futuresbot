"""FUTURES_WILDCARD_COMPLETED_BARS - WILDCARD entries on completed 15m bars.

Assessment 2026-09-23, item 2 (docs/DECISION_RULE.md, IMPARTIAL ASSESSMENT + REPLAY
AUDIT): live WILDCARD scans the FORMING 15m bar and every replay line uses completed
bars, so 25-28% of live fills exist in no dataset. The flag moves WILDCARD to the
convention TREND has used since 2026-09-19. It is NOT ESTABLISHED as a dollar lever
(+$20 to +$100/mo, interval ~[-$180, +$120]) and defaults OFF; the owner switches it
only on the pre-registered forming- vs completed-bar test.

These tests pin two things: flag OFF is today's scan, input for input; flag ON trims
the forming bar, re-prices at the tick with the same distances, refuses stale and
already-reversed signals with a shadow row, and stamps the convention on every entry.
"""
from __future__ import annotations

import os
import time
from dataclasses import replace
from unittest.mock import MagicMock

import pandas as pd
import pytest

import futuresbot.runtime as R
from futuresbot.config import FuturesConfig
from futuresbot.runtime import ENTRY_GATE_KEYS, FuturesRuntime
from futuresbot.wildcard import detect_wildcard_signal

BOUNDARY = (int(time.time()) // 900) * 900        # a 15m bar open
REAL_DETECT = R.detect_wildcard_signal


# --- fixtures ----------------------------------------------------------------

def _seq(side: str = "LONG", legs: int = 17) -> list[float]:
    """Closes that fire the REAL detector on their last bar: a flat day, then an
    alternating 2% impulse / 0.5% pullback run ending pullback -> resume. The 3h
    ROC is ~9%, RSI ~80, the resume bar well under the blow-off limit."""
    up, dn = (0.02, -0.005) if side == "LONG" else (-0.02, 0.005)
    c = [100.0 * (1.005 if i % 2 else 1.0) for i in range(200)]
    for i in range(legs):
        c.append(c[-1] * (1 + (up if i % 2 == 0 else dn)))
    return c


def _bars(closes: list[float], side: str = "LONG", *, forming: bool,
          boundary: int = BOUNDARY) -> pd.DataFrame:
    """15m bars; when `forming` the last one opened at `boundary` and is still open.
    Wicks sit on the side's favourable end so the climax-wick gate passes."""
    last_open = boundary if forming else boundary - 900
    idx = pd.to_datetime([last_open - 900 * (len(closes) - 1 - i) for i in range(len(closes))],
                         unit="s", utc=True)
    hi, lo = (1.001, 0.997) if side == "LONG" else (1.003, 0.999)
    return pd.DataFrame({"open": closes, "high": [c * hi for c in closes],
                         "low": [c * lo for c in closes], "close": closes,
                         "volume": [1e3] * len(closes)}, index=idx)


class _Clock:
    """runtime's `time` module with a pinned time.time()."""

    def __init__(self, t: float) -> None:
        self.t = t

    def time(self) -> float:
        return self.t

    def __getattr__(self, name):
        return getattr(time, name)


def _clean_env(monkeypatch, **env) -> None:
    for k in [k for k in os.environ
              if k.startswith(("FUTURES_WILDCARD_", "FUTURES_EXTERNAL_GATE"))]:
        monkeypatch.delenv(k, raising=False)
    base = {"FUTURES_WILDCARD_ENABLED": "1",
            "FUTURES_WILDCARD_MAX_CALM_RATIO": "0",      # the synthetic run is a calm-shock
            "FUTURES_WILDCARD_LONG_ONLY": "0",
            "FUTURES_EXTERNAL_GATE_ENABLED": "0",
            "MEXC_API_KEY": "k", "MEXC_API_SECRET": "s"}
    base.update(env)
    for k, v in base.items():
        monkeypatch.setenv(k, v)


def _scan(tmp_path, monkeypatch, frames: dict, *, completed: bool, now: float,
          last_scan: float = 0.0, ranges: dict | None = None, **env):
    """Run _maybe_scan_wildcard once against `frames`, recording what the detector
    was handed, what was opened and what was shadow-logged."""
    _clean_env(monkeypatch, FUTURES_WILDCARD_COMPLETED_BARS="1" if completed else "0", **env)
    monkeypatch.setattr(R, "time", _Clock(now))
    seen: list[tuple] = []

    def _spy(frame, sym, reasons=None, min_roc=None):
        sig = REAL_DETECT(frame, sym, reasons, min_roc=min_roc)
        seen.append((sym, frame, min_roc, sig))
        return sig
    monkeypatch.setattr(R, "detect_wildcard_signal", _spy)

    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "rt.json"),
                  status_file=str(tmp_path / "st.json"),
                  telegram_token="", telegram_chat_id="")
    rt = FuturesRuntime(cfg, MagicMock())
    ranges = ranges or {}
    rt.client.get_all_tickers.return_value = [
        {"symbol": s, "amount24": 9e6, "riseFallRate": 0.05,
         "high24Price": 100.0 * (1 + ranges.get(s, 0.5)), "lower24Price": 100.0}
        for s in frames]
    rt.client.get_klines.side_effect = lambda sym, **kw: frames[sym]
    opened: list[tuple] = []
    shadow: list[tuple] = []
    rt._account_snapshot = lambda *a, **k: {"available_usdt": 1000.0}
    rt._get_reference_price = lambda *a, **k: 1.0
    rt._refresh_non_crypto_universe = lambda: None
    rt._is_tradeable_crypto = lambda sym: True
    rt._major_symbols = lambda tickers, n: set()
    rt._alt_breadth = lambda *a, **k: None
    rt._record_ticker_snapshot = lambda movers: None
    rt._maybe_capture_news = lambda: None
    rt._convex_open_count = lambda *a, **k: 0
    rt._preemption_possible = lambda: False
    rt._open_wildcard_position = lambda sig, avail, **kw: opened.append(
        (sig, dict(rt._wildcard_attribution.get(sig.symbol, {})), rt._pending_entry_lateness)) or True
    rt._shadow_log_untaken = lambda sig, kind, reason: shadow.append(
        (sig, reason, dict(rt._wildcard_attribution.get(sig.symbol, {})), rt._pending_entry_lateness))
    rt._last_wildcard_scan_at = last_scan
    rt._maybe_scan_wildcard()
    return rt, seen, opened, shadow


def _dist(sig):
    """(stop distance, target distance) as fractions of the entry."""
    e = float(sig.entry_price)
    return abs(e - float(sig.sl_price)) / e, abs(float(sig.tp_price) - e) / e


# --- the flag ------------------------------------------------------------------

def test_the_flag_defaults_off(monkeypatch):
    """Default-off is the whole safety case: a deploy of this code must not move
    WILDCARD onto a convention no live evidence has priced."""
    monkeypatch.delenv("FUTURES_WILDCARD_COMPLETED_BARS", raising=False)
    assert FuturesRuntime._wildcard_completed_bars() is False
    monkeypatch.setenv("FUTURES_WILDCARD_COMPLETED_BARS", "1")
    assert FuturesRuntime._wildcard_completed_bars() is True


# --- flag OFF: today's scan, input for input ---------------------------------------

def test_flag_off_hands_the_detector_the_raw_kline_frame(tmp_path, monkeypatch):
    """REGRESSION GUARD for 'none may silently change when the flag is 0': the
    detector must receive the very object get_klines returned (forming bar and
    all), with the same trigger, and the signal it returns must reach the order
    untouched - no trim, no re-anchor, no guard."""
    full = _bars(_seq(), forming=True)
    rt, seen, opened, shadow = _scan(tmp_path, monkeypatch, {"A_USDT": full},
                                     completed=False, now=BOUNDARY + 30)
    (sym, frame, min_roc, sig), = seen
    assert frame is full and min_roc == pytest.approx(0.08)
    assert sig is not None and len(opened) == 1
    taken, att, lat = opened[0]
    assert taken is sig and taken.gate_close is None
    assert lat == FuturesRuntime._entry_lateness(full, sig.side)
    assert shadow == []
    hist = rt._last_wildcard_scan["hist"]
    assert "stale_bar" not in hist and "resume_failed" not in hist


def test_flag_off_still_takes_the_forming_bar_signal(tmp_path, monkeypatch):
    """The EVAA shape (DECISION_RULE 2026-09-20): the pullback-resume exists only
    inside the half-formed bar. Today's scan takes it; flag off must keep doing so."""
    rt, seen, opened, _ = _scan(tmp_path, monkeypatch, {"A_USDT": _bars(_seq(), forming=True)},
                                completed=False, now=BOUNDARY + 30)
    assert len(opened) == 1


def test_flag_off_keeps_the_450s_rolling_clock(tmp_path, monkeypatch):
    """Off, the scan still runs 450 s after the last one even inside the same bar,
    and not before: the capture rate the trial-9 clock bought is unchanged."""
    frames = {"A_USDT": _bars(_seq(), forming=True)}
    rt, seen, _, _ = _scan(tmp_path, monkeypatch, frames, completed=False,
                           now=BOUNDARY + 600, last_scan=BOUNDARY + 100)
    assert seen, "a same-bar scan 500 s later must run with the flag off"
    rt, seen, _, _ = _scan(tmp_path, monkeypatch, frames, completed=False,
                           now=BOUNDARY + 600, last_scan=BOUNDARY + 300)
    assert not seen and not rt.client.get_all_tickers.called


def test_flag_off_stamps_the_forming_convention(tmp_path, monkeypatch):
    """Every WILDCARD entry names its convention, so the live book can be split
    after a switch; under the forming bar there is no separate gate close."""
    _, _, opened, _ = _scan(tmp_path, monkeypatch, {"A_USDT": _bars(_seq(), forming=True)},
                            completed=False, now=BOUNDARY + 30)
    att = opened[0][1]
    assert att["wildcard_completed_bars"] == 0.0
    assert "wildcard_gate_close" not in att and "wildcard_bar_age_s" not in att


# --- flag ON ---------------------------------------------------------------------------

def test_flag_on_drops_the_forming_bar_before_the_detector(tmp_path, monkeypatch):
    """The forming-bar read is the defect: the detector must see settled bars only."""
    closes = _seq()
    full = _bars(closes + [closes[-1] * 1.004], forming=True)
    _, seen, _, _ = _scan(tmp_path, monkeypatch, {"A_USDT": full},
                          completed=True, now=BOUNDARY + 30)
    (sym, frame, min_roc, sig), = seen
    assert len(frame) == len(full) - 1
    assert frame.index[-1] == full.index[-2]
    assert float(frame["close"].iloc[-1]) == pytest.approx(closes[-1])
    assert min_roc == pytest.approx(0.08)


def test_flag_on_refuses_a_resume_that_exists_only_in_the_forming_bar(tmp_path, monkeypatch):
    """EVAA: on completed bars the shape is `no_pullback_resume`, so nothing is taken."""
    rt, seen, opened, _ = _scan(tmp_path, monkeypatch, {"A_USDT": _bars(_seq(), forming=True)},
                                completed=True, now=BOUNDARY + 30)
    assert seen[0][3] is None and opened == []
    assert rt._last_wildcard_scan["hist"].get("no_pullback_resume") == 1


@pytest.mark.parametrize("side,tick", [("LONG", 1.004), ("SHORT", 0.996)])
def test_flag_on_anchors_at_the_tick_keeping_both_distances(tmp_path, monkeypatch, side, tick):
    """Sizing and the per-trade risk cap must describe the order actually sent, not a
    close that may be minutes old - and the stop/target DISTANCES the detector designed
    must survive the re-price on both sides. roc_pct stays the gate's own value."""
    closes = _seq(side)
    px = closes[-1] * tick
    full = _bars(closes + [px], side, forming=True)
    _, seen, opened, shadow = _scan(tmp_path, monkeypatch, {"A_USDT": full},
                                    completed=True, now=BOUNDARY + 30)
    gate_sig = seen[0][3]
    assert gate_sig is not None and gate_sig.side == side
    (taken, att, lat), = opened
    assert taken.entry_price == pytest.approx(px)
    assert taken.gate_close == pytest.approx(closes[-1])
    assert _dist(taken) == pytest.approx(_dist(gate_sig))
    assert (taken.sl_price < taken.entry_price < taken.tp_price) == (side == "LONG")
    assert taken.roc_pct == gate_sig.roc_pct and taken.leverage == gate_sig.leverage
    assert lat == FuturesRuntime._entry_lateness(seen[0][1], side)   # ranked on the gate's bars
    assert att["wildcard_completed_bars"] == 1.0
    assert att["wildcard_gate_close"] == pytest.approx(closes[-1])
    assert att["wildcard_bar_age_s"] == pytest.approx(30.0)
    assert shadow == []


def test_flag_on_scans_once_per_bar(tmp_path, monkeypatch):
    """The completed-bar input changes only at a close. A second scan inside the
    same bar could only re-take a staler price, so it must not run at all."""
    closes = _seq()
    frames = {"A_USDT": _bars(closes + [closes[-1] * 1.004], forming=True)}
    rt, seen, _, _ = _scan(tmp_path, monkeypatch, frames, completed=True,
                           now=BOUNDARY + 60, last_scan=BOUNDARY + 5)
    assert not seen and not rt.client.get_all_tickers.called
    _, seen, opened, _ = _scan(tmp_path, monkeypatch, frames, completed=True,
                               now=BOUNDARY + 60, last_scan=BOUNDARY - 400)
    assert seen and len(opened) == 1


def test_flag_on_refuses_and_logs_a_stale_bar(tmp_path, monkeypatch):
    """A restart mid-bar: the gate bar closed 400 s ago, so the tick is not the
    moment the gates approved. Refused before the candidate list, shadow-logged so
    the refusal keeps being priced, counted in the scan histogram."""
    closes = _seq()
    frames = {"A_USDT": _bars(closes + [closes[-1] * 1.004], forming=True)}
    rt, _, opened, shadow = _scan(tmp_path, monkeypatch, frames, completed=True,
                                  now=BOUNDARY + 400)
    assert opened == []
    (sig, reason, att, lat), = shadow
    assert reason == "stale_bar"
    assert att["wildcard_completed_bars"] == 1.0 and att["wildcard_bar_age_s"] == pytest.approx(400.0)
    assert lat is not None
    assert rt._last_wildcard_scan["hist"]["stale_bar"] == 1
    # ...and the limit is an env knob, like TREND's
    _, _, opened, shadow = _scan(tmp_path, monkeypatch, frames, completed=True,
                                 now=BOUNDARY + 400,
                                 FUTURES_WILDCARD_MAX_BAR_AGE_SECONDS="600")
    assert len(opened) == 1 and shadow == []


@pytest.mark.parametrize("side,back", [("LONG", 0.999), ("SHORT", 1.001)])
def test_flag_on_refuses_a_move_that_already_reversed(tmp_path, monkeypatch, side, back):
    """The breakout_failed analog: the tick is back through the pullback bar's close,
    so the resume the detector approved no longer exists at the order price."""
    closes = _seq(side)
    full = _bars(closes + [closes[-2] * back], side, forming=True)
    rt, seen, opened, shadow = _scan(tmp_path, monkeypatch, {"A_USDT": full},
                                     completed=True, now=BOUNDARY + 30)
    assert seen[0][3] is not None and opened == []
    (sig, reason, att, _), = shadow
    assert reason == "resume_failed"
    assert sig.entry_price == pytest.approx(closes[-2] * back)
    assert rt._last_wildcard_scan["hist"]["resume_failed"] == 1


def test_the_stale_guard_units(monkeypatch):
    """stale_bar floors at 60 s whatever the env says; resume_failed re-checks only a
    resume that existed on the completed bars, so with the pullback gate switched off
    (a down gate bar on a LONG) it cannot add a filter of its own."""
    _clean_env(monkeypatch)
    closes = _seq()
    closed = _bars(closes, forming=False)
    sig = detect_wildcard_signal(closed, "A_USDT")
    rt = object.__new__(FuturesRuntime)
    bar_close = closed.index[-1].timestamp() + 900
    assert rt._wildcard_signal_stale(sig, closed, bar_close + 30) is None
    assert rt._wildcard_signal_stale(sig, closed, bar_close + 181) == "stale_bar"
    monkeypatch.setenv("FUTURES_WILDCARD_MAX_BAR_AGE_SECONDS", "5")
    assert rt._wildcard_signal_stale(sig, closed, bar_close + 59) is None
    assert rt._wildcard_signal_stale(sig, closed, bar_close + 61) == "stale_bar"
    down = closed.copy()
    down.iloc[-1, down.columns.get_loc("close")] = closes[-2] * 0.99   # gate bar closed DOWN
    no_resume = replace(sig, entry_price=closes[-2] * 0.98, gate_close=closes[-2] * 0.99)
    assert rt._wildcard_signal_stale(no_resume, down, bar_close + 30) is None
    assert FuturesRuntime._completed_bar_age(pd.DataFrame({"close": [1.0]}), bar_close) is None


def test_flag_on_leaves_the_ticker_screens_alone(tmp_path, monkeypatch):
    """The 24h-range prefilter and the long range cap read the exchange TICKER, not a
    bar: the same symbols are screened in, and a LONG over the cap is refused with the
    same reason, under either convention."""
    closes = _seq()
    for completed in (False, True):
        # a frame that fires under each convention: the resume in the forming bar
        # (off), or in the last completed bar with a tick after it (on)
        f = _bars(closes + [closes[-1] * 1.004] if completed else closes, forming=True)
        frames = {"A_USDT": f, "Q_USDT": f}
        rt, seen, _, shadow = _scan(tmp_path, monkeypatch, frames, completed=completed,
                                    now=BOUNDARY + 30, ranges={"A_USDT": 2.5, "Q_USDT": 0.05},
                                    FUTURES_WILDCARD_LONG_MAX_24H_RANGE="2.0")
        assert [s for s, *_ in seen] == ["A_USDT"]          # Q's 5% range never reaches bars
        assert seen[0][3] is not None
        assert [r for _, r, *_ in shadow] == ["long_range_cap(2.50)"]


def test_flag_on_the_external_veto_sees_the_anchored_order_and_the_gate_roc(tmp_path, monkeypatch):
    """The veto compares the MEXC trigger move with the reference venue: it must get
    the trigger that fired (roc_pct) on the order that will be sent (tick price)."""
    closes = _seq()
    px = closes[-1] * 1.004
    frames = {"A_USDT": _bars(closes + [px], forming=True)}
    got = []
    monkeypatch.setattr(FuturesRuntime, "_external_entry_veto",
                        lambda self, sig, kind: got.append(sig) or (True, "ok"))
    _, seen, opened, _ = _scan(tmp_path, monkeypatch, frames, completed=True,
                               now=BOUNDARY + 30, FUTURES_EXTERNAL_GATE_ENABLED="1")
    (sig,), = [got]
    assert sig.entry_price == pytest.approx(px) and sig.roc_pct == seen[0][3].roc_pct
    assert len(opened) == 1


def test_the_convention_reaches_the_trade_record_and_feature_store():
    """A stamp on the position that is dropped at close cannot split the book."""
    for k in ("wildcard_completed_bars", "wildcard_gate_close", "wildcard_bar_age_s"):
        assert k in ENTRY_GATE_KEYS


# --- the surfaces that describe the scan -------------------------------------------------

def _why_ctx(rt):
    return {"by_symbol": {"A_USDT": {"symbol": "A_USDT", "amount24": 9e6,
                                     "high24Price": 150.0, "lower24Price": 100.0}},
            "majors": set(), "exclude_top": 24, "floor": 1e6, "min_move": 0.08,
            "min_roc": 0.08, "range_prefilter": True, "max_calm": 0.0, "slot_free": True}


@pytest.mark.parametrize("completed,verdict", [(False, "ready"), (True, "shape")])
def test_why_follows_the_scans_bar_convention(monkeypatch, completed, verdict):
    """/why claims to mirror the scan step for step. Flag on, it must not call a
    forming-bar signal "live" that the completed-bar scan will never take."""
    _clean_env(monkeypatch, FUTURES_WILDCARD_COMPLETED_BARS="1" if completed else "0")
    rt = object.__new__(FuturesRuntime)
    rt.open_positions = {}
    rt._is_tradeable_crypto = lambda sym: True
    # /why trims against the wall clock, so the forming bar is the REAL current one
    frame = _bars(_seq(), forming=True, boundary=int(time.time()) // 900 * 900)
    cls, _ = rt._why_symbol_verdict("A_USDT", _why_ctx(rt), frame)
    assert cls == verdict


def test_the_stall_alarm_allows_for_one_scan_per_bar(tmp_path, monkeypatch):
    """Once per bar, a 20-minute-old scan is normal; at the 450 s clock it is a stall.
    The alarm must not cry wolf on every bar after the flag is switched on."""
    _clean_env(monkeypatch)
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "rt.json"),
                  status_file=str(tmp_path / "st.json"),
                  telegram_token="", telegram_chat_id="")
    rt = FuturesRuntime(cfg, MagicMock())
    rt.client.get_all_tickers.return_value = [
        {"symbol": "A_USDT", "amount24": 9e6, "riseFallRate": 0.5,
         "high24Price": 200.0, "lower24Price": 100.0, "riseFallRates": {"r7": 0.0}}]
    monkeypatch.setattr(rt, "_major_symbols", lambda t, n: set())
    monkeypatch.setattr(rt, "_feature_rows_cached", lambda: [])
    monkeypatch.setattr(rt, "_shadow_ledger_path", lambda: "/nonexistent")
    monkeypatch.setattr(rt, "_replay_verdict", lambda s, r, bars_back=96: "x")
    monkeypatch.setattr(rt, "_window_move", lambda sym, hours: (0.0, 0.0))
    rt._paused = False
    rt._last_wildcard_scan = {"at": time.time() - 20 * 60}
    monkeypatch.setenv("FUTURES_WILDCARD_COMPLETED_BARS", "0")
    assert "may have stalled" in "\n".join(rt._missed_opportunity_lines())
    monkeypatch.setenv("FUTURES_WILDCARD_COMPLETED_BARS", "1")
    assert "may have stalled" not in "\n".join(rt._missed_opportunity_lines())
