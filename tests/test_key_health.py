from datetime import datetime, timezone

import pytest

from futuresbot.key_health import (
    build_auth_failure_message,
    build_key_expiry_message,
    classify_auth_failure,
    key_expiry_alert,
    parse_warn_days,
    redact,
    resolve_key_expiry,
)
from futuresbot.marketdata import MexcApiError, MexcFuturesClient

DAY = 86400.0
NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc).timestamp()


def _err(text, **payload):
    return MexcApiError(text, path="/api/v1/private/account/assets", payload=payload)


# --------------------------------------------------------------------------
# classify_auth_failure
# --------------------------------------------------------------------------

def test_classifies_the_four_distinct_auth_failures():
    assert classify_auth_failure(_err("x", code=602, message="Signature verification failed")) == "signature_mismatch"
    assert classify_auth_failure(_err("x", message="api key expired")) == "key_invalid_or_expired"
    assert classify_auth_failure(_err("x", message="permission denied")) == "permission_denied"


def test_ip_block_wins_over_the_key_mention():
    # A real IP rejection names the api key too; sending the operator to renew a
    # healthy key would be the wrong fix.
    reason = classify_auth_failure(_err("x", message="Api key is not in the IP whitelist"))
    assert reason == "ip_not_whitelisted"


def test_http_401_without_a_reason_string_still_classifies():
    class Response:
        status_code = 401

    exc = RuntimeError("nope")
    exc.response = Response()
    assert classify_auth_failure(exc) == "http_auth_rejected"


def test_ordinary_trading_errors_are_not_auth_failures():
    # The alert must stay silent on the errors the bot hits routinely, or it
    # becomes noise and gets ignored.
    assert classify_auth_failure(_err("x", code=2005, message="Balance insufficient")) is None
    assert classify_auth_failure(_err("x", code=1002, message="Contract not exist")) is None
    assert classify_auth_failure(RuntimeError("Connection reset by peer")) is None
    assert classify_auth_failure(TimeoutError("read timed out")) is None


def test_operator_can_pin_an_unknown_code_without_a_redeploy():
    exc = _err("x", code=99999, message="")
    assert classify_auth_failure(exc) is None
    assert classify_auth_failure(exc, extra_codes=("99999",)) == "key_invalid_or_expired"


# --------------------------------------------------------------------------
# expiry resolution
# --------------------------------------------------------------------------

def test_explicit_expiry_beats_derived_expiry():
    ts = resolve_key_expiry(expires_at="2026-10-15", created_at="2026-01-01")
    assert ts == datetime(2026, 10, 15, tzinfo=timezone.utc).timestamp()


def test_expiry_derived_from_creation_plus_90_days():
    created = "2026-08-01T12:00:00Z"
    assert resolve_key_expiry(created_at=created) == NOW + 90 * DAY


def test_no_dates_configured_means_no_guess():
    assert resolve_key_expiry() is None
    assert resolve_key_expiry(expires_at="", created_at="   ") is None
    assert resolve_key_expiry(expires_at="not-a-date") is None


def test_accepts_epoch_and_naive_iso():
    assert resolve_key_expiry(expires_at=NOW) == NOW
    assert resolve_key_expiry(expires_at="2026-08-01 12:00:00") == NOW


# --------------------------------------------------------------------------
# the countdown
# --------------------------------------------------------------------------

def test_silent_until_the_first_threshold_is_crossed():
    assert key_expiry_alert(expiry_ts=NOW + 30 * DAY, now_ts=NOW) is None
    assert key_expiry_alert(expiry_ts=NOW + 7.5 * DAY, now_ts=NOW) is None
    assert key_expiry_alert(expiry_ts=None, now_ts=NOW) is None


def test_alert_escalates_as_expiry_approaches():
    at7 = key_expiry_alert(expiry_ts=NOW + 6.5 * DAY, now_ts=NOW)
    at2 = key_expiry_alert(expiry_ts=NOW + 1.5 * DAY, now_ts=NOW)
    assert at7["threshold"] == 7 and not at7["expired"]
    assert at2["threshold"] == 2 and not at2["expired"]
    assert at7["key"] != at2["key"]


def test_renewal_window_is_flagged_only_inside_five_days():
    assert key_expiry_alert(expiry_ts=NOW + 6.5 * DAY, now_ts=NOW)["renewable"] is False
    assert key_expiry_alert(expiry_ts=NOW + 3 * DAY, now_ts=NOW)["renewable"] is True


def test_expired_key_reports_expired_not_renewable():
    alert = key_expiry_alert(expiry_ts=NOW - 2 * DAY, now_ts=NOW)
    assert alert["expired"] is True
    assert alert["renewable"] is False
    assert alert["threshold"] == 0


def test_dedupe_key_is_per_threshold_per_day():
    # Redeploys must not turn a T-7 warning into a redeploy-rate nag, but the
    # next calendar day must get through.
    a = key_expiry_alert(expiry_ts=NOW + 6.5 * DAY, now_ts=NOW)
    b = key_expiry_alert(expiry_ts=NOW + 6.5 * DAY, now_ts=NOW + 3600)
    c = key_expiry_alert(expiry_ts=NOW + 6.5 * DAY, now_ts=NOW + DAY)
    assert a["key"] == b["key"] != c["key"]


@pytest.mark.parametrize("raw,expected", [
    ("7,2,0", (7, 2, 0)),
    ("3", (3,)),
    ("", (7, 2, 0)),
    (None, (7, 2, 0)),
    ("junk", (7, 2, 0)),
    ("2,7,7", (7, 2)),
])
def test_parse_warn_days(raw, expected):
    assert parse_warn_days(raw) == expected


# --------------------------------------------------------------------------
# messages — these are the only thing the owner actually sees
# --------------------------------------------------------------------------

def test_renewal_message_names_the_exact_mexc_path():
    alert = key_expiry_alert(expiry_ts=NOW + 3 * DAY, now_ts=NOW)
    msg = build_key_expiry_message(alert, NOW + 3 * DAY)
    assert "My API Key" in msg and "Renew" in msg
    assert "3.0 days" in msg


def test_expired_message_warns_that_open_positions_are_unmanaged():
    alert = key_expiry_alert(expiry_ts=NOW - DAY, now_ts=NOW)
    msg = build_key_expiry_message(alert, NOW - DAY)
    assert "EXPIRED" in msg
    assert "stop" in msg.lower()


def test_auth_failure_message_gives_the_reason_specific_fix():
    ip = build_auth_failure_message("ip_not_whitelisted", path="/x", detail="blocked")
    sig = build_auth_failure_message("signature_mismatch", path="/x", detail="bad sign")
    assert "egress IP" in ip
    assert "MEXC_API_SECRET" in sig
    assert "3" in build_auth_failure_message("signature_mismatch", path="/x", detail="d", consecutive=3)


# --------------------------------------------------------------------------
# client wiring — the alert is worthless if it never fires
# --------------------------------------------------------------------------

class _Config:
    futures_base_url = "https://contract.mexc.com"
    api_key = "k"
    api_secret = "s"
    recv_window_seconds = 5


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("futuresbot.marketdata.time.sleep", lambda *_a, **_k: None)
    return MexcFuturesClient(_Config())


def test_hook_fires_once_after_retries_are_exhausted(client, monkeypatch):
    fired = []
    client.auth_error_hook = lambda *args: fired.append(args)
    monkeypatch.setattr(client.session, "get", lambda *a, **k: _Response(
        {"success": False, "code": 602, "message": "Signature verification failed"}))

    with pytest.raises(MexcApiError):
        client.private_get("/api/v1/private/account/assets")

    assert len(fired) == 1
    reason, path, _detail, streak = fired[0]
    assert reason == "signature_mismatch"
    assert path == "/api/v1/private/account/assets"
    assert streak == 1


def test_streak_counts_up_then_resets_on_recovery(client, monkeypatch):
    monkeypatch.setattr(client.session, "get", lambda *a, **k: _Response(
        {"success": False, "message": "api key expired"}))
    for _ in range(3):
        with pytest.raises(MexcApiError):
            client.private_get("/p")
    assert client.auth_error_streak == 3

    monkeypatch.setattr(client.session, "get", lambda *a, **k: _Response({"success": True, "data": {}}))
    client.private_get("/p")
    assert client.auth_error_streak == 0


def test_non_auth_failures_never_fire_the_hook(client, monkeypatch):
    fired = []
    client.auth_error_hook = lambda *args: fired.append(args)
    monkeypatch.setattr(client.session, "get", lambda *a, **k: _Response(
        {"success": False, "code": 2005, "message": "Balance insufficient"}))

    with pytest.raises(MexcApiError):
        client.private_get("/p")

    assert fired == []
    assert client.auth_error_streak == 0


def test_a_raising_hook_never_breaks_the_trading_call(client, monkeypatch):
    def boom(*_args):
        raise ValueError("telegram down")

    client.auth_error_hook = boom
    monkeypatch.setattr(client.session, "get", lambda *a, **k: _Response(
        {"success": False, "message": "signature invalid"}))

    # The original exchange error must surface, not the alerting error.
    with pytest.raises(MexcApiError):
        client.private_get("/p")


# --------------------------------------------------------------------------
# runtime wiring — hook installed, countdown throttled, silent when unset
# --------------------------------------------------------------------------

class _FakeTelegram:
    configured = True

    def __init__(self):
        self.sent: list[str] = []

    def send_message(self, text, **_kwargs):
        self.sent.append(text)
        return True


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    from dataclasses import replace
    from unittest.mock import MagicMock

    from futuresbot.config import FuturesConfig
    from futuresbot.runtime import FuturesRuntime

    for name in ("MEXC_API_KEY_EXPIRES_AT", "MEXC_API_KEY_CREATED_AT",
                 "FUTURES_KEY_EXPIRY_WARN_DAYS", "MEXC_AUTH_ERROR_CODES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    cfg = replace(
        FuturesConfig.from_env(),
        symbol="BTC_USDT",
        symbols=("BTC_USDT",),
        runtime_state_file=str(tmp_path / "rt.json"),
        status_file=str(tmp_path / "st.json"),
        telegram_token="t",
        telegram_chat_id="c",
    )
    from futuresbot.events import TelegramChannel

    rt = FuturesRuntime(cfg, MagicMock())
    # Capture at the channel boundary, not at _notify: the alerts now travel
    # emit() -> EventBus -> TelegramChannel -> send_message, and the test should
    # exercise that whole path including rendering.
    fake = _FakeTelegram()
    rt.events.channels = [TelegramChannel(fake)]
    rt._sent = fake.sent
    return rt


def test_runtime_installs_the_hook_on_the_client(runtime):
    assert runtime.client.auth_error_hook == runtime._on_auth_failure


def test_auth_alert_is_sent_then_deduped_within_the_cooldown(runtime):
    runtime._on_auth_failure("key_invalid_or_expired", "/assets", "api key expired", 1)
    runtime._on_auth_failure("key_invalid_or_expired", "/orders", "api key expired", 2)
    assert len(runtime._sent) == 1
    assert "cannot trade" in runtime._sent[0]

    # A different failure mode is a different problem and must still get through.
    runtime._on_auth_failure("ip_not_whitelisted", "/assets", "ip blocked", 3)
    assert len(runtime._sent) == 2


def test_countdown_is_silent_when_no_expiry_is_configured(runtime):
    runtime._maybe_warn_key_expiry()
    assert runtime._sent == []


def test_countdown_fires_inside_the_window_and_then_throttles(runtime, monkeypatch):
    import time as _time

    soon = datetime.fromtimestamp(_time.time() + 3 * DAY, tz=timezone.utc).isoformat()
    monkeypatch.setenv("MEXC_API_KEY_EXPIRES_AT", soon)

    runtime._maybe_warn_key_expiry()
    assert len(runtime._sent) == 1
    assert "Renew" in runtime._sent[0]

    # Hourly check throttle: the next cycle (seconds later) must not re-send.
    runtime._maybe_warn_key_expiry()
    assert len(runtime._sent) == 1


def test_credentials_never_reach_the_outbound_alert(runtime, monkeypatch):
    # The alert quotes the exchange's error text back to Telegram — the one
    # outbound path a key could ride on. Mandatory once keys belong to others.
    monkeypatch.setattr(runtime.config, "api_key", "mx0vABCDEFGH12345678", raising=False)
    monkeypatch.setattr(runtime.config, "api_secret", "s3cr3t-value-longenough", raising=False)
    runtime._on_auth_failure(
        "signature_mismatch", "/order",
        "rejected for ApiKey=mx0vABCDEFGH12345678 secret=s3cr3t-value-longenough", 1)

    sent = runtime._sent[0]
    assert "mx0vABCDEFGH12345678" not in sent
    assert "s3cr3t-value-longenough" not in sent
    assert "REDACTED" in sent


def test_redaction_leaves_short_strings_alone():
    # A short api_key value must not turn every occurrence of a common word
    # into REDACTED noise.
    assert redact("balance insufficient", ("bal",)) == "balance insufficient"
    assert redact("nothing to hide", ("",)) == "nothing to hide"


def test_countdown_stays_quiet_when_expiry_is_far_off(runtime, monkeypatch):
    import time as _time

    far = datetime.fromtimestamp(_time.time() + 60 * DAY, tz=timezone.utc).isoformat()
    monkeypatch.setenv("MEXC_API_KEY_EXPIRES_AT", far)
    runtime._maybe_warn_key_expiry()
    assert runtime._sent == []
