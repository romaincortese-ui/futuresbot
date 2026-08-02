"""Typed events and delivery channels — phase 3 of docs/MULTI_ACCOUNT_DESIGN.md.

Today every outbound notification is a pre-formatted HTML string handed to
``_notify``. That works for exactly one consumer (Telegram) and blocks every
other one: a web UI cannot render ``"🚀 <b>ENTRY</b> …"`` into a table, and a
database cannot index it.

So notifications become ``Event`` objects — structured data plus a severity —
and each channel renders them its own way. Same event, many presentations, one
source of truth.

Migration is incremental by design: an Event may carry a pre-rendered ``text``,
which channels use verbatim. Day one is byte-identical to today; call sites move
to structured ``data`` one at a time, and a web channel can be added without
touching strategy code at all.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable

log = logging.getLogger(__name__)


class EventKind(str, Enum):
    BOOT = "boot"
    ENTRY = "entry"
    EXIT = "exit"
    HEARTBEAT = "heartbeat"
    AUTH_FAILURE = "auth_failure"
    KEY_EXPIRY = "key_expiry"
    DRAWDOWN = "drawdown"
    DIGEST = "digest"
    COMMAND_REPLY = "command_reply"
    WARNING = "warning"


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


# Muting these would let an account go dark without anyone noticing, which is
# the precise failure the alerts exist to prevent. A channel may not opt out.
UNMUTABLE: frozenset[EventKind] = frozenset({
    EventKind.AUTH_FAILURE,
    EventKind.KEY_EXPIRY,
    EventKind.COMMAND_REPLY,
})


@dataclass(frozen=True, slots=True)
class Event:
    account_id: str
    kind: EventKind
    severity: Severity = Severity.INFO
    at: float = 0.0
    data: Mapping[str, Any] = field(default_factory=dict)
    text: str = ""
    dedupe_key: str | None = None
    cooldown_seconds: int | None = None

    @property
    def is_unmutable(self) -> bool:
        return self.kind in UNMUTABLE

    def as_dict(self) -> dict[str, Any]:
        """Wire format for a web channel, an event store, or a log line.

        ``text`` is deliberately excluded: it is a Telegram rendering artefact
        and letting it into the wire format would tempt a web client to display
        HTML meant for a chat app.
        """

        return {
            "account_id": self.account_id,
            "kind": self.kind.value,
            "severity": self.severity.value,
            "at": self.at,
            "data": dict(self.data),
        }


@runtime_checkable
class Channel(Protocol):
    """Anything that can deliver an Event. Telegram today; HTTP/web later."""

    kind: str

    def deliver(self, event: Event) -> bool:
        ...


class TelegramChannel:
    """Renders Events as Telegram HTML.

    Owns every emoji and every ``<b>`` in the system. Nothing upstream of this
    class knows Telegram exists.
    """

    kind = "telegram"

    _PREFIX = {
        Severity.INFO: "",
        Severity.WARN: "⚠️ ",
        Severity.CRITICAL: "🔴 ",
    }

    def __init__(self, client: Any, *, mute: frozenset[str] = frozenset(), label: str = ""):
        self.client = client
        self.mute = frozenset(m.lower() for m in mute)
        self.label = label

    def wants(self, event: Event) -> bool:
        if event.is_unmutable:
            return True
        return event.kind.value not in self.mute

    def render(self, event: Event) -> str:
        if event.text:
            return event.text
        head = f"{self._PREFIX.get(event.severity, '')}<b>{event.kind.value.replace('_', ' ').title()}</b>"
        if self.label:
            head = f"{head} — {self.label}"
        body = "\n".join(f"{key}: <code>{value}</code>" for key, value in event.data.items())
        return f"{head}\n━━━━━━━━━━━━━━━\n{body}" if body else head

    def deliver(self, event: Event) -> bool:
        if not self.wants(event):
            return False
        if not getattr(self.client, "configured", False):
            return False
        return bool(self.client.send_message(self.render(event)))


class EventBus:
    """Fans an Event out to every channel. Never raises.

    Delivery is best-effort by construction: a dead Telegram must not take the
    trading loop with it, and one failing channel must not starve the others.
    """

    def __init__(self, channels: "list[Channel] | tuple[Channel, ...]" = ()):
        self.channels: list[Channel] = list(channels)
        self.recent: list[Event] = []
        self._recent_limit = 200

    def add(self, channel: Channel) -> None:
        self.channels.append(channel)

    def emit(self, event: Event) -> int:
        """Deliver to every channel; return how many accepted it."""

        self.recent.append(event)
        if len(self.recent) > self._recent_limit:
            del self.recent[: len(self.recent) - self._recent_limit]
        delivered = 0
        for channel in self.channels:
            try:
                if channel.deliver(event):
                    delivered += 1
            except Exception:  # pragma: no cover - a channel may never break trading
                log.exception("channel %s failed to deliver %s",
                              getattr(channel, "kind", "?"), event.kind.value)
        return delivered

    def tail(self, limit: int = 50, *, account_id: str | None = None) -> list[dict[str, Any]]:
        """Read model for a future web UI: the last N events, newest last."""

        rows = [e for e in self.recent if account_id is None or e.account_id == account_id]
        return [e.as_dict() for e in rows[-limit:]]
