"""Notification orchestration for job scouting updates."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Mapping

from job_scout.notifier import telegram as telegram_notifier
from job_scout.state import SnapshotDiff, diff_rows, load_snapshot, save_snapshot
from job_scout.writers import ReportRow

logger = logging.getLogger(__name__)


def maybe_notify(
    rows: Iterable[ReportRow],
    output_dir: Path,
    config: Mapping[str, object],
) -> None:
    """Compare rows against snapshot and send notifications when enabled."""

    notifications = _as_dict(config.get("notifications"))
    enabled = bool(notifications.get("enabled", False))
    channels = notifications.get("channels") or []
    top_n = _parse_int(notifications.get("top_n", 5), 5)
    min_score = _parse_int(notifications.get("minimum_score", 0), 0)

    snapshot_path = output_dir / "state.json"
    previous = load_snapshot(snapshot_path)
    diff = diff_rows(previous, rows)
    save_snapshot(snapshot_path, diff.current_snapshot)

    if not enabled:
        logger.info("Notifications disabled; snapshot updated only.")
        return

    if "telegram" not in channels:
        logger.info("Notifications enabled but no supported channels configured.")
        return

    digest = format_digest(diff, top_n=top_n, minimum_score=min_score)
    if not digest:
        logger.info("No meaningful changes to notify.")
        return

    telegram_config = _as_dict(notifications.get("telegram"))
    if not telegram_config.get("enabled", False):
        logger.info("Telegram notifications disabled by config.")
        return

    bot_token_env = str(
        telegram_config.get("bot_token_env_var", "TELEGRAM_BOT_TOKEN")
    )
    chat_id_env = str(
        telegram_config.get("chat_id_env_var", "TELEGRAM_CHAT_ID")
    )
    sent = telegram_notifier.send_message(
        digest, bot_token_env=bot_token_env, chat_id_env=chat_id_env
    )
    if sent:
        logger.info("Notification sent via Telegram.")
    else:
        logger.info("Notification not sent via Telegram.")


def format_digest(
    diff: SnapshotDiff,
    top_n: int,
    minimum_score: int,
) -> str | None:
    """Format a concise notification digest for new/improved matches."""

    items: list[tuple[str, ReportRow]] = []
    for row in diff.new_rows:
        if (row.match.score or 0) >= minimum_score:
            items.append(("new", row))
    for row in diff.improved_rows:
        if (row.match.score or 0) >= minimum_score:
            items.append(("improved", row))

    if not items:
        return None

    items = sorted(
        items,
        key=lambda entry: (
            entry[1].match.score or 0,
            entry[1].posting.posted_at,
            entry[1].posting.id,
        ),
        reverse=True,
    )
    items = items[: max(top_n, 1)]

    lines: list[str] = []
    lines.append(
        "Job Scout updates "
        f"({len(diff.new_rows)} new, {len(diff.improved_rows)} improved)"
    )

    for index, (kind, row) in enumerate(items, start=1):
        posting = row.posting
        score = row.match.score or 0
        marker = "NEW" if kind == "new" else "IMPROVED"
        line = f"{index}. [{marker}] {posting.title} — {posting.company} (score {score})"
        if kind == "improved":
            prev = diff.previous_scores.get(_snapshot_key(row))
            if prev is not None:
                line += f" (was {prev})"
        lines.append(line)
        lines.append(_format_reasons(row))
        lines.append(posting.url)

    return "\n".join(lines)


def _format_reasons(row: ReportRow) -> str:
    penalties = row.match.score_penalties or row.match.penalties
    bonuses = row.match.score_bonuses
    segments: list[str] = []
    if bonuses:
        segments.append(f"Bonuses: {', '.join(bonuses)}")
    if penalties:
        segments.append(f"Penalties: {', '.join(penalties)}")
    if not segments:
        segments.append("Penalties: none")
    return "   " + " | ".join(segments)


def _snapshot_key(row: ReportRow) -> str:
    return f"{row.posting.source}:{row.posting.id}"


def _as_dict(raw: object) -> dict[str, object]:
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}


def _parse_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
