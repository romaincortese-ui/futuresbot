from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from futuresbot.calibration import apply_signal_calibration
from futuresbot.config import FuturesBacktestConfig
from futuresbot.dynamic_leverage import dynamic_leverage_enabled
from futuresbot.event_overlay import annotate_event_threshold_relief, evaluate_crypto_event_overlay
from futuresbot.event_policy import evaluate_event_policy
from futuresbot.exits import evaluate_profit_lock_bar, evaluate_trailing_bar
from futuresbot.marketdata import FuturesHistoricalDataProvider, MexcFuturesClient
from futuresbot.models import FuturesPosition, FuturesSignal
from futuresbot.opportunity_score import opportunity_balance_fraction, opportunity_metadata
from futuresbot.sharp_opportunity import (
	annotate_sharp_event_signal,
	build_sharp_event_signal,
	evaluate_sharp_opportunity_overlay,
	sharp_event_margin_multiplier,
	sharp_event_signal_allowed,
)
from futuresbot.strategy import score_btc_futures_setup


def _env_float(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name)
        if raw is None or raw.strip() == "":
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _opportunity_bucket_sizing_enabled() -> bool:
	return os.environ.get("FUTURES_OPPORTUNITY_BUCKET_SIZING_ENABLED", "0").strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_replay_time(value: Any) -> datetime | None:
	if value is None:
		return None
	if isinstance(value, pd.Timestamp):
		value = value.to_pydatetime()
	if isinstance(value, datetime):
		return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
	if isinstance(value, (int, float)):
		return datetime.fromtimestamp(float(value), tz=timezone.utc)
	if isinstance(value, str):
		raw = value.strip()
		if not raw:
			return None
		try:
			parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
		except ValueError:
			return None
		return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
	return None


def _crypto_event_margin_multiplier(metadata: Mapping[str, Any] | None) -> float:
	if not isinstance(metadata, Mapping):
		return 1.0
	try:
		value = float(metadata.get("crypto_event_size_multiplier") or 1.0)
	except (TypeError, ValueError):
		return 1.0
	return max(0.0, min(1.0, value))


@dataclass(slots=True)
class BacktestState:
	balance: float
	open_position: FuturesPosition | None = None
	pending_signal: FuturesSignal | None = None
	pending_entry_time: pd.Timestamp | None = None


def _profit_factor(pnl: pd.Series) -> float:
	"""Gate A A2 (memo 1 §7): emit ``inf`` when there are no losing trades
	rather than the misleading ``999.0`` sentinel. Upstream consumers must
	treat inf as a sentinel and combine it with the trade count before
	making any decision."""

	wins = pnl[pnl > 0]
	losses = pnl[pnl < 0]
	if losses.empty:
		return float("inf") if not wins.empty else 0.0
	return float(wins.sum() / abs(losses.sum()))


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
		pnl = group["pnl_usdt"].astype(float)
		node[str(raw_keys[-1])] = {
			"trades": int(len(group)),
			"win_rate": float((pnl > 0).mean()),
			"total_pnl": float(pnl.sum()),
			"profit_factor": _profit_factor(pnl),
			"expectancy": float(pnl.mean()),
		}
	return grouped


def build_report(equity_curve: list[dict[str, Any]], trades: list[dict[str, Any]], initial_balance: float) -> dict[str, Any]:
	equity_df = pd.DataFrame(equity_curve)
	trades_df = pd.DataFrame(trades)
	total_pnl = float(trades_df["pnl_usdt"].sum()) if not trades_df.empty else 0.0
	win_rate = float((trades_df["pnl_usdt"] > 0).mean()) if not trades_df.empty else 0.0
	profit_factor = _profit_factor(trades_df["pnl_usdt"].astype(float)) if not trades_df.empty else 0.0
	peak = equity_df["equity"].cummax() if not equity_df.empty else pd.Series(dtype=float)
	drawdown = ((equity_df["equity"] - peak) / peak).fillna(0.0) if not equity_df.empty else pd.Series(dtype=float)
	max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0
	report = {
		"generated_at": datetime.now(timezone.utc).isoformat(),
		"initial_balance": initial_balance,
		"ending_balance": float(equity_df["equity"].iloc[-1]) if not equity_df.empty else initial_balance,
		"total_trades": int(len(trades_df)),
		"total_pnl": total_pnl,
		"win_rate": win_rate,
		"profit_factor": profit_factor,
		"max_drawdown": max_drawdown,
		"by_strategy": _group_trade_metrics(trades_df, ["strategy"]),
		"by_strategy_signal": _group_trade_metrics(trades_df, ["strategy", "entry_signal"]),
		"by_strategy_symbol": _group_trade_metrics(trades_df, ["strategy", "symbol"]),
		"by_strategy_symbol_signal": _group_trade_metrics(trades_df, ["strategy", "symbol", "entry_signal"]),
	}
	return report


def build_signal_summary(report: Mapping[str, Any], *, limit: int = 3) -> dict[str, list[dict[str, Any]]]:
	strategy_signal = report.get("by_strategy_signal", {}) or {}
	rows: list[dict[str, Any]] = []
	for strategy, signals in strategy_signal.items():
		if not isinstance(signals, Mapping):
			continue
		for signal, metrics in signals.items():
			rows.append(
				{
					"strategy": strategy,
					"entry_signal": signal,
					"trades": int(metrics.get("trades", 0) or 0),
					"total_pnl": float(metrics.get("total_pnl", 0.0) or 0.0),
					"expectancy": float(metrics.get("expectancy", 0.0) or 0.0),
					"profit_factor": float(metrics.get("profit_factor", 0.0) or 0.0),
				}
			)
	eligible = [row for row in rows if row["trades"] > 0]
	best = sorted(eligible, key=lambda item: (item["total_pnl"], item["expectancy"]), reverse=True)[:limit]
	worst = sorted(eligible, key=lambda item: (item["total_pnl"], item["expectancy"]))[:limit]
	return {"best_signals": best, "worst_signals": worst}


def export_artifacts(output_dir: str, equity_curve: list[dict[str, Any]], trades: list[dict[str, Any]], report: dict[str, Any]) -> None:
	# Gate A A2 (memo 1 §7): sanitise ``inf`` profit_factor before writing
	# summary.json so strict JSON consumers can parse it.
	from futuresbot.calibration import _json_safe

	path = Path(output_dir)
	path.mkdir(parents=True, exist_ok=True)
	pd.DataFrame(equity_curve).to_csv(path / "equity_curve.csv", index=False)
	pd.DataFrame(trades).to_csv(path / "trade_journal.csv", index=False)
	(path / "summary.json").write_text(json.dumps(_json_safe(report), indent=2), encoding="utf-8")


class FuturesBacktestEngine:
	def __init__(
		self,
		config: FuturesBacktestConfig,
		provider: FuturesHistoricalDataProvider,
		client: MexcFuturesClient,
		calibration: Mapping[str, Any] | None = None,
	):
		self.config = config
		self.provider = provider
		self.client = client
		self.calibration = calibration
		self.contract = self.client.get_contract_detail(self.config.symbol)
		self.contract_size = float(self.contract.get("contractSize", 0.0001) or 0.0001)
		self.min_vol = int(float(self.contract.get("minVol", 1) or 1))
		self._crypto_event_replay_loaded = False
		self._crypto_event_replay_payload: Any | None = None

	def _load_crypto_event_replay(self) -> Any | None:
		if self._crypto_event_replay_loaded:
			return self._crypto_event_replay_payload
		self._crypto_event_replay_loaded = True
		path = str(getattr(self.config, "crypto_event_state_file", "") or "").strip()
		if not path:
			return None
		try:
			self._crypto_event_replay_payload = json.loads(Path(path).read_text(encoding="utf-8"))
		except Exception:
			self._crypto_event_replay_payload = None
		return self._crypto_event_replay_payload

	def _crypto_event_state_for(self, now: datetime) -> dict[str, Any] | None:
		if not getattr(self.config, "crypto_event_overlay_enabled", True):
			return None
		payload = self._load_crypto_event_replay()
		if not isinstance(payload, (dict, list)):
			return None
		if isinstance(payload, dict) and not any(key in payload for key in ("timeline", "states", "events_by_time")):
			return payload
		items = payload if isinstance(payload, list) else payload.get("timeline") or payload.get("states") or payload.get("events_by_time") or []
		if not isinstance(items, list):
			return None
		current = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
		selected: dict[str, Any] | None = None
		for item in items:
			if not isinstance(item, dict):
				continue
			start = _parse_replay_time(item.get("from") or item.get("start") or item.get("generated_at") or item.get("timestamp"))
			if start is None or start > current:
				continue
			end = _parse_replay_time(item.get("until") or item.get("end") or item.get("expires_at"))
			if end is not None and current >= end:
				continue
			raw_state = item.get("state") if isinstance(item.get("state"), dict) else item
			state = dict(raw_state)
			state.setdefault("generated_at", start.isoformat())
			selected = state
		return selected

	def _apply_crypto_event_overlay(self, signal: FuturesSignal, state: dict[str, Any] | None, now: datetime) -> FuturesSignal | None:
		if not getattr(self.config, "crypto_event_overlay_enabled", True):
			return signal
		decision = evaluate_crypto_event_overlay(
			state,
			symbol=signal.symbol,
			side=signal.side,
			now=now,
			stale_seconds=int(getattr(self.config, "crypto_event_stale_seconds", 1800)),
			min_abs_bias=float(getattr(self.config, "crypto_event_min_abs_bias", 0.35)),
			threshold_relief_points=float(getattr(self.config, "crypto_event_threshold_relief", 4.0)),
			score_boost_points=float(getattr(self.config, "crypto_event_score_boost", 5.0)),
			adverse_score_penalty_points=float(getattr(self.config, "crypto_event_adverse_score_penalty", 4.0)),
		)
		if decision.reason == "no_fresh_crypto_event_state":
			return signal
		if not decision.allowed:
			return None
		metadata = {**(signal.metadata or {}), **decision.metadata, "crypto_event_reason": decision.reason}
		score = max(0.0, float(signal.score) + float(decision.score_offset))
		leverage = int(signal.leverage)
		policy = evaluate_event_policy(
			symbol=signal.symbol,
			side=signal.side,
			state=state,
			now=now,
			stale_after_seconds=int(getattr(self.config, "crypto_event_stale_seconds", 1800)),
		)
		if policy.block_entry:
			return None
		if policy.reasons:
			metadata.update(
				{
					"crypto_event_policy_reasons": list(policy.reasons),
					"crypto_event_size_multiplier": round(policy.size_multiplier, 4),
					"crypto_event_leverage_multiplier": round(policy.leverage_multiplier, 4),
				}
			)
			if policy.state_age_seconds is not None:
				metadata["crypto_event_policy_age_seconds"] = round(policy.state_age_seconds, 1)
			if policy.leverage_multiplier < 1.0:
				leverage = max(1, int(leverage * float(policy.leverage_multiplier)))
		return replace(signal, score=round(score, 2), leverage=leverage, metadata=opportunity_metadata(metadata, score))

	def _contracts_for_entry(self, entry_price: float, leverage: int, balance: float, sl_price: float | None = None, margin_multiplier: float = 1.0, score: float | None = None) -> tuple[int, float, int]:
		if _opportunity_bucket_sizing_enabled():
			fraction = opportunity_balance_fraction(score)
			margin = min(max(0.0, balance) * fraction * max(0.0, min(1.0, float(margin_multiplier or 0.0))), balance)
		else:
			margin = min(self.config.margin_budget_usdt * max(0.0, min(1.0, float(margin_multiplier or 0.0))), balance)
		if entry_price <= 0 or leverage <= 0 or margin <= 0:
			return 0, 0.0, leverage
		# §2.1 — NAV-risk sizing. When USE_NAV_RISK_SIZING=1 the contract count
		# is fixed by ``risk_pct * NAV / stop_distance`` so each trade's stop-out
		# loses exactly ``NAV_RISK_PCT`` of NAV regardless of symbol price scale.
		# This closes the sub-cent-coin blowup hole where the legacy
		# (margin * leverage / entry_price) path sized PEPE to catastrophic
		# notionals because its stop-distance is tiny in absolute terms.
		if sl_price is not None and sl_price > 0 and os.environ.get("USE_NAV_RISK_SIZING", "0").strip().lower() in {"1", "true", "yes", "y", "on"}:
			try:
				from futuresbot.nav_risk_sizing import compute_nav_risk_sizing

				opportunity_sizing = _opportunity_bucket_sizing_enabled()
				risk_pct = _env_float(
					"FUTURES_OPPORTUNITY_NAV_RISK_PCT",
					_env_float("NAV_RISK_PCT", 0.04),
				) if opportunity_sizing else _env_float("NAV_RISK_PCT", 0.01)
				# Confidence-scaled risk sizing — mirror runtime._apply_nav_risk_sizing.
				if os.environ.get("FUTURES_CONFIDENCE_RISK_SIZING_ENABLED", "0").strip().lower() in {"1", "true", "yes", "y", "on"} and score is not None:
					lo = max(0.0, _env_float("FUTURES_MIN_RISK_PCT", 0.10))
					hi = max(lo, _env_float("FUTURES_MAX_RISK_PCT", 0.20))
					span = max(1.0, _env_float("FUTURES_CONFIDENCE_SCORE_SPAN", 20.0))
					threshold = float(self.config.min_confidence_score)
					gap = max(0.0, float(score) - threshold)
					norm = min(1.0, gap / span)
					risk_pct = lo + (hi - lo) * norm
				risk_pct *= max(0.0, min(1.0, float(margin_multiplier or 0.0)))
				min_bound = max(1, int(getattr(self.config, "leverage_min", 1) or 1))
				max_bound = max(min_bound, int(getattr(self.config, "leverage_max", leverage) or leverage))
				if dynamic_leverage_enabled():
					min_bound = max(1, min(max_bound, int(leverage)))
					max_bound = max(min_bound, min(max_bound, int(leverage)))
				nav_lev_min = max(min_bound, min(max_bound, int(_env_float("NAV_LEVERAGE_MIN", min_bound))))
				nav_lev_max = max(nav_lev_min, min(max_bound, int(_env_float("NAV_LEVERAGE_MAX", max_bound))))
				nav = compute_nav_risk_sizing(
					nav_usdt=balance,
					entry_price=entry_price,
					sl_price=sl_price,
					contract_size=self.contract_size,
					risk_pct=risk_pct,
					leverage_min=nav_lev_min,
					leverage_max=nav_lev_max,
					available_margin_usdt=margin,
				)
				if nav is not None and nav.qty_contracts >= self.min_vol:
					return nav.qty_contracts, round(float(nav.margin_usdt), 8), int(nav.applied_leverage)
			except Exception:
				pass
		base_qty = margin * leverage / entry_price
		contracts = int(base_qty / self.contract_size)
		contracts = max(0, contracts)
		if contracts < self.min_vol:
			return 0, 0.0, leverage
		used_margin = contracts * self.contract_size * entry_price / leverage
		return contracts, used_margin, leverage

	def _mark_to_market(self, position: FuturesPosition | None, price: float) -> float:
		if position is None or price <= 0:
			return 0.0
		direction = 1.0 if position.side == "LONG" else -1.0
		return position.base_qty * (price - position.entry_price) * direction

	def _open_position(self, signal: FuturesSignal, entry_time: pd.Timestamp, entry_price: float, balance: float) -> FuturesPosition | None:
		margin_multiplier = sharp_event_margin_multiplier(signal.metadata, 1.0) * _crypto_event_margin_multiplier(signal.metadata)
		contracts, used_margin, applied_leverage = self._contracts_for_entry(
			entry_price, signal.leverage, balance, sl_price=float(signal.sl_price), margin_multiplier=margin_multiplier, score=float(signal.score),
		)
		if contracts <= 0:
			return None
		metadata = opportunity_metadata(signal.metadata, signal.score)
		return FuturesPosition(
			symbol=signal.symbol,
			side=signal.side,
			entry_price=float(entry_price),
			contracts=contracts,
			contract_size=self.contract_size,
			leverage=int(applied_leverage),
			margin_usdt=round(used_margin, 8),
			tp_price=float(signal.tp_price),
			sl_price=float(signal.sl_price),
			position_id="BACKTEST",
			order_id="BACKTEST",
			opened_at=entry_time.to_pydatetime(),
			score=float(signal.score),
			certainty=float(signal.certainty),
			entry_signal=signal.entry_signal,
			metadata=metadata,
		)

	def _close_position(
		self,
		position: FuturesPosition,
		exit_time: pd.Timestamp,
		exit_price: float,
		reason: str,
		*,
		liquidated: bool = False,
		liq_price: float | None = None,
	) -> dict[str, Any]:
		direction = 1.0 if position.side == "LONG" else -1.0
		entry_notional = position.base_qty * position.entry_price
		# Sprint 2 §3.1 — realistic close (slippage + funding + liquidation) when
		# USE_REALISTIC_BACKTEST=1. Falls back to the legacy fee-only model when off
		# so backward comparisons remain apples-to-apples.
		if os.environ.get("USE_REALISTIC_BACKTEST", "0").strip().lower() in {"1", "true", "yes", "y", "on"}:
			try:
				from futuresbot.realistic_costs import simulate_position_close

				funding_rate = _env_float("REALISTIC_FUNDING_RATE_8H", 0.0001)
				slip_per_lev = _env_float("REALISTIC_SLIPPAGE_BPS_PER_LEV", 0.5)
				exit_mult = _env_float("REALISTIC_EXIT_SLIP_MULT", 1.5)
				liq_slip = _env_float("REALISTIC_LIQ_SLIPPAGE", 0.005)
				result = simulate_position_close(
					side=position.side,
					entry_price=position.entry_price,
					exit_price=exit_price,
					base_qty=position.base_qty,
					leverage=position.leverage,
					open_at=position.opened_at,
					close_at=exit_time.to_pydatetime(),
					liquidated=liquidated,
					liq_price=liq_price,
					taker_fee_rate=self.config.taker_fee_rate,
					slip_bps_per_lev=slip_per_lev,
					exit_slip_mult=exit_mult,
					funding_rate_8h=funding_rate,
					liq_extra_slippage=liq_slip,
				)
				pnl = result.net_pnl
				effective_exit = result.effective_exit_price
				fees = result.fees_usdt
				funding_usdt = result.funding_usdt
				slippage_usdt = result.slippage_usdt
			except Exception:
				exit_notional = position.base_qty * exit_price
				gross_pnl = position.base_qty * (exit_price - position.entry_price) * direction
				fees = (entry_notional + exit_notional) * self.config.taker_fee_rate
				pnl = gross_pnl - fees
				effective_exit = exit_price
				funding_usdt = 0.0
				slippage_usdt = 0.0
		else:
			exit_notional = position.base_qty * exit_price
			gross_pnl = position.base_qty * (exit_price - position.entry_price) * direction
			fees = (entry_notional + exit_notional) * self.config.taker_fee_rate
			pnl = gross_pnl - fees
			effective_exit = exit_price
			funding_usdt = 0.0
			slippage_usdt = 0.0
		pnl_pct = (pnl / position.margin_usdt * 100.0) if position.margin_usdt > 0 else 0.0
		# Precision-aware price rendering: small-price coins (PEPE, etc.) would
		# otherwise round to 0.00 in the journal and make exports unreadable.
		def _round_price(px: float) -> float:
			ax = abs(float(px))
			if ax <= 0:
				return 0.0
			if ax < 0.001:
				return round(float(px), 10)
			if ax < 0.1:
				return round(float(px), 6)
			if ax < 100:
				return round(float(px), 4)
			return round(float(px), 2)
		return {
			"symbol": position.symbol,
			"strategy": "BTC_FUTURES",
			"side": position.side,
			"entry_time": position.opened_at.isoformat(),
			"exit_time": exit_time.to_pydatetime().isoformat(),
			"entry_price": _round_price(position.entry_price),
			"exit_price": _round_price(effective_exit),
			"quoted_exit_price": _round_price(exit_price),
			"contracts": position.contracts,
			"base_qty": round(position.base_qty, 8),
			"leverage": position.leverage,
			"margin_usdt": round(position.margin_usdt, 8),
			"entry_signal": position.entry_signal,
			"score": position.score,
			"opportunity_score_10": int((position.metadata or {}).get("opportunity_score_10") or 0),
			"opportunity_balance_fraction": float((position.metadata or {}).get("opportunity_balance_fraction") or 0.0),
			"certainty": position.certainty,
			"exit_reason": reason,
			"tp_price": _round_price(position.tp_price),
			"sl_price": _round_price(position.sl_price),
			"pnl_usdt": round(pnl, 8),
			"pnl_pct": round(pnl_pct, 4),
			"fees_usdt": round(float(fees), 8),
			"funding_usdt": round(float(funding_usdt), 8),
			"slippage_usdt": round(float(slippage_usdt), 8),
			"liquidated": bool(liquidated),
			"sharp_event_overlay": bool((position.metadata or {}).get("sharp_event_overlay")),
			"sharp_event_reason": str((position.metadata or {}).get("sharp_event_reason") or ""),
		}

	def _sharp_event_candidate_decision(self, frame_15m: pd.DataFrame) -> Any | None:
		if not self.config.sharp_event_overlay_enabled:
			return None
		if self.config.symbol.upper() in {sym.upper() for sym in self.config.sharp_event_core_symbols}:
			return None
		return evaluate_sharp_opportunity_overlay(
			frame_15m,
			symbol=self.config.symbol,
			core_symbols=self.config.sharp_event_core_symbols,
			enabled=True,
			risk_multiplier=self.config.sharp_event_overlay_risk_multiplier,
		)

	def _calibration_for_signal(self, signal: FuturesSignal) -> Mapping[str, Any] | None:
		if (
			self.config.sharp_event_bypass_symbol_calibration
			and float((signal.metadata or {}).get("sharp_event_bypass_symbol_calibration") or 0.0) >= 1.0
		):
			return None
		return self.calibration

	def _candidate_signal_for_frame(self, frame_slice: pd.DataFrame, event_now: datetime, remaining_bars: int | None = None) -> FuturesSignal | None:
		crypto_event_state = self._crypto_event_state_for(event_now)
		event_scan_decision = evaluate_crypto_event_overlay(
			crypto_event_state,
			symbol=self.config.symbol,
			now=event_now,
			stale_seconds=int(getattr(self.config, "crypto_event_stale_seconds", 1800)),
			min_abs_bias=float(getattr(self.config, "crypto_event_min_abs_bias", 0.35)),
			threshold_relief_points=float(getattr(self.config, "crypto_event_threshold_relief", 4.0)),
			score_boost_points=float(getattr(self.config, "crypto_event_score_boost", 5.0)),
			adverse_score_penalty_points=float(getattr(self.config, "crypto_event_adverse_score_penalty", 4.0)),
		)
		long_threshold_offset = self.config.long_threshold_offset
		short_threshold_offset = self.config.short_threshold_offset
		if event_scan_decision.threshold_relief > 0:
			if event_scan_decision.bias_score > 0:
				long_threshold_offset = -event_scan_decision.threshold_relief
			else:
				short_threshold_offset = -event_scan_decision.threshold_relief
		sharp_decision = self._sharp_event_candidate_decision(frame_slice)
		sharp_active = bool(sharp_decision is not None and sharp_decision.allowed)
		raw_signal = None
		if sharp_decision is None or sharp_decision.allowed:
			raw_signal = score_btc_futures_setup(
				frame_slice,
				self.config,
				long_threshold_offset=long_threshold_offset,
				short_threshold_offset=short_threshold_offset,
				event_bias_score=event_scan_decision.bias_score if event_scan_decision.fresh else 0.0,
				event_max_severity=event_scan_decision.max_severity if event_scan_decision.fresh else 0.0,
				event_count=event_scan_decision.event_count if event_scan_decision.fresh else 0,
				sharp_event_overlay_active=sharp_active,
			)
			if raw_signal is not None and sharp_decision is not None:
				if not sharp_event_signal_allowed(raw_signal, sharp_decision):
					raw_signal = None
				else:
					raw_signal = annotate_sharp_event_signal(
						raw_signal,
						sharp_decision,
						bypass_symbol_calibration=self.config.sharp_event_bypass_symbol_calibration,
					)
			if sharp_decision is not None:
				min_remaining_bars = max(0, int(_env_float("FUTURES_SHARP_EVENT_BACKTEST_MIN_REMAINING_BARS", 16.0)))
				if remaining_bars is not None and remaining_bars < min_remaining_bars:
					raw_signal = None
				else:
					raw_signal = build_sharp_event_signal(
						frame_slice,
						self.config,
						sharp_decision,
						bypass_symbol_calibration=self.config.sharp_event_bypass_symbol_calibration,
					)
			if raw_signal is not None:
				raw_signal = annotate_event_threshold_relief(raw_signal, event_scan_decision)
				raw_signal = self._apply_crypto_event_overlay(raw_signal, crypto_event_state, event_now)
		calibrated = (
			apply_signal_calibration(
				raw_signal,
				self._calibration_for_signal(raw_signal),
				base_threshold=self.config.min_confidence_score,
				leverage_min=self.config.leverage_min,
				leverage_max=self.config.leverage_max,
			)
			if raw_signal is not None
			else None
		)
		if calibrated is None:
			return None
		metadata = opportunity_metadata(calibrated.metadata, calibrated.score)
		if _opportunity_bucket_sizing_enabled() and float(metadata.get("opportunity_balance_fraction") or 0.0) <= 0:
			return None
		return replace(calibrated, metadata=metadata)

	def _bar_exit(self, position: FuturesPosition, bar: pd.Series) -> tuple[float, str] | None:
		high = float(bar["high"])
		low = float(bar["low"])
		metadata = position.metadata or {}
		trailing_activation_progress = float(metadata.get("trailing_exit_activation_progress", self.config.trailing_exit_activation_progress) or self.config.trailing_exit_activation_progress)
		trailing_min_profit_pct = float(metadata.get("early_exit_min_profit_pct", self.config.early_exit_min_profit_pct) or self.config.early_exit_min_profit_pct)
		trailing_drawdown_pct = float(metadata.get("trailing_exit_drawdown_pct", self.config.trailing_exit_drawdown_pct) or self.config.trailing_exit_drawdown_pct)
		# Sprint 2 §3.1 — liquidation check fires before TP/SL when flag on.
		if os.environ.get("USE_REALISTIC_BACKTEST", "0").strip().lower() in {"1", "true", "yes", "y", "on"}:
			try:
				from futuresbot.realistic_costs import check_liquidation_breach, compute_liq_price

				mm_rate = _env_float("REALISTIC_MAINTENANCE_MARGIN_RATE", 0.005)
				liq = compute_liq_price(
					entry_price=position.entry_price,
					leverage=position.leverage,
					side=position.side,
					maintenance_margin_rate=mm_rate,
				)
				if liq is not None and check_liquidation_breach(
					liq_price=liq.price,
					side=position.side,
					bar_high=high,
					bar_low=low,
				):
					# Sentinel signals a liquidation fill to run(); the fill price
					# (slippage-adjusted) is computed inside _close_position.
					return liq.price, "LIQUIDATED"
			except Exception:
				pass
		if os.environ.get("USE_FUTURES_PROFIT_LOCK", "0").strip().lower() in {"1", "true", "yes", "y", "on"}:
			profit_lock_exit, _changed = evaluate_profit_lock_bar(
				position,
				high=high,
				low=low,
				taker_fee_rate=self.config.taker_fee_rate,
				trigger_pct=max(0.0, _env_float("FUTURES_PROFIT_LOCK_TRIGGER_PCT", 4.0)),
				pullback_fraction=_env_float("FUTURES_PROFIT_LOCK_PULLBACK_FRACTION", 0.20),
				floor_pct=max(0.0, _env_float("FUTURES_PROFIT_LOCK_FLOOR_PCT", 2.0)),
				min_exit_net_pct=max(0.0, _env_float("FUTURES_PROFIT_LOCK_EXIT_MIN_NET_PCT", 0.0)),
			)
			if profit_lock_exit is not None:
				return profit_lock_exit
		if position.side == "LONG":
			if low <= position.sl_price:
				return position.sl_price, "STOP_LOSS"
			trailing_exit, _changed = evaluate_trailing_bar(
				position,
				high=high,
				low=low,
				activation_progress=trailing_activation_progress,
				min_profit_pct=trailing_min_profit_pct,
				drawdown_pct=trailing_drawdown_pct,
			)
			if trailing_exit is not None:
				return trailing_exit
			if high >= position.tp_price:
				return position.tp_price, "TAKE_PROFIT"
			return None
		if high >= position.sl_price:
			return position.sl_price, "STOP_LOSS"
		trailing_exit, _changed = evaluate_trailing_bar(
			position,
			high=high,
			low=low,
			activation_progress=trailing_activation_progress,
			min_profit_pct=trailing_min_profit_pct,
			drawdown_pct=trailing_drawdown_pct,
		)
		if trailing_exit is not None:
			return trailing_exit
		if low <= position.tp_price:
			return position.tp_price, "TAKE_PROFIT"
		return None

	def _hourly_exit(self, position: FuturesPosition, close_price: float) -> tuple[float, str] | None:
		if self.config.trailing_exit_drawdown_pct > 0:
			return None
		if position.side == "LONG":
			total_move = position.tp_price - position.entry_price
			current_move = close_price - position.entry_price
		else:
			total_move = position.entry_price - position.tp_price
			current_move = position.entry_price - close_price
		if total_move <= 0 or current_move <= 0:
			return None
		progress = current_move / total_move
		raw_profit_pct = current_move / position.entry_price
		if progress >= self.config.early_exit_tp_progress and raw_profit_pct >= self.config.early_exit_min_profit_pct:
			return close_price, "HOURLY_TAKE_PROFIT"
		return None

	def run(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
		start_ts = int(self.config.start.timestamp())
		end_ts = int(self.config.end.timestamp())
		frame_15m = self.provider.fetch_klines(self.config.symbol, interval="Min15", start=start_ts, end=end_ts)
		frame_15m = frame_15m.sort_index()
		state = BacktestState(balance=float(self.config.initial_balance))
		trades: list[dict[str, Any]] = []
		equity_curve: list[dict[str, Any]] = []
		step = pd.Timedelta(minutes=15)

		for index in range(220, len(frame_15m)):
			timestamp = frame_15m.index[index]
			bar = frame_15m.iloc[index]

			if state.pending_signal is not None and state.pending_entry_time == timestamp and state.open_position is None:
				position = self._open_position(state.pending_signal, timestamp, float(bar["open"]), state.balance)
				state.pending_signal = None
				state.pending_entry_time = None
				if position is not None:
					state.open_position = position

			if state.open_position is not None:
				bar_exit = self._bar_exit(state.open_position, bar)
				if bar_exit is not None:
					exit_price, reason = bar_exit
					liquidated = reason == "LIQUIDATED"
					trade = self._close_position(
						state.open_position,
						timestamp + step,
						exit_price,
						reason,
						liquidated=liquidated,
						liq_price=exit_price if liquidated else None,
					)
					state.balance += float(trade["pnl_usdt"])
					trades.append(trade)
					state.open_position = None

			close_time = timestamp + step
			if state.open_position is not None and close_time.minute == 0:
				hourly_exit = self._hourly_exit(state.open_position, float(bar["close"]))
				if hourly_exit is not None:
					exit_price, reason = hourly_exit
					trade = self._close_position(state.open_position, close_time, exit_price, reason)
					state.balance += float(trade["pnl_usdt"])
					trades.append(trade)
					state.open_position = None

			if state.open_position is None and close_time.minute == 0 and index + 1 < len(frame_15m):
				calibrated = self._candidate_signal_for_frame(frame_15m.iloc[: index + 1], close_time.to_pydatetime(), len(frame_15m) - index - 1)
				if calibrated is not None:
					state.pending_signal = calibrated
					state.pending_entry_time = frame_15m.index[index + 1]

			equity_curve.append(
				{
					"timestamp": close_time.isoformat(),
					"equity": round(state.balance + self._mark_to_market(state.open_position, float(bar["close"])), 8),
					"cash_balance": round(state.balance, 8),
				}
			)

		if state.open_position is not None:
			final_timestamp = frame_15m.index[-1] + step
			final_close = float(frame_15m.iloc[-1]["close"])
			trade = self._close_position(state.open_position, final_timestamp, final_close, "END_OF_TEST")
			state.balance += float(trade["pnl_usdt"])
			trades.append(trade)
			equity_curve.append({"timestamp": final_timestamp.isoformat(), "equity": round(state.balance, 8), "cash_balance": round(state.balance, 8)})

		return equity_curve, trades