from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import redis
except ImportError:
    redis = None  # type: ignore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _profit_factor(pnl: pd.Series) -> float:
    """Gate A A2 (memo 1 §7): return ``float('inf')`` when there are zero losing
    trades rather than the misleading ``999.0`` sentinel. Downstream consumers
    that treat profit_factor as a numeric comparison must clamp this value
    themselves; the calibration validator below enforces a minimum-trade floor
    before any inf-PF payload is acted upon.
    """

    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    if losses.empty:
        return float("inf") if not wins.empty else 0.0
    return float(wins.sum() / abs(losses.sum()))


def _summarize_trade_group(group: pd.DataFrame) -> dict[str, Any]:
    pnl = group["pnl_usdt"].astype(float)
    return {
        "trades": int(len(group)),
        "win_rate": float((pnl > 0).mean()),
        "total_pnl": float(pnl.sum()),
        "profit_factor": _profit_factor(pnl),
        "expectancy": float(pnl.mean()),
    }


def _group_trade_metrics(trades_df: pd.DataFrame, keys: list[str]) -> dict[str, Any]:
    grouped: dict[str, Any] = {}
    if trades_df.empty:
        return grouped
    normalized = trades_df.copy()
    for key in keys:
        normalized[key] = normalized.get(key, "UNKNOWN")
        normalized[key] = normalized[key].fillna("UNKNOWN").astype(str)
    for raw_keys, group in normalized.groupby(keys):
        if not isinstance(raw_keys, tuple):
            raw_keys = (raw_keys,)
        node = grouped
        for key in raw_keys[:-1]:
            node = node.setdefault(str(key), {})
        node[str(raw_keys[-1])] = _summarize_trade_group(group)
    return grouped


def setup_regime_for_signal(entry_signal: str | None, side: str | None = None) -> str:
    signal = str(entry_signal or "").upper()
    side_name = str(side or "").upper()
    if "EVENT_CATALYST" in signal:
        return "RISK_OFF_SHORT" if side_name == "SHORT" or signal.endswith("_SHORT") else "EVENT_CATALYST_LONG"
    if "IMPULSE_EVENT" in signal:
        return "IMPULSE_EVENT_SHORT" if side_name == "SHORT" or signal.endswith("_SHORT") else "IMPULSE_EVENT_LONG"
    if "RANGE_EXPANSION" in signal:
        return "RANGE_EXPANSION_SHORT" if side_name == "SHORT" or signal.endswith("_SHORT") else "RANGE_EXPANSION_LONG"
    if "MAJOR_THRESHOLD" in signal:
        return "MAJOR_THRESHOLD_SHORT" if side_name == "SHORT" or signal.endswith("_SHORT") else "MAJOR_THRESHOLD_LONG"
    if "LEVEL_BREAK" in signal:
        return "LEVEL_BREAK_SHORT" if side_name == "SHORT" or signal.endswith("_SHORT") else "LEVEL_BREAK_LONG"
    if "BTC_REVERSAL" in signal:
        return "BTC_REVERSAL_SHORT"
    if "BREAKOUT_HOLD" in signal:
        return "BREAKOUT_HOLD_LONG"
    if "TREND_CONTINUATION" in signal:
        return "TREND_CONTINUATION_SHORT" if side_name == "SHORT" or signal.endswith("_SHORT") else "TREND_CONTINUATION_LONG"
    if "MEAN_REVERSION" in signal:
        return "MEAN_REVERSION"
    if signal.startswith("COIL_") or signal.startswith("PRESSURE_"):
        return "BREAKOUT_SHORT" if side_name == "SHORT" or signal.endswith("_SHORT") else "BREAKOUT_LONG"
    if side_name == "SHORT":
        return "OTHER_SHORT"
    if side_name == "LONG":
        return "OTHER_LONG"
    return "UNKNOWN"


def _trade_setup_regime(row: Mapping[str, Any]) -> str:
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        raw = metadata.get("setup_regime")
        if raw:
            return str(raw).upper()
    raw = row.get("setup_regime")
    if raw:
        return str(raw).upper()
    return setup_regime_for_signal(str(row.get("entry_signal") or ""), str(row.get("side") or ""))


def _derive_entry_adjustment(
    metrics: Mapping[str, Any],
    *,
    min_trades: int,
    min_trades_loosen: int | None = None,
) -> dict[str, Any]:
    """Gate A A1 (memo 1 §7): asymmetric trade-count floors.

    ``min_trades`` gates any adjustment at all (tightening is allowed as soon
    as the sample reaches this floor). ``min_trades_loosen``, when supplied,
    gates the *loosen* branch only — the runtime must never widen entry gates
    or inflate size on a small sample. A 4-trade / PF-∞ payload can tighten or
    block the bot; it must not loosen it. Defaults to ``3 * min_trades`` when
    not supplied, matching the Gold-bot 40/15 ratio in spirit.
    """

    trades = int(metrics.get("trades", 0) or 0)
    if trades < min_trades:
        return {"threshold_offset": 0.0, "risk_mult": 1.0, "block_reason": None}
    loosen_floor = int(min_trades_loosen if min_trades_loosen is not None else min_trades * 3)
    profit_factor = float(metrics.get("profit_factor", 0.0) or 0.0)
    expectancy = float(metrics.get("expectancy", 0.0) or 0.0)
    win_rate = float(metrics.get("win_rate", 0.0) or 0.0)
    if trades >= max(20, min_trades * 2) and profit_factor < 0.7 and expectancy < -0.03 and win_rate < 0.4:
        return {
            "threshold_offset": 6.0,
            "risk_mult": 0.5,
            "block_reason": "calibration block: persistent underperformance",
        }
    if profit_factor < 0.95 or expectancy < 0:
        tighten = min(6.0, round(max(0.0, (1.0 - profit_factor) * 10.0) + max(0.0, -expectancy) * 20.0, 2))
        risk_mult = max(0.5, round(1.0 - min(0.45, tighten / 12.0), 2))
        return {"threshold_offset": tighten, "risk_mult": risk_mult, "block_reason": None}
    if profit_factor > 1.15 and expectancy > 0.02 and win_rate > 0.5:
        if trades < loosen_floor:
            # Sample is good but not big enough to justify loosening. Hold
            # neutral rather than widening entries on statistically thin data.
            return {
                "threshold_offset": 0.0,
                "risk_mult": 1.0,
                "block_reason": None,
                "loosen_held": f"trades={trades}<{loosen_floor}",
            }
        relax = min(3.0, round((profit_factor - 1.0) * 5.0 + min(1.0, expectancy * 10.0), 2))
        risk_mult = min(1.25, round(1.0 + min(0.25, relax / 10.0), 2))
        return {"threshold_offset": -relax, "risk_mult": risk_mult, "block_reason": None}
    return {"threshold_offset": 0.0, "risk_mult": 1.0, "block_reason": None}


def build_trade_calibration(
    trades: list[dict[str, Any]],
    *,
    window_start: datetime,
    window_end: datetime,
    min_strategy_trades: int = 12,
    min_symbol_trades: int = 8,
    min_strategy_trades_loosen: int | None = None,
    min_symbol_trades_loosen: int | None = None,
) -> dict[str, Any]:
    # Gate A A1 (memo 1 §7): the floor to *loosen* entries defaults to 3x the
    # floor to *tighten*. You should tighten quickly on weakness and loosen
    # slowly on strength.
    strategy_loosen = min_strategy_trades_loosen if min_strategy_trades_loosen is not None else min_strategy_trades * 3
    symbol_loosen = min_symbol_trades_loosen if min_symbol_trades_loosen is not None else min_symbol_trades * 3
    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        return {
            "generated_at": _utc_now().isoformat(),
            "window_start": window_start.astimezone(timezone.utc).isoformat(),
            "window_end": window_end.astimezone(timezone.utc).isoformat(),
            "total_trades": 0,
            "by_strategy": {},
            "by_strategy_signal": {},
            "by_strategy_regime": {},
            "by_strategy_symbol": {},
            "by_strategy_symbol_regime": {},
            "by_strategy_symbol_signal": {},
            "entry_adjustments": {
                "by_strategy": {},
                "by_strategy_signal": {},
                "by_strategy_regime": {},
                "by_strategy_symbol": {},
                "by_strategy_symbol_regime": {},
                "by_strategy_symbol_signal": {},
            },
        }
    normalized = trades_df.copy()
    for column in ("strategy", "symbol", "entry_signal", "side"):
        normalized[column] = normalized.get(column, "UNKNOWN")
        normalized[column] = normalized[column].fillna("UNKNOWN").astype(str)
    normalized["setup_regime"] = normalized.apply(_trade_setup_regime, axis=1)
    by_strategy = _group_trade_metrics(normalized, ["strategy"])
    by_strategy_signal = _group_trade_metrics(normalized, ["strategy", "entry_signal"])
    by_strategy_regime = _group_trade_metrics(normalized, ["strategy", "setup_regime"])
    by_strategy_symbol = _group_trade_metrics(normalized, ["strategy", "symbol"])
    by_strategy_symbol_regime = _group_trade_metrics(normalized, ["strategy", "symbol", "setup_regime"])
    by_strategy_symbol_signal = _group_trade_metrics(normalized, ["strategy", "symbol", "entry_signal"])
    entry_by_strategy = {
        strategy: _derive_entry_adjustment(metrics, min_trades=min_strategy_trades, min_trades_loosen=strategy_loosen)
        for strategy, metrics in by_strategy.items()
    }
    entry_by_strategy_signal: dict[str, dict[str, Any]] = {}
    for strategy, signals in by_strategy_signal.items():
        for signal, metrics in signals.items():
            entry_adjustment = _derive_entry_adjustment(metrics, min_trades=min_strategy_trades, min_trades_loosen=strategy_loosen)
            if entry_adjustment != {"threshold_offset": 0.0, "risk_mult": 1.0, "block_reason": None}:
                entry_by_strategy_signal.setdefault(strategy, {})[signal] = entry_adjustment
    entry_by_strategy_regime: dict[str, dict[str, Any]] = {}
    for strategy, regimes in by_strategy_regime.items():
        for regime, metrics in regimes.items():
            entry_adjustment = _derive_entry_adjustment(metrics, min_trades=min_strategy_trades, min_trades_loosen=strategy_loosen)
            if entry_adjustment != {"threshold_offset": 0.0, "risk_mult": 1.0, "block_reason": None}:
                entry_by_strategy_regime.setdefault(strategy, {})[regime] = entry_adjustment
    entry_by_strategy_symbol: dict[str, dict[str, Any]] = {}
    for strategy, symbols in by_strategy_symbol.items():
        for symbol, metrics in symbols.items():
            entry_adjustment = _derive_entry_adjustment(metrics, min_trades=min_symbol_trades, min_trades_loosen=symbol_loosen)
            if entry_adjustment != {"threshold_offset": 0.0, "risk_mult": 1.0, "block_reason": None}:
                entry_by_strategy_symbol.setdefault(strategy, {})[symbol] = entry_adjustment
    entry_by_strategy_symbol_regime: dict[str, dict[str, dict[str, Any]]] = {}
    for strategy, symbols in by_strategy_symbol_regime.items():
        for symbol, regimes in symbols.items():
            for regime, metrics in regimes.items():
                entry_adjustment = _derive_entry_adjustment(metrics, min_trades=min_symbol_trades, min_trades_loosen=symbol_loosen)
                if entry_adjustment != {"threshold_offset": 0.0, "risk_mult": 1.0, "block_reason": None}:
                    entry_by_strategy_symbol_regime.setdefault(strategy, {}).setdefault(symbol, {})[regime] = entry_adjustment
    entry_by_strategy_symbol_signal: dict[str, dict[str, dict[str, Any]]] = {}
    for strategy, symbols in by_strategy_symbol_signal.items():
        for symbol, signals in symbols.items():
            for signal, metrics in signals.items():
                entry_adjustment = _derive_entry_adjustment(metrics, min_trades=min_symbol_trades, min_trades_loosen=symbol_loosen)
                if entry_adjustment != {"threshold_offset": 0.0, "risk_mult": 1.0, "block_reason": None}:
                    entry_by_strategy_symbol_signal.setdefault(strategy, {}).setdefault(symbol, {})[signal] = entry_adjustment
    return {
        "generated_at": _utc_now().isoformat(),
        "window_start": window_start.astimezone(timezone.utc).isoformat(),
        "window_end": window_end.astimezone(timezone.utc).isoformat(),
        "total_trades": int(len(normalized)),
        "by_strategy": by_strategy,
        "by_strategy_signal": by_strategy_signal,
        "by_strategy_regime": by_strategy_regime,
        "by_strategy_symbol": by_strategy_symbol,
        "by_strategy_symbol_regime": by_strategy_symbol_regime,
        "by_strategy_symbol_signal": by_strategy_symbol_signal,
        "entry_adjustments": {
            "by_strategy": entry_by_strategy,
            "by_strategy_signal": entry_by_strategy_signal,
            "by_strategy_regime": entry_by_strategy_regime,
            "by_strategy_symbol": entry_by_strategy_symbol,
            "by_strategy_symbol_regime": entry_by_strategy_symbol_regime,
            "by_strategy_symbol_signal": entry_by_strategy_symbol_signal,
        },
    }


def _json_safe(value: Any) -> Any:
    """Gate A A2 (memo 1 §7): recursively sanitise a payload for strict JSON.

    ``float('inf')`` / ``-inf`` / ``nan`` are not valid JSON and break strict
    consumers (Redis clients, JS / Rust / Go parsers). This converts them to
    ``null`` so downstream code sees "no-loss sample" as a first-class empty
    signal rather than a pseudo-numeric 999.
    """

    import math as _math

    if isinstance(value, float):
        if _math.isnan(value) or _math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def write_trade_calibration(file_path: str, calibration: Mapping[str, Any]) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(calibration), indent=2), encoding="utf-8")


def publish_trade_calibration(redis_url: str, redis_key: str, calibration: Mapping[str, Any]) -> bool:
    if not redis_url or not redis_key or redis is None:
        return False
    client = redis.from_url(redis_url)
    client.set(redis_key, json.dumps(_json_safe(calibration)))
    return True


def validate_trade_calibration_payload(data: Mapping[str, Any], *, max_age_hours: float, min_total_trades: int) -> tuple[bool, str | None]:
    total_trades = int(data.get("total_trades", 0) or 0)
    if total_trades < min_total_trades:
        return False, f"insufficient sample ({total_trades} trades < {min_total_trades})"
    generated_at = data.get("generated_at")
    if not generated_at:
        return False, "missing generated_at"
    try:
        created = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return False, "invalid generated_at"
    age_hours = (_utc_now() - created).total_seconds() / 3600.0
    if age_hours > max_age_hours:
        return False, f"stale calibration ({age_hours:.1f}h > {max_age_hours:.1f}h)"
    return True, None


def load_trade_calibration(*, redis_url: str, redis_key: str, file_path: str) -> tuple[dict[str, Any] | None, str | None]:
    if redis_url and redis_key and redis is not None:
        try:
            client = redis.from_url(redis_url)
            raw = client.get(redis_key)
            if raw:
                return json.loads(raw), f"Redis key {redis_key}"
        except Exception:
            pass
    path = Path(file_path)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8")), str(path)
        except Exception:
            return None, None
    return None, None


def _lookup_adjustment(
    section: Mapping[str, Any],
    strategy: str,
    symbol: str,
    entry_signal: str | None = None,
    setup_regime: str | None = None,
) -> dict[str, Any]:
    strategy_name = strategy.upper()
    symbol_name = symbol.upper()
    signal_name = (entry_signal or "").upper()
    regime_name = (setup_regime or "").upper()
    strategy_adjustment = dict(section.get("by_strategy", {}).get(strategy_name, {}))
    strategy_regime_adjustment = dict(section.get("by_strategy_regime", {}).get(strategy_name, {}).get(regime_name, {})) if regime_name else {}
    strategy_signal_adjustment = dict(section.get("by_strategy_signal", {}).get(strategy_name, {}).get(signal_name, {})) if signal_name else {}
    symbol_adjustment = dict(section.get("by_strategy_symbol", {}).get(strategy_name, {}).get(symbol_name, {}))
    symbol_regime_adjustment = (
        dict(section.get("by_strategy_symbol_regime", {}).get(strategy_name, {}).get(symbol_name, {}).get(regime_name, {}))
        if regime_name
        else {}
    )
    symbol_signal_adjustment = (
        dict(section.get("by_strategy_symbol_signal", {}).get(strategy_name, {}).get(symbol_name, {}).get(signal_name, {}))
        if signal_name
        else {}
    )
    merged = {
        **strategy_adjustment,
        **strategy_regime_adjustment,
        **strategy_signal_adjustment,
        **symbol_adjustment,
        **symbol_regime_adjustment,
        **symbol_signal_adjustment,
    }
    if merged:
        if symbol_signal_adjustment:
            merged["source"] = "pair_signal"
        elif symbol_regime_adjustment:
            merged["source"] = "pair_regime"
        elif symbol_adjustment:
            merged["source"] = "pair"
        elif strategy_signal_adjustment:
            merged["source"] = "strategy_signal"
        elif strategy_regime_adjustment:
            merged["source"] = "strategy_regime"
        else:
            merged["source"] = "strategy"
    return merged


def get_entry_adjustment(
    calibration: Mapping[str, Any] | None,
    strategy: str,
    symbol: str,
    entry_signal: str | None = None,
    setup_regime: str | None = None,
) -> dict[str, Any]:
    if not calibration:
        return {"threshold_offset": 0.0, "risk_mult": 1.0, "block_reason": None, "source": None}
    merged = _lookup_adjustment(calibration.get("entry_adjustments", {}), strategy, symbol, entry_signal, setup_regime)
    if not merged:
        return {"threshold_offset": 0.0, "risk_mult": 1.0, "block_reason": None, "source": None}
    merged.setdefault("threshold_offset", 0.0)
    merged.setdefault("risk_mult", 1.0)
    merged.setdefault("block_reason", None)
    return merged

from futuresbot.models import FuturesSignal


EVENT_CALIBRATION_RELIEF_CAP = 4.0
EVENT_BLOCK_OVERRIDE_SCORE_DEFAULT = 85.0
EVENT_BLOCK_OVERRIDE_RISK_MULT_DEFAULT = 0.35
EVENT_BLOCK_OVERRIDE_MAX_LEVERAGE_DEFAULT = 6

EVENT_FAMILY_CALIBRATION_BUCKETS = {
    "LONG": (
        ("EVENT_CATALYST_LONG", "EVENT_CATALYST_LONG"),
        ("IMPULSE_EVENT_CONTINUATION_LONG", "IMPULSE_EVENT_LONG"),
        ("IMPULSE_EVENT_LONG", "IMPULSE_EVENT_LONG"),
    ),
    "SHORT": (
        ("EVENT_CATALYST_SHORT", "RISK_OFF_SHORT"),
        ("IMPULSE_EVENT_CONTINUATION_SHORT", "IMPULSE_EVENT_SHORT"),
        ("IMPULSE_EVENT_SHORT", "IMPULSE_EVENT_SHORT"),
    ),
}


def _float_adjustment_value(adjustment: Mapping[str, Any], key: str, default: float) -> float:
    try:
        return float(adjustment.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name)
        if raw is None or raw.strip() == "":
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        raw = os.environ.get(name)
        if raw is None or raw.strip() == "":
            return default
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def _event_family_calibration_adjustment(
    signal: FuturesSignal,
    calibration: Mapping[str, Any] | None,
    primary_adjustment: Mapping[str, Any],
) -> dict[str, Any]:
    entry_signal_name = str(signal.entry_signal or "").upper()
    side_name = str(signal.side or "").upper()
    if not calibration or "EVENT" not in entry_signal_name or side_name not in EVENT_FAMILY_CALIBRATION_BUCKETS:
        return dict(primary_adjustment)

    strictest = dict(primary_adjustment)
    threshold_offset = _float_adjustment_value(strictest, "threshold_offset", 0.0)
    risk_mult = _float_adjustment_value(strictest, "risk_mult", 1.0)
    block_reason = str(strictest.get("block_reason") or "")
    sources: list[str] = []

    for family_signal, family_regime in EVENT_FAMILY_CALIBRATION_BUCKETS[side_name]:
        family_adjustment = get_entry_adjustment(
            calibration,
            "BTC_FUTURES",
            signal.symbol,
            family_signal,
            family_regime,
        )
        family_source = str(family_adjustment.get("source") or "")
        family_threshold_offset = _float_adjustment_value(family_adjustment, "threshold_offset", 0.0)
        family_risk_mult = _float_adjustment_value(family_adjustment, "risk_mult", 1.0)
        family_block_reason = str(family_adjustment.get("block_reason") or "")
        if family_block_reason and not block_reason:
            block_reason = family_block_reason
            sources.append(f"{family_signal}:{family_source or 'block'}")
        if family_threshold_offset > threshold_offset:
            threshold_offset = family_threshold_offset
            sources.append(f"{family_signal}:{family_source or 'threshold'}")
        if family_risk_mult < risk_mult:
            risk_mult = family_risk_mult
            sources.append(f"{family_signal}:{family_source or 'risk'}")

    applied = (
        threshold_offset != _float_adjustment_value(primary_adjustment, "threshold_offset", 0.0)
        or risk_mult != _float_adjustment_value(primary_adjustment, "risk_mult", 1.0)
        or block_reason != str(primary_adjustment.get("block_reason") or "")
    )
    strictest["threshold_offset"] = threshold_offset
    strictest["risk_mult"] = risk_mult
    strictest["block_reason"] = block_reason or None
    if applied:
        strictest["event_family_calibration_applied"] = 1.0
        strictest["event_family_calibration_sources"] = ",".join(dict.fromkeys(sources))
        strictest["source"] = strictest.get("source") or "event_family"
    return strictest


def _event_calibration_relief(signal: FuturesSignal, threshold_offset: float) -> float:
    if threshold_offset <= 0:
        return 0.0
    entry_signal = str(signal.entry_signal or "").upper()
    if "EVENT" not in entry_signal:
        return 0.0
    metadata = signal.metadata or {}
    try:
        relief = float(metadata.get("crypto_event_threshold_relief") or 0.0)
        bias = float(metadata.get("crypto_event_bias") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if relief <= 0:
        return 0.0
    side_sign = 1.0 if str(signal.side or "").upper() == "LONG" else -1.0 if str(signal.side or "").upper() == "SHORT" else 0.0
    if side_sign == 0.0 or side_sign * bias <= 0:
        return 0.0
    return min(float(threshold_offset), relief, EVENT_CALIBRATION_RELIEF_CAP)


def _fresh_event_aligned(signal: FuturesSignal) -> bool:
    entry_signal = str(signal.entry_signal or "").upper()
    if "EVENT" not in entry_signal:
        return False
    metadata = signal.metadata or {}
    try:
        fresh = float(metadata.get("crypto_event_fresh") or 0.0) > 0.0
        relief = float(metadata.get("crypto_event_threshold_relief") or 0.0)
        bias = float(metadata.get("crypto_event_bias") or 0.0)
    except (TypeError, ValueError):
        return False
    if not fresh or relief <= 0.0:
        return False
    side_sign = 1.0 if str(signal.side or "").upper() == "LONG" else -1.0 if str(signal.side or "").upper() == "SHORT" else 0.0
    return side_sign != 0.0 and side_sign * bias > 0.0


def _calibration_block_override_adjustment(
    signal: FuturesSignal,
    primary_adjustment: Mapping[str, Any],
    adjustment: Mapping[str, Any],
) -> dict[str, Any] | None:
    if not _env_bool("FUTURES_CALIBRATION_BLOCK_OVERRIDE_ENABLED", True):
        return None
    block_reason = str(adjustment.get("block_reason") or "")
    primary_block_reason = str(primary_adjustment.get("block_reason") or "")
    if not block_reason or not primary_block_reason or block_reason != primary_block_reason:
        return None
    min_score = _env_float("FUTURES_CALIBRATION_BLOCK_OVERRIDE_SCORE", EVENT_BLOCK_OVERRIDE_SCORE_DEFAULT)
    if float(signal.score) < min_score or not _fresh_event_aligned(signal):
        return None
    override = dict(adjustment)
    override["block_reason"] = None
    override["risk_mult"] = max(0.0, _env_float("FUTURES_CALIBRATION_BLOCK_OVERRIDE_RISK_MULT", EVENT_BLOCK_OVERRIDE_RISK_MULT_DEFAULT))
    override["block_override_min_score"] = min_score
    override["block_override_max_leverage"] = max(1, _env_int("FUTURES_CALIBRATION_BLOCK_OVERRIDE_MAX_LEVERAGE", EVENT_BLOCK_OVERRIDE_MAX_LEVERAGE_DEFAULT))
    override["calibration_block_override_applied"] = 1.0
    override["calibration_block_override_reason"] = block_reason
    override["source"] = override.get("source") or primary_adjustment.get("source")
    return override


def apply_signal_calibration(
    signal: FuturesSignal,
    calibration: Mapping[str, Any] | None,
    *,
    base_threshold: float,
    leverage_min: int,
    leverage_max: int,
) -> FuturesSignal | None:
    setup_regime = str((signal.metadata or {}).get("setup_regime") or setup_regime_for_signal(signal.entry_signal, signal.side)).upper()
    primary_adjustment = get_entry_adjustment(calibration, "BTC_FUTURES", signal.symbol, signal.entry_signal, setup_regime)
    adjustment = _event_family_calibration_adjustment(signal, calibration, primary_adjustment)
    block_override = _calibration_block_override_adjustment(signal, primary_adjustment, adjustment)
    if block_override is not None:
        adjustment = block_override
    threshold_offset = float(adjustment.get("threshold_offset", 0.0) or 0.0)
    unrelieved_threshold = float(base_threshold) + threshold_offset
    signal.metadata.update(
        {
            "calibration_source": adjustment.get("source"),
            "calibration_threshold_offset": threshold_offset,
            "calibration_event_relief_applied": 0.0,
            "calibration_block_override_applied": float(adjustment.get("calibration_block_override_applied") or 0.0),
            "calibration_block_override_reason": adjustment.get("calibration_block_override_reason"),
            "calibration_block_override_min_score": adjustment.get("block_override_min_score"),
            "event_family_calibration_applied": float(adjustment.get("event_family_calibration_applied") or 0.0),
            "event_family_calibration_sources": adjustment.get("event_family_calibration_sources"),
            "calibrated_threshold": unrelieved_threshold,
            "calibrated_threshold_unrelieved": unrelieved_threshold,
            "setup_regime": setup_regime,
            "calibration_setup_regime": setup_regime,
        }
    )
    block_reason = str(adjustment.get("block_reason") or "")
    if block_reason:
        signal.metadata["calibration_block_reason"] = block_reason
        return None
    event_relief = _event_calibration_relief(signal, threshold_offset)
    block_override_min_score = float(adjustment.get("block_override_min_score") or 0.0)
    threshold = max(float(base_threshold), unrelieved_threshold - event_relief, block_override_min_score)
    signal.metadata["calibration_event_relief_applied"] = round(event_relief, 3)
    signal.metadata["calibrated_threshold"] = threshold
    if signal.score < threshold:
        return None
    risk_mult = float(adjustment.get("risk_mult", 1.0) or 1.0)
    def _metadata_int(name: str, default: int) -> int:
        try:
            return int(float((signal.metadata or {}).get(name, default)))
        except (TypeError, ValueError):
            return default

    signal_min_bound = _metadata_int("leverage_min_bound", leverage_min)
    signal_max_bound = _metadata_int("leverage_max_bound", leverage_max)
    effective_min = max(1, min(int(leverage_min), signal_min_bound, signal_max_bound))
    effective_max = max(effective_min, min(int(leverage_max), signal_max_bound))
    override_max_leverage = int(adjustment.get("block_override_max_leverage") or 0)
    if override_max_leverage > 0:
        effective_max = max(1, min(effective_max, override_max_leverage))
        effective_min = min(effective_min, effective_max)
    calibrated_leverage = max(
        effective_min,
        min(effective_max, int(round(signal.leverage * risk_mult))),
    )
    calibrated = FuturesSignal(
        symbol=signal.symbol,
        side=signal.side,
        score=signal.score,
        certainty=signal.certainty,
        entry_price=signal.entry_price,
        tp_price=signal.tp_price,
        sl_price=signal.sl_price,
        leverage=calibrated_leverage,
        entry_signal=signal.entry_signal,
        metadata={
            **signal.metadata,
            "calibrated_threshold": threshold,
            "calibrated_threshold_unrelieved": unrelieved_threshold,
            "calibration_threshold_offset": threshold_offset,
            "calibration_event_relief_applied": round(event_relief, 3),
            "calibration_block_override_applied": float(adjustment.get("calibration_block_override_applied") or 0.0),
            "calibration_block_override_reason": adjustment.get("calibration_block_override_reason"),
            "calibration_block_override_min_score": adjustment.get("block_override_min_score"),
            "calibration_block_override_max_leverage": override_max_leverage or None,
            "calibration_risk_mult": risk_mult,
            "calibration_source": adjustment.get("source"),
            "event_family_calibration_applied": float(adjustment.get("event_family_calibration_applied") or 0.0),
            "event_family_calibration_sources": adjustment.get("event_family_calibration_sources"),
            "setup_regime": setup_regime,
            "calibration_setup_regime": setup_regime,
        },
    )
    return calibrated


__all__ = [
    "apply_signal_calibration",
    "build_trade_calibration",
    "write_trade_calibration",
    "publish_trade_calibration",
    "load_trade_calibration",
    "validate_trade_calibration_payload",
    "setup_regime_for_signal",
]