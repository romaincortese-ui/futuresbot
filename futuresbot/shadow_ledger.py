"""Shadow ledger — the counterfactual record of trades the bot did NOT take.

The feature store only records CLOSED trades, so the learning stack is
selection-biased: it can evaluate exits/holds but is structurally blind on entry
gates and the external vetoes (which shipped 'monitored' with nothing actually
monitoring them). This module appends a row for every candidate that produced a
SIGNAL but was not taken (external-gate veto, occupied slot, sizing skip), then
later resolves a paper counterfactual under the live convex exit rules
(-1R stop / +5R TP, adverse-first, 48h timeout).

Counterfactual outcomes ignore fills/fees/slippage — DIRECTIONAL evidence for
the propose-only conditional-expectancy engine, never backtest-grade proof.
Pure helpers; the runtime owns file paths and kline fetches. Fail-soft.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

RESOLVE_HORIZON_S = 48 * 3600
TP_R = 5.0


def ledger_path(state_dir: str) -> str:
    return os.environ.get("FUTURES_SHADOW_LEDGER_FILE") or os.path.join(state_dir, "futures_shadow_ledger.jsonl")


def candidate_row(sig: Any, *, sleeve: str, reject_reason: str, lateness: float | None = None) -> dict[str, Any]:
    return {
        "ts": round(time.time()),
        "symbol": sig.symbol, "side": sig.side, "sleeve": sleeve,
        "reject_reason": reject_reason,
        "entry": float(sig.entry_price), "sl": float(sig.sl_price), "tp": float(sig.tp_price),
        "leverage": int(sig.leverage), "sl_margin_pct": float(sig.sl_margin_pct),
        "roc_pct": round(float(sig.roc_pct), 4), "rsi": float(sig.rsi),
        "entry_lateness": round(lateness, 3) if lateness is not None else None,
        "outcome": None,  # resolved later: -1.0 stop / +5.0 tp / timeout mark
    }


def append_row(path: str, row: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def load_rows(path: str) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


def resolve_outcome(row: dict[str, Any], bars: list[tuple[int, float, float]], now_ts: float) -> dict[str, Any] | None:
    """Walk (ts, high, low) bars after the candidate ts under the convex exit:
    -1R stop before +5R TP wins (adverse-first within a bar), +5R TP, or timeout
    at the horizon (marked at the final bar's midpoint R). Returns the updated
    row, or None if still unresolved (insufficient data and horizon not passed)."""
    entry = float(row["entry"]); sl = float(row["sl"]); tp = float(row["tp"])
    sgn = 1.0 if row["side"] == "LONG" else -1.0
    one_r = abs(entry - sl)
    if one_r <= 0:
        return {**row, "outcome": 0.0, "outcome_kind": "degenerate", "resolved_ts": round(now_ts)}
    seen = False
    last_mid = entry
    for ts, hi, lo in bars:
        if ts <= row["ts"]:
            continue
        seen = True
        adverse_hit = (lo <= sl) if sgn > 0 else (hi >= sl)
        if adverse_hit:  # adverse-first: the stop wins ties
            return {**row, "outcome": -1.0, "outcome_kind": "stop", "resolved_ts": ts}
        tp_hit = (hi >= tp) if sgn > 0 else (lo <= tp)
        if tp_hit:
            return {**row, "outcome": TP_R, "outcome_kind": "tp", "resolved_ts": ts}
        last_mid = (hi + lo) / 2.0
    if now_ts - float(row["ts"]) >= RESOLVE_HORIZON_S:
        mark_r = (last_mid - entry) * sgn / one_r if seen else 0.0
        return {**row, "outcome": round(mark_r, 2), "outcome_kind": "timeout", "resolved_ts": round(now_ts)}
    return None


def rewrite(path: str, rows: list[dict[str, Any]]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str) + "\n")
    os.replace(tmp, path)
