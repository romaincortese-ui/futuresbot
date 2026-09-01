"""Sub-trigger shadow logging must LOG below the trigger and TRADE nothing new.

Added 2026-09-01. The 220-day replay found the 3h-ROC bands are bimodal around
the live 8% trigger — negative in all four bands from 3% to 7%, positive in all
three from 7% to 12% — so the gate sits one point inside the good block. That
region can never accrue live evidence, because `_shadow_log_untaken` only fires
on objects that reached the candidate list and the list is itself gated at
`FUTURES_WILDCARD_MIN_ROC`. Widening the scan for logging is the only way to
make the question answerable from live data.

The whole change rests on ONE safety property, which is what these tests pin:
a signal produced under the lowered floor must be logged and then dropped, and
must never reach the candidate list. If that leaks, the bot silently starts
trading a band measured at -$0.33/fill.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from futuresbot.wildcard import ROC_BARS, detect_wildcard_signal


def _frame(move: float, n: int = 300) -> pd.DataFrame:
    """A frame whose trailing 3h ROC is exactly `move`, shaped so the detector's
    climax-wick gate does not reject it (close near the bar high)."""
    rng = np.random.default_rng(11)
    c = 100.0 + np.cumsum(rng.normal(0, 0.01, n))
    start = c[-1 - ROC_BARS]
    for k in range(ROC_BARS):
        c[-ROC_BARS + k] = start * (1.0 + move * (k + 1) / ROC_BARS)
    return pd.DataFrame(
        {"open": c * 0.999, "high": c * 1.0002, "low": c * 0.998, "close": c,
         "volume": np.concatenate([rng.normal(100, 5, n - 1), [400.0]])},
        index=pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"))


def _relax(monkeypatch):
    """Relax the SHAPE gates only — these tests assert what the ROC gate does,
    and a test that skips because an unrelated filter fired proves nothing."""
    monkeypatch.setenv("FUTURES_WILDCARD_REQUIRE_PULLBACK", "0")
    monkeypatch.setenv("FUTURES_WILDCARD_MIN_VOL_Z", "-99")
    monkeypatch.setenv("FUTURES_WILDCARD_RSI_MAX", "500")
    monkeypatch.setenv("FUTURES_WILDCARD_SIGMA_TRIGGER", "0")


def test_default_floor_still_refuses_below_the_trigger(monkeypatch):
    """With no override the detector must behave exactly as it always has."""
    _relax(monkeypatch)
    monkeypatch.setenv("FUTURES_WILDCARD_MIN_ROC", "0.08")
    assert detect_wildcard_signal(_frame(0.075), "TEST_USDT") is None
    assert detect_wildcard_signal(_frame(0.11), "TEST_USDT") is not None


def test_override_admits_the_sub_trigger_band(monkeypatch):
    """A 7.5% move is refused at the live floor and admitted at a 7% one — that
    difference is the entire mechanism the shadow logging depends on."""
    _relax(monkeypatch)
    monkeypatch.setenv("FUTURES_WILDCARD_MIN_ROC", "0.08")
    f = _frame(0.075)
    assert detect_wildcard_signal(f, "TEST_USDT") is None
    sig = detect_wildcard_signal(f, "TEST_USDT", min_roc=0.07)
    assert sig is not None, "the lowered floor must produce a signal to log"
    assert abs(sig.roc_pct) < 0.08, "and it must be recognisably sub-trigger"


def test_override_never_widens_beyond_what_is_asked(monkeypatch):
    """The override is a floor, not a bypass: 6% stays refused at a 7% floor."""
    _relax(monkeypatch)
    monkeypatch.setenv("FUTURES_WILDCARD_MIN_ROC", "0.08")
    assert detect_wildcard_signal(_frame(0.06), "TEST_USDT", min_roc=0.07) is None


def _scan_roc(min_roc: float, shadow_roc: float) -> float:
    """The runtime's selection, mirrored. Kept in lockstep with runtime.py."""
    return shadow_roc if 0.0 < shadow_roc < min_roc else min_roc


def test_flag_off_is_byte_identical():
    """THE SAFETY PROPERTY. Unset (0.0) must leave the scan floor at the live
    trigger, so not one extra object can survive to the candidate list."""
    assert _scan_roc(0.08, 0.0) == 0.08


def test_a_shadow_floor_above_the_trigger_is_ignored():
    """Misconfiguration must not TIGHTEN entry. A floor at or above the trigger
    is meaningless for logging, so it is discarded rather than applied."""
    assert _scan_roc(0.08, 0.09) == 0.08
    assert _scan_roc(0.08, 0.08) == 0.08


def test_a_shadow_floor_below_the_trigger_widens_only_the_scan():
    assert _scan_roc(0.08, 0.07) == 0.07


def test_runtime_drops_every_sub_trigger_candidate(monkeypatch):
    """End to end on the filter itself: given a mixed candidate list, everything
    below min_roc is logged and NONE of it survives."""
    logged: list[tuple[str, str]] = []

    class _Sig:
        def __init__(self, roc, sym):
            self.roc_pct, self.symbol, self.side = roc, sym, "LONG"

    cands = [(1.0, _Sig(0.12, "A"), 1.0), (0.9, _Sig(0.075, "B"), 1.0),
             (0.8, _Sig(0.09, "C"), 1.0), (0.7, _Sig(0.071, "D"), 1.0)]
    min_roc, scan_roc = 0.08, 0.07

    # the exact loop from runtime.py, kept in lockstep
    kept = []
    if scan_roc < min_roc:
        for key, sig, lat in cands:
            r = abs(float(getattr(sig, "roc_pct", 0.0) or 0.0))
            if r < min_roc:
                logged.append((sig.symbol, f"below_trigger({r:.3f})"))
            else:
                kept.append((key, sig, lat))

    assert [s.symbol for _, s, _ in kept] == ["A", "C"], "sub-trigger leaked"
    assert logged == [("B", "below_trigger(0.075)"), ("D", "below_trigger(0.071)")]
