from __future__ import annotations

import logging
import re
from typing import Any

import requests


log = logging.getLogger(__name__)

HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return HTML_TAG_RE.sub("", text)


class TelegramClient:
    def __init__(self, token: str, chat_id: str, *, session: requests.Session | None = None):
        self.token = token.strip()
        self.chat_id = chat_id.strip()
        self.session = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send_message(self, text: str, *, parse_mode: str = "HTML") -> bool:
        if not self.configured:
            return False
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