from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from futuresbot.slippage_attribution import FillRecord, SlippageAttribution


def _fill(
    *,
    symbol: str = "BTC_USDT",
    side: str = "LONG",
    quoted: float = 100.0,
    fill: float = 100.05,
    maker: bool = False,
    sec_to_funding: float = 3600.0,
    leverage: int = 10,
    ts: datetime | None = None,
) -> FillRecord:
    return FillRecord(
        timestamp=ts or datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        symbol=symbol,
        side=side,
        quoted_price=quoted,
        fill_price=fill,
        maker=maker,
        seconds_to_funding=sec_to_funding,
        leverage=leverage,
    )


def test_long_paying_above_quote_counts_as_positive_slippage():
    f = _fill(side="LONG", quoted=100.0, fill=100.05)
    assert f.slippage_bps == pytest.approx(5.0)


def test_short_receiving_below_quote_counts_as_positive_slippage():
    f = _fill(side="SHORT", quoted=100.0, fill=99.95)
    assert f.slippage_bps == pytest.approx(5.0)


def test_summary_is_empty_with_no_fills():
    s = SlippageAttribution()
    summary = s.summarise(now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc))
    assert summary["fills"] == 0
    assert summary["maker_ratio"] == 0.0


def test_summary_tracks_maker_ratio_and_avg_slippage():
    s = SlippageAttribution(window_days=7.0)
    s.record(_fill(maker=True, fill=99.99))   # -1 bps
    s.record(_fill(maker=True, fill=100.00))  # 0 bps
    s.record(_fill(maker=False, fill=100.10)) # +10 bps
    summary = s.summarise(now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc))
    assert summary["fills"] == 3
    assert summary["maker_fills"] == 2
    assert abs(summary["maker_ratio"] - 2 / 3) < 1e-9
    # (-1 + 0 + 10) / 3 = 3.0
    assert abs(summary["avg_slippage_bps"] - 3.0) < 1e-9


def test_prunes_out_of_window_fills():
    s = SlippageAttribution(window_days=1.0)
    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    s.record(_fill(ts=now - timedelta(days=5)))  # should be pruned on next record
    s.record(_fill(ts=now))
    summary = s.summarise(now=now)
    assert summary["fills"] == 1


def test_near_funding_slippage_isolated():
    s = SlippageAttribution(window_days=7.0)
    s.record(_fill(fill=100.20, sec_to_funding=60.0))   # near funding +20bps
    s.record(_fill(fill=100.02, sec_to_funding=7200.0)) # far  +2bps
    summary = s.summarise(now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc))
    assert abs(summary["near_funding_slippage_bps"] - 20.0) < 1e-9
    assert abs(summary["avg_slippage_bps"] - 11.0) < 1e-9


def test_round_trip_serialisation():
    s = SlippageAttribution(window_days=7.0)
    s.record(_fill(symbol="ETH_USDT", maker=True, fill=99.97))
    dicts = s.to_dicts()
    restored = SlippageAttribution.from_dicts(dicts, window_days=7.0)
    assert len(restored.fills()) == 1
    assert restored.fills()[0].symbol == "ETH_USDT"
    assert restored.fills()[0].maker is True
