"""C21 (2026-09-24): a re-adopted position's breakeven stop is not its designed stop.

On re-adoption (/reconcile, boot recovery) the resting exchange stop became sl_price, the
R denominator. When that stop is the breakeven stop (entry + costs, on the PROFIT side),
1R shrank 5-15x: the trail armed at once and the 3R ratchet fired on a ~0.6% move.

Now a profit-side stop is recorded as the ARMED breakeven stop and sl_price takes the
20%-of-margin fallback /reconcile already used when no stop rests. The invariant pinned
alongside: the resting exchange stop is never loosened to that fallback.

Geometry: entry 100, 10x, so the fallback stop is 100 x (1 - 0.20/10) = 98 (LONG) and
102 (SHORT); the breakeven stop rests at 100.19 (LONG) / 99.81 (SHORT).
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from futuresbot.config import FuturesConfig
from futuresbot.runtime import FuturesRuntime


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("FUTURES_CONVEX_BREAKEVEN_ARM_R", "FUTURES_TREND_BREAKEVEN_ARM_R",
                "FUTURES_CONVEX_BREAKEVEN_COST_PCT", "FUTURES_PMT_STOP_FIRST_PARTIAL_BANK_ENABLED",
                "FUTURES_PMT_BANK_PROTECT_ENABLED", "FUTURES_PMT_BANK_BREAKEVEN_BUFFER_PCT",
                "FUTURES_PMT_STOP_FIRST_PARTIAL_BANK_TRIGGER_R",
                "FUTURES_PMT_STOP_FIRST_PARTIAL_BANK_FRACTION"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setenv("FUTURES_CONVEX_BREAKEVEN_ARM_R", "0.90")      # the live arm


class _Exchange:
    def __init__(self, *, side: str = "LONG", stop: float = 100.19, tp: float = 150.0,
                 symbol: str = "ZEC_USDT", close_raises: bool = False) -> None:
        self.side = side
        self.stop = stop
        self.tp = tp
        self.symbol = symbol
        self.close_raises = close_raises
        self.calls: list[tuple[str, dict]] = []

    def get_open_positions(self, symbol=None, **kw):
        return [{"symbol": self.symbol, "positionId": "55",
                 "positionType": 1 if self.side == "LONG" else 2, "holdVol": 4,
                 "holdAvgPrice": 100.0, "leverage": 10, "im": 40.0}]

    def get_contract_detail(self, symbol):
        return {"contractSize": 1.0}

    def get_stop_orders(self, symbol, **kw):
        return [{"positionId": "55", "stopLossPrice": self.stop,
                 "takeProfitPrice": self.tp, "id": "9"}]

    def cancel_all_tpsl(self, **kw):
        self.calls.append(("cancel", kw))
        return {"success": True}

    def place_position_tpsl(self, **kw):
        self.calls.append(("place", kw))
        return {"success": True}

    def close_position(self, **kw):
        self.calls.append(("close", kw))
        if self.close_raises:
            raise RuntimeError("system busy")
        return {"orderId": ""}

    def get_order(self, order_id):
        return {}

    def get_fair_price(self, symbol):
        return 101.0

    def get_account_asset(self, currency="USDT"):
        return {"availableBalance": "1000", "equity": "1000"}

    def get_updates(self, *, offset=None, limit=5, timeout=0):
        return []

    def placed_stops(self) -> list[float]:
        return [kw["stop_loss_price"] for name, kw in self.calls if name == "place"]


def _runtime(tmp_path, exchange: _Exchange, symbols=("BTC_USDT",)) -> FuturesRuntime:
    cfg = replace(FuturesConfig.from_env(), symbol=symbols[0], symbols=tuple(symbols),
                  runtime_state_file=str(tmp_path / "s.json"),
                  status_file=str(tmp_path / "st.json"),
                  telegram_token="t", telegram_chat_id="1", paper_trade=False)
    rt = FuturesRuntime(cfg, exchange)
    rt._notify = lambda *a, **k: None
    rt._notify_once = lambda *a, **k: None
    return rt


def _adopt(tmp_path, **kw):
    exchange = _Exchange(**kw)
    rt = _runtime(tmp_path, exchange)
    message = rt._reconcile_orphans_message()
    return rt, exchange, rt.open_positions[exchange.symbol], message


@pytest.mark.parametrize("side, stop, fallback", [("LONG", 100.19, 98.0), ("SHORT", 99.81, 102.0)])
def test_reconcile_reads_a_profit_side_stop_as_the_armed_breakeven(tmp_path, side, stop, fallback):
    rt, exchange, pos, message = _adopt(tmp_path, side=side, stop=stop)
    assert pos.sl_price == pytest.approx(fallback)
    assert pos.metadata["be_stop_price"] == pytest.approx(stop)
    assert pos.metadata["be_stop_adopted"] == 1.0 and pos.metadata["be_stop_ts"] > 0
    assert pos.metadata["sl_margin_pct"] == pytest.approx(20.0)
    # R uses the fallback: 1R = 2% of price x 4 contracts = $8, not $0.76
    assert rt._position_stop_risk_usdt(pos) == pytest.approx(8.0)
    assert rt._position_stop_risk_pct_of_margin(pos) == pytest.approx(20.0)
    # the stop the exchange must hold is still the one it holds
    assert rt._effective_stop_price(pos) == pytest.approx(stop)
    assert pos.tp_price == pytest.approx(150.0)                  # the target is not re-priced
    assert "(breakeven)" in message
    assert exchange.calls == []                                  # adoption stays read-only


def test_a_stop_exactly_at_entry_is_breakeven_side(tmp_path):
    _, _, pos, _ = _adopt(tmp_path, stop=100.0)
    assert pos.sl_price == pytest.approx(98.0) and pos.metadata["be_stop_price"] == 100.0


@pytest.mark.parametrize("side, stop", [("LONG", 95.0), ("SHORT", 105.0)])
def test_a_loss_side_stop_is_adopted_unchanged(tmp_path, side, stop):
    rt, _, pos, message = _adopt(tmp_path, side=side, stop=stop)
    assert pos.sl_price == pytest.approx(stop)
    assert "be_stop_price" not in pos.metadata and "be_stop_adopted" not in pos.metadata
    assert pos.metadata["sl_margin_pct"] == pytest.approx(50.0)
    assert "(breakeven)" not in message


def test_no_resting_stop_is_adopted_unchanged(tmp_path):
    _, _, pos, message = _adopt(tmp_path, stop=0.0, tp=0.0)
    assert pos.sl_price == 0.0 and "be_stop_price" not in pos.metadata
    assert pos.metadata["sl_margin_pct"] == pytest.approx(20.0)
    assert "NONE" in message


@pytest.mark.parametrize("side, stop, fallback", [("LONG", 100.19, 98.0), ("SHORT", 99.81, 102.0)])
def test_boot_recovery_reads_a_profit_side_stop_the_same_way(tmp_path, side, stop, fallback):
    exchange = _Exchange(side=side, stop=stop, symbol="BTC_USDT")
    rt = _runtime(tmp_path, exchange)
    rt._refresh_live_positions()
    pos = rt.open_positions["BTC_USDT"]
    assert pos.sl_price == pytest.approx(fallback)
    assert pos.metadata["be_stop_price"] == pytest.approx(stop)
    assert rt._effective_stop_price(pos) == pytest.approx(stop)


def test_boot_recovery_loss_side_stop_is_unchanged(tmp_path):
    exchange = _Exchange(stop=95.0, symbol="BTC_USDT")
    rt = _runtime(tmp_path, exchange)
    rt._refresh_live_positions()
    pos = rt.open_positions["BTC_USDT"]
    assert pos.sl_price == pytest.approx(95.0) and "be_stop_price" not in pos.metadata


def test_the_breakeven_code_treats_it_as_armed_and_never_moves_it(tmp_path):
    rt, exchange, pos, _ = _adopt(tmp_path)
    rt._maybe_breakeven_stop(pos, 103.0, r_now=1.5, peak_r=1.5)
    assert exchange.calls == []
    assert pos.metadata["be_stop_price"] == pytest.approx(100.19)


def test_the_trail_no_longer_arms_on_a_tiny_move(tmp_path):
    """+1% was +1.3R against the breakeven 'stop' (0.19% away) and armed the trail; it
    is +0.5R against the fallback and arms nothing."""
    rt, exchange, pos, _ = _adopt(tmp_path)
    assert rt._convex_runner_trail_exit(pos, 101.0) is False
    assert pos.metadata["convex_peak_r"] == pytest.approx(0.5, abs=1e-3)


@pytest.mark.parametrize("price", [101.0, 100.0])      # above, and through, the breakeven
def test_a_failed_close_restores_the_breakeven_never_the_fallback(tmp_path, price):
    rt, exchange, pos, _ = _adopt(tmp_path)
    exchange.close_raises = True
    with pytest.raises(RuntimeError):
        rt._close_position_for_exit(pos, current_price=price, reason="CONVEX_RETENTION_TRAIL")
    assert exchange.placed_stops() == [pytest.approx(100.19)]


def test_the_bare_stop_repair_restores_the_breakeven(tmp_path):
    rt, exchange, pos, _ = _adopt(tmp_path)
    pos.metadata["be_stop_bare"] = 1.0
    assert rt._repair_bare_stop(pos, 99.5) is True
    assert exchange.placed_stops() == [pytest.approx(100.19)]


def test_a_bot_armed_breakeven_still_falls_back_to_its_designed_stop(tmp_path):
    """Unchanged for positions the bot armed itself: through the market, the restore
    uses the designed stop, as before."""
    rt, exchange, pos, _ = _adopt(tmp_path)
    pos.metadata.pop("be_stop_adopted")
    exchange.close_raises = True
    with pytest.raises(RuntimeError):
        rt._close_position_for_exit(pos, current_price=100.0, reason="CONVEX_RETENTION_TRAIL")
    assert exchange.placed_stops() == [pytest.approx(98.0)]


def test_partial_bank_never_re_places_below_the_adopted_breakeven(tmp_path):
    """An ADOPTED position on a config symbol is PMT-sleeve and can partial-bank. Its
    runner stop (entry + 0.15%) beats the 98 fallback but is looser than the 100.19
    resting breakeven, so it must not be placed."""
    exchange = _Exchange(symbol="ETH_USDT")
    rt = _runtime(tmp_path, exchange, symbols=("BTC_USDT", "ETH_USDT"))
    rt._reconcile_orphans_message()
    pos = rt.open_positions["ETH_USDT"]
    assert "wildcard" not in pos.metadata and pos.metadata["pmt_stop_first"] == 1.0
    assert rt._maybe_partial_bank(pos, current_price=102.5, gross_pnl_pct=25.0,
                                  metadata=pos.metadata) is True
    assert [name for name, _ in exchange.calls] == ["close"]    # the bank, no stop re-place
    assert pos.sl_price == pytest.approx(98.0)
    assert rt._effective_stop_price(pos) == pytest.approx(100.19)


# --- FIX ROUND 1 (C21-1): the in-process backup stop stays at the resting breakeven ----

@pytest.mark.parametrize("symbol, symbols", [("ZEC_USDT", ("BTC_USDT",)),                  # adopted WILDCARD
                                             ("ETH_USDT", ("BTC_USDT", "ETH_USDT"))])      # adopted PMT
@pytest.mark.parametrize("side, stop, tp, through, above", [("LONG", 100.19, 150.0, 99.5, 100.5),
                                                            ("SHORT", 99.81, 50.0, 100.5, 99.5)])
def test_a_mark_through_the_adopted_breakeven_closes_in_process(tmp_path, monkeypatch, symbol, symbols,
                                                                side, stop, tp, through, above):
    """Live runs pmt_threshold, so _hourly_exit ends in _pmt_hard_exit - the backup the
    'Stop Not Restored' alert means by 'the in-process stop'. It read sl_price, which
    adoption moved to the 20%-of-margin fallback (98 / 102): with the exchange stop gone
    and the mark through breakeven, nothing closed until -20% of margin."""
    monkeypatch.setenv("FUTURES_STRATEGY_MODE", "pmt_threshold")
    exchange = _Exchange(side=side, stop=stop, tp=tp, symbol=symbol)
    rt = _runtime(tmp_path, exchange, symbols=symbols)
    rt._reconcile_orphans_message()
    pos = rt.open_positions[symbol]
    pos.metadata["be_stop_bare"] = 1.0              # the exchange stop is gone
    assert pos.metadata["be_stop_adopted"] == 1.0
    assert rt._hourly_exit(pos, above) is False     # still on the right side: no close
    assert rt._hourly_exit(pos, through) is True
    assert rt.trade_history[-1]["exit_reason"] == "STOP_LOSS"
    assert symbol not in rt.open_positions
    assert [name for name, _ in exchange.calls] == ["cancel", "close"]


def test_a_non_adopted_position_keeps_its_designed_in_process_stop(tmp_path, monkeypatch):
    """Unchanged for a bot-armed breakeven: the in-process backup reads sl_price, as before."""
    monkeypatch.setenv("FUTURES_STRATEGY_MODE", "pmt_threshold")
    rt, exchange, pos, _ = _adopt(tmp_path)
    pos.metadata.pop("be_stop_adopted")
    assert rt._pmt_hard_exit(pos, current_price=99.5) is False
    assert rt._pmt_hard_exit(pos, current_price=98.0) is True
    assert rt.trade_history[-1]["exit_reason"] == "STOP_LOSS"
