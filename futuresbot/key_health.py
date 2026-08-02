"""MEXC API-key health — expiry countdown and auth-failure detection.

Two independent safety nets around the one credential the bot cannot trade
without. Today a dead key just raises inside the cycle loop and the bot goes
dark with no Telegram message; the owner finds out by opening the app.

1. ``classify_auth_failure`` turns an exchange error into an auth reason, so the
   runtime can shout instead of dying quietly. It distinguishes an IP block from
   an expired key from a bad secret, because the three have different fixes.
2. ``key_expiry_alert`` counts down to the 90-day expiry MEXC applies to any key
   without a whitelisted IP, so the T-5 renewal window is never missed.

Every function takes explicit values and never reads ``os.environ``, so a future
multi-account runtime can call them once per account without rework.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

# MEXC expires any API key that has no linked IP address after 90 days. A key
# can be renewed for another 90 days from 5 days before expiry; whether that is
# repeatable is not documented, so the countdown assumes it is not.
KEY_VALIDITY_DAYS = 90
RENEWAL_WINDOW_DAYS = 5
DEFAULT_WARN_DAYS: tuple[int, ...] = (7, 2, 0)

_DAY_SECONDS = 86400.0

# Ordered most-specific-first: an IP rejection often also mentions the key, so
# it has to win the match or the operator gets sent to renew a healthy key.
_AUTH_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ip_not_whitelisted", ("whitelist", "white list", "ip not", "not in ip", "ip address", "ip restrict", "bind ip")),
    ("signature_mismatch", ("signature", "sign verif", "sign error")),
    ("key_invalid_or_expired", ("api key", "apikey", "api-key", "access key", "accesskey", "key expired",
                                "key is expired", "invalid key", "key does not exist", "key not exist")),
    ("permission_denied", ("permission", "unauthorized", "unauthorised", "not authorized", "forbidden",
                           "no trading rights")),
)

# Reasons that mean "a human must go to the MEXC console", vs transient noise.
_FIX_HINTS = {
    "ip_not_whitelisted": "The container's egress IP is not on the key's whitelist. Check whether Railway rotated it.",
    "signature_mismatch": "MEXC_API_SECRET does not match MEXC_API_KEY — a half-updated Railway variable pair.",
    "key_invalid_or_expired": "The key is expired or was deleted. Renew it, or create a new pair and update Railway.",
    "permission_denied": "The key lacks futures-trading permission.",
    "http_auth_rejected": "MEXC rejected the credentials without a reason string.",
}


def parse_timestamp(raw: Any) -> float | None:
    """Accept an epoch, a ``YYYY-MM-DD`` date, or an ISO-8601 datetime."""

    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw) if raw > 0 else None
    text = str(raw).strip()
    if not text:
        return None
    try:  # bare epoch seconds
        numeric = float(text)
    except ValueError:
        pass
    else:
        return numeric if numeric > 0 else None
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def resolve_key_expiry(
    *,
    expires_at: Any = None,
    created_at: Any = None,
    validity_days: int = KEY_VALIDITY_DAYS,
) -> float | None:
    """Explicit expiry wins; otherwise derive it from the creation date.

    Returns ``None`` when neither is configured — the countdown then stays
    silent rather than guessing a date and crying wolf.
    """

    explicit = parse_timestamp(expires_at)
    if explicit is not None:
        return explicit
    created = parse_timestamp(created_at)
    if created is None:
        return None
    return created + max(1, int(validity_days)) * _DAY_SECONDS


def days_until(expiry_ts: float, now_ts: float) -> float:
    return (float(expiry_ts) - float(now_ts)) / _DAY_SECONDS


def parse_warn_days(raw: Any, *, default: Sequence[int] = DEFAULT_WARN_DAYS) -> tuple[int, ...]:
    """Parse a ``"7,2,0"`` style threshold list, falling back to the default."""

    if raw is None or str(raw).strip() == "":
        return tuple(default)
    out: list[int] = []
    for chunk in str(raw).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(int(float(chunk)))
        except ValueError:
            continue
    return tuple(sorted(set(out), reverse=True)) if out else tuple(default)


def key_expiry_alert(
    *,
    expiry_ts: float | None,
    now_ts: float,
    warn_days: Iterable[int] = DEFAULT_WARN_DAYS,
) -> dict[str, Any] | None:
    """Return the tightest crossed warning threshold, or ``None``.

    The dedupe key carries the threshold and the calendar day, so redeploys
    cannot turn a T-7 warning into a redeploy-rate nag, and each escalation
    (7 -> 2 -> expired) still gets through on its own day.
    """

    if expiry_ts is None:
        return None
    left = days_until(expiry_ts, now_ts)
    crossed = [int(t) for t in warn_days if left <= float(t)]
    if not crossed:
        return None
    threshold = min(crossed)
    day = datetime.fromtimestamp(float(now_ts), tz=timezone.utc).strftime("%Y-%m-%d")
    return {
        "threshold": threshold,
        "days_left": left,
        "expired": left <= 0.0,
        "renewable": 0.0 < left <= float(RENEWAL_WINDOW_DAYS),
        "key": f"key_expiry:{threshold}:{day}",
    }


def build_key_expiry_message(alert: dict[str, Any], expiry_ts: float) -> str:
    when = datetime.fromtimestamp(float(expiry_ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    left = float(alert.get("days_left") or 0.0)
    if alert.get("expired"):
        head = "🔴 <b>MEXC API key EXPIRED</b>"
        body = (
            f"Expired {when} ({abs(left):.1f}d ago).\n"
            "The bot cannot place, manage, or close positions. Any open position is "
            "running on its resting exchange stop only."
        )
        action = "Create a new key pair and update <code>MEXC_API_KEY</code> / <code>MEXC_API_SECRET</code> on Railway."
    else:
        head = "🟠 <b>MEXC API key expiring</b>" if left <= 2 else "🟡 <b>MEXC API key expiring soon</b>"
        body = f"Expires {when} — <b>{left:.1f} days</b> left."
        if alert.get("renewable"):
            action = "Renew now: MEXC → My API Key → Action → Renew (+90 days, same key, no Railway change needed)."
        else:
            action = f"Renew opens {RENEWAL_WINDOW_DAYS} days before expiry: MEXC → My API Key → Action → Renew."
    return f"{head}\n━━━━━━━━━━━━━━━\n{body}\n{action}"


def redact(text: str, secrets: Iterable[str]) -> str:
    """Strip credential material out of anything bound for a log or Telegram.

    The auth alert quotes the exchange's own error string back to the operator,
    which is the one place a key could ever reach an outbound message. Cheap
    insurance at one account; mandatory once the keys belong to other people.
    """

    out = str(text)
    for secret in secrets:
        secret = str(secret or "").strip()
        if len(secret) < 8:  # too short to be a credential; redacting would eat real words
            continue
        out = out.replace(secret, f"{secret[:4]}…REDACTED")
    return out


def _payload_text(payload: Any) -> str:
    if isinstance(payload, dict):
        return " ".join(str(payload.get(field) or "") for field in ("message", "msg", "description", "data"))
    return ""


def classify_auth_failure(exc: BaseException, *, extra_codes: Iterable[str] = ()) -> str | None:
    """Name the auth problem behind an exchange error, or ``None`` if it is not one.

    Deliberately text-driven rather than code-driven: MEXC's contract-API error
    codes are poorly documented and a wrong code table would fail silently in
    the exact scenario this alert exists to catch. ``extra_codes`` lets an
    operator pin a code seen in the wild without a redeploy.
    """

    payload = getattr(exc, "payload", None)
    code = str(payload.get("code")) if isinstance(payload, dict) and payload.get("code") is not None else ""
    if code and code in {str(c).strip() for c in extra_codes if str(c).strip()}:
        return "key_invalid_or_expired"

    haystack = f"{_payload_text(payload)} {exc}".lower()
    for reason, needles in _AUTH_PATTERNS:
        if any(needle in haystack for needle in needles):
            return reason

    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status in (401, 403):
        return "http_auth_rejected"
    return None


def build_auth_failure_message(reason: str, *, path: str, detail: str, consecutive: int = 1) -> str:
    hint = _FIX_HINTS.get(reason, "Check the API key on MEXC.")
    streak = f"\nFailed private calls in a row: <b>{consecutive}</b>." if consecutive > 1 else ""
    return (
        "🔴 <b>MEXC auth failure — bot cannot trade</b>\n"
        "━━━━━━━━━━━━━━━\n"
        f"Reason: <code>{reason}</code>\n"
        f"Endpoint: <code>{path}</code>\n"
        f"Exchange said: <code>{detail[:180]}</code>{streak}\n"
        f"\n{hint}\n"
        "<i>Open positions are unmanaged until this is fixed — the resting stop is the only protection.</i>"
    )
