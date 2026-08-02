"""Channel-agnostic commands — phase 4 of docs/MULTI_ACCOUNT_DESIGN.md.

Today a command is Telegram text, parsed and dispatched inline in one long
if/elif chain, and authorisation is a chat-id comparison buried in the middle of
the polling loop. That couples "what the operator asked for" to "how it
arrived", and it means an HTTP front end would have to fake Telegram updates.

Here a command is a value. ``TelegramCommandSource`` produces them from
getUpdates; a future ``HttpCommandSource`` would produce identical ones from
``POST /accounts/{id}/commands``. Authorisation is decided once, on the Actor,
in ``Authorizer`` — one place to read and one place to get right.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

log = logging.getLogger(__name__)

# Verbs the runtime understands. Kept as data so a web front end can render the
# available actions without hardcoding a second copy of this list.
VERBS: dict[str, str] = {
    "status": "Account status and every open position",
    "why": "Per-symbol entry diagnosis",
    "pnl": "Realized and open P&L",
    "logs": "Recent runtime activity",
    "reconcile": "Adopt untracked exchange positions",
    "pause": "Pause new entries; open positions stay managed",
    "resume": "Resume new entries",
    "close": "Close a position, or all of them",
    "help": "Show available commands",
}

# Verbs that move money or change trading state. A web front end should confirm
# these; an audit trail must record them; read-only actors may not issue them.
MUTATING: frozenset[str] = frozenset({"pause", "resume", "close", "reconcile"})


@dataclass(frozen=True, slots=True)
class Actor:
    """Who issued a command, and over which channel."""

    channel: str = "telegram"
    id: str = ""
    display: str = ""
    read_only: bool = False

    def __str__(self) -> str:
        return f"{self.display or self.id or '?'}@{self.channel}"


@dataclass(frozen=True, slots=True)
class Command:
    account_id: str
    verb: str
    actor: Actor
    args: Mapping[str, Any] = field(default_factory=dict)
    received_at: float = 0.0
    raw: str = ""

    @property
    def is_mutating(self) -> bool:
        return self.verb in MUTATING

    @property
    def target(self) -> str | None:
        """Symbol argument for /close, or None. ``"all"`` stays as-is."""

        value = self.args.get("target")
        return str(value) if value else None


@runtime_checkable
class CommandSource(Protocol):
    kind: str

    def poll(self) -> "list[Command]":
        ...


class Authorizer:
    """Single decision point for "may this actor do this?".

    Fail-closed by construction: an empty allowlist authorises nobody. Today's
    check reads ``if self.config.telegram_chat_id and chat_id != ...`` — which
    authorises EVERYONE when the chat id happens to be unset. That is fine for
    one operator who always sets it and unacceptable once an account belongs to
    someone else.
    """

    def __init__(self, allowed: "set[str] | frozenset[str]", *,
                 allow_read_only: "set[str] | frozenset[str]" = frozenset()):
        self.allowed = frozenset(str(a).strip() for a in allowed if str(a).strip())
        self.allow_read_only = frozenset(str(a).strip() for a in allow_read_only if str(a).strip())

    def allows(self, actor: Actor, verb: str) -> bool:
        identity = str(actor.id).strip()
        if not identity:
            return False
        if identity in self.allowed:
            return not (actor.read_only and verb in MUTATING)
        if identity in self.allow_read_only:
            return verb not in MUTATING
        return False


def parse_command_text(text: str) -> tuple[str, dict[str, Any]] | None:
    """Parse ``/close ETH_USDT`` into ``("close", {"target": "ETH_USDT"})``.

    Returns None for anything that is not a recognised command, so unknown text
    in a chat is ignored rather than dispatched.
    """

    raw = (text or "").strip()
    if not raw.startswith("/"):
        return None
    token, _sep, rest = raw.partition(" ")
    verb = token[1:].split("@", 1)[0].strip().lower()
    # Historic alias kept so existing muscle memory still works.
    if verb == "reconciliate":
        verb = "reconcile"
    if verb not in VERBS:
        return None
    arg = rest.strip()
    args: dict[str, Any] = {}
    if verb == "close" and arg:
        args["target"] = "all" if arg.lower() == "all" else arg.upper()
    elif arg:
        args["arg"] = arg
    return verb, args


class TelegramCommandSource:
    """Turns Telegram getUpdates into Commands.

    Offset bookkeeping stays here rather than in the runtime, because it is a
    Telegram transport detail. A web source has no equivalent.
    """

    kind = "telegram"

    def __init__(self, client: Any, account_id: str, *,
                 authorizer: Authorizer | None = None,
                 limit: int = 25, max_batches: int = 250):
        self.client = client
        self.account_id = account_id
        self.authorizer = authorizer
        self.limit = limit
        self.max_batches = max_batches
        self.offset = 0

    def _actor(self, message: Mapping[str, Any]) -> Actor:
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        # Prefer the user id: in a group chat the chat id is shared by everyone
        # in it, so authorising on chat id authorises the whole group.
        identity = str(sender.get("id") or chat.get("id") or "")
        display = str(sender.get("username") or sender.get("first_name") or "")
        return Actor(channel=self.kind, id=identity, display=display)

    def poll(self) -> list[Command]:
        commands: list[Command] = []
        for _ in range(self.max_batches):
            updates = self.client.get_updates(
                offset=self.offset or None, limit=self.limit, timeout=0)
            if not updates:
                break
            for update in updates:
                if not isinstance(update, dict):
                    continue
                update_id = int(update.get("update_id") or 0)
                if update_id:
                    self.offset = max(self.offset, update_id + 1)
                message = update.get("message") or {}
                if not isinstance(message, dict):
                    continue
                parsed = parse_command_text(str(message.get("text") or ""))
                if parsed is None:
                    continue
                verb, args = parsed
                actor = self._actor(message)
                if self.authorizer is not None and not self.authorizer.allows(actor, verb):
                    log.warning("[COMMAND_DENIED] account=%s verb=%s actor=%s",
                                self.account_id, verb, actor)
                    continue
                commands.append(Command(
                    account_id=self.account_id, verb=verb, actor=actor, args=args,
                    received_at=time.time(), raw=str(message.get("text") or ""),
                ))
            if len(updates) < self.limit:
                break
        return commands


def build_help(verbs: Mapping[str, str] = VERBS) -> str:
    lines = [f"/{verb} — {description}" for verb, description in verbs.items()]
    return "\n".join(lines)
