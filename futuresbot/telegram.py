from __future__ import annotations

import logging
import re
from typing import Any

import requests


log = logging.getLogger(__name__)

HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return HTML_TAG_RE.sub("", text)


LIMIT = 4096
CHUNK = 3800        # headroom for a re-opened <pre> and the HTML we may re-add


def _split_message(text: str, limit: int = CHUNK) -> list[str]:
    """Split on line boundaries, keeping <pre> blocks closed.

    A naive split can land inside a <pre>, which leaves an unclosed tag; that
    is a parse error, and the fallback strips ALL html from that part. So the
    open block is closed at the end of a chunk and re-opened at the start of
    the next.
    """
    parts: list[str] = []
    buf: list[str] = []
    size = 0
    in_pre = False
    for line in text.split(chr(10)):
        # a line longer than the limit on its own cannot be split safely on a
        # boundary; hard-cut it rather than emit an over-length part
        while len(line) > limit:
            head, line = line[:limit], line[limit:]
            if buf:
                parts.append(chr(10).join(buf))
                buf, size = [], 0
            parts.append(head)
        if size + len(line) + 1 > limit and buf:
            tail = buf + (["</pre>"] if in_pre else [])
            parts.append(chr(10).join(tail))
            buf = ["<pre>"] if in_pre else []
            size = len(buf[0]) if buf else 0
        buf.append(line)
        size += len(line) + 1
        opens = line.count("<pre>")
        closes = line.count("</pre>")
        if opens or closes:
            in_pre = opens > closes
    if buf:
        parts.append(chr(10).join(buf))
    return [p for p in parts if p.strip()]


class TelegramClient:
    def __init__(self, token: str, chat_id: str, *, session: requests.Session | None = None):
        self.token = token.strip()
        self.chat_id = chat_id.strip()
        self.session = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send_message(self, text: str, *, parse_mode: str = "HTML") -> bool:
        """Send `text`, splitting it if it exceeds Telegram's 4096-char limit.

        Without the split a long message fails SILENTLY. Telegram answers 400
        with "message is too long", which is not a parse error, so the retry
        branch below does not apply and both attempts return False - surfacing
        as one debug log line. /report renders ten KPIs, each with a wrapped
        note, plus a balance chart, so it sits close enough to the limit that
        adding to it is a silent-failure risk rather than a formatting one.
        """
        if not self.configured:
            return False
        if len(text) > LIMIT:
            return all([self._send_one(part, parse_mode=parse_mode)
                        for part in _split_message(text)])
        return self._send_one(text, parse_mode=parse_mode)

    def _send_one(self, text: str, *, parse_mode: str = "HTML") -> bool:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode}
        for attempt in range(2):
            try:
                response = self.session.post(url, json=payload, timeout=8)
            except Exception:
                if attempt == 1:
                    return False
                continue
            if response.ok:
                return True
            try:
                body = response.json() if response.content else {}
            except Exception:
                body = {}
            description = str(body.get("description") or "")
            if response.status_code == 400 and "parse" in description.lower() and parse_mode:
                payload = {"chat_id": self.chat_id, "text": strip_html(text), "parse_mode": ""}
                continue
            if attempt == 1:
                return False
        return False

    def get_updates(self, *, offset: int | None = None, limit: int = 5, timeout: int = 0) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        params: dict[str, Any] = {"timeout": timeout, "limit": limit}
        if offset is not None:
            params["offset"] = offset
        try:
            response = self.session.get(
                f"https://api.telegram.org/bot{self.token}/getUpdates",
                params=params,
                timeout=max(5, timeout + 5),
            )
        except Exception as exc:
            log.warning("Telegram getUpdates request failed (offset=%s limit=%s): %s", offset, limit, exc)
            return []
        if not response.ok:
            try:
                body = response.json() if response.content else {}
            except Exception:
                body = {}
            log.warning(
                "Telegram getUpdates HTTP %s (offset=%s limit=%s): %s",
                response.status_code,
                offset,
                limit,
                body.get("description") if isinstance(body, dict) else "",
            )
            return []
        try:
            payload = response.json()
        except Exception as exc:
            log.warning("Telegram getUpdates JSON decode failed: %s", exc)
            return []
        result = payload.get("result", []) if isinstance(payload, dict) else []
        return [item for item in result if isinstance(item, dict)]

    def delete_webhook(self, *, drop_pending_updates: bool = False) -> dict[str, Any]:
        """Force long-polling mode: remove any leftover webhook (a webhook makes
        getUpdates return 409 Conflict, so /status etc. silently never arrive).
        """

        if not self.configured:
            return {"ok": False, "description": "telegram not configured"}
        try:
            response = self.session.post(
                f"https://api.telegram.org/bot{self.token}/deleteWebhook",
                json={"drop_pending_updates": bool(drop_pending_updates)},
                timeout=8,
            )
            payload = response.json() if response.content else {}
        except Exception as exc:
            log.warning("Telegram deleteWebhook failed: %s", exc)
            return {"ok": False, "description": str(exc)}
        if not isinstance(payload, dict):
            return {"ok": False, "description": "non-dict response"}
        return payload

    def get_webhook_info(self) -> dict[str, Any]:
        if not self.configured:
            return {}
        try:
            response = self.session.get(
                f"https://api.telegram.org/bot{self.token}/getWebhookInfo",
                timeout=8,
            )
            payload = response.json() if response.content else {}
        except Exception as exc:
            log.warning("Telegram getWebhookInfo failed: %s", exc)
            return {}
        if not isinstance(payload, dict):
            return {}
        result = payload.get("result")
        return result if isinstance(result, dict) else {}