"""Alt-band breadth telemetry: recorded at the scan instant, never read as a gate.

2026-09-09. The four-week segmentation found the bot's OWN scan universe is the
only thing that separates the tape - BTC price does not, and BTC's daily
MA20/MA50 never crossed inside the window while alt breadth halved in a single
day. But the version that could matter is breadth AT THE SCAN INSTANT, and it
cannot be backtested because no intraday breadth history exists. This creates it.

The tests are almost entirely about what it must NOT do. It must not change a
single entry decision, must not raise into a scan, and must not silently pass off
a stale snapshot as current state - which is why `breadth_age_s` is recorded and
why an hour-old capture is dropped rather than stamped.

The one substantive correctness test is the universe: breadth must measure the
MARKET, so it must include symbols the funnel skips because they are already
held. Folding this into the funnel loop would have silently excluded exactly the
symbols the sleeve is most active in.
"""
from __future__ import annotations

import math

import pytest

from futuresbot.runtime import FuturesRuntime


def _rt(monkeypatch, *, crypto=True):
    r = FuturesRuntime.__new__(FuturesRuntime)
    monkeypatch.setattr(FuturesRuntime, "_is_tradeable_crypto",
                        lambda self, sym: crypto and "STOCK" not in sym)
    return r


def _tick(sym, rate, turn=5_000_000.0):
    return {"symbol": sym, "riseFallRate": rate, "amount24": turn}


def _universe(n=40, rate=0.01):
    return [_tick("A%d_USDT" % i, rate) for i in range(n)]


# ---------------------------------------------------------------- the statistic

def test_breadth_is_fraction_up(monkeypatch):
    r = _rt(monkeypatch)
    ticks = [_tick("A%d_USDT" % i, 0.05) for i in range(30)]
    ticks += [_tick("B%d_USDT" % i, -0.05) for i in range(10)]
    out = r._alt_breadth(ticks, set(), 1_000_000.0)
    assert out["breadth_n"] == 40
    assert out["breadth_24h"] == pytest.approx(0.75)


def test_zero_change_is_not_up(monkeypatch):
    """`> 0`, not `>= 0`. A flat symbol is not participation."""
    r = _rt(monkeypatch)
    ticks = [_tick("A%d_USDT" % i, 0.0) for i in range(40)]
    assert r._alt_breadth(ticks, set(), 1_000_000.0)["breadth_24h"] == 0.0


def test_median_not_mean(monkeypatch):
    """One listing pump must not define the tape. Mean here is +0.5; median 0."""
    r = _rt(monkeypatch)
    ticks = [_tick("A%d_USDT" % i, 0.0) for i in range(39)]
    ticks.append(_tick("PUMP_USDT", 20.0))
    out = r._alt_breadth(ticks, set(), 1_000_000.0)
    assert out["alt_med_24h"] == pytest.approx(0.0)
    assert out["breadth_24h"] == pytest.approx(1 / 40)


def test_median_even_sample_averages_middle_pair(monkeypatch):
    r = _rt(monkeypatch)
    ticks = [_tick("A%d_USDT" % i, 0.02) for i in range(20)]
    ticks += [_tick("B%d_USDT" % i, 0.04) for i in range(20)]
    assert r._alt_breadth(ticks, set(), 1_000_000.0)["alt_med_24h"] == pytest.approx(0.03)


def test_dispersion_is_sample_stdev(monkeypatch):
    r = _rt(monkeypatch)
    ticks = [_tick("A%d_USDT" % i, 0.10) for i in range(20)]
    ticks += [_tick("B%d_USDT" % i, -0.10) for i in range(20)]
    out = r._alt_breadth(ticks, set(), 1_000_000.0)
    # mean 0, each deviates 0.10, n-1 denominator over 40 samples
    assert out["alt_disp_24h"] == pytest.approx(math.sqrt(40 * 0.01 / 39), rel=1e-6)


# ---------------------------------------------------------------- the universe

def test_majors_are_excluded(monkeypatch):
    """The sleeve trades the non-major band, so the statistic must too."""
    r = _rt(monkeypatch)
    ticks = _universe(40, 0.01) + [_tick("BTC_USDT", -0.5), _tick("ETH_USDT", -0.5)]
    out = r._alt_breadth(ticks, {"BTC_USDT", "ETH_USDT"}, 1_000_000.0)
    assert out["breadth_n"] == 40
    assert out["breadth_24h"] == 1.0


def test_held_symbols_are_INCLUDED(monkeypatch):
    """THE test. The funnel skips `sym in self.open_positions`, which is right for
    candidate selection and wrong for a market statistic. `_alt_breadth` never
    consults open_positions, so a held symbol still counts toward the tape."""
    r = _rt(monkeypatch)
    r.open_positions = {"A0_USDT": object(), "A1_USDT": object()}
    out = r._alt_breadth(_universe(40, 0.01), set(), 1_000_000.0)
    assert out["breadth_n"] == 40


def test_non_crypto_excluded(monkeypatch):
    r = _rt(monkeypatch)
    ticks = _universe(40, 0.01) + [_tick("SPX500STOCK_USDT", -0.9)]
    assert r._alt_breadth(ticks, set(), 1_000_000.0)["breadth_n"] == 40


def test_non_usdt_excluded(monkeypatch):
    r = _rt(monkeypatch)
    ticks = _universe(40, 0.01) + [_tick("A_USDC", -0.9)]
    assert r._alt_breadth(ticks, set(), 1_000_000.0)["breadth_n"] == 40


def test_turnover_floor_applies(monkeypatch):
    r = _rt(monkeypatch)
    ticks = [_tick("A%d_USDT" % i, 0.01, turn=5_000_000.0) for i in range(25)]
    ticks += [_tick("T%d_USDT" % i, -0.5, turn=1_000.0) for i in range(20)]
    assert r._alt_breadth(ticks, set(), 2_000_000.0)["breadth_n"] == 25


# ---------------------------------------------------------------- refusing to guess

def test_thin_sample_returns_none(monkeypatch):
    """Under 20 symbols the fraction is not a market statistic. Record nothing
    rather than a number a later study would treat as one."""
    r = _rt(monkeypatch)
    assert r._alt_breadth(_universe(19), set(), 1_000_000.0) is None


def test_boundary_at_twenty(monkeypatch):
    r = _rt(monkeypatch)
    assert r._alt_breadth(_universe(20), set(), 1_000_000.0) is not None


def test_empty_and_none_are_safe(monkeypatch):
    r = _rt(monkeypatch)
    assert r._alt_breadth([], set(), 1_000_000.0) is None
    assert r._alt_breadth(None, set(), 1_000_000.0) is None


def test_malformed_rows_are_skipped_not_fatal(monkeypatch):
    r = _rt(monkeypatch)
    ticks = _universe(40, 0.01)
    ticks += [{"symbol": "BAD_USDT", "riseFallRate": "x", "amount24": "y"},
              {"symbol": "NAN_USDT", "riseFallRate": float("nan"), "amount24": 5e6},
              {"symbol": None}]
    out = r._alt_breadth(ticks, set(), 1_000_000.0)
    assert out["breadth_n"] == 40


def test_missing_fields_default_to_zero_rate(monkeypatch):
    """A present, liquid symbol with no rate counts as not-up rather than dropped."""
    r = _rt(monkeypatch)
    ticks = _universe(39, 0.01) + [{"symbol": "Z_USDT", "amount24": 5e6}]
    out = r._alt_breadth(ticks, set(), 1_000_000.0)
    assert out["breadth_n"] == 40
    assert out["breadth_24h"] == pytest.approx(39 / 40)


# ---------------------------------------------------------------- shape contract

def test_reports_exactly_the_four_fields(monkeypatch):
    r = _rt(monkeypatch)
    out = r._alt_breadth(_universe(40), set(), 1_000_000.0)
    assert set(out) == {"breadth_24h", "breadth_n", "alt_med_24h", "alt_disp_24h"}


def test_gates_nothing(monkeypatch):
    """The method reads tickers and returns a dict. It must not touch the
    candidate list, the funnel, or any env flag - if it ever starts gating,
    this test is the place that should have to change first."""
    import inspect
    import textwrap
    # Strip the docstring: it *names* open_positions to explain why the method
    # deliberately does not consult it, so matching raw source would fail on the
    # very comment that documents the guarantee.
    tree = __import__("ast").parse(textwrap.dedent(
        inspect.getsource(FuturesRuntime._alt_breadth)))
    fn = tree.body[0]
    if (fn.body and isinstance(fn.body[0], __import__("ast").Expr)
            and isinstance(fn.body[0].value, __import__("ast").Constant)):
        fn.body = fn.body[1:]
    body = __import__("ast").dump(fn)
    for forbidden in ("_shadow_log_untaken", "_env_float", "_flag", "cands",
                      "open_positions", "_rej"):
        assert forbidden not in body, forbidden
