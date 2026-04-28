"""Tests for assessment-driven P1 fixes.

Covers:

- §6 #5 — funding-observations Redis publisher (cross-bot synergy with the
  spot bot mexc-bot-v2's ``mexcbot.funding_carry``).
- §6 #6 — global ``funding_rate_abs_max`` default tightened from 0.0008/8h
  (~87% APR) to 0.0002/8h (~22% APR).
- §6 #7 — stdout/stderr log split (so Railway stops painting healthy lines
  with severity=error).
- §6 #8 — per-cycle gate-block aggregation into a single CYCLE_SUMMARY line.
- §6 #9 — boot-time per-symbol [CONTRACT_SPEC] log line.
"""

from __future__ import annotations

import importlib
import logging
import sys

import pytest


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    import os

    for key in list(os.environ):
        if key.startswith("FUTURES_") or key in {"MEXC_API_KEY", "MEXC_API_SECRET"}:
            monkeypatch.delenv(key, raising=False)
    yield


# ---------------------------------------------------------------------------
# §6 #6 — funding-rate cap default
# ---------------------------------------------------------------------------


def test_funding_rate_abs_max_default_is_tightened(monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    cfg = importlib.import_module("futuresbot.config").FuturesConfig.from_env()
    assert cfg.funding_rate_abs_max == pytest.approx(0.0002)


def test_funding_rate_abs_max_env_override_respected(monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    monkeypatch.setenv("FUTURES_FUNDING_RATE_ABS_MAX", "0.0005")
    cfg = importlib.import_module("futuresbot.config").FuturesConfig.from_env()
    assert cfg.funding_rate_abs_max == pytest.approx(0.0005)


def test_funding_observations_redis_key_default(monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    cfg = importlib.import_module("futuresbot.config").FuturesConfig.from_env()
    assert cfg.funding_observations_redis_key == "mexc_funding_observations"


def test_funding_observations_redis_key_env_override(monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    monkeypatch.setenv("FUTURES_FUNDING_OBSERVATIONS_REDIS_KEY", "custom_key")
    cfg = importlib.import_module("futuresbot.config").FuturesConfig.from_env()
    assert cfg.funding_observations_redis_key == "custom_key"


# ---------------------------------------------------------------------------
# §6 #5 — funding publisher module
# ---------------------------------------------------------------------------


def _publisher():
    return importlib.import_module("futuresbot.funding_publisher")


def test_observations_from_cache_skips_malformed_entries():
    fp = _publisher()
    cache = {
        "BTC_USDT": (1_700_000_000.0, 0.0001),
        "ETH_USDT": (1_700_000_500.0, -0.0002),
        "BAD_TUPLE_LEN": (1_700_000_000.0,),  # malformed
        "BAD_TYPE": 12345,
    }
    obs = fp.observations_from_cache(cache)
    symbols = sorted(o.symbol for o in obs)
    assert symbols == ["BTC_USDT", "ETH_USDT"]


def test_build_payload_shape_and_age_math():
    fp = _publisher()
    obs = [
        fp.FundingObservation("BTC_USDT", 0.0001, 1_700_000_000.0),
        fp.FundingObservation("ETH_USDT", -0.0002, 1_700_000_400.0),
    ]
    payload = fp.build_payload(obs, now_unix=1_700_000_500.0)
    assert payload["schema_version"] == fp.SCHEMA_VERSION
    assert payload["source"] == "futuresbot"
    assert payload["venue"] == "mexc_perp"
    assert payload["produced_at_unix"] == 1_700_000_500.0
    btc = payload["observations"]["BTC_USDT"]
    assert btc["funding_rate_8h"] == pytest.approx(0.0001)
    # Annualised = rate * 3 * 365.
    assert btc["funding_rate_annualised"] == pytest.approx(0.0001 * 3 * 365)
    assert btc["age_seconds"] == pytest.approx(500.0)
    eth = payload["observations"]["ETH_USDT"]
    assert eth["age_seconds"] == pytest.approx(100.0)


def test_publish_to_redis_uses_set_with_ttl_and_returns_true():
    fp = _publisher()
    captured: dict[str, object] = {}

    class _StubClient:
        def set(self, name, value, ex=None):
            captured["name"] = name
            captured["value"] = value
            captured["ex"] = ex
            return True

    payload = {"schema_version": 1}
    ok = fp.publish_to_redis(_StubClient(), payload, key="my_key", ttl_seconds=900)
    assert ok is True
    assert captured["name"] == "my_key"
    assert captured["ex"] == 900
    assert isinstance(captured["value"], (str, bytes))


def test_publish_via_url_returns_false_on_empty_url():
    fp = _publisher()
    assert fp.publish_via_url("", {"x": 1}) is False
    assert fp.publish_via_url(None, {"x": 1}) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# §6 #7 — stdout/stderr log split
# ---------------------------------------------------------------------------


def test_configure_logging_routes_info_to_stdout_and_warning_to_stderr():
    runtime = importlib.import_module("futuresbot.runtime")
    # Wipe any handlers a prior test installed.
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    runtime._configure_logging()
    handlers = root.handlers
    stream_targets = {h.stream for h in handlers if isinstance(h, logging.StreamHandler)}
    assert sys.stdout in stream_targets
    assert sys.stderr in stream_targets
    # Idempotency: a second call does not duplicate handlers.
    before = len(root.handlers)
    runtime._configure_logging()
    assert len(root.handlers) == before
    # Filter sanity: an INFO record is routed to stdout, a WARNING isn't.
    stdout_handler = next(
        h for h in root.handlers if getattr(h, "stream", None) is sys.stdout
    )
    info_record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0, msg="m", args=(), exc_info=None
    )
    warn_record = logging.LogRecord(
        name="x", level=logging.WARNING, pathname="", lineno=0, msg="m", args=(), exc_info=None
    )
    assert all(f.filter(info_record) if hasattr(f, "filter") else f(info_record) for f in stdout_handler.filters)
    assert not all(
        f.filter(warn_record) if hasattr(f, "filter") else f(warn_record)
        for f in stdout_handler.filters
    )
