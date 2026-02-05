"""Notification orchestration for job scouting updates."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from job_scout.channels import select_channels
from job_scout.notifier import telegram as telegram_notifier
from job_scout.preferences import (
    PreferenceProfile,
    save_profile,
    update_feedback_cache,
)
from job_scout.state import (
    Snapshot,
    load_snapshot,
    mark_notified,
    save_run_state,
)
from job_scout.writers import ReportRow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationResult:
    """Summary of notification behavior for the run."""

    notified_count: int
    notification_mode: str
    skipped_reason: str | None = None


def maybe_notify(
    rows: Iterable[ReportRow],
    output_dir: Path,
    config: Mapping[str, object],
    *,
    preference_profile: PreferenceProfile | None = None,
    preference_path: Path | None = None,
) -> NotificationResult:
    """Send the daily digest notification for the current run."""

    notifications = _as_dict(config.get("notifications"))
    telegram_config = _as_dict(notifications.get("telegram"))
    dedupe_config = _as_dict(notifications.get("dedupe"))
    telegram_enabled = bool(telegram_config.get("enabled", True))
    dry_run = bool(telegram_config.get("dry_run", False))

    min_score = _parse_int(telegram_config.get("min_score", 0), 0)
    digest_config = _as_dict(config.get("digest"))
    digest_mode = str(digest_config.get("mode", "daily_window"))
    if digest_mode != "daily_window":
        logger.info(
            "Digest mode '%s' not supported; using daily_window.",
            digest_mode,
        )
    window_hours = _parse_int(digest_config.get("window_hours", 24), 24)

    snapshot_path = output_dir / "last_run.json"
    previous = load_snapshot(snapshot_path)
    now = _now()
    window_start = now - timedelta(hours=window_hours)

    daily_rows = _select_daily_window_rows(
        rows,
        window_start,
        now,
        minimum_score=min_score,
    )
    total_in_window = len(daily_rows)

    exclude_ids = set()
    if preference_profile:
        personalization = _as_dict(config.get("personalization"))
        if personalization.get("duplicate_action", "skip") == "skip":
            exclude_ids = preference_profile.duplicate_ids
    channel_selection = select_channels(
        daily_rows,
        config,
        exclude_ids=exclude_ids,
    )

    digest = _format_dual_channel_digest(
        channel_selection.top_matches,
        channel_selection.data_only_best_picks,
        total_in_window=total_in_window,
        window_hours=window_hours,
        data_only_reasons=channel_selection.data_only_reasons,
    )

    dedupe_enabled = bool(dedupe_config.get("enabled", True))
    raw_state_path = dedupe_config.get("state_path", "last_notified.json")
    digest_state_path = _resolve_state_path(
        output_dir, raw_state_path
    )
    digest_date = now.date().isoformat()
    digest_hash = compute_digest_hash(
        digest_date,
        channel_selection.top_matches,
        channel_selection.data_only_best_picks,
    )
    digest_payload = _build_digest_payload(
        now=now,
        digest_date=digest_date,
        digest_hash=digest_hash,
        window_hours=window_hours,
        total_in_window=total_in_window,
        top_rows=channel_selection.top_matches,
        data_only_rows=channel_selection.data_only_best_picks,
        data_only_reasons=channel_selection.data_only_reasons,
    )
    base_snapshot = Snapshot(
        generated_at=now.isoformat(),
        jobs=dict(previous.jobs),
    )
    notified_rows = (
        channel_selection.top_matches
        + channel_selection.data_only_best_picks
    )
    skip_reason = None
    if dedupe_enabled:
        skip_reason = _should_skip_digest(
            digest_state_path, digest_date, digest_hash
        )
    if skip_reason:
        logger.info("Skipping Telegram notification: %s.", skip_reason)
        save_run_state(
            snapshot_path,
            base_snapshot,
            digest_payload,
            summary=_build_run_summary(
                total_in_window=total_in_window,
                top_count=len(channel_selection.top_matches),
                data_only_count=len(
                    channel_selection.data_only_best_picks
                ),
            ),
        )
        return NotificationResult(
            notified_count=0,
            notification_mode="daily_window",
            skipped_reason=skip_reason,
        )

    if not telegram_enabled and not dry_run:
        logger.info("Telegram notifications disabled via config.")
        save_run_state(
            snapshot_path,
            base_snapshot,
            digest_payload,
            summary=_build_run_summary(
                total_in_window=total_in_window,
                top_count=len(channel_selection.top_matches),
                data_only_count=len(
                    channel_selection.data_only_best_picks
                ),
            ),
        )
        return NotificationResult(
            notified_count=0,
            notification_mode="disabled",
            skipped_reason="disabled",
        )

    reply_markup = _build_feedback_keyboard(
        _unique_rows(
            channel_selection.top_matches
            + channel_selection.data_only_best_picks
        )
    )
    if dry_run:
        sent, reason = _save_dry_run_payload(
            output_dir=output_dir,
            digest=digest,
            reply_markup=reply_markup,
            digest_payload=digest_payload,
        )
    else:
        sent, reason = telegram_notifier.send_message(
            digest, reply_markup=reply_markup
        )
    if sent:
        logger.info("Notification sent via Telegram.")
        updated_snapshot = mark_notified(base_snapshot, notified_rows)
        save_run_state(
            snapshot_path,
            updated_snapshot,
            digest_payload,
            summary=_build_run_summary(
                total_in_window=total_in_window,
                top_count=len(channel_selection.top_matches),
                data_only_count=len(
                    channel_selection.data_only_best_picks
                ),
                notified_count=len(notified_rows),
            ),
        )
        if dedupe_enabled:
            _save_digest_state(
                digest_state_path,
                digest_date,
                digest_hash,
                notified_rows,
            )
        if preference_profile and preference_path:
            personalization = _as_dict(config.get("personalization"))
            cache_limit = _parse_int(
                personalization.get("cache_limit", 200), 200
            )
            updated_profile = update_feedback_cache(
                preference_profile,
                channel_selection.top_matches
                + channel_selection.data_only_best_picks,
                cache_limit,
            )
            save_profile(preference_path, updated_profile)
    else:
        if reason:
            logger.info("Telegram notification not sent: %s.", reason)
        else:
            logger.info("Telegram notification not sent.")
        save_run_state(
            snapshot_path,
            base_snapshot,
            digest_payload,
            summary=_build_run_summary(
                total_in_window=total_in_window,
                top_count=len(channel_selection.top_matches),
                data_only_count=len(
                    channel_selection.data_only_best_picks
                ),
            ),
        )
    return NotificationResult(
        notified_count=len(notified_rows),
        notification_mode="daily_window",
    )


def compute_digest_hash(
    digest_date: str,
    top_rows: Sequence[ReportRow],
    data_only_rows: Sequence[ReportRow],
) -> str:
    """Compute a stable hash for a digest payload."""

    items = []
    for channel, row in _channel_rows(top_rows, data_only_rows):
        items.append(
            f"{_snapshot_key(row)}:{row.match.score or 0}:{channel}"
        )
    payload = "|".join([digest_date, *sorted(items)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _select_daily_window_rows(
    rows: Iterable[ReportRow],
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


def _format_dual_channel_digest(
    top_rows: Sequence[ReportRow],
    data_only_rows: Sequence[ReportRow],
    total_in_window: int,
    window_hours: int,
    data_only_reasons: Mapping[str, list[str]] | None = None,
) -> str:
    if total_in_window == 0:
        return "No new job postings published in the last 24 hours."
    lines: list[str] = []
    lines.append(f"Job Scout — Daily Digest (last {window_hours}h)")
    lines.append("Published yesterday")
    lines.append(f"Total in window: {total_in_window}")
    if top_rows:
        lines.append("\nTop matches")
        for index, row in enumerate(top_rows, start=1):
            lines.extend(
                _format_row_block(index=index, marker="TOP", row=row)
            )
    if data_only_rows:
        lines.append("\nData-only best picks")
        for index, row in enumerate(data_only_rows, start=1):
            reasons = None
            if data_only_reasons:
                reasons = data_only_reasons.get(_snapshot_key(row))
            lines.extend(
                _format_row_block(
                    index=index,
                    marker="DATA",
                    row=row,
                    extra_reasons=reasons,
                )
            )
    return "\n".join(lines)


def _format_row_block(
    *,
    index: int,
    row: ReportRow,
    marker: str | None,
    previous_score: int | None = None,
    extra_reasons: Sequence[str] | None = None,
) -> list[str]:
    posting = row.posting
    score = row.match.score or 0
    location = posting.location_text or "Unknown location"
    remote_level = row.match.remote_level or "unknown"
    label = f"[{marker}] " if marker else ""
    line = f"{index}. {label}{posting.title} — {posting.company}"
    details = (
        f"   Remote: {remote_level} | Location: {location} | Score: {score}"
    )
    if previous_score is not None:
        details += f" (was {previous_score})"
    return [
        line,
        details,
        _format_rationale(row, extra_reasons=extra_reasons),
        posting.url,
    ]


def _format_rationale(
    row: ReportRow, extra_reasons: Sequence[str] | None = None
) -> str:
    penalties = row.match.score_penalties or row.match.penalties
    bonuses = row.match.score_bonuses
    segments: list[str] = []
    if bonuses:
        segments.append(f"bonuses: {', '.join(bonuses)}")
    if penalties:
        segments.append(f"penalties: {', '.join(penalties)}")
    if extra_reasons:
        segments.append(f"channel: {', '.join(extra_reasons)}")
    if not segments:
        segments.append("penalties: none")
    return "   Reason: " + "; ".join(segments)


def _snapshot_key(row: ReportRow) -> str:
    return f"{row.posting.source}:{row.posting.id}"


def _build_feedback_keyboard(rows: Sequence[ReportRow]) -> dict | None:
    if not rows:
        return None
    keyboard: list[list[dict[str, str]]] = []
    for row in rows:
        key = _snapshot_key(row)
        keyboard.append(
            [
                {"text": "👍", "callback_data": f"pref:up:{key}"},
                {"text": "👎", "callback_data": f"pref:down:{key}"},
                {"text": "⭐", "callback_data": f"pref:star:{key}"},
                {"text": "🧻", "callback_data": f"pref:dup:{key}"},
            ]
        )
    return {"inline_keyboard": keyboard}


def _unique_rows(rows: Sequence[ReportRow]) -> list[ReportRow]:
    seen: set[str] = set()
    unique: list[ReportRow] = []
    for row in rows:
        key = _snapshot_key(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _channel_rows(
    top_rows: Sequence[ReportRow],
    data_only_rows: Sequence[ReportRow],
) -> list[tuple[str, ReportRow]]:
    channel_rows: list[tuple[str, ReportRow]] = []
    for row in _unique_rows(list(top_rows)):
        channel_rows.append(("top_matches", row))
    for row in _unique_rows(list(data_only_rows)):
        channel_rows.append(("data_only_best_picks", row))
    return channel_rows


def _should_skip_digest(
    path: Path,
    digest_date: str,
    digest_hash: str,
) -> str | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Digest state load failed: %s", exc)
        return None
    previous_date = payload.get("date")
    previous_hash = payload.get("digest_hash")
    if previous_date == digest_date and previous_hash == digest_hash:
        return "duplicate_digest"
    if previous_date == digest_date:
        return "already_notified_today"
    return None


def _save_digest_state(
    path: Path,
    digest_date: str,
    digest_hash: str,
    rows: Sequence[ReportRow],
) -> None:
    payload = {
        "date": digest_date,
        "digest_hash": digest_hash,
        "notified_ids": [_snapshot_key(row) for row in rows],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2),
        encoding="utf-8",
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_state_path(output_dir: Path, raw_path: object) -> Path:
    path = Path(str(raw_path))
    if not path.is_absolute():
        return output_dir / path
    return path


def _as_dict(raw: object) -> dict[str, object]:
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}


def _parse_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _serialize_digest_row(
    row: ReportRow,
    channel: str,
    reasons: Sequence[str] | None = None,
) -> dict[str, object]:
    posted_at = getattr(row.posting, "posted_at", None)
    return {
        "id": row.posting.id,
        "source": row.posting.source,
        "title": row.posting.title,
        "company": row.posting.company,
        "score": row.match.score or 0,
        "channel": channel,
        "posted_at": posted_at.isoformat()
        if isinstance(posted_at, datetime)
        else None,
        "location": row.posting.location_text,
        "remote_level": row.match.remote_level,
        "missing_salary": row.match.missing_salary,
        "salary_text": row.posting.salary_text,
        "url": row.posting.url,
        "reasons": list(reasons) if reasons else [],
    }


def _build_digest_payload(
    *,
    now: datetime,
    digest_date: str,
    digest_hash: str,
    window_hours: int,
    total_in_window: int,
    top_rows: Sequence[ReportRow],
    data_only_rows: Sequence[ReportRow],
    data_only_reasons: Mapping[str, list[str]] | None = None,
) -> dict[str, object]:
    jobs: list[dict[str, object]] = []
    for channel, row in _channel_rows(top_rows, data_only_rows):
        reasons = None
        if channel == "data_only_best_picks" and data_only_reasons:
            reasons = data_only_reasons.get(_snapshot_key(row))
        jobs.append(_serialize_digest_row(row, channel, reasons))
    return {
        "generated_at": now.isoformat(),
        "date": digest_date,
        "window_hours": window_hours,
        "total_in_window": total_in_window,
        "top_matches_count": len(top_rows),
        "data_only_count": len(data_only_rows),
        "digest_hash": digest_hash,
        "jobs": jobs,
    }


def _build_run_summary(
    *,
    total_in_window: int,
    top_count: int,
    data_only_count: int,
    notified_count: int = 0,
) -> dict[str, int]:
    return {
        "total_in_window": total_in_window,
        "top_matches_count": top_count,
        "data_only_count": data_only_count,
        "digest_count": top_count + data_only_count,
        "notified_count": notified_count,
    }


def _save_dry_run_payload(
    *,
    output_dir: Path,
    digest: str,
    reply_markup: dict | None,
    digest_payload: Mapping[str, object],
) -> tuple[bool, str | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload_path = output_dir / "telegram_payload.json"
    digest_path = output_dir / "digest.md"
    payload = {
        "chat_id": "dry-run",
        "text": digest,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    payload["digest"] = dict(digest_payload)
    payload_path.write_text(
        json.dumps(payload, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    digest_path.write_text(digest + "\n", encoding="utf-8")
    logger.info("Dry-run payload written to %s.", payload_path)
    return True, "dry_run"
