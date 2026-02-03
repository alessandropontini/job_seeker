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
    missing = []
    if not bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not chat_id:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        reason = f"missing secrets: {', '.join(missing)}"
        logger.warning("Telegram notification skipped (%s).", reason)
        return False, reason

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
            if 200 <= response.status < 300:
                return True, None
            reason = f"unexpected response status {response.status}"
            logger.warning("Telegram notification skipped (%s).", reason)
            return False, reason
    except urllib.error.HTTPError as exc:
        hint = "check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
        reason = f"HTTP error {exc.code}; {hint}"
        logger.warning("Telegram notification skipped (%s).", reason)
        return False, reason
    except urllib.error.URLError as exc:
        reason = f"connection error: {exc.reason}"
        logger.warning("Telegram notification skipped (%s).", reason)
        return False, reason
