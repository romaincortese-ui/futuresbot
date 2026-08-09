"""Trial-6 changes: short-TP clamp, sigma trigger, long-only, convex clock + trail.

Each test pins a defect this session MEASURED, not one someone imagined.
"""
import json
import os
import time
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


def test_retention_floor_banks_the_dead_zone(rt, monkeypatch):
    """TRIAL 7. The invariant: once armed, never exit below 0.30 x peak. The
    BICO shape — peak +1.46R then a full fade — banked $0 under the giveback
    rule (exit level -0.54R); the retention floor banks +0.44R (~+$1.2-1.4).
    Dead-zone trades ([1R,2R) peaks, 20.7% of the panel) go from -0.20R to
    +0.43R mean banked; measured cost of the invariant: +0.030R/trade
    (t_day 0.83 = zero). Design fix, not an edge claim."""
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    seen = {}
    monkeypatch.setattr(rt, "_close_position_for_exit",
                        lambda p, **k: seen.update(reason=k.get("reason")) or True)
    p = _pos()
    assert rt._convex_runner_trail_exit(p, 114.6) is False       # peak +1.46R, arms
    assert p.metadata["convex_peak_r"] == pytest.approx(1.46, abs=0.05)
    # floor = 0.30 x 1.46 = +0.438R -> price 104.38. Above it: hold.
    assert rt._convex_runner_trail_exit(p, 105.0) is False       # +0.50R, holds
    # fade through the floor: exits POSITIVE, never gives back everything
    assert rt._convex_runner_trail_exit(p, 104.0) is True        # +0.40R < floor
    assert seen["reason"] == "CONVEX_RETENTION_TRAIL"


def test_retention_floor_ratchets_with_the_peak(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    seen = {}
    monkeypatch.setattr(rt, "_close_position_for_exit",
                        lambda p, **k: seen.update(reason=k.get("reason")) or True)
    p = _pos()
    assert rt._convex_runner_trail_exit(p, 135.0) is False       # +3.5R, floor 1.05R
    assert rt._convex_runner_trail_exit(p, 120.0) is False       # +2.0R, above floor
    assert rt._convex_runner_trail_exit(p, 110.0) is True        # +1.0R < 1.05R floor
    assert seen["reason"] == "CONVEX_RETENTION_TRAIL"


def test_legacy_giveback_is_reachable_for_rollback(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setenv("FUTURES_CONVEX_TRAIL_RETAIN_FRAC", "0")
    seen = {}
    monkeypatch.setattr(rt, "_close_position_for_exit",
                        lambda p, **k: seen.update(reason=k.get("reason")) or True)
    p = _pos()
    assert rt._convex_runner_trail_exit(p, 135.0) is False       # peak 3.5R
    assert rt._convex_runner_trail_exit(p, 114.0) is True        # -2.1R off peak
    assert seen["reason"] == "CONVEX_RUNNER_TRAIL"


def test_position_open_across_the_deploy_is_tagged_migrated(rt, monkeypatch):
    """BICO-at-deploy: peak_r persisted under the old rule -> tag it so the
    trial-7 scoreboard can exclude it."""
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setattr(rt, "_close_position_for_exit", lambda *a, **k: True)
    p = _pos()
    p.metadata["convex_peak_r"] = 1.4558          # persisted by trial 6.5
    rt._convex_runner_trail_exit(p, 108.5)        # +0.85R, above floor 0.437
    assert p.metadata.get("trail_migrated") == 1.0
    assert p.metadata.get("trail_mode") == "retention"


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
    assert "_is_tradeable_crypto" in src, "wildcard scan still admits non-crypto"


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


# --------------------------------------------------------------------------
# risk dial (default OFF) + capacity instrumentation
# --------------------------------------------------------------------------

class _Sig:
    side = "LONG"; entry_price = 1.0; leverage = 1; sl_margin_pct = 16.37
    balance_fraction = 0.12; tp_margin_pct = 81.85; symbol = "FOO_USDT"


def test_risk_dial_defaults_ON_since_trial_7(rt, monkeypatch):
    """Bundled with the retention trail: $ becomes proportional to R, so the
    owner's dollar floor and the bot's R floor are the same number. Median-
    neutral by construction (risk_pct default = today's measured effective)."""
    monkeypatch.delenv("FUTURES_WILDCARD_RISK_TARGETED", raising=False)
    s = _Sig(); s.sl_margin_pct = 15.6            # the median: sizing unchanged
    assert rt._entry_margin(s, 140.0) == pytest.approx(0.12 * 140.0, rel=0.03)
    s.sl_margin_pct = 20.0                        # wide stop: sized DOWN now
    assert rt._entry_margin(s, 140.0) < 0.12 * 140.0
    monkeypatch.setenv("FUTURES_WILDCARD_RISK_TARGETED", "0")   # rollback path
    assert rt._entry_margin(s, 140.0) == pytest.approx(0.12 * 140.0)


def test_risk_dial_targets_a_constant_fraction_of_the_account(rt, monkeypatch):
    """The whole point: risk becomes a PARAMETER, not the emergent product of
    balance_fraction x sl_margin_pct (which lands anywhere in 1.2%-2.4%)."""
    monkeypatch.setenv("FUTURES_WILDCARD_RISK_TARGETED", "1")
    monkeypatch.setenv("FUTURES_WILDCARD_RISK_PCT", "0.0187")
    for sl_margin in (11.0, 15.6, 20.0):
        s = _Sig(); s.sl_margin_pct = sl_margin
        m = rt._entry_margin(s, 140.0)
        realised_risk = m * sl_margin / 100.0
        assert realised_risk == pytest.approx(0.0187 * 140.0, rel=0.02), (
            f"risk not constant at sl_margin={sl_margin}: ${realised_risk:.3f}")


def test_risk_dial_margin_is_bounded_on_a_pathologically_tight_stop(rt, monkeypatch):
    """Equalising MUST be allowed to size up on a tight stop — that is the
    mechanism. But an extreme stop would demand an unbounded position, and a
    gap-through then loses far more than the modelled 1R, so the margin is
    capped at 1.5x legacy."""
    monkeypatch.setenv("FUTURES_WILDCARD_RISK_TARGETED", "1")
    monkeypatch.setenv("FUTURES_WILDCARD_RISK_PCT", "0.0187")
    s = _Sig(); s.sl_margin_pct = 4.0          # would want ~3.9x legacy
    assert rt._entry_margin(s, 140.0) == pytest.approx(1.5 * 0.12 * 140.0)
    s.sl_margin_pct = 11.0                     # realistic tight -> must be ALLOWED up
    assert rt._entry_margin(s, 140.0) > 0.12 * 140.0


def test_risk_dial_falls_back_when_it_cannot_solve(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_WILDCARD_RISK_TARGETED", "1")
    s = _Sig(); s.sl_margin_pct = 0.0
    assert rt._entry_margin(s, 140.0) == pytest.approx(0.12 * 140.0)


def test_blocked_candidate_is_logged_once_per_episode():
    """REGRESSION. The 15-min scan re-logged the same blocked candidate every
    pass — up to 96 duplicate rows for one signal at the 24h clock. The
    slot_occupied population IS the evidence base for any slot decision."""
    import inspect

    src = inspect.getsource(FuturesRuntime._maybe_scan_wildcard)
    assert "_wildcard_block_logged" in src, "blocked candidates are re-logged every scan"
    assert "self._wildcard_block_logged.clear()" in src, "episode never resets"


def test_funnel_separates_the_capacity_terms():
    """symbol_open is a capacity cost that RISES with hold length; major_excl is
    a permanent universe choice. Collapsed together they were indistinguishable."""
    import inspect

    src = inspect.getsource(FuturesRuntime._maybe_scan_wildcard)
    for k in ('"symbol_open"', '"major_excl"', '"non_crypto"', "scan_capped"):
        assert k in src, f"funnel does not count {k}"


# --------------------------------------------------------------------------
# reporting fixes: sniper dashboard, risk$, record notification, status tidy
# --------------------------------------------------------------------------

def test_close_record_carries_the_dollar_value_of_one_r():
    """A bare R invited a $0.03 sniper '+1.32R' to impersonate a $2.66-R
    wildcard win. risk_usdt is the per-trade denomination."""
    import inspect

    src = inspect.getsource(FuturesRuntime._close_history_trade)
    assert '"risk_usdt"' in src
    fs = inspect.getsource(FuturesRuntime._append_feature_store)
    assert '"risk_usdt"' in fs


def test_record_peak_notification_fires_once_and_changes_no_orders(rt, monkeypatch):
    """🏆 is INFORMATION ONLY: acting on it was measured at ~-$38/yr with TP
    completions collapsing 17 -> 2 (the record-conditioned retention study,
    2026-08-08). The ping goes to the human; the trail level does not move."""
    sent = []
    monkeypatch.setattr(rt, "_notify", lambda msg, **k: sent.append(msg))
    monkeypatch.setattr(rt, "_best_weekly_close_usd", lambda: 1.33)
    monkeypatch.setattr(rt, "_save_state", lambda: None)
    p = _pos()
    rt._maybe_record_peak_notify(p, 1.46)          # peak$ ~ 1.46 x $10 > $1.33
    assert len(sent) == 1 and "🏆" in sent[0]
    assert p.metadata.get("record_peak_notified") == 1.0
    rt._maybe_record_peak_notify(p, 2.0)           # second ratchet: silent
    assert len(sent) == 1


def test_record_peak_notification_respects_the_weekly_best(rt, monkeypatch):
    sent = []
    monkeypatch.setattr(rt, "_notify", lambda msg, **k: sent.append(msg))
    monkeypatch.setattr(rt, "_best_weekly_close_usd", lambda: 10_000.0)
    p = _pos()
    rt._maybe_record_peak_notify(p, 1.46)
    assert not sent and "record_peak_notified" not in p.metadata


def test_status_renders_no_per_candidate_sniper_rows():
    """2026-08-09: ALL per-candidate rows are gone, open ones included. They
    were counterfactuals drawn like real positions — side, leverage, entry —
    directly above "No open positions."."""
    import inspect

    src = inspect.getsource(FuturesRuntime._sniper_shadow_status_lines)
    assert "_sniper_row_lines" not in src, "position-shaped shadow rows are back"
    assert not hasattr(FuturesRuntime, "_sniper_row_lines"), "dead renderer resurrected"
    assert "_sniper_study_line" in src, "live variant has no study dashboard"


def test_status_system_lines_are_merged():
    import inspect

    src = inspect.getsource(FuturesRuntime._build_status_message)
    assert "Sys: calib" in src, "calibration/overlay/entries no longer merged"
    assert '"Calibration: ' not in src


# --------------------------------------------------------------------------
# sleeve tagging (trial-7 amendment, 2026-08-09)
# --------------------------------------------------------------------------

def _snipe(**md):
    p = _pos()
    p.metadata = {"wildcard": 1.0, "pmt_stop_first": 1.0, "sniper": 1.0,
                  "sl_margin_pct": 4.79, **md}
    p.leverage = 13
    return p


def test_sniper_positions_are_tagged_at_open():
    """ROOT CAUSE. The shared entry primitive stamped wildcard=1.0 on every
    convex position with a branch only for SQUEEZE, so a sniper trade was
    indistinguishable from a wildcard one."""
    import inspect

    src = inspect.getsource(FuturesRuntime._open_wildcard_position)
    assert 'kind == "SNIPER"' in src and 'metadata["sniper"]' in src


def test_sleeve_kind_resolves_specific_markers_before_the_shared_flag(rt):
    assert rt._sleeve_kind(_snipe()) == "SNIPER"
    p = _pos(); p.metadata = {"wildcard": 1.0, "squeeze": 1.0}
    assert rt._sleeve_kind(p) == "SQUEEZE"
    assert rt._sleeve_kind(_pos()) == "WILDCARD"
    p2 = _pos(); p2.metadata = {}
    assert rt._sleeve_kind(p2) == "PMT"


def test_sniper_does_not_consume_a_wildcard_slot(rt):
    """It did: _convex_open_count counted anything wildcard-flagged and
    non-squeeze, so a sniper position occupied one of trial 7's two slots."""
    rt.open_positions = {"A_USDT": _snipe(), "B_USDT": _pos()}
    assert rt._convex_open_count("WILDCARD") == 1
    assert rt._convex_open_count("SNIPER") == 1
    assert rt._convex_open_count("SQUEEZE") == 0


def test_convex_exits_do_not_apply_to_sniper_positions(rt, monkeypatch):
    """The 24h clock and retention trail were designed and priced for a ~16%
    stop, not the sniper's 0.37%."""
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    assert rt._is_wildcard_convex(_pos()) is True
    assert rt._is_wildcard_convex(_snipe()) is False
    sq = _pos(); sq.metadata = {"wildcard": 1.0, "squeeze": 1.0}
    assert rt._is_wildcard_convex(sq) is True     # squeeze keeps the convex stack


def test_retention_floor_never_sits_below_the_sleeve_cost_drag(rt, monkeypatch):
    """AVAX_USDT 2026-08-09: peaked +1.68R, floor 0.30x = +0.50R gross, closed
    -0.01R net — because cost drag on a 0.37% stop is 0.52R per round trip.
    A floor below breakeven banks a loss by construction."""
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    closed = []
    monkeypatch.setattr(rt, "_close_position_for_exit",
                        lambda p, **k: closed.append(k.get("reason")) or True)
    # wildcard geometry: 16.4% stop -> cost drag ~0.012R -> floor is the 0.30 rule
    p = _pos()
    p.metadata["convex_peak_r"] = 2.0
    assert rt._convex_runner_trail_exit(p, 106.5) is False      # +0.65R > 0.60 floor
    assert rt._convex_runner_trail_exit(p, 105.0) is True       # +0.50R < 0.60 floor
    assert closed == ["CONVEX_RETENTION_TRAIL"]


def test_entry_message_names_the_sleeve_that_opened_it(rt):
    assert "🎯" in rt._entry_message(_snipe())
    assert "Meteorite" not in rt._entry_message(_snipe())
    assert "🎲" in rt._entry_message(_pos())


def test_entry_message_does_not_promise_a_partial_bank_on_convex(rt, monkeypatch):
    monkeypatch.setenv("FUTURES_PARTIAL_BANK_ENABLED", "1")
    assert "Bank 50%" not in rt._entry_message(_snipe())
    assert "Bank 50%" not in rt._entry_message(_pos())


def test_feature_store_row_carries_sleeve_and_exit_rule():
    """Correction: both were written to the trade record but never reached the
    feature store — every row read sleeve=None."""
    import inspect

    src = inspect.getsource(FuturesRuntime._append_feature_store)
    assert '"sleeve"' in src and '"exit_rule"' in src


def test_sniper_is_exit_governed_by_its_own_stop_and_tp_only(rt, monkeypatch):
    """Excluding SNIPER from the convex stack must not hand it to the PMT lock
    stack instead: micro-lock arms at 2.0% MARGIN, which on the sniper's 4.8%
    stop is +0.42R — still under its 0.52R round-trip cost."""
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    monkeypatch.setenv("FUTURES_MICRO_LOCK_ENABLED", "1")
    monkeypatch.setenv("USE_FUTURES_PROFIT_LOCK", "1")
    snipe = _snipe()
    assert rt._skips_discretionary_locks(snipe) is True
    assert rt._micro_lock_exit(snipe, 101.0) is False
    assert rt._profit_lock_exit(snipe, 101.0) is False
    # ...and it is NOT convex either: no 24h clock, no retention trail.
    assert rt._is_wildcard_convex(snipe) is False


def test_pmt_positions_still_reach_the_lock_stack(rt, monkeypatch):
    """Guard against the carve-out widening into 'nobody gets locks'."""
    monkeypatch.setenv("FUTURES_WILDCARD_CONVEX_EXIT_ENABLED", "1")
    p = _pos()
    p.metadata = {}
    assert rt._skips_discretionary_locks(p) is False


# --------------------------------------------------------------------------
# /status rewrite (2026-08-09, owner review)
# --------------------------------------------------------------------------

def test_status_never_prints_the_dead_signal_line(rt):
    """"Signal: none" was a constant. The only surface the owner reads (/status)
    passed no signal at all, and the signal it would have passed comes from the
    PMT scan, which returns None while FUTURES_ENTRY_MIN_SCORE>=999. It read
    "none" whether the bot had just vetoed a 24% mover or seen nothing."""
    import inspect

    src = inspect.getsource(FuturesRuntime._build_status_message)
    assert "self._signal_line(signal)" in src
    assert "if signal:" in src, "signal line must be gated on a signal existing"


def test_status_shows_the_wildcard_funnel(rt):
    rt._last_wildcard_scan = {
        "at": time.time() - 180, "funnel": {"in_band": 674}, "scanned": 24,
        "cands": 0, "hist": {"roc_below_min": 17, "no_pullback_resume": 4},
        "best": None, "shorts_blocked": 0,
    }
    text = "\n".join(rt._wildcard_status_lines())
    assert "674 in-band" in text and "24 scanned" in text
    assert "roc_below_min x17" in text


def test_status_hides_the_blocker_histogram_once_a_signal_exists(rt):
    rt._last_wildcard_scan = {
        "at": time.time(), "funnel": {"in_band": 674}, "scanned": 22, "cands": 1,
        "hist": {"roc_below_min": 18},
        "best": {"symbol": "BTW_USDT", "side": "LONG", "roc": 0.243, "rsi": 81.0},
        "shorts_blocked": 0,
    }
    text = "\n".join(rt._wildcard_status_lines())
    assert "roc_below_min" not in text, "blockers are noise once something fired"
    assert "BTW_USDT" in text and "+24.3%/3h" in text


def test_status_surfaces_the_last_rejected_wildcard_candidate(rt, tmp_path, monkeypatch):
    """A 24.3% mover was found and vetoed 15 minutes before a /status that said
    "Signal: none". slot_occupied (11 of 23 all-time) is the sleeve's real
    bottleneck and had no surface at all."""
    led = tmp_path / "shadow.jsonl"
    led.write_text(json.dumps({
        "ts": time.time() - 2820, "sleeve": "WILDCARD", "symbol": "BTW_USDT",
        "side": "LONG", "roc_pct": 0.2428,
        "reject_reason": "veto:crowded_longs(funding=0.150%)",
    }) + "\n", encoding="utf-8")
    monkeypatch.setattr(rt, "_shadow_ledger_path", lambda: str(led))
    line = rt._last_wildcard_reject()
    assert "BTW_USDT" in line and "+24.3%/3h" in line and "47m ago" in line
    # Plain English, but the number that fired the gate survives.
    assert "crowded longs (funding 0.150%)" in line
    assert "veto:" not in line and "=" not in line


def test_reject_labels_fall_back_to_the_raw_reason(rt):
    assert rt._reject_label("slot_occupied") == "no free slot"
    assert rt._reject_label("veto:ref_not_listed") == "not listed on the reference exchange"
    assert rt._reject_label("veto:move_not_corroborated(mexc=12.7%,ref=-0.5%)") == (
        "move not confirmed on the reference exchange (mexc 12.7%, ref -0.5%)")
    assert rt._reject_label("brand_new_gate") == "brand_new_gate"
    assert rt._reject_label(None) == "unknown"


def test_trial_counter_is_scoped_to_the_trial_not_the_200_row_cap(rt, monkeypatch):
    """_save_state persists trade_history[-200:], so "Trades: 200" was a
    saturated window pinned forever, not a count."""
    from futuresbot import learning_digest as ld

    monkeypatch.setattr(ld, "TRIAL_START", 1000.0)
    monkeypatch.setattr(rt, "_feature_rows_cached", lambda: [
        {"ts": 900.0, "kind": "WILDCARD", "r_multiple": 9.0, "pnl_usdt": 99.0},   # pre-trial
        {"ts": 1500.0, "kind": "WILDCARD", "r_multiple": 0.42, "pnl_usdt": 1.168},
        {"ts": 1600.0, "kind": "WILDCARD", "r_multiple": 0.53, "pnl_usdt": 0.646},
        {"ts": 1700.0, "kind": "SNIPER", "r_multiple": -1.45, "pnl_usdt": -0.096},  # other sleeve
    ])
    line = rt._trial_progress_line()
    assert "<b>2</b>/30 WC closes" in line
    assert "netR <b>+0.95</b>" in line and "net <b>$+1.81</b>" in line


def test_trial_start_is_env_overridable_and_no_longer_stale(monkeypatch):
    """It was hardcoded to trial 4 (2026-07-13) and never moved through trials
    5, 6, 6.5 and 7 — the weekly digest counted four trials as one.

    Tests the resolver, not the module constant: reloading learning_digest
    mid-suite pollutes every module holding a reference to it."""
    from futuresbot.learning_digest import _trial_start

    monkeypatch.setenv("FUTURES_TRIAL_START_TS", "1786130520")
    assert _trial_start() == 1786130520.0
    monkeypatch.setenv("FUTURES_TRIAL_START_TS", "not-a-number")
    monkeypatch.delenv("FUTURES_TRIAL_START_TS")
    assert _trial_start() == datetime(2026, 8, 7, 19, 22, tzinfo=timezone.utc).timestamp()


def test_status_does_not_count_slots_for_a_disabled_sleeve(rt, monkeypatch):
    """It printed "SQ: 0/1" while FUTURES_SQUEEZE_ENABLED=0 — a slot counter for
    a sleeve that cannot open a position — and had no counter at all for the
    sniper, the one sleeve holding real money."""
    import inspect

    src = inspect.getsource(FuturesRuntime._build_status_message)
    assert "if squeeze_enabled():" in src
    assert "sniper_enabled() and not sniper_shadow_only()" in src
    assert "_sleeve_kind(p) == 'PMT'" in src, "PMT count must not use the convex flag"


def test_status_states_decommissioned_sleeves_exactly_once(rt):
    import inspect

    src = inspect.getsource(FuturesRuntime._build_status_message)
    assert src.count("PMT ⛔ decommissioned") == 0, "the standalone PMT line is gone"
    assert "off = [n for n, on in" in src


# --------------------------------------------------------------------------
# trial 8: the majors band (2026-08-09)
# --------------------------------------------------------------------------

def _tick(sym, turn, move=0.0):
    return {"symbol": sym, "amount24": turn, "riseFallRate": move}


def test_turnover_ranking_no_longer_promotes_a_symbol_for_moving(rt, monkeypatch):
    """THE DEFECT. Turnover is CREATED by the move, so ranking on raw 24h
    turnover excluded symbols in proportion to how hard they had just run.
    TUT_USDT sat at rank 12 with $76M *because* it was +19% that day, while
    every genuine major in the same band moved under 2%."""
    ticks = [_tick("BTC_USDT", 1_700_000_000), _tick("ETH_USDT", 1_000_000_000),
             _tick("SPIKE_USDT", 76_000_000, 0.19), _tick("CALM_USDT", 40_000_000)]
    # SPIKE traded 10x its baseline today; everyone else is at baseline
    monkeypatch.setattr(rt, "_turnover_deflator",
                        lambda sym: 0.1 if sym == "SPIKE_USDT" else 1.0)
    majors = rt._major_symbols(ticks, 3)
    assert "SPIKE_USDT" not in majors, "a one-day spike still promotes a small cap"
    assert {"BTC_USDT", "ETH_USDT", "CALM_USDT"} == majors


def test_the_deflator_can_only_demote_never_promote(rt, monkeypatch):
    """One-sided by construction, because the distortion is. An unclamped ratio
    ranked SOXL — a tokenised ETF whose weekend volume goes to zero, deflator
    16.98 — above every crypto major, and made BNB tradeable."""
    import inspect

    src = inspect.getsource(FuturesRuntime._turnover_deflator)
    assert "min(1.0, med / last)" in src


def test_majors_ranking_is_crypto_only(rt, monkeypatch):
    """Six of the raw top 30 were tokenised equities, so exclusion slots were
    spent on symbols the scan drops anyway — "top-30" never meant top-30
    crypto."""
    monkeypatch.setattr(rt, "_turnover_deflator", lambda sym: 1.0)
    ticks = [_tick("SKHYNIXSTOCK_USDT", 900_000_000), _tick("XAU_USDT", 800_000_000),
             _tick("BTC_USDT", 700_000_000), _tick("ALT_USDT", 1_000_000)]
    assert rt._major_symbols(ticks, 2) == {"BTC_USDT", "ALT_USDT"}


def test_synthetic_commodity_perps_cannot_be_scanned(rt):
    """XAU_USDT passes universe._is_crypto_usdt_symbol and produced trial 4's
    worst trade (-3.79R in 60s on a 0.28% stop). Once it stopped occupying an
    exclusion slot it would have become scannable."""
    assert rt._is_tradeable_crypto("XAU_USDT") is False
    assert rt._is_tradeable_crypto("SOXL_USDT") is False
    assert rt._is_tradeable_crypto("JP225_USDT") is False
    assert rt._is_tradeable_crypto("QBTSSTOCK_USDT") is False
    assert rt._is_tradeable_crypto("BTW_USDT") is True
    assert rt._is_tradeable_crypto("TUT_USDT") is True


def test_deflator_fails_open_to_the_old_behaviour(rt, monkeypatch):
    """A kline failure must not silently reclassify the whole universe."""
    class _Boom:
        def get_klines(self, *a, **k):
            raise RuntimeError("api down")

    rt.client = _Boom()
    rt._turnover_baseline = {}
    assert rt._turnover_deflator("X_USDT") == 1.0


def test_the_exclusion_count_holds_the_treatment_constant(rt):
    """Ranking crypto-only at 30 would have WIDENED the exclusion by the ~6
    slots the tokenised equities used to occupy, silently making BMT_USDT
    (+35% that day, raw rank 38) untradeable. 24 preserves the effective
    breadth; the ranking method is what changed, not the count."""
    import inspect

    src = inspect.getsource(FuturesRuntime._maybe_scan_wildcard)
    assert 'FUTURES_WILDCARD_EXCLUDE_TOP_TURNOVER", 24.0' in src


# --------------------------------------------------------------------------
# trial 8: the 24h pre-filter, and the missed-opportunity check
# --------------------------------------------------------------------------

def test_range_prefilter_cannot_hide_a_candidate_the_detector_would_take(rt):
    """The screen used |24h CHANGE| while the detector triggers on |3h ROC| —
    a different quantity. A symbol that ran +30% in 3h and gave it back showed
    ~0% on the day and never reached the detector.

    The 24h RANGE is a mathematical upper bound on the trailing 3h move (both
    ends of the 3h window lie inside the 24h window), so screening on it is
    LOSSLESS: nothing that could fire the trigger can be filtered out."""
    spiked = {"symbol": "S_USDT", "riseFallRate": 0.004,      # flat on the day
              "high24Price": 130.0, "lower24Price": 100.0}    # ...but +30% range
    assert rt._range_24h(spiked) == 0.30
    assert abs(float(spiked["riseFallRate"])) < 0.03          # old screen: dropped
    assert rt._range_24h(spiked) >= 0.08                      # new screen: kept


def test_range_is_zero_on_a_malformed_ticker(rt):
    assert rt._range_24h({}) == 0.0
    assert rt._range_24h({"high24Price": 100.0, "lower24Price": 0.0}) == 0.0
    assert rt._range_24h({"high24Price": 1.0, "lower24Price": 2.0}) == 0.0
    assert rt._range_24h({"high24Price": "x", "lower24Price": "y"}) == 0.0


def test_prefilter_threshold_is_derived_from_the_trigger_not_set_apart(rt):
    """The two drifted apart once and cost a day of signals; the default now
    comes FROM the trigger so it cannot happen silently again."""
    import inspect

    src = inspect.getsource(FuturesRuntime._maybe_scan_wildcard)
    assert 'FUTURES_WILDCARD_MIN_24H_RANGE", min_roc' in src
    assert "FUTURES_WILDCARD_RANGE_PREFILTER" in src, "no rollback path"


def test_missed_check_names_the_reason_for_every_top_mover(rt, monkeypatch):
    """2026-08-09: eight of the day's ten biggest gainers went untaken and
    working out why took a manual pass over four data sources."""
    ticks = [
        {"symbol": "TRADED_USDT", "riseFallRate": 0.5, "amount24": 9e6,
         "high24Price": 150.0, "lower24Price": 100.0},
        {"symbol": "BLOCKED_USDT", "riseFallRate": 0.4, "amount24": 9e6,
         "high24Price": 140.0, "lower24Price": 100.0},
        {"symbol": "MAJOR_USDT", "riseFallRate": 0.3, "amount24": 9e6,
         "high24Price": 135.0, "lower24Price": 100.0},
        {"symbol": "THIN_USDT", "riseFallRate": 0.2, "amount24": 1e5,
         "high24Price": 130.0, "lower24Price": 100.0},
    ]
    rt.client = MagicMock()
    rt.client.get_all_tickers.return_value = ticks
    monkeypatch.setattr(rt, "_major_symbols", lambda t, n: {"MAJOR_USDT"})
    monkeypatch.setattr(rt, "_feature_rows_cached",
                        lambda: [{"symbol": "TRADED_USDT", "ts": time.time()}])
    monkeypatch.setattr(rt, "_replay_verdict", lambda sym, roc: "no signal")
    import futuresbot.shadow_ledger as _sl
    monkeypatch.setattr(_sl, "load_rows", lambda p: [
        {"symbol": "BLOCKED_USDT", "ts": time.time(), "reject_reason": "slot_occupied"}])
    monkeypatch.setattr(rt, "_shadow_ledger_path", lambda: "x")

    text = "\n".join(rt._missed_opportunity_lines())
    assert "TRADED_USDT" in text and "traded" in text
    assert "no free slot" in text                      # plain English, not the enum
    assert "MAJOR_USDT" in text and "majors band" in text
    assert "THIN_USDT" in text and "floor" in text


def test_missed_check_never_breaks_the_digest(rt):
    rt.client = MagicMock()
    rt.client.get_all_tickers.side_effect = RuntimeError("api down")
    assert rt._missed_opportunity_lines() == []


def test_replay_verdict_only_runs_the_detector_on_trigger_bars(rt):
    """96 full detector calls per symbol per day is not worth paying when one
    float comparison decides ~70% of them."""
    import inspect

    src = inspect.getsource(FuturesRuntime._replay_verdict)
    assert "< min_roc" in src and "continue" in src
    assert "detect_wildcard_signal" in src


def test_digest_carries_the_missed_check_when_supplied():
    from futuresbot.learning_digest import build_learning_digest

    msg = build_learning_digest([], [], missed_lines=["🔎 x", "• Y_USDT — traded"])
    assert "Y_USDT" in msg
    assert "🔎 x" in msg
    assert "Y_USDT" not in build_learning_digest([], [])


def test_trial8_records_which_old_gate_each_candidate_sat_behind(rt):
    """Trial 8 bundles two universe changes. Rather than run two 90-day trials,
    every candidate records which side of each OLD gate it was on, so the
    result can be split by change after the fact instead of being ambiguous."""
    import inspect

    src = inspect.getsource(FuturesRuntime._maybe_scan_wildcard)
    assert "legacy_majors = self._top_turnover_symbols(tickers, 30)" in src
    assert '"legacy_major": bool(sym in legacy_majors)' in src
    assert '"legacy_prefilter_ok"' in src

    store = inspect.getsource(FuturesRuntime._append_feature_store)
    assert '"legacy_major": md.get("legacy_major")' in store
    assert '"legacy_prefilter_ok": md.get("legacy_prefilter_ok")' in store

    shadow = inspect.getsource(FuturesRuntime._shadow_log_untaken)
    assert "self._wildcard_attribution.get" in shadow


def test_attribution_survives_a_symbol_the_scan_never_saw(rt):
    """A signal from a path that did not populate the map must not raise."""
    rt._wildcard_attribution = {}
    from futuresbot.shadow_ledger import candidate_row

    class _Sig:
        symbol = "X_USDT"; side = "LONG"; entry_price = 1.0; sl_price = 0.9
        tp_price = 1.5; leverage = 5; sl_margin_pct = 10.0; roc_pct = 0.09; rsi = 60.0

    row = candidate_row(_Sig(), sleeve="WILDCARD", reject_reason="x", extra={})
    assert row["symbol"] == "X_USDT"
    assert "legacy_major" not in row
    tagged = candidate_row(_Sig(), sleeve="WILDCARD", reject_reason="x",
                           extra={"legacy_major": True, "legacy_prefilter_ok": False})
    assert tagged["legacy_major"] is True and tagged["symbol"] == "X_USDT"
