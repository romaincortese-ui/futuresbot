"""TREND-only trail and breakeven overrides (assessment 2026-09-23, item 3).

The retention trail and the breakeven stop are shared by WILDCARD, SQUEEZE and
TREND. The impartial assessment ranked "TREND without the retention trail (or
arming at >= 2R)" as a candidate: in-sample +$85/month [-$28, +$204], NOT
ESTABLISHED - one bull market. So the variants exist in code, behind flags that
default to today's behaviour, for a pre-registered test to price:

    FUTURES_TREND_TRAIL_ENABLED    default 1       (0 = no trail on TREND)
    FUTURES_TREND_TRAIL_ARM_R      default shared  (FUTURES_CONVEX_TRAIL_ARM_R, 1.0)
    FUTURES_TREND_BREAKEVEN_ARM_R  default shared  (FUTURES_CONVEX_BREAKEVEN_ARM_R, live 0.90)

Three properties are pinned here. Unset, both sleeves behave exactly as before.
No TREND variable can ever reach a WILDCARD or SQUEEZE position. And the
variants do what the test that will price them assumes: trail-off keeps the
stop, target, breakeven and clock; arm-2R moves the gate and nothing else.

Geometry used throughout: entry 100, stop 90, 10x leverage, margin $10 - so a
+10% price move is exactly +1R and 1R is $10. Retain is pinned at the live 0.50.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from futuresbot import shadow_ledger as shadow
from futuresbot.config import FuturesConfig
from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime

_TREND_VARS = ("FUTURES_TREND_TRAIL_ENABLED", "FUTURES_TREND_TRAIL_ARM_R",
               "FUTURES_TREND_BREAKEVEN_ARM_R")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in _TREND_VARS + (
            "FUTURES_CONVEX_TRAIL_ARM_R", "FUTURES_CONVEX_TRAIL_RETAIN_FRAC",
            "FUTURES_CONVEX_TRAIL_RATCHET_R", "FUTURES_CONVEX_TRAIL_RATCHET_RETAIN",
            "FUTURES_CONVEX_RUNNER_TRAIL", "FUTURES_CONVEX_COST_PCT",
            "FUTURES_CONVEX_COST_FLOOR_MULT", "FUTURES_CONVEX_BREAKEVEN_ARM_R",
            "FUTURES_CONVEX_BREAKEVEN_SHADOW_R", "FUTURES_CONVEX_BREAKEVEN_COST_PCT",
            "FUTURES_CONVEX_TIME_STOP_HOURS", "FUTURES_WILDCARD_CONVEX_EXIT_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setenv("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", "0.50")      # the live value


class _Client:
    """Fair price and book for /arm, resting-order calls for the breakeven stop."""

    def __init__(self, price: float = 106.0) -> None:
        self.price = price
        self.calls: list[tuple[str, dict]] = []

    def get_fair_price(self, symbol):
        return self.price

    def get_ticker(self, symbol):
        return {"bid1": self.price, "ask1": self.price, "lastPrice": self.price}

    def cancel_all_tpsl(self, *, position_id=None, symbol=None, **kw):
        self.calls.append(("cancel", {"position_id": position_id, "symbol": symbol}))
        return {"success": True}

    def place_position_tpsl(self, **kw):
        self.calls.append(("place", kw))
        return {"success": True}

    def get_open_positions(self, symbol=None):
        return [{"positionType": 1, "holdVol": 1}]

    def get_account_asset(self, currency="USDT"):
        return {"availableBalance": "200", "equity": "200"}

    def get_updates(self, *, offset=None, limit=5, timeout=0):
        return []


def _runtime(tmp_path, client: _Client | None = None) -> FuturesRuntime:
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "s.json"),
                  status_file=str(tmp_path / "st.json"),
                  telegram_token="t", telegram_chat_id="1", paper_trade=False)
    rt = FuturesRuntime(cfg, client or _Client())
    rt._sent = []
    rt._notify = lambda message, *a, **k: rt._sent.append(message)
    rt._notify_once = lambda *a, **k: None
    rt._save_state = lambda: None
    rt._closed = []
    rt._close_position_for_exit = (
        lambda p, **kw: rt._closed.append((p.symbol, kw.get("reason"))) or True)
    return rt


def _pos(kind: str, symbol: str | None = None,
         opened_ago: timedelta = timedelta(hours=1)) -> FuturesPosition:
    md = {"wildcard": 1.0, "sl_margin_pct": 100.0}
    if kind == "TREND":
        md["trend"] = 1.0
    elif kind == "SQUEEZE":
        md["squeeze"] = 1.0
    return FuturesPosition(
        symbol=symbol or f"{kind}_USDT", side="LONG", entry_price=100.0, contracts=1,
        contract_size=1.0, leverage=10, margin_usdt=10.0, tp_price=150.0, sl_price=90.0,
        position_id="7", order_id="1", opened_at=datetime.now(timezone.utc) - opened_ago,
        score=96.0, certainty=0.9, entry_signal=f"{kind}_LONG", metadata=md)


def _walk(rt: FuturesRuntime, pos: FuturesPosition, prices: list[float]) -> int | None:
    """Poll the trail along a price path; return the index of the closing poll."""
    for i, price in enumerate(prices):
        if rt._convex_runner_trail_exit(pos, price):
            return i
    return None


def _placed_stops(client: _Client) -> list[float]:
    return [kw["stop_loss_price"] for name, kw in client.calls if name == "place"]


# Peak +1.5R, then a fade through the 0.50 x 1.5 = +0.75R floor at price 107.
_FADE_15R = [105.0, 110.0, 115.0, 110.0, 108.0, 107.0, 104.0]
# Peak +2.1R, then a fade through the 0.50 x 2.1 = +1.05R floor.
_FADE_21R = [110.0, 121.0, 115.0, 111.0, 110.0]


# --- unset: identical to today, for both sleeves ---------------------------

def test_unset_the_accessors_return_exactly_the_shared_values(tmp_path, monkeypatch):
    """The whole ship condition: with no TREND variable set, every sleeve reads the
    shared arm, the shared switch and the shared breakeven arm - including when the
    shared values themselves are moved, so TREND can never silently pin the old
    default."""
    rt = _runtime(tmp_path)
    for kind in ("WILDCARD", "SQUEEZE", "TREND"):
        p = _pos(kind)
        assert rt._trail_enabled_for(p) is True
        assert rt._trail_arm_r_for(p) == pytest.approx(1.0)
        assert rt._breakeven_arm_r_for(p) == pytest.approx(0.0)
    monkeypatch.setenv("FUTURES_CONVEX_TRAIL_ARM_R", "1.4")
    monkeypatch.setenv("FUTURES_CONVEX_BREAKEVEN_ARM_R", "0.90")
    for kind in ("WILDCARD", "SQUEEZE", "TREND"):
        p = _pos(kind)
        assert rt._trail_arm_r_for(p) == pytest.approx(1.4)
        assert rt._breakeven_arm_r_for(p) == pytest.approx(0.90)
    monkeypatch.setenv("FUTURES_CONVEX_RUNNER_TRAIL", "0")
    for kind in ("WILDCARD", "SQUEEZE", "TREND"):
        assert rt._trail_enabled_for(_pos(kind)) is False


def test_unset_trend_trails_exactly_like_wildcard(tmp_path):
    """Same path, same poll, same floor, same reason: the TREND position must close
    where today's shared trail closes it (floor 0.50 x 1.5R = +0.75R, price 107)."""
    rt = _runtime(tmp_path)
    trend, wild = _pos("TREND"), _pos("WILDCARD")
    assert _walk(rt, trend, _FADE_15R) == 5
    assert _walk(rt, wild, _FADE_15R) == 5
    assert rt._closed == [("TREND_USDT", "CONVEX_RETENTION_TRAIL"),
                          ("WILDCARD_USDT", "CONVEX_RETENTION_TRAIL")]
    assert trend.metadata["convex_peak_r"] == wild.metadata["convex_peak_r"] == pytest.approx(1.5)


def test_unset_status_line_and_record_message_are_unchanged(tmp_path, monkeypatch):
    """The two human surfaces print what they printed before: "arms at $+10.00"
    and the old literal "Trail arms at +1R." below the arm."""
    rt = _runtime(tmp_path)
    trend = _pos("TREND")
    trend.metadata["convex_peak_r"] = 0.6
    assert "arms at <b>$+10.00</b>" in rt._trail_line(trend)
    monkeypatch.setattr(FuturesRuntime, "_best_weekly_close_usd", lambda self: 1.0)
    rt._maybe_record_peak_notify(trend, 0.8)
    assert rt._sent[-1].endswith("\nTrail arms at +1R.")


# --- the TREND variables never reach WILDCARD or SQUEEZE --------------------

def test_trend_variables_never_touch_wildcard_or_squeeze(tmp_path, monkeypatch):
    """Every TREND variable set to its most aggressive value: the other sleeves must
    still arm at 1R, close on the same poll and move their breakeven stop at 0.90R.
    The arm family is refuted on WILDCARD (four grids); a TREND test that leaked
    into it would reset a trial nobody chose to reset."""
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ENABLED", "0")
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ARM_R", "2.0")
    monkeypatch.setenv("FUTURES_TREND_BREAKEVEN_ARM_R", "0")
    monkeypatch.setenv("FUTURES_CONVEX_BREAKEVEN_ARM_R", "0.90")
    for kind in ("WILDCARD", "SQUEEZE"):
        client = _Client()
        rt = _runtime(tmp_path, client)
        p = _pos(kind)
        assert rt._trail_enabled_for(p) is True
        assert rt._trail_arm_r_for(p) == pytest.approx(1.0)
        assert rt._breakeven_arm_r_for(p) == pytest.approx(0.90)
        assert _walk(rt, p, _FADE_15R) == 5
        assert rt._closed == [(p.symbol, "CONVEX_RETENTION_TRAIL")]
        assert _placed_stops(client) == [pytest.approx(100.19)]     # breakeven moved once


def test_shadow_ledger_scores_wildcard_rows_identically_under_trend_variables(monkeypatch):
    """The ledger is the counterfactual corpus; a TREND flag must not move one
    WILDCARD row."""
    row = _row("WILDCARD")
    before = shadow.resolve_outcome(dict(row), _bars(_FADE_15R), 1e12, convex=True)
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ENABLED", "0")
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ARM_R", "2.0")
    after = shadow.resolve_outcome(dict(row), _bars(_FADE_15R), 1e12, convex=True)
    assert before == after and before["outcome_kind"] == "trail"


# --- trail off on TREND ----------------------------------------------------

def test_trend_trail_off_never_closes_on_the_floor(tmp_path, monkeypatch):
    """The path that closes today's TREND at +0.75R rides on: no floor exists."""
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ENABLED", "0")
    rt = _runtime(tmp_path)
    trend = _pos("TREND")
    assert _walk(rt, trend, _FADE_15R + [101.0, 95.0]) is None
    assert rt._closed == []


def test_trend_trail_off_keeps_the_bookkeeping_and_the_breakeven_stop(tmp_path, monkeypatch):
    """The switch sits BELOW the peak, trough and breakeven code on purpose. The
    breakeven stop is a separate mechanism (owner decision 2026-09-20) and must not
    be switched off by the trail switch; the peak feeds the feature store."""
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ENABLED", "0")
    monkeypatch.setenv("FUTURES_CONVEX_BREAKEVEN_ARM_R", "0.90")
    client = _Client()
    rt = _runtime(tmp_path, client)
    trend = _pos("TREND")
    _walk(rt, trend, [97.0, 105.0, 115.0, 108.0])
    assert trend.metadata["convex_peak_r"] == pytest.approx(1.5)
    assert trend.metadata["convex_trough_r"] == pytest.approx(-0.3)
    assert _placed_stops(client) == [pytest.approx(100.19)]
    assert trend.metadata["be_stop_price"] == pytest.approx(100.19)


def test_trend_trail_off_keeps_the_24h_clock(tmp_path, monkeypatch):
    """Trail-off is stop + target + breakeven + clock, the variant the assessment
    priced. The clock must not read the trail switch."""
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ENABLED", "0")
    rt = _runtime(tmp_path)
    old = _pos("TREND", opened_ago=timedelta(hours=25))
    assert rt._convex_time_stop_exit(old, 104.0) is True
    assert rt._closed == [("TREND_USDT", "CONVEX_TIME_STOP")]


def test_trend_trail_off_hides_the_floor_from_status_and_messages(tmp_path, monkeypatch):
    """A floor that cannot fire must not be printed as one: /status drops the trail
    line, the record-peak message says there is no trail, and /arm refuses."""
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ENABLED", "0")
    rt = _runtime(tmp_path, _Client(price=115.0))
    trend = _pos("TREND")
    trend.metadata["convex_peak_r"] = 1.5
    assert rt._trail_line(trend) is None
    monkeypatch.setattr(FuturesRuntime, "_best_weekly_close_usd", lambda self: 1.0)
    rt._maybe_record_peak_notify(trend, 1.5)
    assert "Floor locked" not in rt._sent[-1]
    assert "No trail on this sleeve" in rt._sent[-1]
    rt.open_positions[trend.symbol] = trend
    ok, message = rt._manual_arm(trend.symbol)
    assert ok is False and "not managed by the retention trail" in message
    assert "manual_arm" not in trend.metadata


def test_the_master_switch_still_wins_over_the_trend_switch(tmp_path, monkeypatch):
    """FUTURES_TREND_TRAIL_ENABLED=1 cannot re-enable a trail the owner killed."""
    monkeypatch.setenv("FUTURES_CONVEX_RUNNER_TRAIL", "0")
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ENABLED", "1")
    rt = _runtime(tmp_path)
    assert rt._trail_enabled_for(_pos("TREND")) is False
    assert _walk(rt, _pos("TREND"), _FADE_15R) is None


# --- arm at 2R on TREND ----------------------------------------------------

def test_trend_arm_2r_leaves_a_15r_peak_unfloored(tmp_path, monkeypatch):
    """The path today's rule closes at +0.75R rides on under a 2R arm."""
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ARM_R", "2.0")
    rt = _runtime(tmp_path)
    assert _walk(rt, _pos("TREND"), _FADE_15R + [101.0]) is None
    assert rt._closed == []


def test_trend_arm_2r_moves_the_gate_and_nothing_else(tmp_path, monkeypatch):
    """Once armed, the floor is the same retain x peak: 0.50 x 2.1R = +1.05R, so the
    poll at +1.0R (price 110) closes, with the same reason as today."""
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ARM_R", "2.0")
    rt = _runtime(tmp_path)
    trend = _pos("TREND")
    assert _walk(rt, trend, _FADE_21R) == 4
    assert rt._closed == [("TREND_USDT", "CONVEX_RETENTION_TRAIL")]


def test_trend_arm_2r_is_what_status_and_messages_quote(tmp_path, monkeypatch):
    """/status must say it arms at $+20.00 (2R x $10), and a record peak at 1.5R
    must not claim a floor the exit path will not enforce."""
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ARM_R", "2.0")
    rt = _runtime(tmp_path)
    trend = _pos("TREND")
    trend.metadata["convex_peak_r"] = 1.5
    assert "arms at <b>$+20.00</b>" in rt._trail_line(trend)
    monkeypatch.setattr(FuturesRuntime, "_best_weekly_close_usd", lambda self: 1.0)
    rt._maybe_record_peak_notify(trend, 1.5)
    assert rt._sent[-1].endswith("\nTrail arms at +2R.")


def test_manual_arm_on_trend_stamps_the_trend_arm(tmp_path, monkeypatch):
    """/arm measures "below the gate" against the gate the exit path applies, and
    records it: the manual_arm_decisive filter at close compares against it."""
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ARM_R", "2.0")
    rt = _runtime(tmp_path, _Client(price=115.0))                   # +1.5R
    trend = _pos("TREND")
    rt.open_positions[trend.symbol] = trend
    ok, _ = rt._manual_arm(trend.symbol)
    assert ok is True
    assert trend.metadata["manual_arm_arm_r"] == pytest.approx(2.0)


# --- the TREND breakeven override -------------------------------------------

def test_trend_breakeven_can_be_switched_off_alone(tmp_path, monkeypatch):
    """Lane D's counterfactual behind the +$85 had no breakeven stop, so the test
    must be able to reproduce that variant; WILDCARD keeps its 0.90R arm."""
    monkeypatch.setenv("FUTURES_CONVEX_BREAKEVEN_ARM_R", "0.90")
    monkeypatch.setenv("FUTURES_TREND_BREAKEVEN_ARM_R", "0")
    client = _Client()
    rt = _runtime(tmp_path, client)
    trend = _pos("TREND")
    rt._maybe_breakeven_stop(trend, 110.0, r_now=1.0, peak_r=1.0)
    assert client.calls == [] and "be_stop_price" not in trend.metadata
    rt._maybe_breakeven_stop(_pos("WILDCARD"), 110.0, r_now=1.0, peak_r=1.0)
    assert _placed_stops(client) == [pytest.approx(100.19)]


def test_trend_breakeven_arm_can_move(tmp_path, monkeypatch):
    monkeypatch.setenv("FUTURES_CONVEX_BREAKEVEN_ARM_R", "0.90")
    monkeypatch.setenv("FUTURES_TREND_BREAKEVEN_ARM_R", "1.5")
    client = _Client()
    rt = _runtime(tmp_path, client)
    trend = _pos("TREND")
    rt._maybe_breakeven_stop(trend, 110.0, r_now=1.0, peak_r=1.0)
    assert client.calls == []
    rt._maybe_breakeven_stop(trend, 115.0, r_now=1.5, peak_r=1.5)
    assert _placed_stops(client) == [pytest.approx(100.19)]


# --- shadow ledger mirror --------------------------------------------------

def _row(sleeve: str) -> dict:
    return {"ts": 0, "symbol": "X_USDT", "side": "LONG", "sleeve": sleeve,
            "entry": 100.0, "sl": 90.0, "tp": 150.0, "tp_r": 5.0}


def _bars(prices: list[float]) -> list[tuple[int, float, float, float]]:
    """One bar per price, high = low = close, so the resolver sees the same path the
    live poll does."""
    return [(60 * (i + 1), p, p, p) for i, p in enumerate(prices)]


def test_shadow_ledger_unset_scores_trend_as_today():
    """Unset: a TREND row resolves exactly like a WILDCARD row of the same geometry,
    and carries no new key."""
    t = shadow.resolve_outcome(_row("TREND"), _bars(_FADE_15R), 1e12, convex=True)
    w = shadow.resolve_outcome(_row("WILDCARD"), _bars(_FADE_15R), 1e12, convex=True)
    assert t["outcome_kind"] == w["outcome_kind"] == "trail"
    assert t["outcome"] == w["outcome"]
    assert t["trail_arm_r"] == 1.0 and "trail_enabled" not in t


def test_shadow_ledger_mirrors_the_trend_switch_and_arm(monkeypatch):
    """The ledger reads the same environment the live trail reads (its own header,
    after the 0.30 -> 0.50 drift). A TREND switch it did not know would score every
    TREND counterfactual under a trail that had stopped running."""
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ENABLED", "0")
    off = shadow.resolve_outcome(_row("TREND"), _bars(_FADE_15R), 1e12, convex=True)
    assert off["outcome_kind"] == "timeout" and off["trail_enabled"] == 0
    monkeypatch.delenv("FUTURES_TREND_TRAIL_ENABLED")
    monkeypatch.setenv("FUTURES_TREND_TRAIL_ARM_R", "2.0")
    arm2 = shadow.resolve_outcome(_row("TREND"), _bars(_FADE_15R), 1e12, convex=True)
    assert arm2["outcome_kind"] == "timeout" and arm2["trail_arm_r"] == 2.0
    armed = shadow.resolve_outcome(_row("TREND"), _bars(_FADE_21R), 1e12, convex=True)
    assert armed["outcome_kind"] == "trail" and armed["outcome"] == pytest.approx(1.05)
