"""Vintage breakdown: does the R-design edge hold across entry eras?"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.replay_r_design import (  # noqa: E402
    Design,
    atr_at,
    atr_series_15m,
    fetch_symbol_frames,
    load_trades,
    simulate,
)


def main() -> int:
    horizon_s = int(168 * 3600)
    trades = load_trades()
    frames = fetch_symbol_frames(trades, horizon_s)
    atrs = {sym: atr_series_15m(frame) for sym, frame in frames.items()}

    designs = [
        Design(stop_atr=3.0, target_r=5.0, breakeven=False),
        Design(stop_atr=4.0, target_r=10.0, breakeven=False),
        Design(stop_atr=3.0, target_r=0.0, breakeven=False),  # trail
    ]
    for design in designs:
        rows = []
        for t in trades:
            atr_value = atr_at(atrs[t.symbol], pd.Timestamp(t.entry_ts, unit="s", tz="UTC"))
            sim = simulate(t, frames[t.symbol], atr_value, design, horizon_s)
            if sim:
                ts = pd.Timestamp(t.entry_ts, unit="s", tz="UTC")
                rows.append(
                    {
                        "month": ts.strftime("%Y-%m"),
                        "era": "PMT(Jun3+)" if ts >= pd.Timestamp("2026-06-03", tz="UTC") else "legacy",
                        "symbol": t.symbol,
                        "r_net": sim["r_net"],
                        "win": sim["win"],
                    }
                )
        df = pd.DataFrame(rows)
        print(f"\n=== {design.label()} ===")
        print(df.groupby("month").agg(n=("r_net", "size"), mean_r=("r_net", "mean"), sum_r=("r_net", "sum"), wr=("win", "mean")).round(3))
        print(df.groupby("era").agg(n=("r_net", "size"), mean_r=("r_net", "mean"), sum_r=("r_net", "sum"), wr=("win", "mean")).round(3))
        pmt = df[df.era != "legacy"]
        if not pmt.empty:
            print("PMT-era by symbol:")
            print(pmt.groupby("symbol").agg(n=("r_net", "size"), mean_r=("r_net", "mean"), sum_r=("r_net", "sum")).round(3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
