from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from futuresbot.config import DEFAULT_FUTURES_SYMBOLS, FuturesConfig, parse_utc_datetime
from futuresbot.indicators import calc_adx, calc_atr, calc_ema, calc_rsi, resample_ohlcv
from futuresbot.marketdata import FuturesHistoricalDataProvider, MexcFuturesClient
from futuresbot.strategy import score_btc_futures_setup


POSITION_HISTORY_PATH = "/api/v1/private/position/list/history_positions"


@dataclass(slots=True)
class AnalysedTrade:
    raw: dict[str, Any]
    row: dict[str, Any]


def _utc_from_ms(value: Any) -> datetime | None:
    try:
        millis = int(float(value))
    except (TypeError, ValueError):
        return None
    if millis <= 0:
        return None
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc)


def _request_time(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    # The live endpoint is fussy about time filters; --no-time-filter is the
    # reliable mode when MEXC rejects otherwise valid windows.
    return int(dt.astimezone(timezone.utc).timestamp())


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _side(position_type: Any) -> str:
    return "LONG" if str(position_type) == "1" else "SHORT" if str(position_type) == "2" else "UNKNOWN"


def _extract_rows(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(payload, dict):
        return [], {}
    data = payload.get("data", [])
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)], {}
    if isinstance(data, dict):
        rows = data.get("resultList", [])
        return [row for row in rows if isinstance(row, dict)], data
    return [], {}


def _active_symbols(client: MexcFuturesClient) -> list[str]:
    payload = client.public_get("/api/v1/contract/detail")
    data = payload.get("data", []) if isinstance(payload, dict) else []
    symbols: list[str] = []
    for row in data if isinstance(data, list) else []:
        symbol = str(row.get("symbol") or "").upper()
        quote = str(row.get("quoteCoin") or "").upper()
        state = row.get("state")
        if symbol.endswith("_USDT") and quote == "USDT" and state in {0, "0", None}:
            symbols.append(symbol)
    return sorted(set(symbols))


def _fetch_history_for_symbol(
    client: MexcFuturesClient,
    symbol: str | None,
    *,
    start: datetime | None,
    end: datetime | None,
    max_pages: int,
    page_size: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        params: dict[str, Any] = {"page_num": page, "page_size": page_size}
        if symbol:
            params["symbol"] = symbol
        if start:
            params["start_time"] = _request_time(start)
        if end:
            params["end_time"] = _request_time(end)
        payload = client.private_get(POSITION_HISTORY_PATH, params)
        page_rows, page_meta = _extract_rows(payload)
        if not page_rows:
            break
        rows.extend(page_rows)
        total_page = int(_float(page_meta.get("totalPage"), 0)) if page_meta else 0
        if total_page and page >= total_page:
            break
        if len(page_rows) < page_size and not total_page:
            break
        time.sleep(0.11)
    return rows


def _dedupe(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("positionId") or ""),
            str(row.get("symbol") or ""),
            str(row.get("createTime") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def fetch_history(
    client: MexcFuturesClient,
    *,
    symbols: list[str] | None,
    start: datetime | None,
    end: datetime | None,
    max_pages: int,
    page_size: int,
    all_symbols: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not symbols:
        try:
            rows = _fetch_history_for_symbol(client, None, start=start, end=end, max_pages=max_pages, page_size=page_size)
        except RuntimeError as exc:
            print(f"account-wide history unavailable for this window: {exc}", flush=True)
        if rows:
            return _dedupe(rows)

    scan_symbols = symbols or list(DEFAULT_FUTURES_SYMBOLS)
    if all_symbols:
        scan_symbols = _active_symbols(client)
    collected: list[dict[str, Any]] = list(rows)
    for index, symbol in enumerate(scan_symbols, start=1):
        try:
            symbol_rows = _fetch_history_for_symbol(
                client,
                symbol,
                start=start,
                end=end,
                max_pages=max_pages,
                page_size=page_size,
            )
        except RuntimeError as exc:
            print(f"{symbol}: history fetch failed: {exc}", flush=True)
            continue
        if symbol_rows:
            print(f"{symbol}: {len(symbol_rows)} closed positions", flush=True)
        collected.extend(symbol_rows)
        if index % 15 == 0:
            time.sleep(0.5)
    return _dedupe(collected)


def _history_windows(start: datetime, end: datetime, chunk_days: float) -> list[tuple[datetime, datetime]]:
    windows: list[tuple[datetime, datetime]] = []
    cursor = start.astimezone(timezone.utc)
    final = end.astimezone(timezone.utc)
    step = timedelta(days=max(1.0, min(float(chunk_days), 89.0)))
    while cursor < final:
        window_end = min(final, cursor + step)
        windows.append((cursor, window_end))
        cursor = window_end
    return windows


def _market_features(frame: pd.DataFrame, entry_time: datetime, side: str) -> dict[str, float]:
    if frame.empty:
        return {}
    before = frame.loc[frame.index <= pd.Timestamp(entry_time)]
    if len(before) < 120:
        return {}
    close = before["close"].astype(float)
    volume = before["volume"].astype(float)
    latest = float(close.iloc[-1])
    features: dict[str, float] = {}
    for label, bars in (("ret_1h", 4), ("ret_6h", 24), ("ret_24h", 96)):
        if len(close) > bars and float(close.iloc[-bars - 1]) > 0:
            raw = latest / float(close.iloc[-bars - 1]) - 1.0
            features[label] = raw
            features[f"side_aligned_{label}"] = raw if side == "LONG" else -raw if side == "SHORT" else 0.0
    last_24h = before.iloc[-96:] if len(before) >= 96 else before
    if not last_24h.empty and latest > 0:
        features["range_24h_pct"] = (float(last_24h["high"].max()) - float(last_24h["low"].min())) / latest
    atr = calc_atr(before, 14)
    adx = calc_adx(resample_ohlcv(before, "1h"), 14)
    rsi = calc_rsi(close, 14)
    ema20 = calc_ema(close, 20)
    ema50 = calc_ema(close, 50)
    if len(atr) and _float(atr.iloc[-1]) > 0 and latest > 0:
        features["atr_15m_pct"] = _float(atr.iloc[-1]) / latest
    if len(adx):
        features["adx_1h"] = _float(adx.iloc[-1])
    if len(rsi):
        features["rsi_15m"] = _float(rsi.iloc[-1])
    if len(ema20) and len(ema50) and _float(ema50.iloc[-1]) > 0:
        features["ema20_ema50_gap_pct"] = _float(ema20.iloc[-1]) / _float(ema50.iloc[-1]) - 1.0
    baseline = float(volume.iloc[-33:-1].mean()) if len(volume) >= 34 else 0.0
    if baseline > 0:
        features["volume_ratio_8h"] = float(volume.iloc[-1]) / baseline
    return features


def _score_with_bot(
    *,
    config: FuturesConfig,
    provider: FuturesHistoricalDataProvider,
    row: dict[str, Any],
    entry_time: datetime,
) -> tuple[dict[str, Any], dict[str, float]]:
    symbol = str(row.get("symbol") or "").upper()
    side = _side(row.get("positionType"))
    start = int((entry_time - timedelta(days=8)).timestamp())
    end = int((entry_time + timedelta(minutes=15)).timestamp())
    try:
        frame = provider.fetch_klines(symbol, interval="Min15", start=start, end=end)
    except Exception as exc:
        return {"bot_error": f"{type(exc).__name__}: {exc}"}, {}
    features = _market_features(frame, entry_time, side)
    if frame.empty:
        return {"bot_signal": "NO_DATA"}, features
    scoped = config.for_symbol(symbol)
    try:
        signal = score_btc_futures_setup(frame.loc[frame.index <= pd.Timestamp(entry_time)], scoped)
    except Exception as exc:
        return {"bot_error": f"{type(exc).__name__}: {exc}"}, features
    if signal is None:
        return {"bot_signal": "NO_SIGNAL", "bot_side_match": False}, features
    return (
        {
            "bot_signal": signal.entry_signal,
            "bot_side": signal.side,
            "bot_side_match": signal.side == side,
            "bot_score": round(float(signal.score), 4),
            "bot_leverage": int(signal.leverage),
            "bot_certainty": round(float(signal.certainty), 4),
            "bot_trend_24h": signal.metadata.get("trend_24h"),
            "bot_trend_6h": signal.metadata.get("trend_6h"),
            "bot_adx_1h": signal.metadata.get("adx_1h"),
            "bot_volume_ratio": signal.metadata.get("volume_ratio"),
            "bot_impulse_move_pct": signal.metadata.get("impulse_move_pct"),
            "bot_impulse_move_atr": signal.metadata.get("impulse_move_atr"),
            "bot_market_gate_penalty": signal.metadata.get("market_gate_penalty"),
        },
        features,
    )


def analyse_trade(config: FuturesConfig, provider: FuturesHistoricalDataProvider, raw: dict[str, Any]) -> AnalysedTrade:
    symbol = str(raw.get("symbol") or "").upper()
    side = _side(raw.get("positionType"))
    entry_time = _utc_from_ms(raw.get("createTime"))
    exit_time = _utc_from_ms(raw.get("updateTime"))
    realised = _float(raw.get("realised"))
    close_pnl = _float(raw.get("closeProfitLoss"))
    total_fee = abs(_float(raw.get("totalFee"), abs(_float(raw.get("fee")))))
    hold_fee = _float(raw.get("holdFee"))
    duration_hours = 0.0
    if entry_time and exit_time:
        duration_hours = max(0.0, (exit_time - entry_time).total_seconds() / 3600.0)
    bot_fields: dict[str, Any] = {}
    features: dict[str, float] = {}
    if entry_time and symbol:
        bot_fields, features = _score_with_bot(config=config, provider=provider, row=raw, entry_time=entry_time)
    row: dict[str, Any] = {
        "position_id": raw.get("positionId"),
        "symbol": symbol,
        "side": side,
        "entry_time": entry_time.isoformat() if entry_time else "",
        "exit_time": exit_time.isoformat() if exit_time else "",
        "duration_hours": round(duration_hours, 4),
        "leverage": int(_float(raw.get("leverage"), 0.0)),
        "close_vol": _float(raw.get("closeVol")),
        "open_avg_price": _float(raw.get("openAvgPrice") or raw.get("newOpenAvgPrice")),
        "close_avg_price": _float(raw.get("closeAvgPrice") or raw.get("newCloseAvgPrice")),
        "realised": round(realised, 8),
        "close_pnl_ex_fee": round(close_pnl, 8),
        "total_fee": round(total_fee, 8),
        "hold_fee": round(hold_fee, 8),
        "profit_ratio": round(_float(raw.get("profitRatio")), 8),
        "winner": realised > 0,
        **{key: round(value, 8) for key, value in features.items()},
        **bot_fields,
    }
    return AnalysedTrade(raw=raw, row=row)


def _pf(rows: list[dict[str, Any]]) -> float:
    wins = sum(float(row.get("realised") or 0.0) for row in rows if float(row.get("realised") or 0.0) > 0)
    losses = abs(sum(float(row.get("realised") or 0.0) for row in rows if float(row.get("realised") or 0.0) < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return wins / losses


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    winners = [row for row in rows if float(row.get("realised") or 0.0) > 0]
    losers = [row for row in rows if float(row.get("realised") or 0.0) < 0]
    return {
        "total_trades": total,
        "wins": len(winners),
        "losses": len(losers),
        "win_rate": (len(winners) / total) if total else 0.0,
        "total_realised": round(sum(float(row.get("realised") or 0.0) for row in rows), 8),
        "total_close_pnl_ex_fee": round(sum(float(row.get("close_pnl_ex_fee") or 0.0) for row in rows), 8),
        "total_fee": round(sum(float(row.get("total_fee") or 0.0) for row in rows), 8),
        "profit_factor": round(_pf(rows), 6),
        "avg_winner": round(sum(float(row.get("realised") or 0.0) for row in winners) / len(winners), 8) if winners else 0.0,
        "avg_loser": round(sum(float(row.get("realised") or 0.0) for row in losers) / len(losers), 8) if losers else 0.0,
    }


def _group(rows: list[dict[str, Any]], key: str, *, min_count: int) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get(key) or "UNKNOWN")].append(row)
    grouped = []
    for name, bucket_rows in buckets.items():
        if len(bucket_rows) < min_count:
            continue
        item = _summary(bucket_rows)
        item[key] = name
        grouped.append(item)
    return sorted(grouped, key=lambda item: (float(item["total_realised"]), int(item["total_trades"])), reverse=True)


def _bucketed_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bucketed: list[dict[str, Any]] = []
    for row in rows:
        clone = dict(row)
        leverage = int(_float(row.get("leverage")))
        duration = _float(row.get("duration_hours"))
        side_ret_6h = _float(row.get("side_aligned_ret_6h"), 999.0)
        side_ret_24h = _float(row.get("side_aligned_ret_24h"), 999.0)
        bot_score = _float(row.get("bot_score"), -1.0)
        clone["leverage_bucket"] = "lt20" if leverage < 20 else "20" if leverage == 20 else "21_35" if leverage <= 35 else "gt35"
        clone["duration_bucket"] = "lt1h" if duration < 1 else "1_4h" if duration < 4 else "4_24h" if duration < 24 else "gt24h"
        clone["side_ret_6h_bucket"] = "unknown" if side_ret_6h == 999.0 else "adverse" if side_ret_6h < -0.005 else "flat" if side_ret_6h < 0.005 else "aligned"
        clone["side_ret_24h_bucket"] = "unknown" if side_ret_24h == 999.0 else "adverse" if side_ret_24h < -0.01 else "flat" if side_ret_24h < 0.01 else "aligned"
        clone["bot_score_bucket"] = "no_signal" if bot_score < 0 else "lt56" if bot_score < 56 else "56_65" if bot_score < 65 else "65_72" if bot_score < 72 else "gte72"
        bucketed.append(clone)
    return bucketed


def build_report(rows: list[dict[str, Any]], *, min_group_count: int) -> dict[str, Any]:
    bucketed = _bucketed_rows(rows)
    winners = [row for row in bucketed if float(row.get("realised") or 0.0) > 0]
    losers = [row for row in bucketed if float(row.get("realised") or 0.0) < 0]
    bot_matched = [row for row in bucketed if row.get("bot_side_match") is True]
    bot_missed_winners = [row for row in winners if row.get("bot_side_match") is not True]
    bot_matched_losers = [row for row in losers if row.get("bot_side_match") is True]
    return {
        "summary": _summary(bucketed),
        "bot_alignment": {
            "bot_side_matched_trades": len(bot_matched),
            "bot_side_matched_summary": _summary(bot_matched),
            "manual_winners_not_matched_by_bot": len(bot_missed_winners),
            "bot_matched_losers": len(bot_matched_losers),
        },
        "by_symbol": _group(bucketed, "symbol", min_count=min_group_count),
        "by_side": _group(bucketed, "side", min_count=1),
        "by_leverage_bucket": _group(bucketed, "leverage_bucket", min_count=1),
        "by_duration_bucket": _group(bucketed, "duration_bucket", min_count=1),
        "by_side_ret_6h_bucket": _group(bucketed, "side_ret_6h_bucket", min_count=1),
        "by_side_ret_24h_bucket": _group(bucketed, "side_ret_24h_bucket", min_count=1),
        "by_bot_signal": _group(bucketed, "bot_signal", min_count=1),
        "by_bot_score_bucket": _group(bucketed, "bot_score_bucket", min_count=1),
        "top_winners": sorted(bucketed, key=lambda row: float(row.get("realised") or 0.0), reverse=True)[:10],
        "top_losers": sorted(bucketed, key=lambda row: float(row.get("realised") or 0.0))[:10],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse historical MEXC futures positions against the current bot scorer.")
    parser.add_argument("--out", default="backtest_output/manual_futures_history")
    parser.add_argument("--start", default="", help="UTC start time, e.g. 2026-01-01T00:00:00+00:00")
    parser.add_argument("--end", default="", help="UTC end time, defaults to now")
    parser.add_argument("--days", type=float, default=365.0, help="Rolling window if --start is omitted")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols; default scans the production 10 after all-symbol probe")
    parser.add_argument("--all-symbols", action="store_true", help="Scan every active MEXC USDT futures contract if all-symbol probe is empty")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--chunk-days", type=float, default=89.0, help="MEXC history endpoint accepts at most 90 days")
    parser.add_argument("--no-time-filter", action="store_true", help="Reliable mode: page latest closed positions without start/end filters")
    parser.add_argument("--min-group-count", type=int, default=2)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    end = parse_utc_datetime(args.end) if args.end.strip() else datetime.now(timezone.utc)
    start = parse_utc_datetime(args.start) if args.start.strip() else end - timedelta(days=float(args.days))
    symbols = [part.strip().upper() for part in args.symbols.replace(",", " ").split() if part.strip()]

    config = FuturesConfig.from_env()
    client = MexcFuturesClient(config)
    provider = FuturesHistoricalDataProvider(client, cache_dir=str(out / "kline_cache"))
    history: list[dict[str, Any]] = []
    windows: list[tuple[datetime | None, datetime | None]]
    if args.no_time_filter:
        windows = [(None, None)]
    else:
        windows = _history_windows(start, end, float(args.chunk_days))
    for window_index, (window_start, window_end) in enumerate(windows, start=1):
        if window_start is None or window_end is None:
            print(f"history window {window_index}/{len(windows)}: no time filter", flush=True)
        else:
            print(
                f"history window {window_index}/{len(windows)}: "
                f"{window_start.isoformat()} -> {window_end.isoformat()}",
                flush=True,
            )
        history.extend(
            fetch_history(
                client,
                symbols=symbols or None,
                start=window_start,
                end=window_end,
                max_pages=max(1, int(args.max_pages)),
                page_size=max(1, min(100, int(args.page_size))),
                all_symbols=bool(args.all_symbols),
            )
        )
    history = _dedupe(history)
    history = sorted(history, key=lambda row: int(_float(row.get("createTime"), 0.0)))
    analysed: list[AnalysedTrade] = []
    for index, raw in enumerate(history, start=1):
        analysed.append(analyse_trade(config, provider, raw))
        if index % 10 == 0:
            print(f"analysed {index}/{len(history)} positions", flush=True)
    rows = [item.row for item in analysed]
    report = build_report(rows, min_group_count=max(1, int(args.min_group_count)))
    (out / "raw_positions.json").write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")
    (out / "manual_futures_analysis.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    write_csv(out / "manual_futures_trades.csv", rows)
    summary = report["summary"]
    alignment = report["bot_alignment"]
    print(json.dumps({"summary": summary, "bot_alignment": alignment, "out": str(out)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
