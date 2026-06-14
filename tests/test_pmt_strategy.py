from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd

from futuresbot.backtest import FuturesBacktestEngine
from futuresbot.exits import evaluate_profit_lock_bar
from futuresbot.models import FuturesPosition
from futuresbot.pmt_strategy import (
    DEFAULT_PMT_PROFILES,
    ELIGIBLE_PMT_SYMBOLS,
    MentalThresholdCross,
    PairMarketTrend,
    classify_pair_market_trend,
    diagnose_pmt_threshold_rejection,
    mental_threshold_step,
    pmt_win_cooldown_exit_reason,
    pmt_symbol_allowed,
    score_pmt_threshold_signal,
)


def _frame(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range(datetime(2026, 6, 1, tzinfo=timezone.utc), periods=len(closes), freq="15min")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [price * 1.001 for price in closes],
            "low": [price * 0.999 for price in closes],
            "close": closes,
            "volume": [1000.0 for _ in closes[:-1]] + [1400.0],
        },
        index=index,
    )


def _config(symbol: str = "BTC_USDT") -> SimpleNamespace:
    return SimpleNamespace(symbol=symbol, min_confidence_score=70.0, leverage_min=15, leverage_max=25)


def _enable_pmt(monkeypatch, *, min_score: str = "70") -> None:
    for name in (
        "FUTURES_BTCUSDT_PMT_THRESHOLD_STEP",
        "FUTURES_ETHUSDT_PMT_THRESHOLD_STEP",
        "FUTURES_SOLUSDT_PMT_THRESHOLD_STEP",
        "FUTURES_BNBUSDT_PMT_THRESHOLD_STEP",
        "FUTURES_SEIUSDT_PMT_THRESHOLD_STEP",
        "FUTURES_ZECUSDT_PMT_THRESHOLD_STEP",
        "FUTURES_PMT_MIN_LEVERAGE",
        "FUTURES_PMT_MAX_LEVERAGE",
        "FUTURES_LEVERAGE_MIN",
        "FUTURES_LEVERAGE_MAX",
        "FUTURES_PMT_PROFIT_LOCK_TRIGGER_PCT",
        "FUTURES_PMT_PROFIT_LOCK_GIVEBACK_PCT",
        "FUTURES_PMT_PROFIT_LOCK_PULLBACK_FRACTION",
        "FUTURES_PMT_PROFIT_LOCK_FLOOR_PCT",
        "FUTURES_PMT_PROFIT_LOCK_EXIT_MIN_NET_PCT",
        "FUTURES_PMT_SIMPLE_SCORING_ENABLED",
        "FUTURES_PMT_SIMPLE_BLOCK_CONFIRMATION_NO_FOLLOWTHROUGH",
        "FUTURES_PMT_SIMPLE_BLOCK_RECENT_FAILED_RECLAIM",
        "FUTURES_PMT_SIMPLE_COUNTERTREND_SCORE",
        "FUTURES_PMT_SIMPLE_CORE_WEIGHT",
        "FUTURES_PMT_SIMPLE_MEGA_SCORE",
        "FUTURES_PMT_SIMPLE_FLASH_SCORE",
        "FUTURES_PMT_SIMPLE_TREND_SCORE",
        "FUTURES_PMT_SIMPLE_FLAT_SCORE",
        "FUTURES_PMT_SIMPLE_CONTEXT_BONUS_CAP",
        "FUTURES_PMT_SIMPLE_LATE_ENTRY_DISTANCE_PCT",
        "FUTURES_PMT_SIMPLE_EXTREME_LATE_ENTRY_DISTANCE_PCT",
        "FUTURES_PMT_SIMPLE_LATE_ENTRY_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_EXTREME_LATE_ENTRY_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_BLOCK_WEAK_FOLLOWTHROUGH",
        "FUTURES_PMT_SIMPLE_WEAK_FOLLOWTHROUGH_1BAR_PCT",
        "FUTURES_PMT_SIMPLE_WEAK_FOLLOWTHROUGH_1H_PCT",
        "FUTURES_PMT_SIMPLE_WEAK_FOLLOWTHROUGH_MIN_VOLUME_RATIO",
        "FUTURES_PMT_SIMPLE_WEAK_FOLLOWTHROUGH_PENALTY",
        "FUTURES_PMT_SIMPLE_WEAK_FOLLOWTHROUGH_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_EXHAUSTED_CLIMAX_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_EXHAUSTION_1BAR_PENALTY",
        "FUTURES_PMT_SIMPLE_EXHAUSTION_1H_PENALTY",
        "FUTURES_PMT_SIMPLE_VOLUME_CLIMAX_PENALTY",
        "FUTURES_PMT_SIMPLE_STACKED_EXHAUSTION_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_ONE_HOUR_EXHAUSTION_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_EXHAUSTION_MIN_SCORE",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_EXHAUSTION_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_SEVERE_EXHAUSTION_1BAR_PCT",
        "FUTURES_PMT_SIMPLE_SEVERE_EXHAUSTION_1H_PCT",
        "FUTURES_PMT_SIMPLE_SEVERE_HIGH_SCORE_EXHAUSTION_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_STRETCHED_6H_PCT",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_STRETCHED_12H_PCT",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_TREND_STRETCH_PENALTY",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_TREND_STRETCH_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_VOLUME_CHASE_RATIO",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_VOLUME_CHASE_1H_PCT",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_VOLUME_CHASE_PENALTY",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_VOLUME_CHASE_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_BLOWOFF_VOLUME_RATIO",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_BLOWOFF_1BAR_PCT",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_BLOWOFF_1H_PCT",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_BLOWOFF_PENALTY",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_BLOWOFF_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_BROADER_OVERSTRETCH_24H_PCT",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_BROADER_OVERSTRETCH_MAX_1H_PCT",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_BROADER_OVERSTRETCH_PENALTY",
        "FUTURES_PMT_SIMPLE_HIGH_SCORE_BROADER_OVERSTRETCH_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_BLOCK_SCORE9_FATIGUE",
        "FUTURES_PMT_SIMPLE_SCORE9_FATIGUE_6H_PCT",
        "FUTURES_PMT_SIMPLE_SCORE9_FATIGUE_12H_PCT",
        "FUTURES_PMT_SIMPLE_SCORE9_LATE_STRETCH_12H_PCT",
        "FUTURES_PMT_SIMPLE_SCORE9_LATE_STRETCH_24H_PCT",
        "FUTURES_PMT_SIMPLE_SCORE9_LATE_STRETCH_DISTANCE_PCT",
        "FUTURES_PMT_SIMPLE_SCORE9_FATIGUE_PENALTY",
        "FUTURES_PMT_SIMPLE_SCORE9_FATIGUE_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_SCORE9_OVERSTRETCHED_24H_PCT",
        "FUTURES_PMT_SIMPLE_SCORE9_BROADER_OVERSTRETCH_PENALTY",
        "FUTURES_PMT_SIMPLE_SCORE9_BROADER_OVERSTRETCH_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_SCORE9_CONFLICT_6H_PCT",
        "FUTURES_PMT_SIMPLE_SCORE9_CONFLICT_MAX_1H_PCT",
        "FUTURES_PMT_SIMPLE_SCORE9_LATE_FLAT_DISTANCE_PCT",
        "FUTURES_PMT_SIMPLE_SCORE9_LATE_FLAT_6H_PCT",
        "FUTURES_PMT_SIMPLE_SCORE9_LATE_FLAT_12H_PCT",
        "FUTURES_PMT_SIMPLE_SCORE9_LOW_VOLUME_PULLBACK_RATIO",
        "FUTURES_PMT_SIMPLE_SCORE9_WEAK_QUALITY_PENALTY",
        "FUTURES_PMT_SIMPLE_SCORE9_WEAK_QUALITY_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_SCORE9_FAILED_VOLUME_RATIO",
        "FUTURES_PMT_SIMPLE_SCORE9_FAILED_VOLUME_MAX_DISTANCE_PCT",
        "FUTURES_PMT_SIMPLE_SCORE9_FAILED_VOLUME_PENALTY",
        "FUTURES_PMT_SIMPLE_SCORE9_FAILED_VOLUME_SCORE_CAP",
        "FUTURES_PMT_SIMPLE_BLOCK_FAILED_RECLAIM_BY_CAP",
        "FUTURES_PMT_SIMPLE_FAILED_RECLAIM_SCORE_CAP",
        "FUTURES_PMT_CONFIRMATION_BARS",
        "FUTURES_PMT_CONFIRMATION_MIN_FOLLOWTHROUGH_PCT",
        "FUTURES_PMT_FUNDING_SCORE_ENABLED",
        "FUTURES_PMT_FUNDING_ADVERSE_EXCESS_PENALTY_PER_CAP",
        "FUTURES_PMT_FUNDING_ADVERSE_MAX_PENALTY",
        "FUTURES_PMT_FUNDING_ADVERSE_REDUCED_SIZE_CAP_ENABLED",
        "FUTURES_PMT_FUNDING_ADVERSE_SCORE_CAP",
        "FUTURES_PMT_FUNDING_FAVORABLE_MAX_BONUS",
        "FUTURES_PMT_FUNDING_FAVORABLE_BONUS_PER_CAP",
        "FUTURES_PMT_FUNDING_SCORE_FALLBACK_CAP",
        "FUTURES_PMT_BLOCK_RECENT_FAILED_RECLAIM",
        "FUTURES_PMT_RECENT_RECLAIM_LOOKBACK_BARS",
        "FUTURES_PMT_BLOCK_BROADER_TREND_CONFLICT",
        "FUTURES_PMT_EXHAUSTION_1BAR_PCT",
        "FUTURES_PMT_EXHAUSTION_1BAR_PENALTY",
        "FUTURES_PMT_EXHAUSTION_1H_PCT",
        "FUTURES_PMT_EXHAUSTION_1H_PENALTY",
        "FUTURES_PMT_VOLUME_CLIMAX_RATIO",
        "FUTURES_PMT_VOLUME_CLIMAX_PENALTY",
        "FUTURES_PMT_EDGE_SCORING_ENABLED",
        "FUTURES_PMT_LATE_ENTRY_DISTANCE_PCT",
        "FUTURES_PMT_EXTREME_LATE_ENTRY_DISTANCE_PCT",
        "FUTURES_PMT_LATE_ENTRY_SCORE_CAP",
        "FUTURES_PMT_EXTREME_LATE_ENTRY_SCORE_CAP",
        "FUTURES_PMT_EXHAUSTED_CLIMAX_SCORE_CAP",
        "FUTURES_PMT_ONE_HOUR_EXHAUSTION_SCORE_CAP",
        "FUTURES_PMT_STACKED_EXHAUSTION_SCORE_CAP",
        "FUTURES_PMT_FLASH_SCORE_CAP",
        "FUTURES_PMT_WEAK_BROADER_TREND_SCORE_CAP",
        "FUTURES_PMT_WEAK_FOLLOWTHROUGH_1BAR_PCT",
        "FUTURES_PMT_WEAK_FOLLOWTHROUGH_SCORE_CAP",
        "FUTURES_PMT_SCORE_BAND_SIZING_ENABLED",
        "FUTURES_PMT_REDUCED_SCORE_ENTRIES_ENABLED",
        "FUTURES_PMT_REDUCED_ENTRY_MIN_SCORE",
        "FUTURES_PMT_REDUCED_ENTRY_MIN_EDGE_SCORE",
        "FUTURES_PMT_FULL_BALANCE_MIN_SCORE",
        "FUTURES_PMT_SCORE_BAND_SIZE_85_91",
        "FUTURES_PMT_SCORE_BAND_SIZE_90_91",
        "FUTURES_PMT_SCORE_BAND_SIZE_92_96",
        "FUTURES_PMT_SCORE_BAND_SIZE_92_94",
        "FUTURES_PMT_SCORE_BAND_SIZE_97_100",
        "FUTURES_PMT_SCORE_BAND_SIZE_95_100",
        "FUTURES_PMT_STOP_FIRST_SIZING_ENABLED",
        "FUTURES_PMT_STOP_FIRST_ATR_PERIOD",
        "FUTURES_PMT_STOP_FIRST_ATR_MULT",
        "FUTURES_PMT_STOP_FIRST_RISK_BUDGET_MARGIN_PCT",
        "FUTURES_PMT_STOP_FIRST_TARGET_R",
        "FUTURES_PMT_STOP_FIRST_MIN_LEVERAGE",
        "MEXC_PERP_DEFAULT_TAKER_FEE_RATE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FUTURES_STRATEGY_MODE", "pmt_threshold")
    monkeypatch.setenv("FUTURES_PMT_SYMBOLS", ",".join(ELIGIBLE_PMT_SYMBOLS))
    monkeypatch.setenv("FUTURES_PMT_MIN_SCORE", min_score)
    monkeypatch.setenv("FUTURES_PMT_PROFIT_LOCK_MIN_TP_PROGRESS", "0.0")


def test_pmt_defaults_allow_only_six_eligible_pairs(monkeypatch):
    monkeypatch.delenv("FUTURES_PMT_SYMBOLS", raising=False)

    assert all(pmt_symbol_allowed(symbol) for symbol in ELIGIBLE_PMT_SYMBOLS)
    assert pmt_symbol_allowed("DOGE_USDT") is False
    assert pmt_symbol_allowed("XRP_USDT") is False

    monkeypatch.setenv("FUTURES_PMT_SYMBOLS", "*")
    assert all(pmt_symbol_allowed(symbol) for symbol in ELIGIBLE_PMT_SYMBOLS)
    assert pmt_symbol_allowed("DOGE_USDT") is False


def test_pmt_win_cooldown_includes_peak_profit_lock():
    assert pmt_win_cooldown_exit_reason("TAKE_PROFIT") is True
    assert pmt_win_cooldown_exit_reason("PEAK_PROFIT_LOCK") is True
    assert pmt_win_cooldown_exit_reason("STOP_LOSS") is False


def test_each_eligible_pair_has_unique_pmt_and_mental_thresholds():
    # Every eligible pair has a profile; profiles may be a SUPERSET (universe-
    # expansion candidates gated on via env, not in the champion default set).
    assert set(ELIGIBLE_PMT_SYMBOLS).issubset(DEFAULT_PMT_PROFILES)

    # The eligible-6 each have a distinct mental step and a distinct trend-band
    # set (no pair shares another's live calibration).
    elig = [DEFAULT_PMT_PROFILES[s] for s in ELIGIBLE_PMT_SYMBOLS]
    assert len({p.threshold_step for p in elig}) == len(elig)
    assert len({(p.flat_24h_pct, p.flash_6h_pct, p.mega_12h_pct, p.mega_24h_pct) for p in elig}) == len(elig)

    # Across the FULL profile set the trend-band calibration is unique per pair
    # (each derived from its own history). Numeric step values may coincide
    # across different price scales (e.g. SOL 2.5 vs TAO 2.5) and that is fine.
    all_bands = [
        (p.flat_24h_pct, p.flash_6h_pct, p.mega_12h_pct, p.mega_24h_pct)
        for p in DEFAULT_PMT_PROFILES.values()
    ]
    assert len(set(all_bands)) == len(all_bands)


def test_non_btc_pmt_profiles_match_researched_candidate():
    # Recalibrated to real crypto sizes (2026-06-08): MEGA bands scaled ~0.6x,
    # FLASH normalised toward ~1.5% for majors. See DEFAULT_PMT_PROFILES.
    expected = {
        "ETH_USDT": (50.0, 0.010, 0.015, 0.024, 0.031),
        "SOL_USDT": (2.5, 0.012, 0.016, 0.025, 0.037),
        "BNB_USDT": (20.0, 0.011, 0.015, 0.019, 0.030),
        "SEI_USDT": (0.01, 0.020, 0.022, 0.048, 0.072),
        "ZEC_USDT": (25.0, 0.030, 0.032, 0.060, 0.096),
    }

    for symbol, values in expected.items():
        profile = DEFAULT_PMT_PROFILES[symbol]
        assert (
            profile.threshold_step,
            profile.flat_24h_pct,
            profile.flash_6h_pct,
            profile.mega_12h_pct,
            profile.mega_24h_pct,
        ) == values


def test_pmt_mega_bullish_breakout_scores_long_for_each_eligible_pair(monkeypatch):
    _enable_pmt(monkeypatch)
    levels = {
        "BTC_USDT": 75000.0,
        "ETH_USDT": 1850.0,
        "SOL_USDT": 80.0,
        "BNB_USDT": 680.0,
        "SEI_USDT": 0.07,
        "ZEC_USDT": 600.0,
    }

    for symbol in ELIGIBLE_PMT_SYMBOLS:
        profile = DEFAULT_PMT_PROFILES[symbol]
        level = levels[symbol]
        step = mental_threshold_step(symbol)
        crossed = level + step * 0.12
        current = level + step * 0.18
        previous = level - step * 0.10
        start = current / (1.0 + profile.mega_12h_pct * 1.2)
        frame = _frame([start] * 105 + [previous, crossed, current])

        pmt = classify_pair_market_trend(frame, symbol)
        signal = score_pmt_threshold_signal(frame, _config(symbol))

        assert pmt is not None, symbol
        assert pmt.label == "MEGA_BULLISH", symbol
        assert signal is not None, symbol
        assert signal.side == "LONG", symbol
        assert signal.entry_signal == "PMT_THRESHOLD_LONG", symbol
        assert signal.metadata["mental_threshold_level"] == level
        assert signal.metadata["pmt_label"] == "MEGA_BULLISH"


def test_pmt_flat_threshold_breakdown_scores_short(monkeypatch):
    _enable_pmt(monkeypatch)
    frame = _frame([75100.0] * 110 + [75100.0, 74940.0, 74890.0])

    pmt = classify_pair_market_trend(frame, "BTC_USDT")
    signal = score_pmt_threshold_signal(frame, _config())

    assert pmt is not None
    assert pmt.label == "FLAT"
    assert signal is not None
    assert signal.side == "SHORT"
    assert signal.entry_signal == "PMT_THRESHOLD_SHORT"
    assert signal.metadata["mental_threshold_level"] == 75000.0


def test_pmt_mega_bearish_blocks_countertrend_long(monkeypatch):
    _enable_pmt(monkeypatch)
    frame = _frame([78000.0] * 105 + [74960.0, 75100.0])

    pmt = classify_pair_market_trend(frame, "BTC_USDT")
    signal = score_pmt_threshold_signal(frame, _config())

    assert pmt is not None
    assert pmt.label == "MEGA_BEARISH"
    assert signal is None


def test_pmt_mega_bearish_breakdown_targets_200pct_margin(monkeypatch):
    _enable_pmt(monkeypatch)
    frame = _frame([78000.0] * 103 + [75220.0, 75160.0, 75080.0, 74940.0, 74890.0])

    signal = score_pmt_threshold_signal(frame, _config())

    assert signal is not None
    assert signal.side == "SHORT"
    assert signal.leverage == 25
    assert signal.score >= 97.0
    assert signal.metadata["pmt_label"] == "MEGA_BEARISH"
    assert signal.metadata["pmt_score_model"] == "setup_edge_v1"
    assert signal.metadata["pmt_setup_score"] >= signal.score - 0.01
    assert signal.metadata["pmt_edge_score"] >= signal.score - 0.01
    assert signal.metadata["pmt_balance_fraction"] == 1.0
    assert signal.metadata["tp_margin_pct"] == 200.0
    assert signal.metadata["sl_margin_pct"] <= 16.0
    assert signal.metadata["profit_lock_trigger_pct_override"] == 5.5
    assert signal.metadata["profit_lock_giveback_pct_override"] == 0.0
    assert signal.metadata["profit_lock_pullback_fraction_override"] == 0.15
    assert signal.metadata["profit_lock_min_tp_progress_override"] == 0.0
    assert signal.metadata["profit_lock_floor_pct_override"] == 5.0
    assert signal.metadata["profit_lock_exit_min_net_pct_override"] == 0.0
    assert signal.tp_price == signal.entry_price * (1.0 - 2.0 / signal.leverage)
    assert signal.sl_price <= signal.entry_price * (1.0 + 0.16 / signal.leverage)


def test_pmt_requires_confirmation_after_threshold_cross(monkeypatch):
    _enable_pmt(monkeypatch)
    pending = _frame([78000.0] * 100 + [75100.0] * 5 + [75080.0, 74940.0])
    confirmed = _frame([78000.0] * 100 + [75100.0] * 5 + [75080.0, 74940.0, 74880.0])

    assert score_pmt_threshold_signal(pending, _config()) is None
    assert diagnose_pmt_threshold_rejection(pending, _config()).startswith("confirmation_pending")
    assert score_pmt_threshold_signal(confirmed, _config()) is not None


def test_pmt_blocks_confirmation_without_followthrough(monkeypatch):
    _enable_pmt(monkeypatch)
    frame = _frame([78000.0] * 100 + [75100.0] * 5 + [75080.0, 74940.0, 74930.0])

    assert score_pmt_threshold_signal(frame, _config()) is None
    assert diagnose_pmt_threshold_rejection(frame, _config()).startswith("confirmation_no_followthrough")


def test_pmt_blocks_recent_failed_reclaim(monkeypatch):
    _enable_pmt(monkeypatch)
    frame = _frame([78000.0] * 100 + [75100.0] * 5 + [75080.0, 74940.0, 75120.0, 75080.0, 74920.0, 74860.0])

    assert score_pmt_threshold_signal(frame, _config()) is None
    assert diagnose_pmt_threshold_rejection(frame, _config()).startswith("recent_failed_reclaim")


def test_pmt_blocks_broader_trend_conflict(monkeypatch):
    _enable_pmt(monkeypatch)
    frame = _frame([66000.0] * 60 + [62000.0] * 48 + [63750.0, 64200.0, 64340.0])

    pmt = classify_pair_market_trend(frame, "BTC_USDT")
    assert pmt is not None
    assert pmt.label == "MEGA_BULLISH"
    assert pmt.move_24h_pct < -0.008
    assert score_pmt_threshold_signal(frame, _config()) is None
    assert diagnose_pmt_threshold_rejection(frame, _config()).startswith("broader_trend_conflict")


def test_pmt_exhaustion_penalty_can_drop_score_below_threshold(monkeypatch):
    _enable_pmt(monkeypatch, min_score="95")
    monkeypatch.setenv("FUTURES_PMT_CONFIRMATION_BARS", "0")
    monkeypatch.setenv("FUTURES_PMT_EXHAUSTION_1BAR_PENALTY", "30")
    frame = _frame([78000.0] * 100 + [75100.0] * 5 + [75080.0, 74400.0])

    assert score_pmt_threshold_signal(frame, _config()) is None
    rejection = diagnose_pmt_threshold_rejection(frame, _config())
    assert rejection.startswith("score_below_threshold")
    assert "one_bar_exhaustion" in rejection


def test_pmt_edge_scoring_rejects_exhausted_volume_chase(monkeypatch):
    _enable_pmt(monkeypatch, min_score="95")
    frame = _frame([76000.0] * 100 + [81000.0] * 5 + [81900.0, 82150.0, 82400.0])
    frame.loc[frame.index[-1], "volume"] = 3200.0

    assert score_pmt_threshold_signal(frame, _config()) is None
    rejection = diagnose_pmt_threshold_rejection(frame, _config())
    assert rejection.startswith("score_below_threshold")
    assert "exhausted_volume_climax" in rejection


def test_pmt_edge_scoring_rejects_one_hour_exhaustion(monkeypatch):
    _enable_pmt(monkeypatch, min_score="95")
    frame = _frame([78000.0] * 100 + [75100.0] * 5 + [75080.0, 74940.0, 74000.0])

    assert score_pmt_threshold_signal(frame, _config()) is None
    rejection = diagnose_pmt_threshold_rejection(frame, _config())
    assert rejection.startswith("score_below_threshold")
    assert "one_hour_exhaustion" in rejection


def test_pmt_reduced_score_entry_accepts_clean_edge_at_smaller_size(monkeypatch):
    _enable_pmt(monkeypatch, min_score="95")
    monkeypatch.setenv("FUTURES_PMT_CONFIRMATION_BARS", "0")
    monkeypatch.setenv("FUTURES_PMT_REDUCED_ENTRY_MIN_SCORE", "90")
    monkeypatch.setenv("FUTURES_PMT_EXHAUSTION_1BAR_PENALTY", "30")
    monkeypatch.setenv("FUTURES_PMT_EXHAUSTION_1H_PENALTY", "30")
    # Pin BTC trend thresholds to the pre-recalibration values so this test
    # exercises the reduced-score-band MECHANISM independently of the default
    # MEGA/FLASH calibration (which test_non_btc_pmt_profiles_* covers). Under
    # the recalibrated defaults this ~2.7% move clears 95 (full conviction);
    # the mechanism itself is unchanged.
    monkeypatch.setenv("FUTURES_BTCUSDT_PMT_FLASH_6H_PCT", "0.010")
    monkeypatch.setenv("FUTURES_BTCUSDT_PMT_MEGA_12H_PCT", "0.030")
    monkeypatch.setenv("FUTURES_BTCUSDT_PMT_MEGA_24H_PCT", "0.050")
    frame = _frame([77000.0] * 100 + [75100.0] * 5 + [75080.0, 74940.0])

    signal = score_pmt_threshold_signal(frame, _config())

    assert signal is not None
    assert 90.0 <= signal.score < 95.0
    assert signal.metadata["pmt_reduced_score_entry"] is True
    assert signal.metadata["pmt_reduced_score_reason"] == "clean_reduced_score"
    assert signal.metadata["pmt_balance_fraction"] == 0.25


def test_pmt_reduced_score_entry_blocks_exhausted_edge(monkeypatch):
    _enable_pmt(monkeypatch, min_score="95")
    monkeypatch.setenv("FUTURES_PMT_REDUCED_ENTRY_MIN_SCORE", "90")
    monkeypatch.setenv("FUTURES_PMT_LATE_ENTRY_DISTANCE_PCT", "0")
    monkeypatch.setenv("FUTURES_PMT_EXTREME_LATE_ENTRY_DISTANCE_PCT", "0")
    frame = _frame([78000.0] * 100 + [75100.0] * 5 + [75080.0, 74940.0, 74000.0])

    assert score_pmt_threshold_signal(frame, _config()) is None
    rejection = diagnose_pmt_threshold_rejection(frame, _config())
    assert rejection.startswith("reduced_score_blocked")
    assert "one_hour_exhaustion" in rejection


def test_pmt_min_score_requires_strictly_higher_score(monkeypatch):
    _enable_pmt(monkeypatch, min_score="92.5")
    monkeypatch.setenv("FUTURES_PMT_REDUCED_ENTRY_MIN_SCORE", "92.5")
    # Disable the float-boundary tolerance: this test pins the STRICT floor
    # semantics; the epsilon behavior is covered by its own test below.
    monkeypatch.setenv("FUTURES_PMT_SCORE_FLOOR_EPSILON", "0")
    frame = _frame([61000.0, 60990.0])

    monkeypatch.setattr(
        "futuresbot.pmt_strategy.classify_pair_market_trend",
        lambda frame, symbol: PairMarketTrend(symbol, "BEARISH", -0.05, -0.04, -0.02),
    )
    monkeypatch.setattr(
        "futuresbot.pmt_strategy.detect_mental_threshold_cross",
        lambda frame, symbol: MentalThresholdCross("SHORT", 61000.0, 61010.0, 60990.0, -0.001, 0.001),
    )
    monkeypatch.setattr(
        "futuresbot.pmt_strategy._score_threshold_cross",
        lambda frame, pmt, cross: (92.5, {"pmt_label": pmt.label, "pmt_edge_score": 95.0}),
    )

    assert score_pmt_threshold_signal(frame, _config()) is None
    rejection = diagnose_pmt_threshold_rejection(frame, _config())
    assert rejection.startswith("score_below_threshold score=92.50 min=92.50")

    monkeypatch.setattr(
        "futuresbot.pmt_strategy._score_threshold_cross",
        lambda frame, pmt, cross: (92.51, {"pmt_label": pmt.label, "pmt_edge_score": 95.0}),
    )
    signal = score_pmt_threshold_signal(frame, _config())

    assert signal is not None
    assert signal.score == 92.51
    assert signal.metadata["pmt_balance_fraction"] == 0.50


def test_pmt_simple_scoring_uses_trend_and_threshold_as_core(monkeypatch):
    _enable_pmt(monkeypatch, min_score="90")
    monkeypatch.setenv("FUTURES_PMT_SIMPLE_SCORING_ENABLED", "1")
    frame = _frame([75600.0] * 100 + [75100.0] * 5 + [75080.0, 74940.0])

    signal = score_pmt_threshold_signal(frame, _config())

    assert signal is not None
    assert signal.side == "SHORT"
    assert signal.score >= 90.0
    assert signal.metadata["pmt_score_model"] == "simple_trend_threshold_v1"
    assert signal.metadata["pmt_simple_core_weight"] == 0.90
    assert signal.metadata["mental_threshold_confirmation_bars"] == 0


def test_pmt_simple_core_weight_scales_context_bonus(monkeypatch):
    _enable_pmt(monkeypatch, min_score="80")
    monkeypatch.setenv("FUTURES_PMT_SIMPLE_SCORING_ENABLED", "1")
    frame = _frame([75600.0] * 100 + [75100.0] * 5 + [75080.0, 74940.0])

    monkeypatch.setenv("FUTURES_PMT_SIMPLE_CORE_WEIGHT", "0.95")
    defensive_signal = score_pmt_threshold_signal(frame, _config())

    monkeypatch.setenv("FUTURES_PMT_SIMPLE_CORE_WEIGHT", "0.75")
    aggressive_signal = score_pmt_threshold_signal(frame, _config())

    assert defensive_signal is not None
    assert aggressive_signal is not None
    assert defensive_signal.metadata["pmt_simple_core_weight"] == 0.95
    assert aggressive_signal.metadata["pmt_simple_core_weight"] == 0.75
    assert aggressive_signal.metadata["pmt_simple_context_bonus"] > defensive_signal.metadata["pmt_simple_context_bonus"]
    assert aggressive_signal.score > defensive_signal.score


def test_pmt_simple_scoring_sizes_down_exhausted_volume_chase(monkeypatch):
    _enable_pmt(monkeypatch, min_score="90")
    monkeypatch.setenv("FUTURES_PMT_SIMPLE_SCORING_ENABLED", "1")
    monkeypatch.setenv("FUTURES_PMT_SIMPLE_HIGH_SCORE_BLOWOFF_VOLUME_RATIO", "10")
    monkeypatch.setenv("FUTURES_PMT_SIMPLE_HIGH_SCORE_BROADER_OVERSTRETCH_24H_PCT", "1.0")
    frame = _frame([76000.0] * 100 + [81000.0] * 5 + [81900.0, 82450.0])
    frame.loc[frame.index[-1], "volume"] = 1600.0

    signal = score_pmt_threshold_signal(frame, _config())

    assert signal is not None
    assert signal.score == 92.0
    assert signal.metadata["pmt_balance_fraction"] == 0.50
    assert "simple_exhausted_volume_climax" in signal.metadata["pmt_score_caps"]


def test_pmt_simple_scoring_rejects_high_score_blowoff_chase(monkeypatch):
    _enable_pmt(monkeypatch, min_score="90")
    monkeypatch.setenv("FUTURES_PMT_SIMPLE_SCORING_ENABLED", "1")
    monkeypatch.setenv("FUTURES_PMT_SIMPLE_HIGH_SCORE_BROADER_OVERSTRETCH_24H_PCT", "1.0")
    monkeypatch.setenv("FUTURES_PMT_SIMPLE_HIGH_SCORE_BLOWOFF_1H_PCT", "0.015")
    frame = _frame([76000.0] * 100 + [81000.0] * 5 + [81900.0, 82450.0])
    frame.loc[frame.index[-1], "volume"] = 3200.0

    assert score_pmt_threshold_signal(frame, _config()) is None
    rejection = diagnose_pmt_threshold_rejection(frame, _config())
    assert rejection.startswith("score_below_threshold")
    assert "simple_high_score_blowoff_chase" in rejection


def test_pmt_simple_scoring_rejects_high_score_broader_overstretch(monkeypatch):
    _enable_pmt(monkeypatch, min_score="90")
    monkeypatch.setenv("FUTURES_PMT_SIMPLE_SCORING_ENABLED", "1")
    monkeypatch.setenv("FUTURES_PMT_SIMPLE_HIGH_SCORE_BLOWOFF_VOLUME_RATIO", "10")
    frame = _frame([76000.0] * 100 + [81000.0] * 5 + [81900.0, 82450.0])
    frame.loc[frame.index[-1], "volume"] = 1600.0

    assert score_pmt_threshold_signal(frame, _config()) is None
    rejection = diagnose_pmt_threshold_rejection(frame, _config())
    assert rejection.startswith("score_below_threshold")
    assert "simple_high_score_broader_overstretch" in rejection


def test_pmt_simple_scoring_rejects_weak_followthrough(monkeypatch):
    _enable_pmt(monkeypatch, min_score="90")
    monkeypatch.setenv("FUTURES_PMT_SIMPLE_SCORING_ENABLED", "1")
    frame = _frame([76000.0] * 100 + [75010.0] * 5 + [75020.0, 74980.0])
    frame.loc[frame.index[-1], "volume"] = 2200.0

    assert score_pmt_threshold_signal(frame, _config()) is None
    rejection = diagnose_pmt_threshold_rejection(frame, _config())
    assert rejection.startswith("score_below_threshold")
    assert "simple_weak_followthrough" in rejection


def test_pmt_simple_scoring_sizes_down_severe_high_score_exhaustion(monkeypatch):
    _enable_pmt(monkeypatch, min_score="90")
    monkeypatch.setenv("FUTURES_PMT_SIMPLE_SCORING_ENABLED", "1")
    frame = _frame([78000.0] * 100 + [75100.0] * 5 + [75080.0, 74000.0])

    signal = score_pmt_threshold_signal(frame, _config())

    assert signal is not None
    assert signal.score == 92.0
    assert signal.metadata["pmt_balance_fraction"] == 0.50
    assert "simple_severe_high_score_exhaustion" in signal.metadata["pmt_score_caps"]


def test_pmt_simple_scoring_sizes_down_high_score_trend_stretch(monkeypatch):
    _enable_pmt(monkeypatch, min_score="90")
    monkeypatch.setenv("FUTURES_PMT_SIMPLE_SCORING_ENABLED", "1")
    frame = _frame([80000.0] * 80 + [77000.0] * 20 + [75100.0] * 4 + [75080.0, 74940.0])

    signal = score_pmt_threshold_signal(frame, _config())

    assert signal is not None
    assert signal.score == 92.0
    assert signal.metadata["pmt_balance_fraction"] == 0.50
    assert "simple_high_score_trend_stretch" in signal.metadata["pmt_score_caps"]


def test_pmt_funding_penalty_does_not_veto_mega_threshold(monkeypatch):
    _enable_pmt(monkeypatch, min_score="90")
    monkeypatch.setenv("FUTURES_PMT_SIMPLE_SCORING_ENABLED", "1")
    monkeypatch.setenv("FUTURES_PMT_FUNDING_ADVERSE_EXCESS_PENALTY_PER_CAP", "0.01")
    frame = _frame([78000.0] * 100 + [75100.0] * 5 + [75080.0, 74940.0])

    signal = score_pmt_threshold_signal(
        frame,
        _config(),
        funding_rate=-0.00042,
        funding_cap=0.00025,
    )

    assert signal is not None
    assert signal.side == "SHORT"
    assert signal.score >= 90.0
    assert signal.metadata["pmt_funding_adverse"] is True
    assert signal.metadata["pmt_funding_score_penalty"] > 0.0
    assert signal.metadata["pmt_score_before_funding"] > signal.score
    assert signal.score == 91.99
    assert signal.metadata["pmt_balance_fraction"] == 0.25
    assert signal.metadata["pmt_funding_score_cap"] == 91.99
    assert "funding_adverse" in signal.metadata["pmt_score_penalties"]
    assert "funding_adverse_reduced_size" in signal.metadata["pmt_score_caps"]


def test_pmt_backtest_contract_sizing_uses_score_band_fraction(monkeypatch):
    _enable_pmt(monkeypatch)
    engine = object.__new__(FuturesBacktestEngine)
    engine.config = SimpleNamespace(margin_budget_usdt=75.0, leverage_min=15, leverage_max=50, min_confidence_score=70.0)
    engine.contract_size = 0.0001
    engine.min_vol = 1

    contracts, used_margin, leverage = engine._contracts_for_entry(
        entry_price=100.0,
        leverage=50,
        balance=123.45,
        sl_price=100.4,
        score=94.0,
    )

    assert contracts == 308625
    assert used_margin == 61.725
    assert leverage == 50


def test_pmt_backtest_contract_sizing_uses_full_balance_for_high_score(monkeypatch):
    _enable_pmt(monkeypatch)
    engine = object.__new__(FuturesBacktestEngine)
    engine.config = SimpleNamespace(margin_budget_usdt=75.0, leverage_min=15, leverage_max=50, min_confidence_score=70.0)
    engine.contract_size = 0.0001
    engine.min_vol = 1

    contracts, used_margin, leverage = engine._contracts_for_entry(
        entry_price=100.0,
        leverage=50,
        balance=123.45,
        sl_price=100.4,
        score=95.0,
    )

    assert contracts == 617250
    assert used_margin == 123.45
    assert leverage == 50


def test_pmt_backtest_contract_sizing_can_keep_full_balance(monkeypatch):
    _enable_pmt(monkeypatch)
    monkeypatch.setenv("FUTURES_PMT_SCORE_BAND_SIZING_ENABLED", "0")
    engine = object.__new__(FuturesBacktestEngine)
    engine.config = SimpleNamespace(margin_budget_usdt=75.0, leverage_min=15, leverage_max=50, min_confidence_score=70.0)
    engine.contract_size = 0.0001
    engine.min_vol = 1

    contracts, used_margin, leverage = engine._contracts_for_entry(
        entry_price=100.0,
        leverage=50,
        balance=123.45,
        sl_price=100.4,
        score=95.0,
    )

    assert contracts == 617250
    assert used_margin == 123.45
    assert leverage == 50


def test_profit_lock_fixed_giveback_exits_one_point_from_peak():
    position = FuturesPosition(
        symbol="BTC_USDT",
        side="LONG",
        entry_price=100.0,
        contracts=50,
        contract_size=1.0,
        leverage=50,
        margin_usdt=100.0,
        tp_price=104.0,
        sl_price=99.6,
        position_id="pmt-test",
        order_id="pmt-test",
        opened_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        score=95.0,
        certainty=0.95,
        entry_signal="PMT_THRESHOLD_LONG",
        metadata={},
    )

    first_exit, changed = evaluate_profit_lock_bar(
        position,
        high=100.22,
        low=100.21,
        taker_fee_rate=0.0,
        trigger_pct=10.0,
        pullback_fraction=0.20,
        floor_pct=0.0,
        giveback_pct=1.0,
    )
    second_exit, _changed = evaluate_profit_lock_bar(
        position,
        high=100.22,
        low=100.19,
        taker_fee_rate=0.0,
        trigger_pct=10.0,
        pullback_fraction=0.20,
        floor_pct=0.0,
        giveback_pct=1.0,
    )

    assert first_exit is None
    assert changed
    assert second_exit == (100.2, "PEAK_PROFIT_LOCK")


def test_pmt_profit_lock_uses_pmt_overrides_without_tp_progress():
    position = FuturesPosition(
        symbol="ETH_USDT",
        side="SHORT",
        entry_price=100.0,
        contracts=50,
        contract_size=1.0,
        leverage=50,
        margin_usdt=100.0,
        tp_price=96.0,
        sl_price=100.28,
        position_id="pmt-eth-lock-test",
        order_id="pmt-eth-lock-test",
        opened_at=datetime(2026, 6, 3, 20, 49, tzinfo=timezone.utc),
        score=100.0,
        certainty=0.99,
        entry_signal="PMT_THRESHOLD_SHORT",
        metadata={
            "profit_lock_trigger_pct_override": 4.0,
            "profit_lock_giveback_pct_override": 0.0,
            "profit_lock_pullback_fraction_override": 0.35,
            "profit_lock_min_tp_progress_override": 0.0,
            "profit_lock_exit_min_net_pct_override": 0.0,
            "profit_lock_floor_pct_override": 3.0,
        },
    )

    early_peak_exit, changed = evaluate_profit_lock_bar(
        position,
        high=99.7,
        low=99.56,
        taker_fee_rate=0.0,
        trigger_pct=10.0,
        pullback_fraction=0.20,
        floor_pct=0.0,
        giveback_pct=1.0,
        min_tp_progress=0.95,
    )
    assert early_peak_exit is None
    assert changed
    assert round(position.metadata["profit_lock_stop_gross_pnl_pct"], 3) == 14.3

    below_min_net_exit, _changed = evaluate_profit_lock_bar(
        position,
        high=99.7,
        low=99.56,
        taker_fee_rate=0.0,
        trigger_pct=10.0,
        pullback_fraction=0.20,
        floor_pct=0.0,
        giveback_pct=1.0,
        min_tp_progress=0.95,
    )
    runner_peak_exit, _changed = evaluate_profit_lock_bar(
        position,
        high=98.7,
        low=98.616,
        taker_fee_rate=0.0,
        trigger_pct=10.0,
        pullback_fraction=0.20,
        floor_pct=0.0,
        giveback_pct=1.0,
        min_tp_progress=0.95,
    )
    final_exit, _changed = evaluate_profit_lock_bar(
        position,
        high=99.6,
        low=98.616,
        taker_fee_rate=0.0,
        trigger_pct=10.0,
        pullback_fraction=0.20,
        floor_pct=0.0,
        giveback_pct=1.0,
        min_tp_progress=0.95,
    )

    assert below_min_net_exit is None
    assert runner_peak_exit is None
    assert round(position.metadata["profit_lock_peak_gross_pnl_pct"], 3) == 69.2
    assert round(position.metadata["profit_lock_stop_gross_pnl_pct"], 3) == 44.98
    assert final_exit == (99.1004, "PEAK_PROFIT_LOCK")

def test_trap_reclaim_blocks_long_after_recent_breakdown(monkeypatch):
    _enable_pmt(monkeypatch)
    from futuresbot.pmt_strategy import is_trap_reclaim
    # 425 broke DOWN mid-window, then LONG recross with negative 24h tape (ZEC 2026-06-11)
    frame = _frame([430.0] * 40 + [424.0] * 56 + [424.5, 425.6, 426.0])
    cross = MentalThresholdCross("LONG", 425.0, 424.5, 426.0, 0.003, 0.002)
    pmt = PairMarketTrend("ZEC_USDT", "BULLISH", -0.05, -0.01, 0.01)
    assert is_trap_reclaim(frame, cross, pmt) is True
    pmt_up = PairMarketTrend("ZEC_USDT", "BULLISH", 0.05, 0.01, 0.01)
    assert is_trap_reclaim(frame, cross, pmt_up) is False  # tape agrees: not a trap
    monkeypatch.setenv("FUTURES_PMT_BLOCK_TRAP_RECLAIM", "0")
    assert is_trap_reclaim(frame, cross, pmt) is False


def test_trap_reclaim_allows_fresh_breakout(monkeypatch):
    _enable_pmt(monkeypatch)
    from futuresbot.pmt_strategy import is_trap_reclaim
    # level never broke down in lookback: clean break, no trap
    frame = _frame([424.0] * 96 + [424.5, 425.6, 426.0])
    cross = MentalThresholdCross("LONG", 425.0, 424.5, 426.0, 0.003, 0.002)
    pmt = PairMarketTrend("ZEC_USDT", "BULLISH", -0.05, -0.01, 0.01)
    assert is_trap_reclaim(frame, cross, pmt) is False


def test_stop_first_low_tier_lock_overrides(monkeypatch):
    # Floor lowered for the synthetic frame; this test pins TIER routing
    # (score <95 -> tight lock), not the production floor.
    _enable_pmt(monkeypatch, min_score="70")
    monkeypatch.setenv("FUTURES_PMT_REDUCED_ENTRY_MIN_SCORE", "70")
    monkeypatch.setenv("FUTURES_PMT_CONFIRMATION_BARS", "0")
    monkeypatch.setenv("FUTURES_PMT_STOP_FIRST_SIZING_ENABLED", "1")
    closes = [63800.0] * 110 + [63900.0, 64120.0]
    signal = score_pmt_threshold_signal(_frame(closes), _config())
    assert signal is not None
    md = signal.metadata
    if float(signal.score) < 95.0:
        sl_margin = float(md["sl_margin_pct"])
        # R/cost-calibrated tier: arm = 0.35R; floor = max(0.15R, 1.5x RT fee)
        assert md["profit_lock_trigger_pct_override"] == __import__("pytest").approx(0.35 * sl_margin, rel=1e-4)
        assert md["profit_lock_pullback_fraction_override"] == 0.30
        assert md["profit_lock_floor_pct_override"] >= 0.15 * sl_margin - 1e-9
    else:
        assert md["profit_lock_trigger_pct_override"] > 10.0


def test_volume_filter_disabled_by_default(monkeypatch):
    _enable_pmt(monkeypatch)
    from futuresbot.pmt_strategy import volume_filter_blocks
    # low-volume final bar; filter is off by default so it never blocks
    closes = [60000.0] * 120
    frame = _frame(closes)
    frame.loc[frame.index[-1], "volume"] = 100.0
    assert volume_filter_blocks(frame) is False


def test_volume_filter_blocks_low_volume_when_enabled(monkeypatch):
    _enable_pmt(monkeypatch)
    monkeypatch.setenv("FUTURES_PMT_VOLUME_FILTER_ENABLED", "1")
    from futuresbot.pmt_strategy import volume_filter_blocks, volume_expansion_z
    closes = [60000.0] * 120
    frame = _frame(closes)
    # give the base bars real variance so std>0, then set the breakout bar
    vols = [900.0 + (i % 5) * 50.0 for i in range(120)]
    frame["volume"] = vols
    frame.loc[frame.index[-1], "volume"] = 200.0  # below-average breakout bar
    assert volume_expansion_z(frame) < 0.5
    assert volume_filter_blocks(frame) is True
    frame.loc[frame.index[-1], "volume"] = 5000.0  # volume-expanded breakout
    assert volume_expansion_z(frame) >= 0.5
    assert volume_filter_blocks(frame) is False


def test_volume_filter_fails_open_without_volume(monkeypatch):
    _enable_pmt(monkeypatch)
    monkeypatch.setenv("FUTURES_PMT_VOLUME_FILTER_ENABLED", "1")
    import pandas as pd
    from futuresbot.pmt_strategy import volume_filter_blocks
    frame = pd.DataFrame({"open": [1, 2], "high": [1, 2], "low": [1, 2], "close": [1, 2]})
    assert volume_filter_blocks(frame) is False


def test_universe_expansion_profiles_present(monkeypatch):
    # Universe-expansion pairs (derived per-pair, 2026-06-14): present with
    # their derived geometry, and allowed only when listed in FUTURES_PMT_SYMBOLS
    # (champion default stays the eligible 6).
    from futuresbot.pmt_strategy import DEFAULT_PMT_PROFILES, pmt_symbol_allowed
    expected = {
        "XAU_USDT": (50.0, 0.0052, 0.0061, 0.0125, 0.0229),
        "XLM_USDT": (0.0025, 0.0266, 0.0372, 0.0593, 0.1129),
        "TONCOIN_USDT": (0.025, 0.0301, 0.0314, 0.0514, 0.0802),
        "ENA_USDT": (0.001, 0.0259, 0.0339, 0.0596, 0.0819),
        "TAO_USDT": (2.5, 0.0238, 0.0261, 0.0396, 0.0643),
    }
    for sym, vals in expected.items():
        p = DEFAULT_PMT_PROFILES[sym]
        assert (p.threshold_step, p.flat_24h_pct, p.flash_6h_pct, p.mega_12h_pct, p.mega_24h_pct) == vals
    # champion default (eligible 6) does NOT allow the new pairs
    monkeypatch.delenv("FUTURES_PMT_SYMBOLS", raising=False)
    assert pmt_symbol_allowed("XAU_USDT") is False
    assert pmt_symbol_allowed("BTC_USDT") is True
    # explicit env list (shadow) DOES allow them
    monkeypatch.setenv("FUTURES_PMT_SYMBOLS", "BTC_USDT,XAU_USDT,XLM_USDT")
    assert pmt_symbol_allowed("XAU_USDT") is True


def test_low_tier_early_lock_can_be_disabled(monkeypatch):
    # When the early lock is disabled, a 92.5-95 trade no longer arms the tight
    # pre-bank lock; it uses the runner-tier lock (far out) + bank/breakeven.
    _enable_pmt(monkeypatch, min_score="70")
    monkeypatch.setenv("FUTURES_PMT_REDUCED_ENTRY_MIN_SCORE", "70")
    monkeypatch.setenv("FUTURES_PMT_CONFIRMATION_BARS", "0")
    monkeypatch.setenv("FUTURES_PMT_STOP_FIRST_SIZING_ENABLED", "1")
    closes = [63800.0] * 110 + [63900.0, 64120.0]
    # early lock ON (default): low-tier arm is the tight ~0.30R value
    sig_on = score_pmt_threshold_signal(_frame(closes), _config())
    # early lock OFF: low-tier should use the runner-tier (far) arm
    monkeypatch.setenv("FUTURES_PMT_STOP_FIRST_LOW_TIER_EARLY_LOCK_ENABLED", "0")
    sig_off = score_pmt_threshold_signal(_frame(closes), _config())
    assert sig_on is not None and sig_off is not None
    if float(sig_on.score) < 95.0:
        on_arm = sig_on.metadata["profit_lock_trigger_pct_override"]
        off_arm = sig_off.metadata["profit_lock_trigger_pct_override"]
        assert off_arm > on_arm  # far-out runner lock vs tight early lock
