"""Notification orchestration for job scouting updates."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

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
        return NotificationResult(
            notified_count=0, notification_mode="disabled"
        )

    digest, mode, notified_rows = build_digest(
        diff, rows, top_n=top_n, minimum_score=min_score
    )
    sent, reason = telegram_notifier.send_message(digest)
    if sent:
        logger.info("Notification sent via Telegram.")
        updated_snapshot = mark_notified(diff.current_snapshot, notified_rows)
        save_snapshot(snapshot_path, updated_snapshot)
    else:
        if reason:
            logger.info("Telegram notification not sent: %s.", reason)
        else:
            logger.info("Telegram notification not sent.")
        save_snapshot(snapshot_path, diff.current_snapshot)
    return NotificationResult(
        notified_count=len(notified_rows), notification_mode=mode
    )


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

    ranked = _sort_ranked_rows(items)
    return ranked[: max(top_n, 1)]


def select_top_matches(
    rows: Iterable[ReportRow],
    top_n: int,
    minimum_score: int,
) -> list[ReportRow]:
    """Select top matches for daily digests."""

    candidates = [
        row
        for row in rows
        if row.match.matches_all
        and (row.match.score or 0) >= minimum_score
    ]
    ranked = _sort_rows(candidates)
    return ranked[: max(top_n, 1)]


def build_digest(
    diff: SnapshotDiff,
    rows: Iterable[ReportRow],
    top_n: int,
    minimum_score: int,
) -> tuple[str, str, Sequence[object]]:
    """Build a digest payload and determine notification mode."""

    notified_rows = select_notified_rows(
        diff, top_n=top_n, minimum_score=minimum_score
    )
    if notified_rows:
        return (
            _format_delta_digest(diff, notified_rows),
            "delta_digest",
            notified_rows,
        )
    top_rows = select_top_matches(
        rows, top_n=top_n, minimum_score=minimum_score
    )
    return (
        _format_daily_digest(top_rows),
        "daily_digest",
        top_rows,
    )


def _format_delta_digest(
    diff: SnapshotDiff,
    notified_rows: list[tuple[str, ReportRow]],
) -> str:
    lines: list[str] = []
    lines.append("Job Scout digest")
    lines.append(
        f"New/Improved ({len(diff.new_rows)} new, {len(diff.improved_rows)} improved)"
    )
    for index, (kind, row) in enumerate(notified_rows, start=1):
        marker = "NEW" if kind == "new" else "IMPROVED"
        prev = diff.previous_scores.get(_snapshot_key(row))
        lines.extend(
            _format_row_block(
                index=index,
                marker=marker,
                row=row,
                previous_score=prev if kind == "improved" else None,
            )
        )
    return "\n".join(lines)


def _format_daily_digest(rows: Sequence[ReportRow]) -> str:
    lines: list[str] = []
    lines.append("Job Scout daily digest")
    if not rows:
        lines.append("Top matches today: none found.")
        return "\n".join(lines)
    lines.append(f"Top matches today ({len(rows)})")
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
        f"{index}. {label}{posting.title} — {posting.company} "
        f"| Remote: {remote_level} | Location: {location} | Score: {score}"
    )
    if previous_score is not None:
        line += f" (was {previous_score})"
    return [
        line,
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


def _sort_ranked_rows(
    rows: list[tuple[str, ReportRow]]
) -> list[tuple[str, ReportRow]]:
    return sorted(
        rows,
        key=lambda entry: (
            -(entry[1].match.score or 0),
            entry[1].posting.id,
            entry[1].posting.source,
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
