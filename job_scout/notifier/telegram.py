"""Telegram notifier for Job Scout."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramSendResult:
    """Detailed Telegram send result with forensic-safe metadata."""

    sent: bool
    reason: str | None
    attempted: bool
    responses: list[dict[str, object]]
    chat_fingerprint: str | None
    thread_id: int | None
    chat_check: dict[str, object] | None = None


def send_message(
    text: str, reply_markup: dict | None = None
) -> tuple[bool, str | None]:
    """Send a Telegram message, returning (sent, reason)."""

    return send_messages([{"text": text, "reply_markup": reply_markup}])


def send_messages(
    messages: list[dict[str, object]]
) -> tuple[bool, str | None]:
    """Send one or more Telegram messages in sequence."""

    result = send_messages_detailed(messages)
    return result.sent, result.reason


def send_messages_detailed(
    messages: list[dict[str, object]],
    *,
    run_chat_check: bool = False,
) -> TelegramSendResult:
    """Send Telegram messages and return forensic response diagnostics."""

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    token_present = bool(bot_token)
    chat_id_present = bool(chat_id)
    chat_fingerprint = _chat_id_fingerprint(chat_id)
    thread_id = _resolve_thread_id()
    responses: list[dict[str, object]] = []
    if not token_present or not chat_id_present:
        reason = "missing Telegram configuration"
        logger.warning(
            "Telegram notification skipped (token_present=%s, chat_id_present=%s).",
            token_present,
            chat_id_present,
        )
        return TelegramSendResult(
            sent=False,
            reason=reason,
            attempted=False,
            responses=responses,
            chat_fingerprint=chat_fingerprint,
            thread_id=thread_id,
            chat_check=None,
        )

    chat_check = None
    if run_chat_check:
        chat_check = _telegram_get_chat(bot_token, str(chat_id), chat_fingerprint)

    status, body = _telegram_request_json(bot_token, "getMe")
    responses.append({"method": "getMe", "status": status, "response": body})
    if status is None:
        logger.warning("Telegram getMe failed (connection error).")
        return TelegramSendResult(
            sent=False,
            reason="connection error",
            attempted=True,
            responses=responses,
            chat_fingerprint=chat_fingerprint,
            thread_id=thread_id,
            chat_check=chat_check,
        )
    if status != 200 or not isinstance(body, dict) or not body.get("ok"):
        logger.warning("Telegram getMe failed (status=%s).", status)
        return TelegramSendResult(
            sent=False,
            reason="getMe failed",
            attempted=True,
            responses=responses,
            chat_fingerprint=chat_fingerprint,
            thread_id=thread_id,
            chat_check=chat_check,
        )

    for message in messages:
        text = str(message.get("text", ""))
        reply_markup = message.get("reply_markup")
        message_payload: dict[str, object] = {
            "chat_id": str(chat_id),
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            message_payload["reply_markup"] = reply_markup
        if thread_id is not None:
            message_payload["message_thread_id"] = thread_id
        payload = json.dumps(message_payload).encode("utf-8")
        status, body = _telegram_request_json(
            bot_token, "sendMessage", payload=payload
        )
        responses.append(
            {
                "method": "sendMessage",
                "status": status,
                "request": {
                    "chat_id_fingerprint": chat_fingerprint,
                    "message_thread_id": thread_id,
                },
                "response": body,
            }
        )
        if status is None:
            logger.warning("Telegram sendMessage failed (connection error).")
            return TelegramSendResult(
                sent=False,
                reason="connection error",
                attempted=True,
                responses=responses,
                chat_fingerprint=chat_fingerprint,
                thread_id=thread_id,
                chat_check=chat_check,
            )
        if status != 200 or not isinstance(body, dict) or not body.get("ok"):
            logger.warning("Telegram sendMessage failed (status=%s).", status)
            return TelegramSendResult(
                sent=False,
                reason="sendMessage failed",
                attempted=True,
                responses=responses,
                chat_fingerprint=chat_fingerprint,
                thread_id=thread_id,
                chat_check=chat_check,
            )

    logger.info("Telegram message sent.")
    return TelegramSendResult(
        sent=True,
        reason=None,
        attempted=True,
        responses=responses,
        chat_fingerprint=chat_fingerprint,
        thread_id=thread_id,
        chat_check=chat_check,
    )


def get_updates(
    offset: int | None = None,
) -> tuple[list[dict], str | None]:
    """Fetch Telegram updates for feedback callbacks."""

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return [], "missing Telegram configuration"
    payload: dict[str, object] = {"timeout": 0}
    if offset is not None:
        payload["offset"] = offset
    status, body = _telegram_request_payload(
        bot_token, "getUpdates", payload=json.dumps(payload).encode("utf-8")
    )
    if status is None:
        return [], "connection error"
    if status != 200:
        return [], "getUpdates failed"
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return [], "invalid response"
    if not data.get("ok"):
        return [], "getUpdates not ok"
    result = data.get("result", [])
    if isinstance(result, list):
        return result, None
    return [], "invalid response"


def answer_callback_query(callback_query_id: str) -> bool:
    """Acknowledge a Telegram callback query."""

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return False
    payload = json.dumps({"callback_query_id": callback_query_id}).encode(
        "utf-8"
    )
    status, _description = _telegram_request(
        bot_token, "answerCallbackQuery", payload=payload
    )
    return status == 200


def _telegram_get_chat(
    bot_token: str, chat_id: str, fingerprint: str | None
) -> dict[str, object]:
    payload = json.dumps({"chat_id": chat_id}).encode("utf-8")
    status, body = _telegram_request_json(bot_token, "getChat", payload=payload)
    base: dict[str, object] = {
        "status": status,
        "id_fingerprint": fingerprint,
    }
    if isinstance(body, dict) and body.get("ok"):
        result = body.get("result")
        if isinstance(result, dict):
            base.update(
                {
                    "ok": True,
                    "type": result.get("type"),
                    "title": result.get("title") if isinstance(result.get("title"), str) else None,
                    "is_forum": bool(result.get("is_forum", False)),
                }
            )
            return base
    base["ok"] = False
    if isinstance(body, dict):
        base["error_code"] = body.get("error_code")
        base["description"] = body.get("description")
    return base


def _resolve_thread_id() -> int | None:
    raw = os.getenv("TELEGRAM_MESSAGE_THREAD_ID", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning("Ignoring invalid TELEGRAM_MESSAGE_THREAD_ID value.")
        return None


def _chat_id_fingerprint(chat_id: str | None) -> str | None:
    if not chat_id:
        return None
    return hashlib.sha256(chat_id.encode("utf-8")).hexdigest()[:8]


def _telegram_request_json(
    bot_token: str,
    method: str,
    payload: bytes | None = None,
) -> tuple[int | None, dict[str, object] | str]:
    status, body = _telegram_request_payload(bot_token, method, payload=payload)
    if status is None:
        return None, body
    try:
        decoded = json.loads(body)
        if isinstance(decoded, dict):
            return status, decoded
    except json.JSONDecodeError:
        pass
    return status, body


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


def _telegram_request_payload(
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
            if isinstance(body, bytes):
                return response.status, body.decode(
                    "utf-8", errors="replace"
                )
            return response.status, str(body)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        payload_text = (
            body.decode("utf-8", errors="replace")
            if isinstance(body, bytes)
            else str(body)
        )
        return exc.code, payload_text
    except urllib.error.URLError as exc:
        return None, str(exc.reason)


def _extract_description(body: bytes | str) -> str:
    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="replace")
    else:
        text = str(body)
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            description = payload.get("description")
            if isinstance(description, str):
                return description
    except json.JSONDecodeError:
        pass
    return text


def _send_message_hint(description: str) -> str | None:
    lowered = description.lower()
    if "chat not found" in lowered:
        return "check TELEGRAM_CHAT_ID"
    if "bot was blocked" in lowered:
        return "unblock the bot in Telegram"
    if "can't parse" in lowered or "message text is empty" in lowered:
        return "validate message payload format"
    return None
