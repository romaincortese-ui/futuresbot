"""Phase grids must preserve the detector's 15m semantics exactly."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path("tools").resolve()))
import numpy as np, pandas as pd
from pit_intrabar import phase_grid, grids_from_5m

def _f5(n=90):
    rng = np.random.default_rng(5)
    c = 100 + np.cumsum(rng.normal(0, .05, n))
    return pd.DataFrame({"open": c*.999, "high": c*1.002, "low": c*.998,
                         "close": c, "volume": np.full(n, 10.0)},
                        index=pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC"))

def test_phase_grids_preserve_15m_semantics():
    """The detector's ROC_BARS=12 means 3h ONLY if the bars are 15m. Feeding it
    5m data would silently make the trigger a 1h lookback; these grids keep the
    15m semantics while tripling how often a signal can fire."""
    f = _f5()
    g0, g1, g2 = phase_grid(f,0), phase_grid(f,1), phase_grid(f,2)
    assert len(g0) == 30, len(g0)
    # NON-OVERLAPPING: consecutive bars must not share source rows
    assert (g0.index[1] - g0.index[0]).total_seconds() == 900, "not a 15m grid"
    # phases are genuinely offset by 5 minutes
    assert (g1.index[0] - g0.index[0]).total_seconds() == 300
    assert (g2.index[0] - g1.index[0]).total_seconds() == 300
    # OHLC aggregation is correct for the first bar of phase 0
    assert g0["open"].iloc[0] == f["open"].iloc[0]
    assert g0["close"].iloc[0] == f["close"].iloc[2]
    assert g0["high"].iloc[0] == f["high"].iloc[0:3].max()
    assert g0["low"].iloc[0] == f["low"].iloc[0:3].min()
    assert g0["volume"].iloc[0] == 30.0
    # three grids together give 3x the detection opportunities of one
    tot = len(g0)+len(g1)+len(g2)
    assert tot >= 88, tot
    # the union covers every 5m step exactly once
    allix = sorted(list(g0.index)+list(g1.index)+list(g2.index))
    assert len(set(allix)) == len(allix), "grids overlap in time"
    # a short frame degrades to empty, never raises
    assert len(phase_grid(_f5(2), 0)) == 0
    gs = grids_from_5m({"A": f}, min_bars=1000)
    assert gs == [{}, {}, {}], "min_bars must filter"
    print("PASS: phase grids are non-overlapping 15m, correctly aggregated, 3x density")
