"""Notification orchestration for job scouting updates."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from job_scout.channels import select_channels
from job_scout.feedback import (
    build_callback_data,
    build_run_id,
    build_short_id,
    build_job_hash,
    register_feedback_window,
)
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
    resolve_state_path,
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
    send_per_job = bool(telegram_config.get("send_per_job", True))
    send_header = bool(telegram_config.get("send_header", True))
    persist_payload = bool(telegram_config.get("persist_payload", False))
    digest_config = _as_dict(config.get("digest"))
    digest_mode = str(digest_config.get("mode", "daily_window"))
    if digest_mode != "daily_window":
        logger.info(
            "Digest mode '%s' not supported; using daily_window.",
            digest_mode,
        )
    window_hours = _parse_int(digest_config.get("window_hours", 24), 24)

    state_config = _as_dict(config.get("state"))
    state_dir = state_config.get("dir")
    state_suffix = state_config.get("suffix")
    snapshot_path = resolve_state_path(
        output_dir,
        "last_run.json",
        state_dir=state_dir,
        state_suffix=state_suffix,
    )
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
    digest_scope = "daily_window"
    if not daily_rows:
        fallback_rows = _select_fallback_rows(rows, minimum_score=min_score)
        if fallback_rows:
            logger.info(
                "Daily window empty; using %d fallback rows for digest.",
                len(fallback_rows),
            )
            daily_rows = fallback_rows
            total_in_window = len(fallback_rows)
            digest_scope = "fallback_recent"

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
        digest_scope=digest_scope,
        data_only_reasons=channel_selection.data_only_reasons,
    )

    dedupe_enabled = bool(dedupe_config.get("enabled", True))
    raw_state_path = dedupe_config.get("state_path", "last_notified.json")
    digest_state_path = resolve_state_path(
        output_dir,
        raw_state_path,
        state_dir=state_dir,
        state_suffix=state_suffix,
    )
    digest_date = now.date().isoformat()
    digest_hash = compute_digest_hash(
        digest_date,
        channel_selection.top_matches,
        channel_selection.data_only_best_picks,
    )
    run_id = build_run_id(now, digest_hash)
    feedback_config = _as_dict(config.get("feedback"))
    feedback_window_minutes = _feedback_window_minutes(
        feedback_config
    )
    feedback_open_at = now.astimezone(timezone.utc)
    feedback_close_at = feedback_open_at + timedelta(
        minutes=feedback_window_minutes
    )
    short_ids = _assign_short_ids(
        channel_selection.top_matches
        + channel_selection.data_only_best_picks
    )
    digest_payload = _build_digest_payload(
        now=now,
        digest_date=digest_date,
        digest_hash=digest_hash,
        run_id=run_id,
        feedback_open_at=feedback_open_at.isoformat(),
        feedback_close_at=feedback_close_at.isoformat(),
        window_hours=window_hours,
        digest_scope=digest_scope,
        total_in_window=total_in_window,
        top_rows=channel_selection.top_matches,
        data_only_rows=channel_selection.data_only_best_picks,
        data_only_reasons=channel_selection.data_only_reasons,
        short_ids=short_ids,
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
        logger.info(
            "Telegram send attempted: no; reason=%s.", skip_reason
        )
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
        logger.info(
            "Telegram send attempted: no; reason=disabled."
        )
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

    message_payloads = _build_message_payloads(
        channel_selection.top_matches,
        channel_selection.data_only_best_picks,
        data_only_reasons=channel_selection.data_only_reasons,
        total_in_window=total_in_window,
        window_hours=window_hours,
        digest_scope=digest_scope,
        run_id=run_id,
        short_ids=short_ids,
        digest_hash=digest_hash,
        send_header=send_header,
        send_per_job=send_per_job,
    )
    if persist_payload:
        _persist_payload(
            output_dir=output_dir,
            message_payloads=message_payloads,
            digest_payload=digest_payload,
        )
    if dry_run:
        sent, reason = _save_dry_run_payload(
            output_dir=output_dir,
            message_payloads=message_payloads,
            digest_payload=digest_payload,
        )
        logger.info("Telegram send attempted: no; reason=dry_run.")
    else:
        feedback_jobs = _build_feedback_job_map(
            channel_selection.top_matches,
            channel_selection.data_only_best_picks,
            short_ids,
            digest_hash,
        )
        if feedback_jobs:
            register_ok, register_reason = register_feedback_window(
                run_id=run_id,
                open_at=feedback_open_at.isoformat(),
                close_at=feedback_close_at.isoformat(),
                jobs=feedback_jobs,
                config=config,
            )
            if not register_ok and register_reason:
                logger.info(
                    "Feedback window registration skipped: %s.",
                    register_reason,
                )
        sent, reason = telegram_notifier.send_messages(message_payloads)
        logger.info(
            "Telegram send attempted: yes; reason=%s.",
            reason or "sent",
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


def _select_fallback_rows(
    rows: Iterable[ReportRow],
    minimum_score: int,
) -> list[ReportRow]:
    candidates: list[ReportRow] = []
    for row in rows:
        if not row.match.matches_all:
            continue
        if (row.match.score or 0) < minimum_score:
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
    digest_scope: str,
    data_only_reasons: Mapping[str, list[str]] | None = None,
) -> str:
    if total_in_window == 0:
        return "No new job postings published in the last 24 hours."
    lines: list[str] = []
    if digest_scope == "fallback_recent":
        lines.append("Job Scout — Daily Digest (fallback)")
        lines.append(
            "No new postings in the last 24h; showing latest accepted matches."
        )
        lines.append(f"Total in digest: {total_in_window}")
    else:
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


def _build_feedback_keyboard_for_job(
    run_id: str, short_id: str, job_hash: str
) -> dict[str, object]:
    keyboard = [
        [
            {
                "text": "Mi piace",
                "callback_data": build_callback_data(
                    run_id, short_id, "L", job_hash
                ),
            },
            {
                "text": "Forse",
                "callback_data": build_callback_data(
                    run_id, short_id, "M", job_hash
                ),
            },
            {
                "text": "Non mi piace",
                "callback_data": build_callback_data(
                    run_id, short_id, "D", job_hash
                ),
            },
            {
                "text": "Non rilevante",
                "callback_data": build_callback_data(
                    run_id, short_id, "X", job_hash
                ),
            },
        ]
    ]
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


def _as_dict(raw: object) -> dict[str, object]:
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}


def _parse_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _feedback_window_minutes(config: Mapping[str, object]) -> int:
    env_minutes = os.getenv("FEEDBACK_WINDOW_MINUTES")
    if env_minutes:
        try:
            minutes = int(env_minutes)
            return max(minutes, 1)
        except ValueError:
            pass
    return _parse_int(config.get("window_minutes", 60), 60)


def _serialize_digest_row(
    row: ReportRow,
    channel: str,
    reasons: Sequence[str] | None = None,
    short_id: str | None = None,
    job_hash: str | None = None,
) -> dict[str, object]:
    posted_at = getattr(row.posting, "posted_at", None)
    job_key = _snapshot_key(row)
    return {
        "id": row.posting.id,
        "source": row.posting.source,
        "job_key": job_key,
        "short_id": short_id,
        "job_hash": job_hash,
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
        "description_snippet": row.posting.description_snippet,
        "tags": list(row.posting.tags),
        "reasons": list(reasons) if reasons else [],
    }


def _build_digest_payload(
    *,
    now: datetime,
    digest_date: str,
    digest_hash: str,
    run_id: str,
    feedback_open_at: str,
    feedback_close_at: str,
    window_hours: int,
    digest_scope: str,
    total_in_window: int,
    top_rows: Sequence[ReportRow],
    data_only_rows: Sequence[ReportRow],
    data_only_reasons: Mapping[str, list[str]] | None = None,
    short_ids: Mapping[str, str] | None = None,
) -> dict[str, object]:
    jobs: list[dict[str, object]] = []
    top_matches_payload: list[dict[str, object]] = []
    data_only_payload: list[dict[str, object]] = []
    for channel, row in _channel_rows(top_rows, data_only_rows):
        reasons = None
        if channel == "data_only_best_picks" and data_only_reasons:
            reasons = data_only_reasons.get(_snapshot_key(row))
        short_id = None
        if short_ids:
            short_id = short_ids.get(_snapshot_key(row))
        job_hash = build_job_hash(_snapshot_key(row), digest_hash)
        serialized = _serialize_digest_row(
            row, channel, reasons, short_id=short_id, job_hash=job_hash
        )
        jobs.append(serialized)
        if channel == "top_matches":
            top_matches_payload.append(serialized)
        else:
            data_only_payload.append(serialized)
    return {
        "generated_at": now.isoformat(),
        "date": digest_date,
        "run_id": run_id,
        "feedback_open_at": feedback_open_at,
        "feedback_close_at": feedback_close_at,
        "window_hours": window_hours,
        "scope": digest_scope,
        "total_in_window": total_in_window,
        "top_matches_count": len(top_rows),
        "data_only_count": len(data_only_rows),
        "digest_hash": digest_hash,
        "jobs": jobs,
        "top_matches": top_matches_payload,
        "data_only_best_picks": data_only_payload,
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

def _assign_short_ids(rows: Sequence[ReportRow]) -> dict[str, str]:
    used: set[str] = set()
    short_ids: dict[str, str] = {}
    for row in _unique_rows(rows):
        key = _snapshot_key(row)
        short_ids[key] = build_short_id(key, used)
    return short_ids


def _build_message_payloads(
    top_rows: Sequence[ReportRow],
    data_only_rows: Sequence[ReportRow],
    *,
    data_only_reasons: Mapping[str, list[str]] | None,
    total_in_window: int,
    window_hours: int,
    digest_scope: str,
    run_id: str,
    short_ids: Mapping[str, str],
    digest_hash: str,
    send_header: bool,
    send_per_job: bool,
) -> list[dict[str, object]]:
    if total_in_window == 0:
        return [{"text": "No new job postings published in the last 24 hours."}]
    payloads: list[dict[str, object]] = []
    if send_header:
        payloads.append(
            {
                "text": _format_digest_header(
                    total_in_window=total_in_window,
                    window_hours=window_hours,
                    digest_scope=digest_scope,
                )
            }
        )
    if not send_per_job:
        payloads.append(
            {
                "text": _format_dual_channel_digest(
                    top_rows,
                    data_only_rows,
                    total_in_window=total_in_window,
                    window_hours=window_hours,
                    digest_scope=digest_scope,
                    data_only_reasons=data_only_reasons,
                )
            }
        )
        return payloads
    for channel, row in _channel_rows(top_rows, data_only_rows):
        reasons = None
        if channel == "data_only_best_picks" and data_only_reasons:
            reasons = data_only_reasons.get(_snapshot_key(row))
        job_key = _snapshot_key(row)
        short_id = short_ids.get(job_key)
        if not short_id:
            continue
        job_hash = build_job_hash(job_key, digest_hash)
        payloads.append(
            {
                "text": _format_job_message(
                    row,
                    channel=channel,
                    extra_reasons=reasons,
                ),
                "reply_markup": _build_feedback_keyboard_for_job(
                    run_id, short_id, job_hash
                ),
            }
        )
    return payloads


def _format_digest_header(
    *, total_in_window: int, window_hours: int, digest_scope: str
) -> str:
    if digest_scope == "fallback_recent":
        return (
            "Job Scout — Daily Digest (fallback)\n"
            f"Total in digest: {total_in_window}"
        )
    return (
        f"Job Scout — Daily Digest (last {window_hours}h)\n"
        f"Total in window: {total_in_window}"
    )


def _format_job_message(
    row: ReportRow,
    *,
    channel: str,
    extra_reasons: Sequence[str] | None = None,
) -> str:
    posting = row.posting
    score = row.match.score or 0
    channel_label = channel.upper()
    salary_line = (
        f"Salary: {posting.salary_text}"
        if posting.salary_text
        else "Salary: missing"
    )
    details = (
        f"{posting.title} — {posting.company}\n"
        f"Remote: {row.match.remote_level} | "
        f"Location: {posting.location_text or 'Unknown location'} | "
        f"{salary_line} | Score: {score}\n"
        f"Channel: {channel_label}\n"
        f"{_format_rationale(row, extra_reasons=extra_reasons)}\n"
        f"{posting.url}"
    )
    return details


def _build_feedback_job_map(
    top_rows: Sequence[ReportRow],
    data_only_rows: Sequence[ReportRow],
    short_ids: Mapping[str, str],
    digest_hash: str,
) -> list[dict[str, object]]:
    jobs: list[dict[str, object]] = []
    for row in _unique_rows(list(top_rows) + list(data_only_rows)):
        key = _snapshot_key(row)
        short_id = short_ids.get(key)
        if not short_id:
            continue
        job_hash = build_job_hash(key, digest_hash)
        jobs.append(
            {
                "short_id": short_id,
                "job_key": key,
                "job_hash": job_hash,
                "source": row.posting.source,
                "title": row.posting.title,
                "url": row.posting.url,
            }
        )
    return jobs


def _persist_payload(
    *,
    output_dir: Path,
    message_payloads: Sequence[Mapping[str, object]],
    digest_payload: Mapping[str, object],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload_path = output_dir / "telegram_payload.json"
    payload_path.write_text(
        json.dumps(
            {"messages": list(message_payloads), "digest": dict(digest_payload)},
            sort_keys=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    digest_path = output_dir / "digest.md"
    digest_path.write_text(
        "\n\n".join(
            str(payload.get("text", ""))
            for payload in message_payloads
        ),
        encoding="utf-8",
    )


def _save_dry_run_payload(
    *,
    output_dir: Path,
    message_payloads: Sequence[Mapping[str, object]],
    digest_payload: Mapping[str, object],
) -> tuple[bool, str | None]:
    _persist_payload(
        output_dir=output_dir,
        message_payloads=message_payloads,
        digest_payload=digest_payload,
    )
    logger.info("Dry-run payload written to %s.", output_dir)
    return True, "dry_run"
