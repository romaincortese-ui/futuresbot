"""Extended probe: wider stops/targets, horizon sensitivity, per-symbol robustness."""

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


def run_designs(trades, frames, atrs, designs, horizon_s, label):
    print(f"\n=== {label} (horizon {horizon_s/3600:.0f}h) ===")
    header = f"{'design':<44} {'n':>4} {'meanR':>7} {'medR':>6} {'sumM%':>9} {'WR%':>6} {'lev':>5} {'TO%':>5}"
    print(header)
    print("-" * len(header))
    out = []
    for design in designs:
        rows = []
        per_trade = []
        for t in trades:
            atr_value = atr_at(atrs[t.symbol], pd.Timestamp(t.entry_ts, unit="s", tz="UTC"))
            sim = simulate(t, frames[t.symbol], atr_value, design, horizon_s)
            if sim:
                rows.append(sim)
                per_trade.append((t.symbol, sim["r_net"]))
        if not rows:
            continue
        df = pd.DataFrame(rows)
        out.append((design, df, per_trade))
        print(
            f"{design.label():<44} {len(df):>4} {df.r_net.mean():>7.3f} {df.r_net.median():>6.2f} "
            f"{df.net_margin_pct.sum():>9.1f} {df.win.mean()*100:>6.1f} {df.leverage.mean():>5.1f} {df.timed_out.mean()*100:>5.1f}"
        )
    return out


def main() -> int:
    horizon_s = int(168 * 3600)
    trades = load_trades()
    frames = fetch_symbol_frames(trades, horizon_s)
    atrs = {sym: atr_series_15m(frame) for sym, frame in frames.items()}

    wide = [
        Design(stop_atr=s, target_r=t, breakeven=False)
        for s in (3.0, 3.5, 4.0, 5.0)
        for t in (5.0, 7.0, 10.0, 0.0)
    ]
    results = run_designs(trades, frames, atrs, wide, horizon_s, "Wider stops/targets")

    # horizon sensitivity for the canonical design
    for hours in (48, 96, 168, 336):
        run_designs(trades, frames, atrs, [Design(stop_atr=3.0, target_r=5.0, breakeven=False)], int(hours * 3600), f"Horizon {hours}h")

    # per-symbol and tail-dependence for the best from the wide sweep
    best_design, best_df, per_trade = max(results, key=lambda r: r[1].r_net.mean())
    print(f"\n=== Robustness for: {best_design.label()} ===")
    pt = pd.DataFrame(per_trade, columns=["symbol", "r_net"])
    print(pt.groupby("symbol").agg(n=("r_net", "size"), mean_r=("r_net", "mean"), sum_r=("r_net", "sum")).round(3))
    sorted_r = pt.r_net.sort_values(ascending=False)
    total = sorted_r.sum()
    top5 = sorted_r.head(5).sum()
    print(f"total R: {total:.1f} | top-5 trades contribute: {top5:.1f} ({top5/total*100 if total else 0:.0f}%)")
    print(f"without top-5: mean R = {(total-top5)/(len(sorted_r)-5):.3f}")
    # time-split robustness (first half vs second half of the 229)
    half = len(trades) // 2
    ids = [(t.entry_ts) for t in trades]
    cutoff = sorted(ids)[half]
    early = pt[[t.entry_ts <= cutoff for t in trades][: len(pt)]]
    print(f"first-half mean R: {early.r_net.mean():.3f} (n={len(early)}) | second-half mean R: {pt[~pt.index.isin(early.index)].r_net.mean():.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
