"""Telegram notifier for Job Scout."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


def send_message(text: str) -> tuple[bool, str | None]:
    """Send a Telegram message, returning (sent, reason)."""

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    token_present = bool(bot_token)
    chat_id_present = bool(chat_id)
    if not token_present or not chat_id_present:
        reason = "missing Telegram configuration"
        logger.warning(
            "Telegram notification skipped (token_present=%s, chat_id_present=%s).",
            token_present,
            chat_id_present,
        )
        return False, reason

    status, description = _telegram_request(bot_token, "getMe")
    if status is None:
        logger.warning("Telegram getMe failed (connection error): %s.", description)
        return False, "connection error"
    if status != 200:
        logger.warning(
            "Telegram getMe failed (status=%s): %s.", status, description
        )
        return False, "getMe failed"
    logger.info("Telegram token validated via getMe.")

    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    status, description = _telegram_request(
        bot_token, "sendMessage", payload=payload
    )
    if status is None:
        logger.warning(
            "Telegram sendMessage failed (connection error): %s.", description
        )
        return False, "connection error"
    if status != 200:
        hint = _send_message_hint(description)
        if hint:
            logger.warning(
                "Telegram sendMessage failed (status=%s): %s. Hint: %s.",
                status,
                description,
                hint,
            )
        else:
            logger.warning(
                "Telegram sendMessage failed (status=%s): %s.",
                status,
                description,
            )
        return False, "sendMessage failed"

    logger.info("Telegram message sent.")
    return True, None


def _telegram_request(
    bot_token: str,
    method: str,
    payload: bytes | None = None,
) -> tuple[int | None, str]:
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
            return response.status, _extract_description(body)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        return exc.code, _extract_description(body)
    except urllib.error.URLError as exc:
        return None, str(exc.reason)


def _extract_description(payload: bytes | str | None) -> str:
    if not payload:
        return "no description"
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="replace")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return "no description"
    description = data.get("description")
    return description or "no description"


def _send_message_hint(description: str) -> str | None:
    lowered = description.lower()
    if "chat not found" in lowered:
        return "Likely wrong chat_id or bot has not been added/started."
    if "not enough rights" in lowered or "need administrator rights" in lowered:
        return "Bot lacks administrator rights in the target chat/channel."
    if "bot was blocked by the user" in lowered:
        return "The user has blocked the bot."
    return None
