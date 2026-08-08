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


def test_status_drops_resolved_sniper_samples_keeps_open_ones():
    """Status tidy: resolved sample rows were 2 lines of stale history per
    variant and once rendered the same DOGE candidate twice."""
    import inspect

    src = inspect.getsource(FuturesRuntime._sniper_shadow_status_lines)
    assert 'r.get("outcome") is None' in src, "resolved rows are back in /status"
    assert "_sniper_study_line" in src, "live variant has no study dashboard"


def test_status_system_lines_are_merged():
    import inspect

    src = inspect.getsource(FuturesRuntime._build_status_message)
    assert "Sys: calib" in src, "calibration/overlay/entries no longer merged"
    assert '"Calibration: ' not in src
