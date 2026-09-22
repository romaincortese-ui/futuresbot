"""The post-rally TREND target cap (wc/REGIME, pre-registered 2026-09-22).

Flagged bars have reached the 3R target 0 times in 126 fills across three eras against
6.2% elsewhere, while reaching 1R slightly MORE often - so the cap trims the target and
must leave the stop, and therefore 1R and every R-denominated rule, untouched.

The flag is read on COMPLETED 15m closes because that is the frame the +$5.85/mo was
measured on; an hourly frame, or one that includes the forming bar, is a different flag
(wc/TPCAP release gate, fixes 1 and 1b).
"""
import inspect
import time
from unittest.mock import MagicMock

import pandas as pd
import pytest

from futuresbot.runtime import ENTRY_GATE_KEYS, FuturesRuntime

BARS = 700


def _frame(closes, *, forming=False):
    """A 15m frame whose last bar is complete unless `forming` is set."""
    now = time.time()
    last_open = (int(now) // 900) * 900 - (0 if forming else 900)
    stamps = [last_open - 900 * (len(closes) - 1 - i) for i in range(len(closes))]
    return pd.DataFrame({"close": closes},
                        index=pd.to_datetime(stamps, unit="s", utc=True))


def _rt(closes, *, forming=False):
    rt = object.__new__(FuturesRuntime)
    rt.client = MagicMock()
    rt.client.get_klines.return_value = _frame(closes, forming=forming)
    rt._env_float = lambda name, default=0.0: {"FUTURES_TREND_FLAGGED_TP_R": 1.0}.get(name, default)
    return rt


def _series(*, roc24=0.0, roc72=0.0, roc168=0.0, dist=0.0, n=BARS):
    """A 15m close series carrying the four quantities the flag reads.

    Anchors sit at -97 (24h), -289 (72h) and -673 (168h); the trailing 7d high is the
    max of the last 672 closes, so the 168h anchor is deliberately outside it."""
    last = 100.0
    closes = [last / (1.0 + roc168)] * n
    closes[-673] = last / (1.0 + roc168)
    closes[-289] = last / (1.0 + roc72)
    closes[-97] = last / (1.0 + roc24)
    closes[-1] = last
    if dist < 0:                       # the 7d high sits `dist` above the last close
        closes[-100] = last / (1.0 + dist)
    return closes


def _sig(side="LONG", entry=100.0, sl=90.0, tp=130.0):
    from futuresbot.wildcard import WildcardSignal
    return WildcardSignal(symbol="ETH_USDT", side=side, entry_price=entry, sl_price=sl,
                          tp_price=tp, leverage=5, roc_pct=0.05, atr_pct=0.03,
                          sl_margin_pct=20.0, tp_margin_pct=60.0, balance_fraction=0.12,
                          rsi=55.0, roc_z=1.0, sl_frac_designed=0.10, calm_ratio=0.3, vol_z=1.5)


STALL = dict(roc24=0.004, roc72=0.07, roc168=0.08, dist=-0.05)


def test_stall_leg_flags_when_the_run_stops():
    rt = _rt(_series(**STALL))
    flagged, fields = rt._btc_exhaustion_flag()
    assert flagged is True
    assert fields["trend_flag"] == 1.0
    assert fields["trend_flag_btc_72h"] == pytest.approx(0.07, abs=1e-3)


def test_stall_leg_does_not_flag_while_the_run_continues():
    rt = _rt(_series(roc24=0.05, roc72=0.07, roc168=0.08, dist=-0.05))
    assert rt._btc_exhaustion_flag()[0] is False


def test_extension_leg_flags_at_the_seven_day_high():
    rt = _rt(_series(roc24=0.03, roc72=0.03, roc168=0.14, dist=0.0))
    flagged, fields = rt._btc_exhaustion_flag()
    assert flagged is True
    assert fields["trend_flag_btc_168h"] == pytest.approx(0.14, abs=1e-3)


def test_quiet_market_does_not_flag():
    rt = _rt(_series(roc24=0.002, roc72=0.01, roc168=0.02, dist=-0.03))
    assert rt._btc_exhaustion_flag()[0] is False


def test_the_forming_bar_is_dropped():
    """A spike in the in-progress bar must not set the 7d high, or the extension leg
    flags itself every time BTC prints a new high tick."""
    closes = _series(roc24=0.002, roc72=0.01, roc168=0.02, dist=-0.03) + [1e6]
    rt = _rt(closes, forming=True)
    flagged, fields = rt._btc_exhaustion_flag()
    assert flagged is False
    assert fields["trend_flag_dist_7d_high"] == pytest.approx(-0.03, abs=1e-3)


def test_flag_fails_soft_and_negative_caches():
    rt = _rt(_series(**STALL))
    rt.client.get_klines.side_effect = RuntimeError("no feed")
    flagged, fields = rt._btc_exhaustion_flag()
    assert flagged is False and fields["trend_flag_error"] == 1.0
    rt._btc_exhaustion_flag()
    assert rt.client.get_klines.call_count == 1      # a dead feed is asked once per TTL


def test_cap_moves_the_target_and_never_the_stop():
    rt = _rt(_series(**STALL))
    sig = _sig(entry=100.0, sl=90.0, tp=130.0)
    out = rt._apply_trend_tp_cap(sig)
    assert out.tp_price == pytest.approx(110.0)      # 1R above entry
    assert out.sl_price == sig.sl_price              # 1R itself is unchanged
    assert out.entry_price == sig.entry_price
    assert rt._last_trend_flag["trend_flag_tp_capped"] == 1.0


def test_tp_margin_pct_tracks_the_capped_target():
    """_classify_exit_kind derives tp_r from tp_margin_pct/sl_margin_pct, so a stale 3R
    value files every completed 1R target as a non-completion."""
    rt = _rt(_series(**STALL))
    out = rt._apply_trend_tp_cap(_sig())
    assert out.tp_margin_pct == pytest.approx(1.0 * out.sl_margin_pct)


def test_the_counterfactual_anchor_is_stamped():
    """Without the original target the pre-registered kill rule reads 0.00 on every
    capped fill and the feature dies whatever its merit."""
    rt = _rt(_series(**STALL))
    rt._apply_trend_tp_cap(_sig(tp=130.0))
    assert rt._last_trend_flag["trend_flag_tp_r_orig"] == pytest.approx(3.0)
    assert rt._last_trend_flag["trend_flag_tp_price_orig"] == pytest.approx(130.0)


def test_cap_respects_the_short_side():
    rt = _rt(_series(**STALL))
    out = rt._apply_trend_tp_cap(_sig(side="SHORT", entry=100.0, sl=110.0, tp=70.0))
    assert out.tp_price == pytest.approx(90.0)


def test_unflagged_entries_keep_the_3r_target_but_are_still_stamped():
    rt = _rt(_series(roc24=0.002, roc72=0.01, roc168=0.02, dist=-0.03))
    sig = _sig()
    out = rt._apply_trend_tp_cap(sig)
    assert out is sig
    assert rt._last_trend_flag["trend_flag"] == 0.0
    assert rt._last_trend_flag["trend_flag_tp_capped"] == 0.0


def test_the_knob_is_the_kill_switch():
    rt = _rt(_series(**STALL))
    rt._env_float = lambda name, default=0.0: 0.0 if name == "FUTURES_TREND_FLAGGED_TP_R" else default
    sig = _sig()
    assert rt._apply_trend_tp_cap(sig) is sig
    assert rt._last_trend_flag == {}
    rt.client.get_klines.assert_not_called()          # off means no API call either


def test_flag_is_cached_for_ten_minutes():
    rt = _rt(_series(**STALL))
    rt._btc_exhaustion_flag()
    rt._btc_exhaustion_flag()
    assert rt.client.get_klines.call_count == 1


def test_flag_fields_reach_the_trade_record_and_only_on_trend():
    for key in ("trend_flag", "trend_flag_btc_72h", "trend_flag_tp_capped", "trend_flag_tp_r",
                "trend_flag_error", "trend_flag_tp_r_orig", "trend_flag_tp_price_orig"):
        assert key in ENTRY_GATE_KEYS
    src = inspect.getsource(FuturesRuntime._open_wildcard_position)
    assert "_last_trend_flag" in src and 'kind).upper() == "TREND"' in src


def test_the_cap_is_applied_on_the_entry_path():
    src = inspect.getsource(FuturesRuntime._maybe_scan_trend)
    assert "_apply_trend_tp_cap" in src
    assert src.index("_apply_trend_tp_cap") < src.index('kind="TREND"')


def test_the_flag_reads_completed_fifteen_minute_bars():
    src = inspect.getsource(FuturesRuntime._btc_exhaustion_flag)
    assert 'interval="Min15"' in src and "_drop_incomplete_klines" in src
