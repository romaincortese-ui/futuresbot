"""Gate B regression coverage for memo 1 §7 items B1/B2/B3/B4."""
from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock

import pytest

from futuresbot.config import FuturesConfig
from futuresbot.exchange_spec import (
    DEFAULT_EXPECTATIONS,
    ExpectedContract,
    validate_contract,
    validate_specs,
)
from futuresbot.gate_b_readiness import (
    GateBReadinessReport,
    SymbolResult,
    evaluate_gate_b_readiness,
)
from futuresbot.runtime import FuturesRuntime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_runtime(*, paper: bool = True, symbols=("BTC_USDT",), funding_cap: float = 0.0008) -> FuturesRuntime:
    cfg = FuturesConfig.from_env()
    cfg.paper_trade = paper
    cfg.symbols = list(symbols)
    cfg.symbol = symbols[0]
    cfg.funding_rate_abs_max = funding_cap
    client = MagicMock()
    client.get_funding_rate.return_value = {"fundingRate": 0.0001}
    client.get_contract_detail.return_value = {
        "contractSize": 0.0001,
        "minVol": 1,
        "priceUnit": 0.1,
        "takerFeeRate": 0.0004,
    }
    return FuturesRuntime(cfg, client)


# ---------------------------------------------------------------------------
# B2 — [FUNDING_BLOCK] structured log
# ---------------------------------------------------------------------------


def test_funding_gate_emits_structured_funding_block_log(caplog):
    runtime = _build_runtime(funding_cap=0.0001)
    runtime.client.get_funding_rate.return_value = {"fundingRate": 0.0010}
    scoped = runtime._config_for_symbol("BTC_USDT")

    caplog.set_level(logging.INFO, logger="futuresbot.runtime")
    ok = runtime._funding_gate_ok(scoped)

    assert ok is False
    records = [r.message for r in caplog.records if "[FUNDING_BLOCK]" in r.message]
    assert len(records) == 1
    msg = records[0]
    assert "symbol=BTC_USDT" in msg
    assert "funding_rate=0.00100" in msg
    assert "cap=0.00010" in msg
    assert "direction=long" in msg  # positive rate -> crowded longs


def test_funding_gate_direction_short_for_negative_rate(caplog):
    runtime = _build_runtime(funding_cap=0.0001)
    runtime.client.get_funding_rate.return_value = {"fundingRate": -0.0009}
    scoped = runtime._config_for_symbol("BTC_USDT")

    caplog.set_level(logging.INFO, logger="futuresbot.runtime")
    runtime._funding_gate_ok(scoped)

    msg = [r.message for r in caplog.records if "[FUNDING_BLOCK]" in r.message][0]
    assert "direction=short" in msg


def test_funding_gate_passes_silently_when_within_cap(caplog):
    runtime = _build_runtime(funding_cap=0.0008)
    runtime.client.get_funding_rate.return_value = {"fundingRate": 0.0003}
    scoped = runtime._config_for_symbol("BTC_USDT")

    caplog.set_level(logging.INFO, logger="futuresbot.runtime")
    ok = runtime._funding_gate_ok(scoped)

    assert ok is True
    assert not [r for r in caplog.records if "[FUNDING_BLOCK]" in r.message]


# ---------------------------------------------------------------------------
# B2 — [ENTRY] structured audit log
# ---------------------------------------------------------------------------


def test_entry_fill_log_emits_structured_line(caplog):
    from futuresbot.models import FuturesPosition
    from datetime import datetime, timezone

    runtime = _build_runtime()
    scoped = runtime._config_for_symbol("BTC_USDT")
    position = FuturesPosition(
        symbol="BTC_USDT",
        side="LONG",
        entry_price=50_000.0,
        contracts=100,
        contract_size=0.0001,
        leverage=20,
        margin_usdt=25.0,
        tp_price=51_000.0,
        sl_price=49_500.0,
        position_id="P1",
        order_id="O1",
        opened_at=datetime.now(timezone.utc),
        score=72.0,
        certainty=0.85,
        entry_signal="coil_breakout",
    )

    caplog.set_level(logging.INFO, logger="futuresbot.runtime")
    runtime._log_entry_fill(
        position=position,
        intended_price=50_000.0,
        fill_price=50_050.0,  # +10 bps adverse slippage
        mode="live",
        order_id="O1",
        maker_filled=False,
        scoped=scoped,
    )

    entry_records = [r.message for r in caplog.records if "[ENTRY]" in r.message]
    assert len(entry_records) == 1
    msg = entry_records[0]
    assert "symbol=BTC_USDT" in msg
    assert "side=LONG" in msg
    assert "mode=live" in msg
    assert "maker=false" in msg
    assert "leverage=x20" in msg
    assert "contracts=100" in msg
    # slippage = (50050-50000)/50000 * 10000 = +10.0 bps for LONG
    assert "slippage_bps=+10.00" in msg
    assert "order=O1" in msg


def test_entry_fill_log_sign_flips_for_short(caplog):
    from futuresbot.models import FuturesPosition
    from datetime import datetime, timezone

    runtime = _build_runtime()
    scoped = runtime._config_for_symbol("BTC_USDT")
    position = FuturesPosition(
        symbol="BTC_USDT",
        side="SHORT",
        entry_price=50_000.0,
        contracts=100,
        contract_size=0.0001,
        leverage=20,
        margin_usdt=25.0,
        tp_price=49_000.0,
        sl_price=50_500.0,
        position_id="P1",
        order_id="O1",
        opened_at=datetime.now(timezone.utc),
        score=72.0,
        certainty=0.85,
        entry_signal="coil_breakout",
    )

    caplog.set_level(logging.INFO, logger="futuresbot.runtime")
    runtime._log_entry_fill(
        position=position,
        intended_price=50_000.0,
        fill_price=50_050.0,  # filled HIGHER on a short = FAVOURABLE slippage
        mode="live",
        order_id="O1",
        maker_filled=False,
        scoped=scoped,
    )

    msg = [r.message for r in caplog.records if "[ENTRY]" in r.message][0]
    # For a short at entry 50000 filled at 50050, the fill is ABOVE the
    # intended price — advantageous for the short side, so signed slippage
    # should be negative in adverse-convention (favourable to the trader).
    assert "slippage_bps=-10.00" in msg


# ---------------------------------------------------------------------------
# B1 — [LIVE] banner
# ---------------------------------------------------------------------------


def test_boot_manifest_emits_live_banner_when_paper_false(caplog):
    runtime = _build_runtime(paper=False)
    caplog.set_level(logging.INFO, logger="futuresbot.runtime")

    runtime._log_boot_manifest()

    live_lines = [r for r in caplog.records if "[LIVE]" in r.message and "real-money" in r.message]
    assert len(live_lines) == 1
    assert live_lines[0].levelno >= logging.WARNING
    msg = live_lines[0].message
    assert "symbols=BTC_USDT" in msg
    assert "max_total_margin=" in msg
    assert "hard_loss_cap_pct=" in msg


def test_boot_manifest_no_live_banner_in_paper_mode(caplog):
    runtime = _build_runtime(paper=True)
    caplog.set_level(logging.INFO, logger="futuresbot.runtime")

    runtime._log_boot_manifest()

    assert not [r for r in caplog.records if "[LIVE]" in r.message and "real-money" in r.message]


# ---------------------------------------------------------------------------
# B3 — walk-forward readiness aggregator
# ---------------------------------------------------------------------------


def test_gate_b_readiness_passes_when_all_thresholds_met():
    results = {
        "BTC_USDT": SymbolResult("BTC_USDT", oos_trades=25, oos_profit_factor=1.5, total_pnl_usdt=100.0, max_drawdown_usdt=15.0),
        "ETH_USDT": SymbolResult("ETH_USDT", oos_trades=22, oos_profit_factor=1.4, total_pnl_usdt=80.0, max_drawdown_usdt=12.0),
        "TAO_USDT": SymbolResult("TAO_USDT", oos_trades=20, oos_profit_factor=1.3, total_pnl_usdt=60.0, max_drawdown_usdt=10.0),
    }
    report = evaluate_gate_b_readiness(symbol_results=results, margin_budget_usdt=300.0)
    assert report.passed is True
    assert report.reasons == []
    assert report.aggregate_pnl_usdt == pytest.approx(240.0)


def test_gate_b_readiness_fails_on_low_pf():
    results = {
        "BTC_USDT": SymbolResult("BTC_USDT", oos_trades=25, oos_profit_factor=1.1, total_pnl_usdt=40.0, max_drawdown_usdt=10.0),
    }
    report = evaluate_gate_b_readiness(symbol_results=results, margin_budget_usdt=100.0)
    assert report.passed is False
    assert any("oos_pf=1.100<1.3" in r for r in report.reasons)


def test_gate_b_readiness_fails_on_thin_sample():
    results = {
        "BTC_USDT": SymbolResult("BTC_USDT", oos_trades=12, oos_profit_factor=1.5, total_pnl_usdt=40.0, max_drawdown_usdt=5.0),
    }
    report = evaluate_gate_b_readiness(symbol_results=results, margin_budget_usdt=100.0)
    assert report.passed is False
    assert any("oos_trades=12<20" in r for r in report.reasons)


def test_gate_b_readiness_fails_on_aggregate_drawdown():
    results = {
        "BTC_USDT": SymbolResult("BTC_USDT", oos_trades=25, oos_profit_factor=1.5, total_pnl_usdt=100.0, max_drawdown_usdt=40.0),
        "ETH_USDT": SymbolResult("ETH_USDT", oos_trades=22, oos_profit_factor=1.5, total_pnl_usdt=80.0, max_drawdown_usdt=30.0),
    }
    # Budget=100 → aggregate DD=70 → 0.70 > 0.20
    report = evaluate_gate_b_readiness(symbol_results=results, margin_budget_usdt=100.0)
    assert report.passed is False
    assert any("aggregate_drawdown_pct" in r for r in report.reasons)


def test_gate_b_readiness_fails_on_single_symbol_concentration():
    results = {
        "BTC_USDT": SymbolResult("BTC_USDT", oos_trades=25, oos_profit_factor=1.5, total_pnl_usdt=400.0, max_drawdown_usdt=10.0),
        "ETH_USDT": SymbolResult("ETH_USDT", oos_trades=22, oos_profit_factor=1.4, total_pnl_usdt=50.0, max_drawdown_usdt=5.0),
        "TAO_USDT": SymbolResult("TAO_USDT", oos_trades=20, oos_profit_factor=1.3, total_pnl_usdt=50.0, max_drawdown_usdt=5.0),
    }
    # BTC share = 400/500 = 0.80 > 0.60
    report = evaluate_gate_b_readiness(symbol_results=results, margin_budget_usdt=1000.0)
    assert report.passed is False
    assert any("BTC_USDT: pnl_concentration=0.800" in r for r in report.reasons)


def test_gate_b_readiness_empty_input():
    report = evaluate_gate_b_readiness(symbol_results={}, margin_budget_usdt=100.0)
    assert report.passed is False
    assert report.reasons == ["no_symbols_scored"]


def test_gate_b_readiness_invalid_margin_budget():
    results = {"BTC_USDT": SymbolResult("BTC_USDT", 25, 1.5, 100.0, 10.0)}
    report = evaluate_gate_b_readiness(symbol_results=results, margin_budget_usdt=0.0)
    assert report.passed is False
    assert any("invalid_margin_budget" in r for r in report.reasons)


# ---------------------------------------------------------------------------
# B4 — exchange-spec validator
# ---------------------------------------------------------------------------


def test_validate_contract_accepts_exact_match():
    expected = ExpectedContract(contract_size=0.0001, min_vol=1, taker_fee_rate=0.0004)
    detail = {"contractSize": 0.0001, "minVol": 1, "takerFeeRate": 0.0004}
    assert validate_contract(symbol="BTC_USDT", detail=detail, expected=expected) == []


def test_validate_contract_flags_contract_size_mismatch():
    expected = ExpectedContract(contract_size=0.0001, min_vol=1, taker_fee_rate=0.0004)
    detail = {"contractSize": 0.001, "minVol": 1, "takerFeeRate": 0.0004}
    reasons = validate_contract(symbol="BTC_USDT", detail=detail, expected=expected)
    assert len(reasons) == 1
    assert "contractSize=0.001" in reasons[0]
    assert "expected=0.0001" in reasons[0]


def test_validate_contract_flags_taker_fee_drift():
    expected = ExpectedContract(taker_fee_rate=0.0004)
    detail = {"takerFeeRate": 0.0008}  # doubled fee tier — must flag
    reasons = validate_contract(symbol="BTC_USDT", detail=detail, expected=expected)
    assert len(reasons) == 1
    assert "takerFeeRate=0.0008" in reasons[0]


def test_validate_contract_accepts_taker_fee_within_tolerance():
    expected = ExpectedContract(taker_fee_rate=0.0004, taker_fee_tolerance=0.0001)
    detail = {"takerFeeRate": 0.00045}  # 5 bps drift within 1 bps tolerance? NO
    reasons = validate_contract(symbol="BTC_USDT", detail=detail, expected=expected)
    # 0.00005 > 0.0001? No, 0.00005 < 0.0001 → accepted
    assert reasons == []


def test_validate_contract_flags_missing_field():
    expected = ExpectedContract(contract_size=0.0001)
    detail = {}
    reasons = validate_contract(symbol="BTC_USDT", detail=detail, expected=expected)
    assert any("missing_field=contractSize" in r for r in reasons)


def test_validate_contract_flags_null_detail():
    expected = ExpectedContract(contract_size=0.0001)
    reasons = validate_contract(symbol="BTC_USDT", detail=None, expected=expected)
    assert reasons == ["BTC_USDT: contract_detail=None (fetch_failed)"]


def test_validate_contract_skips_none_fields():
    expected = ExpectedContract(contract_size=None, min_vol=None, taker_fee_rate=None)
    detail = {"contractSize": 999.0}  # would mismatch but we skip
    assert validate_contract(symbol="BTC_USDT", detail=detail, expected=expected) == []


def test_validate_specs_catches_fetch_exceptions():
    def _raising_fetcher(_sym: str):
        raise ConnectionError("network down")

    expected = {"BTC_USDT": ExpectedContract(contract_size=0.0001)}
    ok, reasons = validate_specs(symbols=["BTC_USDT"], fetcher=_raising_fetcher, expectations=expected)
    assert ok is False
    assert any("fetch_error=ConnectionError" in r for r in reasons)


def test_validate_specs_skips_symbols_without_expectation():
    def _fetcher(_sym: str):
        return {"contractSize": 999.0}  # would mismatch if checked

    ok, reasons = validate_specs(symbols=["UNKNOWN_USDT"], fetcher=_fetcher, expectations={})
    assert ok is True
    assert reasons == []


def test_runtime_exchange_spec_validator_refuses_start_in_strict_mode(monkeypatch, caplog):
    monkeypatch.setenv("FUTURES_EXCHANGE_SPEC_CHECK", "true")
    monkeypatch.setenv("FUTURES_EXCHANGE_SPEC_STRICT", "true")
    runtime = _build_runtime()
    runtime.client.get_contract_detail.return_value = {
        "contractSize": 999.0,  # intentional mismatch
        "minVol": 1,
        "takerFeeRate": 0.0004,
    }
    caplog.set_level(logging.ERROR, logger="futuresbot.runtime")

    with pytest.raises(SystemExit):
        runtime._validate_exchange_specs_on_boot()

    assert any("[EXCHANGE_SPEC_FAIL]" in r.message for r in caplog.records)


def test_runtime_exchange_spec_validator_warns_in_non_strict_mode(monkeypatch, caplog):
    monkeypatch.setenv("FUTURES_EXCHANGE_SPEC_CHECK", "true")
    monkeypatch.setenv("FUTURES_EXCHANGE_SPEC_STRICT", "false")
    runtime = _build_runtime()
    runtime.client.get_contract_detail.return_value = {
        "contractSize": 999.0,
        "minVol": 1,
        "takerFeeRate": 0.0004,
    }
    caplog.set_level(logging.WARNING, logger="futuresbot.runtime")

    # Should not raise
    runtime._validate_exchange_specs_on_boot()

    assert any("[EXCHANGE_SPEC_WARN]" in r.message for r in caplog.records)


def test_runtime_exchange_spec_validator_skips_entirely_when_disabled(monkeypatch, caplog):
    monkeypatch.setenv("FUTURES_EXCHANGE_SPEC_CHECK", "false")
    runtime = _build_runtime()
    runtime.client.get_contract_detail.return_value = {"contractSize": 999.0}
    caplog.set_level(logging.INFO, logger="futuresbot.runtime")

    runtime._validate_exchange_specs_on_boot()

    # No boot-validator logs at all
    assert not [r for r in caplog.records if "[EXCHANGE_SPEC" in r.message]


def test_runtime_exchange_spec_validator_accepts_correct_specs(monkeypatch, caplog):
    monkeypatch.setenv("FUTURES_EXCHANGE_SPEC_CHECK", "true")
    monkeypatch.setenv("FUTURES_EXCHANGE_SPEC_STRICT", "true")
    runtime = _build_runtime()
    # BTC_USDT expectation: contractSize=0.0001, minVol=1, takerFeeRate=0.0004
    runtime.client.get_contract_detail.return_value = {
        "contractSize": 0.0001,
        "minVol": 1,
        "takerFeeRate": 0.0004,
    }
    caplog.set_level(logging.INFO, logger="futuresbot.runtime")

    runtime._validate_exchange_specs_on_boot()

    assert any("[EXCHANGE_SPEC_OK]" in r.message for r in caplog.records)


def test_default_expectations_cover_active_symbols():
    # Ensure the hardcoded defaults match the bot's current active symbol set.
    for sym in ("BTC_USDT", "ETH_USDT", "TAO_USDT", "SILVER_USDT"):
        assert sym in DEFAULT_EXPECTATIONS
        assert DEFAULT_EXPECTATIONS[sym].taker_fee_rate == 0.0004
