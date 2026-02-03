"""Telegram notifier for Job Scout."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


def send_message(text: str, bot_token_env: str, chat_id_env: str) -> bool:
    """Send a Telegram message, returning True on success."""

    bot_token = os.getenv(bot_token_env)
    chat_id = os.getenv(chat_id_env)
    if not bot_token or not chat_id:
        logger.warning(
            "Telegram disabled: missing %s or %s",
            bot_token_env,
            chat_id_env,
        )
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        logger.warning("Telegram HTTP error: %s", exc.code)
    except urllib.error.URLError as exc:
        logger.warning("Telegram connection error: %s", exc.reason)
    return False
