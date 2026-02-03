"""Notification orchestration for job scouting updates."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from job_scout.notifier import telegram as telegram_notifier
from job_scout.state import (
    Snapshot,
    load_snapshot,
    mark_notified,
    save_snapshot,
)
from job_scout.writers import ReportRow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationResult:
    """Summary of notification behavior for the run."""

    notified_count: int
    notification_mode: str


def maybe_notify(
    rows: Iterable[ReportRow],
    output_dir: Path,
    config: Mapping[str, object],
) -> NotificationResult:
    """Send the daily digest notification for the current run."""

    notifications = _as_dict(config.get("notifications"))
    telegram_config = _as_dict(notifications.get("telegram"))
    top_n = _parse_int(telegram_config.get("top_n", 10), 10)
    min_score = _parse_int(telegram_config.get("min_score", 0), 0)
    digest_config = _as_dict(config.get("digest"))
    digest_mode = str(digest_config.get("mode", "daily_window"))
    if digest_mode != "daily_window":
        logger.info(
            "Digest mode '%s' not supported; using daily_window.", digest_mode
        )
    window_hours = _parse_int(digest_config.get("window_hours", 24), 24)
    digest_top_n = _parse_int(digest_config.get("top_n", top_n), top_n)

    snapshot_path = output_dir / "last_run.json"
    previous = load_snapshot(snapshot_path)
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=window_hours)
    daily_rows = _select_daily_window_rows(
        rows,
        previous,
        window_start,
        now,
        minimum_score=min_score,
    )
    total_in_window = len(daily_rows)
    top_rows = _sort_rows(daily_rows)[: max(digest_top_n, 1)] if daily_rows else []

    digest = _format_daily_window_digest(
        top_rows,
        total_in_window=total_in_window,
        window_hours=window_hours,
    )
    sent, reason = telegram_notifier.send_message(digest)
    if sent:
        logger.info("Notification sent via Telegram.")
        updated_snapshot = mark_notified(previous, top_rows)
        save_snapshot(snapshot_path, updated_snapshot)
    else:
        if reason:
            logger.info("Telegram notification not sent: %s.", reason)
        else:
            logger.info("Telegram notification not sent.")
        fallback_snapshot = Snapshot(
            generated_at=now.isoformat(),
            jobs=dict(previous.jobs),
        )
        save_snapshot(snapshot_path, fallback_snapshot)
    return NotificationResult(
        notified_count=len(top_rows),
        notification_mode="daily_window",
    )


def _select_daily_window_rows(
    rows: Iterable[ReportRow],
    snapshot: Snapshot,
    window_start: datetime,
    window_end: datetime,
    minimum_score: int,
) -> list[ReportRow]:
    candidates: list[ReportRow] = []
    for row in rows:
        if not row.match.matches_all:
            continue
        if (row.match.score or 0) < minimum_score:
            continue
        if _was_previously_notified(snapshot, row):
            continue
        if not _posted_within_window(
            row, window_start=window_start, window_end=window_end
        ):
            continue
        candidates.append(row)
    return candidates


def _posted_within_window(
    row: ReportRow,
    window_start: datetime,
    window_end: datetime,
) -> bool:
    posted_at = getattr(row.posting, "posted_at", None)
    if not isinstance(posted_at, datetime):
        logger.warning(
            "Skipping digest row with missing/invalid posted_at: %s.",
            _snapshot_key(row),
        )
        return False
    if posted_at.tzinfo is None:
        logger.warning(
            "Skipping digest row with naive posted_at: %s.",
            _snapshot_key(row),
        )
        return False
    try:
        posted_at_utc = posted_at.astimezone(timezone.utc)
    except (ValueError, OSError) as exc:
        logger.warning(
            "Skipping digest row with invalid posted_at: %s (%s).",
            _snapshot_key(row),
            exc,
        )
        return False
    return window_start <= posted_at_utc <= window_end


def _was_previously_notified(
    snapshot: Snapshot,
    row: ReportRow,
) -> bool:
    entry = snapshot.jobs.get(_snapshot_key(row))
    if not isinstance(entry, dict):
        return False
    notified_at = entry.get("notified_at")
    return bool(notified_at)


def _format_daily_window_digest(
    rows: Sequence[ReportRow],
    total_in_window: int,
    window_hours: int,
) -> str:
    if total_in_window == 0:
        return "No new job postings published in the last 24 hours."
    lines: list[str] = []
    lines.append(f"Job Scout — Daily Digest (last {window_hours}h)")
    lines.append("Published yesterday")
    lines.append(f"Total in window: {total_in_window}")
    for index, row in enumerate(rows, start=1):
        lines.extend(
            _format_row_block(index=index, marker=None, row=row)
        )
    return "\n".join(lines)


def _format_row_block(
    *,
    index: int,
    row: ReportRow,
    marker: str | None,
    previous_score: int | None = None,
) -> list[str]:
    posting = row.posting
    score = row.match.score or 0
    location = posting.location_text or "Unknown location"
    remote_level = row.match.remote_level or "unknown"
    label = f"[{marker}] " if marker else ""
    line = (
        f"{index}. {label}{posting.title} — {posting.company}"
    )
    details = (
        f"   Remote: {remote_level} | Location: {location} | Score: {score}"
    )
    if previous_score is not None:
        details += f" (was {previous_score})"
    return [
        line,
        details,
        _format_rationale(row),
        posting.url,
    ]


def _format_rationale(row: ReportRow) -> str:
    penalties = row.match.score_penalties or row.match.penalties
    bonuses = row.match.score_bonuses
    segments: list[str] = []
    if bonuses:
        segments.append(f"bonuses: {', '.join(bonuses)}")
    if penalties:
        segments.append(f"penalties: {', '.join(penalties)}")
    if not segments:
        segments.append("penalties: none")
    return "   Reason: " + "; ".join(segments)


def _snapshot_key(row: ReportRow) -> str:
    return f"{row.posting.source}:{row.posting.id}"


def _sort_rows(rows: Iterable[ReportRow]) -> list[ReportRow]:
    return sorted(
        list(rows),
        key=lambda row: (
            -(row.match.score or 0),
            row.posting.id,
            row.posting.source,
        ),
    )


def _as_dict(raw: object) -> dict[str, object]:
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}


def _parse_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
