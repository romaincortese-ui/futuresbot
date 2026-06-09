"""Replay the real MEXC fill history through stop-first R-multiple designs.

Reads ``_position_history_full.jsonl`` (see tools/export_position_history.py),
pulls public 5m OHLCV around each entry, then:

  A. Decomposes realized PnL into gross vs fees (margin-% per trade).
  B. Measures MFE/MAE in ATR multiples from each real entry.
  C. Sweeps stop-first R-designs (stop = k x ATR = 1R = 20% margin budget,
     leverage = floor(budget / stop_pct) clamped, TP/breakeven/trail in R)
     and reports net-of-fee expectancy per design.

Usage (public endpoints only, no credentials needed):

    python tools/replay_r_design.py [--horizon-hours 168] [--top 12]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from futuresbot.config import FuturesConfig
from futuresbot.marketdata import FuturesHistoricalDataProvider, MexcFuturesClient

HISTORY_PATH = ROOT / "_position_history_full.jsonl"
CACHE_DIR = ROOT / "_replay_cache"
TAKER_FEE = 0.0008  # conservative per-side taker fee (matches prod default)
RISK_BUDGET_MARGIN = 0.20  # stop = 1R = 20% of margin
LEVERAGE_CAP = 25
LEVERAGE_FLOOR = 1
ATR_PERIOD = 14  # Wilder ATR on 15m bars


@dataclass
class Trade:
    symbol: str
    side: str  # LONG / SHORT
    entry_ts: int  # epoch seconds
    exit_ts: int
    entry_price: float
    exit_price: float
    leverage: float
    margin: float
    realised: float
    fee: float


def load_trades() -> list[Trade]:
    trades: list[Trade] = []
    for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        entry_price = float(row.get("openAvgPrice") or 0.0)
        exit_price = float(row.get("closeAvgPrice") or 0.0)
        margin = float(row.get("im") or 0.0)
        if entry_price <= 0 or exit_price <= 0:
            continue
        if margin <= 0:
            # closed positions report im=0; reconstruct from realised/profitRatio when possible
            realised = float(row.get("realised") or 0.0)
            ratio = float(row.get("profitRatio") or 0.0)
            margin = abs(realised / ratio) if ratio else 0.0
        if margin <= 0:
            continue
        trades.append(
            Trade(
                symbol=str(row.get("symbol") or ""),
                side="LONG" if int(row.get("positionType") or 1) == 1 else "SHORT",
                entry_ts=int(row.get("createTime") or 0) // 1000,
                exit_ts=int(row.get("updateTime") or 0) // 1000,
                entry_price=entry_price,
                exit_price=exit_price,
                leverage=float(row.get("leverage") or 0.0),
                margin=margin,
                realised=float(row.get("realised") or 0.0),
                fee=float(row.get("totalFee") or 0.0) + float(row.get("holdFee") or 0.0),
            )
        )
    return trades


def fee_decomposition(trades: list[Trade]) -> dict:
    rows = []
    for t in trades:
        net_pct = t.realised / t.margin * 100.0
        gross_pct = (t.realised + abs(t.fee)) / t.margin * 100.0
        fee_pct = abs(t.fee) / t.margin * 100.0
        rows.append((gross_pct, fee_pct, net_pct))
    frame = pd.DataFrame(rows, columns=["gross_pct", "fee_pct", "net_pct"])
    return {
        "trades": len(frame),
        "gross_mean_pct": frame.gross_pct.mean(),
        "fee_mean_pct": frame.fee_pct.mean(),
        "net_mean_pct": frame.net_pct.mean(),
        "gross_win_rate": (frame.gross_pct > 0).mean(),
        "net_win_rate": (frame.net_pct > 0).mean(),
        "net_sum_pct": frame.net_pct.sum(),
        "fee_over_gross_edge": (frame.fee_pct.mean() / frame.gross_pct.mean()) if frame.gross_pct.mean() else float("nan"),
    }


def fetch_symbol_frames(trades: list[Trade], horizon_s: int) -> dict[str, pd.DataFrame]:
    config = FuturesConfig.from_env()
    client = MexcFuturesClient(config)
    provider = FuturesHistoricalDataProvider(client, str(CACHE_DIR))
    frames: dict[str, pd.DataFrame] = {}
    for symbol in sorted({t.symbol for t in trades}):
        sym_trades = [t for t in trades if t.symbol == symbol]
        start = min(t.entry_ts for t in sym_trades) - 4 * 86400
        end = max(max(t.exit_ts for t in sym_trades), max(t.entry_ts for t in sym_trades) + horizon_s) + 3600
        frame = provider.fetch_klines(symbol, interval="Min5", start=start, end=end)
        frames[symbol] = frame
        print(f"  {symbol}: {len(frame)} 5m bars cached")
    return frames


def atr_series_15m(frame_5m: pd.DataFrame) -> pd.Series:
    ohlc = frame_5m[["open", "high", "low", "close"]].astype(float)
    bars = ohlc.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    prev_close = bars["close"].shift(1)
    tr = pd.concat(
        [bars["high"] - bars["low"], (bars["high"] - prev_close).abs(), (bars["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / ATR_PERIOD, adjust=False).mean()


def atr_at(atr: pd.Series, ts: pd.Timestamp) -> float:
    sliced = atr.loc[:ts]
    if sliced.empty:
        return float("nan")
    return float(sliced.iloc[-1])


def excursions(trade: Trade, frame: pd.DataFrame, atr_value: float, horizon_s: int) -> tuple[float, float, float, float]:
    """Return (mfe_atr, mae_atr, mfe_atr_to_exit, mae_atr_to_exit)."""
    start = pd.Timestamp(trade.entry_ts, unit="s", tz="UTC")
    end = pd.Timestamp(trade.entry_ts + horizon_s, unit="s", tz="UTC")
    exit_t = pd.Timestamp(trade.exit_ts, unit="s", tz="UTC")
    window = frame.loc[start:end]
    if window.empty or not atr_value or math.isnan(atr_value):
        return (float("nan"),) * 4

    def _mfe_mae(win: pd.DataFrame) -> tuple[float, float]:
        highs = win["high"].astype(float)
        lows = win["low"].astype(float)
        if trade.side == "LONG":
            mfe = (highs.max() - trade.entry_price) / atr_value
            mae = (trade.entry_price - lows.min()) / atr_value
        else:
            mfe = (trade.entry_price - lows.min()) / atr_value
            mae = (highs.max() - trade.entry_price) / atr_value
        return max(0.0, mfe), max(0.0, mae)

    mfe_h, mae_h = _mfe_mae(window)
    to_exit = frame.loc[start:exit_t]
    mfe_e, mae_e = _mfe_mae(to_exit) if not to_exit.empty else (float("nan"), float("nan"))
    return mfe_h, mae_h, mfe_e, mae_e


@dataclass
class Design:
    stop_atr: float
    target_r: float  # 0 => trail-only
    breakeven: bool
    trail_arm_r: float = 2.0
    trail_dist_r: float = 1.5
    pyramid: bool = False  # open 40%, add 60% at +1R, stop -> entry

    def label(self) -> str:
        tgt = f"TP{self.target_r:g}R" if self.target_r else f"trail(arm{self.trail_arm_r:g}R,d{self.trail_dist_r:g}R)"
        parts = [f"stop{self.stop_atr:g}xATR", tgt]
        if self.breakeven:
            parts.append("BE@1R")
        if self.pyramid:
            parts.append("pyr40+60@1R")
        return " ".join(parts)


def simulate(trade: Trade, frame: pd.DataFrame, atr_value: float, design: Design, horizon_s: int) -> dict | None:
    if not atr_value or math.isnan(atr_value) or atr_value <= 0:
        return None
    entry = trade.entry_price
    stop_dist = design.stop_atr * atr_value
    stop_frac = stop_dist / entry
    if stop_frac <= 0:
        return None
    leverage = max(LEVERAGE_FLOOR, min(LEVERAGE_CAP, int(RISK_BUDGET_MARGIN / stop_frac)))
    sign = 1.0 if trade.side == "LONG" else -1.0
    start = pd.Timestamp(trade.entry_ts, unit="s", tz="UTC")
    end = pd.Timestamp(trade.entry_ts + horizon_s, unit="s", tz="UTC")
    window = frame.loc[start:end]
    if window.empty:
        return None

    stop_price = entry - sign * stop_dist
    target_price = entry + sign * design.target_r * stop_dist if design.target_r else None
    be_armed = False
    trail_armed = False
    peak_r = 0.0
    pyramid_added = not design.pyramid
    add_price = entry + sign * stop_dist  # +1R
    size_now = 0.4 if design.pyramid else 1.0
    tranches: list[tuple[float, float]] = [(size_now, entry)]  # (fraction, fill price)

    exit_price: float | None = None
    highs = window["high"].astype(float).to_numpy()
    lows = window["low"].astype(float).to_numpy()
    closes = window["close"].astype(float).to_numpy()

    for high, low, close in zip(highs, lows, closes):
        fav_extreme = high if sign > 0 else low
        adv_extreme = low if sign > 0 else high
        bar_r = sign * (fav_extreme - entry) / stop_dist
        # conservative: check stop before favorable events within the same bar
        if (sign > 0 and low <= stop_price) or (sign < 0 and high >= stop_price):
            exit_price = stop_price
            break
        if not pyramid_added and ((sign > 0 and high >= add_price) or (sign < 0 and low <= add_price)):
            tranches.append((0.6, add_price))
            size_now = 1.0
            pyramid_added = True
            stop_price = entry  # combined stop to original entry
            be_armed = True
        if design.breakeven and not be_armed and bar_r >= 1.0:
            stop_price = entry
            be_armed = True
        peak_r = max(peak_r, bar_r)
        if design.target_r:
            if (sign > 0 and high >= target_price) or (sign < 0 and low <= target_price):
                exit_price = target_price
                break
        else:
            if not trail_armed and peak_r >= design.trail_arm_r:
                trail_armed = True
            if trail_armed:
                trail_price = entry + sign * (peak_r - design.trail_dist_r) * stop_dist
                if sign > 0:
                    stop_price = max(stop_price, trail_price)
                else:
                    stop_price = min(stop_price, trail_price)
                if (sign > 0 and low <= stop_price) or (sign < 0 and high >= stop_price):
                    exit_price = stop_price
                    break
        _ = adv_extreme

    timed_out = exit_price is None
    if exit_price is None:
        exit_price = float(closes[-1])

    # margin-space PnL net of taker fees, aggregated across tranches
    pnl_margin = 0.0
    fee_margin = 0.0
    for frac, fill in tranches:
        move = sign * (exit_price - fill) / fill
        pnl_margin += frac * move * leverage
        fee_margin += frac * TAKER_FEE * 2.0 * leverage
    net_margin = pnl_margin - fee_margin
    r_net = net_margin / RISK_BUDGET_MARGIN
    return {
        "net_margin_pct": net_margin * 100.0,
        "r_net": r_net,
        "leverage": leverage,
        "win": net_margin > 0,
        "timed_out": timed_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon-hours", type=float, default=168.0)
    parser.add_argument("--top", type=int, default=14)
    args = parser.parse_args()
    horizon_s = int(args.horizon_hours * 3600)

    trades = load_trades()
    print(f"Loaded {len(trades)} closed positions from {HISTORY_PATH.name}")

    print("\n=== A. Fee decomposition (realized fills) ===")
    fees = fee_decomposition(trades)
    for key, value in fees.items():
        print(f"  {key}: {value:.4f}" if isinstance(value, float) else f"  {key}: {value}")

    print("\nFetching OHLCV (public, cached)...")
    frames = fetch_symbol_frames(trades, horizon_s)
    atrs = {sym: atr_series_15m(frame) for sym, frame in frames.items()}

    print("\n=== B. Excursion study (ATR(14) on 15m) ===")
    exc_rows = []
    trade_atrs: list[float] = []
    for t in trades:
        atr_value = atr_at(atrs[t.symbol], pd.Timestamp(t.entry_ts, unit="s", tz="UTC"))
        trade_atrs.append(atr_value)
        exc_rows.append(excursions(t, frames[t.symbol], atr_value, horizon_s))
    exc = pd.DataFrame(exc_rows, columns=["mfe_atr", "mae_atr", "mfe_atr_exit", "mae_atr_exit"]).dropna()
    print(f"  trades with data: {len(exc)}")
    print(f"  median MFE (to horizon): {exc.mfe_atr.median():.2f} xATR | median MAE: {exc.mae_atr.median():.2f} xATR")
    print(f"  median MFE (to actual exit): {exc.mfe_atr_exit.median():.2f} xATR | median MAE: {exc.mae_atr_exit.median():.2f} xATR")
    for k in (1.0, 1.5, 2.0, 2.5, 3.0):
        survive = (exc.mae_atr < k).mean()
        runners = ((exc.mae_atr < k) & (exc.mfe_atr >= 2.0 * k)).mean()
        print(f"  stop {k:>3.1f}xATR: survives MAE {survive*100:5.1f}% | survives & reaches 2R {runners*100:5.1f}%")

    print("\n=== C. R-design sweep (stop-first sizing, fees included) ===")
    designs: list[Design] = []
    for stop_atr in (1.0, 1.5, 2.0, 2.5, 3.0):
        for target_r in (2.0, 3.0, 5.0, 0.0):
            for breakeven in (False, True):
                designs.append(Design(stop_atr=stop_atr, target_r=target_r, breakeven=breakeven))
    results = []
    for design in designs:
        rows = []
        for t, atr_value in zip(trades, trade_atrs):
            sim = simulate(t, frames[t.symbol], atr_value, design, horizon_s)
            if sim:
                rows.append(sim)
        if not rows:
            continue
        df = pd.DataFrame(rows)
        results.append(
            {
                "design": design.label(),
                "design_obj": design,
                "n": len(df),
                "mean_r": df.r_net.mean(),
                "sum_margin_pct": df.net_margin_pct.sum(),
                "win_rate": df.win.mean(),
                "mean_lev": df.leverage.mean(),
                "timeout_rate": df.timed_out.mean(),
            }
        )
    results.sort(key=lambda r: r["mean_r"], reverse=True)
    header = f"{'design':<42} {'n':>4} {'meanR':>7} {'sumM%':>9} {'WR%':>6} {'lev':>5} {'TO%':>5}"
    print(header)
    print("-" * len(header))
    for row in results[: args.top]:
        print(
            f"{row['design']:<42} {row['n']:>4} {row['mean_r']:>7.3f} {row['sum_margin_pct']:>9.1f} "
            f"{row['win_rate']*100:>6.1f} {row['mean_lev']:>5.1f} {row['timeout_rate']*100:>5.1f}"
        )

    print("\n=== C2. Pyramid variants of top-3 designs ===")
    pyr_results = []
    for row in results[:3]:
        base: Design = row["design_obj"]
        design = Design(
            stop_atr=base.stop_atr,
            target_r=base.target_r,
            breakeven=base.breakeven,
            trail_arm_r=base.trail_arm_r,
            trail_dist_r=base.trail_dist_r,
            pyramid=True,
        )
        rows = []
        for t, atr_value in zip(trades, trade_atrs):
            sim = simulate(t, frames[t.symbol], atr_value, design, horizon_s)
            if sim:
                rows.append(sim)
        if not rows:
            continue
        df = pd.DataFrame(rows)
        pyr_results.append(
            {
                "design": design.label(),
                "n": len(df),
                "mean_r": df.r_net.mean(),
                "sum_margin_pct": df.net_margin_pct.sum(),
                "win_rate": df.win.mean(),
                "mean_lev": df.leverage.mean(),
                "timeout_rate": df.timed_out.mean(),
            }
        )
    for row in pyr_results:
        print(
            f"{row['design']:<42} {row['n']:>4} {row['mean_r']:>7.3f} {row['sum_margin_pct']:>9.1f} "
            f"{row['win_rate']*100:>6.1f} {row['mean_lev']:>5.1f} {row['timeout_rate']*100:>5.1f}"
        )

    out = {
        "fees": fees,
        "excursion": {
            "median_mfe_atr": exc.mfe_atr.median(),
            "median_mae_atr": exc.mae_atr.median(),
        },
        "sweep": [{k: v for k, v in row.items() if k != "design_obj"} for row in results],
        "pyramid": pyr_results,
    }
    (ROOT / "_replay_r_design_results.json").write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    print("\nWrote _replay_r_design_results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
