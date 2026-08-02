"""Phases 3 + 4 — typed events with pluggable channels, channel-agnostic commands."""
import pytest

from futuresbot.commands import (
    MUTATING,
    VERBS,
    Actor,
    Authorizer,
    Command,
    TelegramCommandSource,
    parse_command_text,
)
from futuresbot.events import (
    UNMUTABLE,
    Event,
    EventBus,
    EventKind,
    Severity,
    TelegramChannel,
)


class _FakeTelegram:
    configured = True

    def __init__(self):
        self.sent = []

    def send_message(self, text, **_kwargs):
        self.sent.append(text)
        return True


def _event(kind=EventKind.ENTRY, **kw):
    return Event(account_id=kw.pop("account_id", "main"), kind=kind, **kw)


# ==========================================================================
# Events
# ==========================================================================

def test_prerendered_text_passes_through_unchanged():
    # The migration contract: day one must be byte-identical to today.
    fake = _FakeTelegram()
    TelegramChannel(fake).deliver(_event(text="🚀 <b>ENTRY</b> BTC"))
    assert fake.sent == ["🚀 <b>ENTRY</b> BTC"]


def test_structured_data_renders_without_any_text():
    fake = _FakeTelegram()
    TelegramChannel(fake).deliver(_event(kind=EventKind.EXIT, data={"symbol": "ETH", "r": 5.0}))
    body = fake.sent[0]
    assert "Exit" in body and "ETH" in body and "5.0" in body


def test_wire_format_excludes_telegram_rendering():
    # A web client must never receive chat-app HTML.
    payload = _event(text="<b>bold</b>", data={"symbol": "SOL"}).as_dict()
    assert "text" not in payload
    assert payload["data"] == {"symbol": "SOL"}
    assert payload["kind"] == "entry"


def test_account_label_appears_only_when_set():
    fake = _FakeTelegram()
    TelegramChannel(fake, label="Test2").deliver(_event(kind=EventKind.HEARTBEAT, data={"x": 1}))
    assert "Test2" in fake.sent[0]

    plain = _FakeTelegram()
    TelegramChannel(plain).deliver(_event(kind=EventKind.HEARTBEAT, data={"x": 1}))
    assert "Test2" not in plain.sent[0]


def test_muting_suppresses_ordinary_events():
    fake = _FakeTelegram()
    channel = TelegramChannel(fake, mute=frozenset({"heartbeat"}))
    assert channel.deliver(_event(kind=EventKind.HEARTBEAT, data={"x": 1})) is False
    assert fake.sent == []


@pytest.mark.parametrize("kind", sorted(UNMUTABLE, key=lambda k: k.value))
def test_critical_events_cannot_be_muted(kind):
    # An account that has silenced its own auth failures goes dark unnoticed.
    fake = _FakeTelegram()
    channel = TelegramChannel(fake, mute=frozenset({k.value for k in EventKind}))
    assert channel.deliver(_event(kind=kind, text="x")) is True


def test_severity_prefixes_escalate():
    fake = _FakeTelegram()
    channel = TelegramChannel(fake)
    channel.deliver(_event(kind=EventKind.WARNING, severity=Severity.CRITICAL, data={"a": 1}))
    assert fake.sent[0].startswith("🔴")


def test_unconfigured_channel_delivers_nothing():
    class Off:
        configured = False

        def send_message(self, *_a, **_k):
            raise AssertionError("must not send")

    assert TelegramChannel(Off()).deliver(_event(text="x")) is False


# --- bus ------------------------------------------------------------------

def test_bus_fans_out_to_every_channel():
    a, b = _FakeTelegram(), _FakeTelegram()
    bus = EventBus([TelegramChannel(a), TelegramChannel(b)])
    assert bus.emit(_event(text="hello")) == 2
    assert a.sent == b.sent == ["hello"]


def test_one_broken_channel_never_starves_the_others():
    class Broken:
        kind = "broken"

        def deliver(self, _event):
            raise RuntimeError("down")

    good = _FakeTelegram()
    bus = EventBus([Broken(), TelegramChannel(good)])
    assert bus.emit(_event(text="still delivered")) == 1
    assert good.sent == ["still delivered"]


def test_bus_tail_is_a_read_model_filtered_by_account():
    bus = EventBus([])
    bus.emit(_event(account_id="main", text="a"))
    bus.emit(_event(account_id="test2", text="b"))
    assert len(bus.tail()) == 2
    assert [r["account_id"] for r in bus.tail(account_id="test2")] == ["test2"]


def test_bus_history_is_bounded():
    bus = EventBus([])
    for _ in range(250):
        bus.emit(_event(text="x"))
    assert len(bus.recent) == 200


# ==========================================================================
# Commands
# ==========================================================================

@pytest.mark.parametrize("text,expected", [
    ("/status", ("status", {})),
    ("/STATUS", ("status", {})),
    ("/status@mybot", ("status", {})),
    ("/close", ("close", {})),
    ("/close all", ("close", {"target": "all"})),
    ("/close eth_usdt", ("close", {"target": "ETH_USDT"})),
    ("/reconciliate", ("reconcile", {})),
])
def test_command_parsing(text, expected):
    assert parse_command_text(text) == expected


@pytest.mark.parametrize("text", ["", "hello", "close all", "/nonsense", "/", None])
def test_non_commands_are_ignored(text):
    assert parse_command_text(text) is None


def test_mutating_verbs_are_marked():
    assert Command("main", "close", Actor()).is_mutating
    assert not Command("main", "status", Actor()).is_mutating
    assert MUTATING <= set(VERBS)


# --- authorisation --------------------------------------------------------

def test_authorizer_is_fail_closed_on_an_empty_allowlist():
    # Today's check authorises EVERYONE when the chat id happens to be unset.
    auth = Authorizer(set())
    assert not auth.allows(Actor(id="123"), "status")


def test_authorizer_rejects_an_actor_with_no_identity():
    assert not Authorizer({"123"}).allows(Actor(id=""), "status")


def test_read_only_actors_can_look_but_not_touch():
    auth = Authorizer({"owner"}, allow_read_only={"viewer"})
    assert auth.allows(Actor(id="viewer"), "status")
    assert not auth.allows(Actor(id="viewer"), "close")
    assert auth.allows(Actor(id="owner"), "close")
    assert not auth.allows(Actor(id="stranger"), "status")


def test_read_only_flag_on_the_actor_also_blocks_mutation():
    auth = Authorizer({"owner"})
    assert not auth.allows(Actor(id="owner", read_only=True), "close")
    assert auth.allows(Actor(id="owner", read_only=True), "status")


# --- telegram source ------------------------------------------------------

class _Updates:
    def __init__(self, batches):
        self._batches = list(batches)
        self.calls = []

    def get_updates(self, *, offset=None, limit=25, timeout=0):
        self.calls.append(offset)
        return self._batches.pop(0) if self._batches else []


def _update(uid, text, user_id="u1", chat_id="c1"):
    return {"update_id": uid,
            "message": {"text": text, "from": {"id": user_id, "username": "rc"},
                        "chat": {"id": chat_id}}}


def test_source_produces_commands_and_advances_the_offset():
    client = _Updates([[_update(10, "/status"), _update(11, "/close all")]])
    source = TelegramCommandSource(client, "main")
    commands = source.poll()
    assert [c.verb for c in commands] == ["status", "close"]
    assert commands[1].target == "all"
    assert commands[0].account_id == "main"
    assert source.offset == 12


def test_source_authorises_on_user_id_not_chat_id():
    # In a group chat the chat id is shared by everyone in it.
    client = _Updates([[_update(1, "/close all", user_id="stranger", chat_id="group")]])
    source = TelegramCommandSource(client, "main", authorizer=Authorizer({"owner"}))
    assert source.poll() == []
    # ...but the offset still advanced, so a denied command is not retried forever.
    assert source.offset == 2


def test_source_ignores_chatter_and_malformed_updates():
    client = _Updates([[_update(1, "good morning"), {"update_id": 2}, "junk"]])
    assert TelegramCommandSource(client, "main").poll() == []


def test_source_stops_when_a_batch_is_short():
    client = _Updates([[_update(1, "/status")], [_update(2, "/pnl")]])
    source = TelegramCommandSource(client, "main", limit=25)
    assert len(source.poll()) == 1
    assert len(client.calls) == 1
