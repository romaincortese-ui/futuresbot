"""A long Telegram message must not fail silently.

Telegram caps a message at 4096 characters. Over that it answers 400 with
"message is too long" - which is NOT a parse error, so the existing retry
branch does not apply, both attempts return False, and the whole message
vanishes behind one debug log line.

/report renders ten KPIs, each with a wrapped note, plus a balance chart added
2026-09-03. It now sits close enough to the limit that adding to it is a
silent-failure risk rather than a formatting one, and /report is the command
consulted before a withdrawal.
"""
from __future__ import annotations

from futuresbot.telegram import CHUNK, LIMIT, _split_message


def test_short_messages_are_not_split():
    assert _split_message("one\ntwo\nthree") == ["one\ntwo\nthree"]


def test_every_part_is_under_the_limit():
    text = "\n".join("line %d %s" % (i, "x" * 60) for i in range(400))
    parts = _split_message(text)
    assert len(parts) > 1
    assert all(len(p) <= LIMIT for p in parts)


def test_nothing_is_lost_in_the_split():
    text = "\n".join("row %d" % i for i in range(2000))
    joined = "\n".join(_split_message(text))
    for probe in ("row 0", "row 999", "row 1999"):
        assert probe in joined


def test_a_pre_block_is_closed_and_reopened_across_a_split():
    """A split landing inside <pre> leaves an unclosed tag, which is a parse
    error - and the fallback then strips ALL html from that part, destroying
    the chart's alignment."""
    body = "\n".join("col %d" % i for i in range(1200))
    text = "header\n<pre>" + body + "</pre>\nfooter"
    parts = _split_message(text)
    assert len(parts) > 1
    for p in parts:
        assert p.count("<pre>") == p.count("</pre>"), p[:80]


def test_a_single_over_long_line_is_hard_cut_not_emitted_whole():
    """One 9000-char line has no boundary to split on. It must still not be
    sent over-length."""
    parts = _split_message("y" * 9000)
    assert len(parts) > 1
    assert all(len(p) <= CHUNK for p in parts)


def test_send_message_splits_rather_than_failing(monkeypatch):
    from futuresbot.telegram import TelegramClient

    c = TelegramClient("tok", "chat")
    sent = []
    monkeypatch.setattr(c, "_send_one",
                        lambda text, parse_mode="HTML": sent.append(text) or True)
    long_text = "\n".join("line %d" % i for i in range(3000))
    assert c.send_message(long_text) is True
    assert len(sent) > 1, "the message was not split"
    assert all(len(s) <= LIMIT for s in sent)


def test_one_failed_part_fails_the_whole_send(monkeypatch):
    """A partially delivered report is worse than a reported failure."""
    from futuresbot.telegram import TelegramClient

    c = TelegramClient("tok", "chat")
    calls = []

    def _one(text, parse_mode="HTML"):
        calls.append(text)
        return len(calls) != 2

    monkeypatch.setattr(c, "_send_one", _one)
    long_text = "\n".join("line %d" % i for i in range(3000))
    assert c.send_message(long_text) is False
    assert len(calls) > 2, "later parts must still be attempted"
