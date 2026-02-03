"""Notification orchestration for job scouting updates."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Mapping

from job_scout.notifier import telegram as telegram_notifier
from job_scout.state import (
    SnapshotDiff,
    diff_rows,
    load_snapshot,
    mark_notified,
    save_snapshot,
)
from job_scout.writers import ReportRow

logger = logging.getLogger(__name__)


def maybe_notify(
    rows: Iterable[ReportRow],
    output_dir: Path,
    config: Mapping[str, object],
) -> None:
    """Compare rows against snapshot and send notifications when enabled."""

    notifications = _as_dict(config.get("notifications"))
    telegram_config = _as_dict(notifications.get("telegram"))
    enabled = bool(telegram_config.get("enabled", False))
    top_n = _parse_int(telegram_config.get("top_n", 5), 5)
    min_score = _parse_int(telegram_config.get("min_score", 0), 0)
    min_improvement = _parse_int(
        telegram_config.get("min_score_improvement", 5), 5
    )

    snapshot_path = output_dir / "last_run.json"
    previous = load_snapshot(snapshot_path)
    diff = diff_rows(previous, rows, min_improvement=min_improvement)

    if not enabled:
        logger.info("Notifications disabled; snapshot updated only.")
        save_snapshot(snapshot_path, diff.current_snapshot)
        return

    notified_rows = select_notified_rows(
        diff, top_n=top_n, minimum_score=min_score
    )
    digest = format_digest(
        diff, notified_rows=notified_rows
    )
    if not digest:
        logger.info("No meaningful changes to notify.")
        save_snapshot(snapshot_path, diff.current_snapshot)
        return
    sent, reason = telegram_notifier.send_message(digest)
    if sent:
        logger.info("Notification sent via Telegram.")
        updated_snapshot = mark_notified(diff.current_snapshot, notified_rows)
        save_snapshot(snapshot_path, updated_snapshot)
    else:
        if reason:
            logger.warning("Telegram notification skipped: %s.", reason)
        else:
            logger.warning("Telegram notification skipped.")
        save_snapshot(snapshot_path, diff.current_snapshot)


def select_notified_rows(
    diff: SnapshotDiff,
    top_n: int,
    minimum_score: int,
) -> list[tuple[str, ReportRow]]:
    """Select which rows to notify based on thresholds and ranking."""

    items: list[tuple[str, ReportRow]] = []
    for row in diff.new_rows:
        if (row.match.score or 0) >= minimum_score:
            items.append(("new", row))
    for row in diff.improved_rows:
        if (row.match.score or 0) >= minimum_score:
            items.append(("improved", row))

    items = sorted(
        items,
        key=lambda entry: (
            entry[1].match.score or 0,
            entry[1].posting.posted_at,
            entry[1].posting.id,
        ),
        reverse=True,
    )
    return items[: max(top_n, 1)]


def format_digest(
    diff: SnapshotDiff,
    notified_rows: list[tuple[str, ReportRow]],
) -> str | None:
    """Format a concise notification digest for new/improved matches."""

    if not notified_rows:
        return None

    lines: list[str] = []
    lines.append(
        "Job Scout updates "
        f"({len(diff.new_rows)} new, {len(diff.improved_rows)} improved)"
    )

    for index, (kind, row) in enumerate(notified_rows, start=1):
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
    hard_reasons = row.match.hard_reject_reasons
    segments: list[str] = []
    if bonuses:
        segments.append(f"Bonuses: {', '.join(bonuses)}")
    if penalties:
        segments.append(f"Penalties: {', '.join(penalties)}")
    if hard_reasons:
        segments.append(f"Hard reasons: {', '.join(hard_reasons)}")
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
