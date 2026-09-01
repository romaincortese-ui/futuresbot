"""Intra-bar detection for replays. The default from 2026-09-01.

WHY EVERY REPLAY SHOULD USE THIS. The live bot scans every
FUTURES_WILDCARD_SCAN_INTERVAL_SECONDS (450s) and hands the detector a
PARTIALLY FORMED 15m candle. Replays only ever saw completed bars, so they
could not fire where live fires, and fired where live had already exited.

Measured against the 16 trades the bot actually took in trials 17-18
(tools/pit_fidelity_ablation.py):

    lever                          matched   net $   vs live
    baseline, completed bars         4/16   -13.72   -28.68
    24h range gate at 8%             4/16   -13.72   -28.68   INERT
    frame 672 bars instead of 260    4/16   -13.72   -28.68   INERT
    INTRA-BAR, 3 phase grids         4/16    +4.42   -10.55   <- 63% of the gap
    external veto proxy              5/16    -6.03   -20.99
    all four together                6/16    +2.93   -12.03

So intra-bar closes nearly two thirds of the DOLLAR error. It does not improve
trade-by-trade agreement, which stalls at 6/16 - that residual is the universe,
and it needs the ticker snapshots the runtime now records, not better maths.

WHY NOT JUST FEED THE DETECTOR 5m BARS. Because ROC_BARS = 12 assumes 15m bars.
Passing 5m data silently turns the "3h extreme move" trigger into a 1h one and
every threshold in the detector then means something different. The signal would
not be the live signal.

WHAT THIS DOES INSTEAD. Builds three PHASE-SHIFTED 15m grids from 5m data:
bars ending at :00/:15/:30..., at :05/:20/:35..., and at :10/:25/:40... Each
grid is a proper NON-OVERLAPPING 15m series, so ROC_BARS stays a 3h lookback and
pullback-resume still compares genuinely distinct candles - while a signal can
now fire every 5 minutes instead of every 15.

Overlapping rolling windows were rejected for exactly that reason: consecutive
bars would share two thirds of their data, and the detector's pullback-resume
gate compares the last three closes, so it would see three near-identical
candles and decide on noise.

USAGE

    from pit_intrabar import fetch_grids
    grids = fetch_grids(client, symbols, days=14)     # list of 3 {sym: frame}
    for g in grids:
        candidates += my_scan(g)
    candidates.sort(key=lambda z: z["ts"])            # then book ONCE

Book the union through pit_book.take() once, not per grid - the slot book and
the one-entry-per-scan rule must see the whole stream.

READ-ONLY helper.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from pit_fetch import fetch_frames

PHASES = (0, 1, 2)


def phase_grid(df5: pd.DataFrame, phase: int) -> pd.DataFrame:
    """Non-overlapping 15m OHLCV bars from 5m data, offset by `phase` bars.

    phase 0 -> bars closing at :00/:15/:30/:45
    phase 1 -> bars closing at :05/:20/:35/:50
    phase 2 -> bars closing at :10/:25/:40/:55
    """
    n = len(df5)
    if n < 3:
        return pd.DataFrame()
    op = (df5["open"] if "open" in df5 else df5["close"]).to_numpy()
    hi, lo, cl = df5["high"].to_numpy(), df5["low"].to_numpy(), df5["close"].to_numpy()
    vo = df5["volume"].to_numpy() if "volume" in df5 else None
    ix = list(df5.index)
    o, h, l, c, v, idx = [], [], [], [], [], []
    k = phase
    while k + 3 <= n:
        o.append(float(op[k]))
        h.append(float(max(hi[k:k + 3])))
        l.append(float(min(lo[k:k + 3])))
        c.append(float(cl[k + 2]))
        v.append(float(vo[k:k + 3].sum()) if vo is not None else 0.0)
        idx.append(ix[k + 2])
        k += 3
    cols: dict[str, Any] = {"open": o, "high": h, "low": l, "close": c}
    if vo is not None:
        cols["volume"] = v
    return pd.DataFrame(cols, index=pd.DatetimeIndex(idx))


def grids_from_5m(frames5: dict[str, pd.DataFrame], *,
                  min_bars: int = 300) -> list[dict[str, pd.DataFrame]]:
    """Three phase grids from a {symbol: 5m frame} map."""
    out: list[dict[str, pd.DataFrame]] = []
    for ph in PHASES:
        g: dict[str, pd.DataFrame] = {}
        for s, df in frames5.items():
            try:
                gg = phase_grid(df, ph)
            except Exception:
                continue
            if len(gg) >= min_bars:
                g[s] = gg
        out.append(g)
    return out


def fetch_grids(client, symbols, *, days: float, workers: int = 6,
                min_bars: int = 300, now_ts: int | None = None,
                strict: bool = False):
    """Fetch 5m klines and return (three phase grids, fetch report).

    `days` is in days of history, as for fetch_frames. Note the fetch report's
    `want` is computed on a 15m bar so it understates the 5m bar count by 3x;
    that only loosens its truncation guard, it does not mislead about coverage.
    """
    f5, rep = fetch_frames(client, symbols, days=days, workers=workers,
                           min_bars=min_bars * 3, interval="Min5",
                           strict=strict, now_ts=now_ts)
    return grids_from_5m(f5, min_bars=min_bars), rep
