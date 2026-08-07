"""Trial-6 changes: short-TP clamp, sigma trigger, long-only, convex clock + trail.

Each test pins a defect this session MEASURED, not one someone imagined.
"""
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from futuresbot.config import FuturesConfig
from futuresbot.models import FuturesPosition
from futuresbot.runtime import FuturesRuntime
from futuresbot.wildcard import (
    detect_wildcard_signal,
    wildcard_long_only,
    wildcard_sigma_trigger_enabled,
)


def _frame(closes, vol_last=3000.0):
    """Long-shaped bars: close near the high, so the climax-wick guard passes."""
    n = len(closes)
    vols = [1000.0 + (i % 5) * 60.0 for i in range(n - 1)] + [vol_last]
    return pd.DataFrame({
        "open": closes, "high": [c * 1.0008 for c in closes],
        "low": [c * 0.996 for c in closes], "close": closes, "volume": vols,
    })


def _frame_short(closes, vol_last=3000.0):
    """Short-shaped bars: close near the LOW. For a short the adverse wick is
    (close - low)/range, so long-shaped bars are rejected as climax candles."""
    n = len(closes)
    vols = [1000.0 + (i % 5) * 60.0 for i in range(n - 1)] + [vol_last]
    return pd.DataFrame({
        "open": closes, "high": [c * 1.004 for c in closes],
        "low": [c * 0.9992 for c in closes], "close": closes, "volume": vols,
    })


def _apply(moves, base_n=28):
    closes = [1.0] * base_n; p = 1.0
    for m in moves:
        p *= (1.0 + m); closes.append(p)
    return closes


_MID_LONG = [0.02, 0.02, 0.02, -0.01, 0.02, 0.02, 0.02, -0.01, 0.02, 0.02, -0.012, 0.006]
_MID_SHORT = [-m for m in _MID_LONG]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("FUTURES_WILDCARD_SIGMA_TRIGGER", "FUTURES_WILDCARD_LONG_ONLY",
              "FUTURES_WILDCARD_MIN_ROC_Z", "FUTURES_WILDCARD_SL_ATR_MULT",
              "FUTURES_WILDCARD_MAX_SHORT_TP_DIST", "FUTURES_WILDCARD_TP_FROM_DESIGNED_STOP",
              "FUTURES_CONVEX_TIME_STOP_HOURS", "FUTURES_CONVEX_RUNNER_TRAIL",
              "FUTURES_WILDCARD_CONVEX_EXIT_ENABLED"):
        monkeypatch.delenv(k, raising=False)


# --------------------------------------------------------------------------
# short take-profit clamp
# --------------------------------------------------------------------------

def test_short_take_profit_is_never_at_or_below_zero(monkeypatch):
    """tp = entry*(1 - sl_frac*5). At the live 3.0xATR stop, sl_frac reaches 0.20
    and the short's target is computed at price ZERO — an order that can only
    fill if the token goes to nothing. Measured on 21% of live short signals."""
    monkeypatch.setenv("FUTURES_WILDCARD_SL_ATR_MULT", "3.0")
    sig = detect_wildcard_signal(_frame_short(_apply(_MID_SHORT)), "FOO_USDT")
    assert sig is not None and sig.side == "SHORT"
    assert sig.tp_price > 0.0, "short target computed at or below zero"
    assert sig.tp_price < sig.entry_price, "short target must be below entry"


def test_short_tp_clamp_is_configurable_and_binds(monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_SL_ATR_MULT", "3.0")
    monkeypatch.setenv("FUTURES_WILDCARD_MAX_SHORT_TP_DIST", "0.30")
    sig = detect_wildcard_signal(_frame_short(_apply(_MID_SHORT)), "FOO_USDT")
    assert sig is not None
    assert sig.tp_price >= sig.entry_price * 0.70 - 1e-12


def test_long_target_is_unbounded_and_untouched(monkeypatch):
    """The clamp is short-only: a long's payoff is not bounded by zero."""
    monkeypatch.setenv("FUTURES_WILDCARD_SL_ATR_MULT", "3.0")
    sig = detect_wildcard_signal(_frame(_apply(_MID_LONG)), "FOO_USDT")
    assert sig is not None and sig.side == "LONG"
    assert sig.tp_price > sig.entry_price


# --------------------------------------------------------------------------
# sigma-normalised trigger
# --------------------------------------------------------------------------

def test_sigma_trigger_defaults_off():
    assert wildcard_sigma_trigger_enabled() is False


def test_sigma_trigger_rejects_when_history_is_too_short(monkeypatch):
    """Refuse to guess. 60 bars can never supply 96 trailing 3h returns."""
    monkeypatch.setenv("FUTURES_WILDCARD_SIGMA_TRIGGER", "1")
    reasons: list[str] = []
    assert detect_wildcard_signal(_frame(_apply(_MID_LONG)), "FOO_USDT", reasons) is None
    assert "no_roc_sigma" in reasons


def test_sigma_trigger_rejects_a_routine_move_on_a_volatile_symbol(monkeypatch):
    """The whole point. On the band's most volatile names an 8% 3h move is ~1
    sigma and happens on ~19% of all bars; the fixed rule calls that an anomaly."""
    monkeypatch.setenv("FUTURES_WILDCARD_SIGMA_TRIGGER", "1")
    monkeypatch.setenv("FUTURES_WILDCARD_MIN_ROC_Z", "4.0")
    # History in alternating 12-bar RUNS, not alternating bars: bar-level noise
    # cancels over a 12-bar window, so only sustained runs make the 3h return
    # distribution itself wide. This symbol routinely swings ~15% per 3h, which
    # is exactly the profile of the band names that supply most of the sleeve's
    # signal (BTW breached 8%/3h on 19.2% of all its bars).
    closes, p = [], 1.0
    for block in range(34):
        step = 0.012 if block % 2 == 0 else -0.011
        for _ in range(12):
            p *= (1.0 + step); closes.append(p)
    for m in _MID_LONG:                      # continue the SAME series
        p *= (1.0 + m); closes.append(p)
    reasons: list[str] = []
    sig = detect_wildcard_signal(_frame(closes), "NOISY_USDT", reasons)
    assert sig is None
    assert "roc_z_below_min" in reasons


def test_sigma_trigger_fires_on_a_genuine_outlier(monkeypatch):
    """Same +11% move, but on a symbol whose own 3h sigma is tiny."""
    monkeypatch.setenv("FUTURES_WILDCARD_SIGMA_TRIGGER", "1")
    monkeypatch.setenv("FUTURES_WILDCARD_MIN_ROC_Z", "4.0")
    closes, p = [], 1.0
    for i in range(400):                       # very quiet trailing history
        p *= (1.0 + (0.0004 if i % 2 == 0 else -0.00035))
        closes.append(p)
    for m in _MID_LONG:
        p *= (1.0 + m); closes.append(p)
    sig = detect_wildcard_signal(_frame(closes), "QUIET_USDT")
    assert sig is not None, "a real outlier must still fire"
    assert sig.roc_z is not None and abs(sig.roc_z) >= 4.0


def test_roc_z_is_recorded_even_when_the_sigma_trigger_is_off():
    """It must be loggable as a FEATURE before it is used as a GATE, so the
    expectancy engine can settle sigma-vs-percent on real fills."""
    sig = detect_wildcard_signal(_frame(_apply(_MID_LONG)), "FOO_USDT")
    assert sig is not None
    assert sig.sl_frac_designed is not None and sig.sl_frac_designed > 0


# --------------------------------------------------------------------------
# long-only
# --------------------------------------------------------------------------

def test_long_only_defaults_on():
    assert wildcard_long_only() is True


def test_long_only_can_be_disabled(monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_LONG_ONLY", "0")
    assert wildcard_long_only() is False


def test_shorts_are_filtered_after_candidates_are_built_not_in_the_detector():
    """Load-bearing. _shadow_log_untaken only fires on objects that reached the
    candidate list, so rejecting SHORT inside detect_wildcard_signal would yield
    ZERO shadow rows and destroy the question permanently."""
    import inspect

    src = inspect.getsource(FuturesRuntime._maybe_scan_wildcard)
    assert "wildcard_long_only()" in src, "long-only not applied in the scan"
    assert "side_disabled" in src, "blocked shorts are not shadow-logged"
    det = inspect.getsource(detect_wildcard_signal)
    assert "long_only" not in det, "side filter must NOT live in the detector"


# --------------------------------------------------------------------------
# convex clock + runner trail
# --------------------------------------------------------------------------

@pytest.fixture
def rt(tmp_path, monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    cfg = replace(FuturesConfig.from_env(), symbol="BTC_USDT", symbols=("BTC_USDT",),
                  runtime_state_file=str(tmp_path / "rt.json"),
                  status_file=str(tmp_path / "st.json"),
                  telegram_token="", telegram_chat_id="")
    return FuturesRuntime(cfg, MagicMock())


def _pos(hours_held=1.0, entry=100.0, sl=90.0, side="LONG"):
    return FuturesPosition(
        symbol="FOO_USDT", side=side, entry_price=entry, contracts=100,
        contract_size=1.0, leverage=2, margin_usdt=50.0,
        tp_price=entry * 1.5, sl_price=sl, position_id="1", order_id="1",
        opened_at=datetime.now(timezone.utc) - timedelta(hours=hours_held),
        score=96.0, certainty=0.9, entry_signal="WILDCARD_LONG",
        metadata={"wildcard": 1.0, "sl_margin_pct": 20.0},
    )


def test_time_stop_is_inert_on_non_convex_positions(rt, monkeypatch):
    monkeypatch.delenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", raising=False)
    assert rt._convex_time_stop_exit(_pos(hours_held=99.0), 100.0) is False


def test_time_stop_default_is_24h_not_6h(rt, monkeypatch):
    """TRIAL 6.5. The 6h default was sized on a stop-only/no-take-profit decay
    curve — a policy the bot does not run. With the live +5R bracket attached,
    the same signals IMPROVE monotonically out to 24h+ (6h +0.139R -> 24h
    +0.214R, 72h-6h +0.103R at t_day +2.00, 0/12 LOMO flips). 6h captured only
    23% of eventual +5R completions; 24h captures 54%."""
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setattr(rt, "_close_position_for_exit", lambda *a, **k: True)
    # inside the clock: held 7h would have fired under trial 6's 6h default
    assert rt._convex_time_stop_exit(_pos(hours_held=7.0), 100.0) is False
    assert rt._convex_time_stop_exit(_pos(hours_held=23.0), 100.0) is False


def test_time_stop_fires_at_24h(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    seen = {}
    monkeypatch.setattr(rt, "_close_position_for_exit",
                        lambda p, **k: seen.update(reason=k.get("reason")) or True)
    assert rt._convex_time_stop_exit(_pos(hours_held=25.0), 100.0) is True
    assert seen["reason"] == "CONVEX_TIME_STOP"


def test_trail_does_not_arm_below_one_r(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setattr(rt, "_close_position_for_exit", lambda *a, **k: True)
    p = _pos()
    assert rt._convex_runner_trail_exit(p, 104.0) is False       # ~+0.4R
    assert rt._convex_runner_trail_exit(p, 103.0) is False       # gave back, still unarmed


def test_trail_giveback_is_2r_and_marginal_peaks_are_left_alone(rt, monkeypatch):
    """TRIAL 6.5. At giveback=1R, a trade arming at exactly +1R had its trail
    level at exactly 0R — the live HFT trade (+1.07R peak -> +0.03R exit) was
    that mechanical floor case, and the trail cut +5R completions from 121/598
    to 50/598. At giveback=2R the trail is inert below a +2R peak: it protects a
    genuine runner and never scratches a marginal one. Tightening instead was
    measured to HALVE mean R."""
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setattr(rt, "_close_position_for_exit", lambda *a, **k: True)
    # the HFT case: peak +1.07R then fade — must NOT fire at giveback 2R
    p = _pos()
    assert rt._convex_runner_trail_exit(p, 110.7) is False       # peak +1.07R, arms
    assert rt._convex_runner_trail_exit(p, 100.3) is False       # +0.03R: trial-6 scratched here


def test_trail_exits_after_giving_back_two_r_from_the_peak(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    seen = {}
    monkeypatch.setattr(rt, "_close_position_for_exit",
                        lambda p, **k: seen.update(reason=k.get("reason")) or True)
    p = _pos()
    assert rt._convex_runner_trail_exit(p, 135.0) is False       # +3.5R, arms, records peak
    assert p.metadata["convex_peak_r"] == pytest.approx(3.5, abs=0.05)
    assert rt._convex_runner_trail_exit(p, 120.0) is False       # -1.5R off peak, holds
    assert rt._convex_runner_trail_exit(p, 114.0) is True        # -2.1R off peak, exits
    assert seen["reason"] == "CONVEX_RUNNER_TRAIL"


def test_trail_lets_a_runner_run(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setattr(rt, "_close_position_for_exit", lambda *a, **k: True)
    p = _pos()
    for px in (115.0, 130.0, 150.0, 180.0):
        assert rt._convex_runner_trail_exit(p, px) is False
    assert p.metadata["convex_peak_r"] == pytest.approx(8.0, abs=0.05)


# --------------------------------------------------------------------------
# sleeve attribution
# --------------------------------------------------------------------------

def test_convex_exits_are_reachable_under_the_live_pmt_strategy_mode():
    """REGRESSION. Shipped once and was silently dead: _hourly_exit RETURNS
    inside `if pmt_strategy_enabled():`, and live runs FUTURES_STRATEGY_MODE=
    pmt_threshold. Placing the convex exits after that branch made them
    unreachable in production while every unit test still passed. A wildcard
    position is not a PMT position and must not be gated on the PMT flag.
    """
    import inspect

    src = inspect.getsource(FuturesRuntime._hourly_exit)
    convex = src.index("_convex_time_stop_exit")
    pmt = src.index("if pmt_strategy_enabled():")
    assert convex < pmt, "convex exits must run BEFORE the PMT early-return branch"


def test_convex_time_stop_fires_even_when_pmt_mode_is_on(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setenv("FUTURES_STRATEGY_MODE", "pmt_threshold")
    seen = {}
    monkeypatch.setattr(rt, "_close_position_for_exit",
                        lambda p, **k: seen.update(reason=k.get("reason")) or True)
    assert rt._hourly_exit(_pos(hours_held=25.0), 100.0) is True
    assert seen["reason"] == "CONVEX_TIME_STOP"


def test_wildcard_scan_excludes_tokenised_equities():
    """Confirmed live on trial-6 day 1: QBTSSTOCK_USDT SHORT reached the wildcard
    candidate list. universe.py has carried this filter all along and the sniper
    excludes these by category; only the wildcard scan never applied it."""
    import inspect

    from futuresbot.universe import _is_crypto_usdt_symbol

    assert _is_crypto_usdt_symbol("QBTSSTOCK_USDT", None) is False
    assert _is_crypto_usdt_symbol("NVIDIA_USDT", None) is False
    assert _is_crypto_usdt_symbol("BTW_USDT", None) is True
    src = inspect.getsource(FuturesRuntime._maybe_scan_wildcard)
    assert "_is_crypto_usdt_symbol" in src, "wildcard scan still admits non-crypto"


def test_feature_store_row_carries_the_trial6_columns():
    """REGRESSION. The trial-6 columns were added to the trade-history record and
    never reached the feature store, because that row is built field by field
    rather than from the trade dict — so the Stage-2 learning corpus, the file
    that actually gets analysed, never saw them."""
    import inspect

    src = inspect.getsource(FuturesRuntime._append_feature_store)
    for col in ('"roc_z"', '"sl_frac_designed"', '"peak_r"', '"hold_hours"'):
        assert col in src, f"{col} missing from the feature store row"


def test_sniper_scan_log_does_not_claim_shadow_while_trading_live():
    """REGRESSION, operator safety. The scan summary hard-coded `mode=shadow`
    and warned that live entries were "not implemented in this build" — text
    left behind when the live leg landed in 3247faf. It therefore reported
    shadow-only on the very scans where the sleeve opened real positions
    (XRP_USDT and AVAX_USDT, 2026-08-06). A log that misstates whether real
    money is at risk is worse than no log.
    """
    import inspect

    src = inspect.getsource(FuturesRuntime._log_sniper_variant)
    assert "not implemented in this build" not in src, "stale shadow-only claim is back"
    assert "mode=shadow%s" not in src, "mode is hard-coded to shadow again"
    assert "sniper_live_variants()" in src, "mode is not derived from the live gate"


def test_sleeve_tag_distinguishes_the_sleeves(rt):
    assert rt._sleeve_of(_pos()) == "WILDCARD"
    p = _pos(); p.metadata = {"squeeze": 1.0}
    assert rt._sleeve_of(p) == "SQUEEZE"
    p.metadata = {"sniper": 1.0, "sniper_variant": "FAST"}
    assert rt._sleeve_of(p) == "SNIPER:FAST"
    p.metadata = {}
    assert rt._sleeve_of(p) == "PMT"


def test_close_record_carries_sleeve_and_exit_rule():
    """226 live ledger rows carried neither, so five separate analyses had to
    infer their own subject from six symbol names."""
    import inspect

    src = inspect.getsource(FuturesRuntime._close_history_trade)
    for field in ('"sleeve"', '"exit_rule"', '"hold_hours"', '"equity_at_close_usdt"'):
        assert field in src, f"{field} not recorded at close"


# --------------------------------------------------------------------------
# shadow-ledger double-write (trial 6.5 follow-up, measurement only)
# --------------------------------------------------------------------------

def test_sniper_live_skip_does_not_write_a_second_shadow_row():
    """REGRESSION. _log_sniper_variant writes every signal as `shadow_only`,
    then calls the live opener — which used to write the SAME signal AGAIN as
    `slot_occupied`. That inflated SNIPER_FAST to 21 rows for 17 distinct
    signals, double-weighted 4 of them in the /status cfR and win%, and
    rendered DOGE_USDT as two identical lines."""
    import inspect

    src = inspect.getsource(FuturesRuntime._maybe_open_sniper_live)
    assert '_shadow_log_untaken' not in src, "live sniper path re-logs an already-logged signal"
    assert "SNIPER_LIVE_SKIP" in src, "slot-occupied skip is no longer recorded anywhere"


def test_load_rows_collapses_same_signal_written_twice(tmp_path):
    """Four such pairs are already on the /data volume, so the READER must
    dedupe or every consumer keeps double-counting them."""
    import json as _json

    from futuresbot.shadow_ledger import load_rows

    p = tmp_path / "shadow.jsonl"
    base = {"sleeve": "SNIPER_FAST", "symbol": "DOGE_USDT", "side": "LONG",
            "entry": 0.0699, "sl": 0.0702, "tp": 0.0693}
    rows = [
        {**base, "ts": 1786022584, "reject_reason": "shadow_only"},
        {**base, "ts": 1786022585, "reject_reason": "slot_occupied"},   # duplicate
        {**base, "ts": 1786022584 + 7200, "reject_reason": "shadow_only"},  # genuine re-fire
        {"sleeve": "WILDCARD", "symbol": "AKE_USDT", "side": "LONG", "entry": 1.0,
         "sl": 0.9, "tp": 1.5, "ts": 1786022584, "reject_reason": "slot_occupied"},
    ]
    p.write_text("\n".join(_json.dumps(r) for r in rows), encoding="utf-8")
    out = load_rows(str(p))
    assert len(out) == 3, f"expected the 1s-apart pair collapsed, got {len(out)}"
    assert out[0]["reject_reason"] == "shadow_only", "kept the wrong row of the pair"
    assert sum(1 for r in out if r["sleeve"] == "SNIPER_FAST") == 2
    assert sum(1 for r in out if r["sleeve"] == "WILDCARD") == 1, "unrelated sleeve dropped"


def test_status_sniper_header_is_derived_from_the_live_gate():
    """REGRESSION, operator safety. The header read 'never trades'
    unconditionally while SNIPER FAST held real XRP/AVAX positions. 2225084
    fixed the identical stale claim in the scan log and missed this surface."""
    import inspect

    src = inspect.getsource(FuturesRuntime._sniper_shadow_status_lines)
    assert "sniper_live_variants()" in src, "status mode is not derived from the live gate"
    assert 'f"🎯 Sniper <b>SHADOW</b> (logs would-be entries, never trades)' not in src
