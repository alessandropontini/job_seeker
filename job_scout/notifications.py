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
from zoneinfo import ZoneInfo

from job_scout.channels import select_channels
from job_scout.digesting import is_candidate_after_hard_filters, score_bounds
from job_scout.feedback import (
    FeedbackRegistrationResult,
    build_callback_data,
    build_job_hash,
    build_run_id,
    build_short_id,
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
    notified: bool = False
    digest_date_local: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    diagnostics: dict[str, object] | None = None
    telegram_attempted: bool = False
    telegram_ok: bool = False
    telegram_message_id: int | None = None
    telegram_chat_id_fingerprint: str | None = None
    telegram_thread_id: int | None = None
    telegram_error_code: int | None = None
    telegram_description: str | None = None
    digest_mode: str = "TOP"
    anti_zero_triggered: bool = False
    threshold_initial: int = 70
    threshold_final: int = 70
    min_results: int = 5
    window_rows_count: int = 0
    selection_pool_count: int = 0
    selected_count: int = 0
    digest_top_matches_count: int = 0
    digest_data_only_count: int = 0
    digest_count: int = 0
    selected_min_score: int = 0
    selected_max_score: int = 0
    digest_min_score: int = 0
    digest_max_score: int = 0
    reason_when_zero: str | None = None
    selection_window_days: int = 1


def select_digest_items(
    candidates_scored: Sequence[ReportRow],
    fetched_count: int,
    min_results: int,
    high_threshold: int,
    low_threshold: int,
    step: int,
    force_send: bool,
    run_mode: str,
) -> tuple[list[ReportRow], str, bool, int, int]:
    """Select digest items with adaptive thresholding and anti-zero fallback."""

    if fetched_count <= 0 or not candidates_scored:
        return [], "TOP", False, high_threshold, 0

    sorted_jobs = sorted(
        candidates_scored,
        key=lambda row: (-(row.match.score or 0), row.posting.id),
    )
    positive_scored_jobs = [
        row for row in sorted_jobs if (row.match.score or 0) > 0
    ]
    target_results = max(min_results, 1)
    floor_threshold = min(high_threshold, low_threshold)
    step_size = max(step, 1)
    threshold = high_threshold
    mode = "TOP"

    selected = [
        row for row in sorted_jobs if (row.match.score or 0) >= threshold
    ]
    while len(selected) < target_results and threshold > floor_threshold:
        threshold = max(floor_threshold, threshold - step_size)
        selected = [
            row
            for row in sorted_jobs
            if (row.match.score or 0) >= threshold
        ]
        mode = "ADAPTIVE"

    anti_zero_triggered = False
    if len(selected) < target_results and fetched_count > 0:
        anti_zero_triggered = True
        mode = "LOW_CONFIDENCE"
        fallback_pool = positive_scored_jobs or sorted_jobs
        selected = fallback_pool[: min(target_results, len(fallback_pool))]

    if (
        fetched_count > 0
        and run_mode == "manual"
        and force_send
        and not selected
        and sorted_jobs
    ):
        anti_zero_triggered = True
        mode = "LOW_CONFIDENCE"
        fallback_pool = positive_scored_jobs or sorted_jobs
        selected = fallback_pool[:1]

    return selected, mode, anti_zero_triggered, threshold, len(selected)


def maybe_notify(
    rows: Iterable[ReportRow],
    output_dir: Path,
    config: Mapping[str, object],
    *,
    preference_profile: PreferenceProfile | None = None,
    preference_path: Path | None = None,
    run_mode: str = "scheduled",
    force_send: bool = False,
    fetched_count: int | None = None,
    selection_window_days: int = 1,
) -> NotificationResult:
    """Send the daily digest notification for the current run."""

    rows = list(rows)
    notifications = _as_dict(config.get("notifications"))
    telegram_config = _as_dict(notifications.get("telegram"))
    dedupe_config = _as_dict(notifications.get("dedupe"))
    telegram_enabled = bool(telegram_config.get("enabled", True))
    dry_run = bool(telegram_config.get("dry_run", False))
    send_mode = _resolve_telegram_send_mode(telegram_config)

    min_score = _parse_int(telegram_config.get("min_score", 0), 0)
    send_per_job = bool(telegram_config.get("send_per_job", True))
    send_header = bool(telegram_config.get("send_header", True))
    digest_config = _as_dict(config.get("digest"))
    digest_mode = str(digest_config.get("mode", "daily_window"))
    if digest_mode != "daily_window":
        logger.info(
            "Digest mode '%s' not supported; using daily_window.",
            digest_mode,
        )
    window_hours = _parse_int(digest_config.get("window_hours", 24), 24)
    selection_window_days = max(_parse_int(selection_window_days, 1), 1)

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
    runtime_config = _as_dict(config.get("runtime"))
    timezone_name = str(runtime_config.get("digest_timezone", "Europe/Rome"))
    profession_query = str(
        runtime_config.get("profession_query") or ""
    ).strip()
    location_scope = str(
        runtime_config.get("location_scope") or ""
    ).strip()
    digest_tz = ZoneInfo(timezone_name)
    now_local = now.astimezone(digest_tz)
    target_date_local = (now_local - timedelta(days=1)).date()
    if run_mode == "manual":
        target_date_local = now_local.date()
    window_start = now - timedelta(hours=window_hours)

    if run_mode == "scheduled":
        daily_rows = _select_digest_date_rows(
            rows,
            target_date_local=target_date_local,
            timezone_name=timezone_name,
            minimum_score=min_score,
        )
        digest_scope = "daily_window"
    else:
        window_start = now - timedelta(days=selection_window_days)
        daily_rows = _select_daily_window_rows(
            rows,
            window_start,
            now,
            minimum_score=min_score,
        )
        digest_scope = (
            "manual_since_days" if selection_window_days > 1 else "daily_window"
        )
    window_rows_count = len(daily_rows)
    if not daily_rows:
        fallback_rows = _select_fallback_rows(rows, minimum_score=min_score)
        if fallback_rows:
            logger.info(
                "Daily window empty; using %d fallback rows for digest.",
                len(fallback_rows),
            )
            daily_rows = fallback_rows
            window_rows_count = len(fallback_rows)
            digest_scope = "fallback_recent"

    digest_settings = _as_dict(digest_config.get("selection"))
    min_results = _parse_int(digest_settings.get("min_results", 5), 5)
    high_threshold = _parse_int(
        digest_settings.get("high_threshold", 70), 70
    )
    low_threshold = _parse_int(
        digest_settings.get("low_threshold", 40), 40
    )
    threshold_step = _parse_int(digest_settings.get("step", 5), 5)
    effective_fetched_count = fetched_count if fetched_count is not None else len(rows)

    hard_filtered_candidates = [
        row
        for row in rows
        if _is_candidate_after_hard_filters(row)
    ]
    selection_pool = [
        row for row in daily_rows if _is_candidate_after_hard_filters(row)
    ]
    if effective_fetched_count > 0 and not selection_pool:
        selection_pool = [
            row for row in hard_filtered_candidates if row.match.score is not None
        ]
        if selection_pool and digest_scope != "fallback_recent":
            digest_scope = "fallback_recent"
    selection_pool_count = len(selection_pool)

    (
        selected_rows,
        digest_mode,
        anti_zero_triggered,
        final_threshold,
        selected_count,
    ) = (
        select_digest_items(
            selection_pool,
            fetched_count=effective_fetched_count,
            min_results=min_results,
            high_threshold=high_threshold,
            low_threshold=low_threshold,
            step=threshold_step,
            force_send=force_send,
            run_mode=run_mode,
        )
    )
    selected_min_score, selected_max_score = score_bounds(selected_rows)

    reason_when_zero = None
    if selected_count == 0:
        if effective_fetched_count <= 0:
            reason_when_zero = "fetched_count_zero"
        elif not hard_filtered_candidates:
            reason_when_zero = "no_candidates_after_hard_filters"

    exclude_ids = set()
    if preference_profile:
        personalization = _as_dict(config.get("personalization"))
        if personalization.get("duplicate_action", "skip") == "skip":
            exclude_ids = preference_profile.duplicate_ids
    channel_selection = select_channels(
        selected_rows,
        config,
        exclude_ids=exclude_ids,
    )
    if anti_zero_triggered and not channel_selection.top_matches:
        channel_selection = channel_selection.__class__(
            top_matches=list(selected_rows),
            data_only_best_picks=[],
            data_only_reasons={},
        )
    digest_rows = (
        channel_selection.top_matches
        + channel_selection.data_only_best_picks
    )
    digest_count = len(digest_rows)
    digest_min_score, digest_max_score = score_bounds(digest_rows)

    _annotate_report_mode(
        output_dir=output_dir,
        digest_mode=digest_mode,
        threshold_final=final_threshold,
    )

    digest = _format_dual_channel_digest(
        channel_selection.top_matches,
        channel_selection.data_only_best_picks,
        digest_count=digest_count,
        window_hours=window_hours,
        digest_scope=digest_scope,
        digest_mode=digest_mode,
        data_only_reasons=channel_selection.data_only_reasons,
        selection_window_days=selection_window_days,
    )

    dedupe_enabled = bool(dedupe_config.get("enabled", True))
    raw_state_path = dedupe_config.get("state_path", "last_notified.json")
    digest_state_path = resolve_state_path(
        output_dir,
        raw_state_path,
        state_dir=state_dir,
        state_suffix=state_suffix,
    )
    digest_date = target_date_local.isoformat()
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
        selection_window_days=selection_window_days,
        total_in_window=digest_count,
        digest_mode=digest_mode,
        anti_zero_triggered=anti_zero_triggered,
        threshold_initial=high_threshold,
        threshold_final=final_threshold,
        min_results=min_results,
        top_rows=channel_selection.top_matches,
        data_only_rows=channel_selection.data_only_best_picks,
        data_only_reasons=channel_selection.data_only_reasons,
        short_ids=short_ids,
    )
    digest_payload["run_mode"] = run_mode
    digest_payload["force_send"] = bool(force_send)
    digest_payload["timezone"] = timezone_name
    digest_payload["target_date_local"] = digest_date
    base_snapshot = Snapshot(
        generated_at=now.isoformat(),
        jobs=dict(previous.jobs),
    )
    notified_rows = (
        channel_selection.top_matches
        + channel_selection.data_only_best_picks
    )
    last_seen_job_ids = [
        _snapshot_key(row)
        for row in _unique_rows(
            list(channel_selection.top_matches)
            + list(channel_selection.data_only_best_picks)
        )
    ]
    live_state_payload = {
        "last_successful_run_at": now.isoformat(),
        "last_digest_date_local": digest_date,
        "last_seen_job_ids": last_seen_job_ids,
    }
    skip_reason = None
    if dedupe_enabled and run_mode == "scheduled" and not force_send:
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
                window_rows_count=window_rows_count,
                selection_pool_count=selection_pool_count,
                selected_count=selected_count,
                top_count=len(channel_selection.top_matches),
                data_only_count=len(
                    channel_selection.data_only_best_picks
                ),
                digest_mode=digest_mode,
                anti_zero_triggered=anti_zero_triggered,
                threshold_initial=high_threshold,
                threshold_final=final_threshold,
                min_results=min_results,
                reason_when_zero=reason_when_zero,
            ),
            live_state=live_state_payload,
        )
        return NotificationResult(
            notified_count=0,
            notification_mode="daily_window",
            skipped_reason=skip_reason,
            notified=False,
            digest_date_local=digest_date,
            window_start=window_start.isoformat(),
            window_end=now.isoformat(),
            diagnostics={
                "run_mode": run_mode,
                "timezone": timezone_name,
                "reason": skip_reason,
            },
            digest_mode=digest_mode,
            anti_zero_triggered=anti_zero_triggered,
            threshold_initial=high_threshold,
            threshold_final=final_threshold,
            min_results=min_results,
            window_rows_count=window_rows_count,
            selection_pool_count=selection_pool_count,
            selected_count=selected_count,
            digest_top_matches_count=len(channel_selection.top_matches),
            digest_data_only_count=len(
                channel_selection.data_only_best_picks
            ),
            digest_count=digest_count,
            selected_min_score=selected_min_score,
            selected_max_score=selected_max_score,
            digest_min_score=digest_min_score,
            digest_max_score=digest_max_score,
            reason_when_zero=reason_when_zero,
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
                window_rows_count=window_rows_count,
                selection_pool_count=selection_pool_count,
                selected_count=selected_count,
                top_count=len(channel_selection.top_matches),
                data_only_count=len(
                    channel_selection.data_only_best_picks
                ),
                digest_mode=digest_mode,
                anti_zero_triggered=anti_zero_triggered,
                threshold_initial=high_threshold,
                threshold_final=final_threshold,
                min_results=min_results,
                reason_when_zero=reason_when_zero,
            ),
            live_state=live_state_payload,
        )
        return NotificationResult(
            notified_count=0,
            notification_mode="disabled",
            skipped_reason="disabled",
            notified=False,
            digest_date_local=digest_date,
            window_start=window_start.isoformat(),
            window_end=now.isoformat(),
            diagnostics={"run_mode": run_mode, "timezone": timezone_name},
            digest_mode=digest_mode,
            anti_zero_triggered=anti_zero_triggered,
            threshold_initial=high_threshold,
            threshold_final=final_threshold,
            min_results=min_results,
            window_rows_count=window_rows_count,
            selection_pool_count=selection_pool_count,
            selected_count=selected_count,
            digest_top_matches_count=len(channel_selection.top_matches),
            digest_data_only_count=len(
                channel_selection.data_only_best_picks
            ),
            digest_count=digest_count,
            selected_min_score=selected_min_score,
            selected_max_score=selected_max_score,
            digest_min_score=digest_min_score,
            digest_max_score=digest_max_score,
            reason_when_zero=reason_when_zero,
        )

    if run_mode == "scheduled" and digest_count == 0:
        logger.info("Scheduled run has no matches; sending diagnostic Telegram message.")

    message_payloads = _build_message_payloads(
        channel_selection.top_matches,
        channel_selection.data_only_best_picks,
        data_only_reasons=channel_selection.data_only_reasons,
        digest_count=digest_count,
        window_hours=window_hours,
        digest_scope=digest_scope,
        digest_mode=digest_mode,
        selection_window_days=selection_window_days,
        run_id=run_id,
        short_ids=short_ids,
        digest_hash=digest_hash,
        send_header=send_header,
        send_per_job=send_per_job,
        run_mode=run_mode,
        force_send=force_send,
        profession_query=profession_query,
        location_scope=location_scope,
        reason_when_zero=reason_when_zero,
    )
    _persist_payload(
        output_dir=output_dir,
        message_payloads=message_payloads,
        digest_payload=digest_payload,
    )
    feedback_jobs = _build_feedback_job_map(
        channel_selection.top_matches,
        channel_selection.data_only_best_picks,
        short_ids,
        digest_hash,
    )
    feedback_enabled = bool(feedback_config.get("enabled", False))
    if feedback_jobs and feedback_enabled and send_mode in {"real", "fake"}:
        registration_result = register_feedback_window(
            run_id=run_id,
            open_at=feedback_open_at.isoformat(),
            close_at=feedback_close_at.isoformat(),
            jobs=feedback_jobs,
            config=config,
        )
        _write_feedback_registration_result(
            output_dir=output_dir,
            result=registration_result,
        )
        logger.info(
            "Feedback registration result: endpoint=%s method=%s status=%s reason=%s body=%s",
            registration_result.endpoint,
            registration_result.method,
            registration_result.status,
            registration_result.reason or "ok",
            registration_result.body_excerpt,
        )
        if send_mode == "fake" and not registration_result.ok:
            logger.warning(
                "Feedback window registration failed in fake mode: status=%s reason=%s body=%s",
                registration_result.status,
                registration_result.reason,
                registration_result.body_excerpt,
            )

    telegram_attempted = False
    telegram_ok = False
    telegram_message_id = None
    telegram_chat_fingerprint = None
    telegram_thread_id = None
    telegram_error_code = None
    telegram_description = None
    chat_check_payload = None
    send_responses: list[dict[str, object]] = []

    if dry_run:
        sent, reason = _save_dry_run_payload(
            output_dir=output_dir,
            message_payloads=message_payloads,
            digest_payload=digest_payload,
        )
        logger.info("Telegram send attempted: no; reason=dry_run.")
    elif send_mode == "fake":
        sent, reason = _save_fake_run_payload(
            output_dir=output_dir,
            message_payloads=message_payloads,
            digest_payload=digest_payload,
        )
        logger.info("Telegram send attempted: no; reason=fake_run.")
    else:
        telegram_result = telegram_notifier.send_messages_detailed(
            message_payloads,
            run_chat_check=(run_mode == "manual"),
        )
        sent = telegram_result.sent
        reason = telegram_result.reason
        telegram_attempted = telegram_result.attempted
        telegram_ok = telegram_result.sent
        telegram_chat_fingerprint = telegram_result.chat_fingerprint
        telegram_thread_id = telegram_result.thread_id
        chat_check_payload = telegram_result.chat_check
        send_responses = telegram_result.responses
        logger.info(
            "Telegram send attempted: yes; reason=%s.",
            reason or "sent",
        )
        _write_telegram_send_response(output_dir=output_dir, responses=send_responses)
        if chat_check_payload is not None:
            _write_telegram_chat_check(
                output_dir=output_dir,
                chat_check=chat_check_payload,
            )
        last_send = _last_send_message_response(send_responses)
        if isinstance(last_send, Mapping):
            telegram_ok = bool(last_send.get("ok", False))
            result_payload = last_send.get("result")
            if isinstance(result_payload, Mapping):
                message_id = result_payload.get("message_id")
                if isinstance(message_id, int):
                    telegram_message_id = message_id
            error_code = last_send.get("error_code")
            if isinstance(error_code, int):
                telegram_error_code = error_code
            description = last_send.get("description")
            if isinstance(description, str):
                telegram_description = description
    if sent:
        logger.info("Notification sent via Telegram.")
        updated_snapshot = mark_notified(base_snapshot, notified_rows)
        save_run_state(
            snapshot_path,
            updated_snapshot,
            digest_payload,
            summary=_build_run_summary(
                window_rows_count=window_rows_count,
                selection_pool_count=selection_pool_count,
                selected_count=selected_count,
                top_count=len(channel_selection.top_matches),
                data_only_count=len(
                    channel_selection.data_only_best_picks
                ),
                notified_count=len(notified_rows),
                digest_mode=digest_mode,
                anti_zero_triggered=anti_zero_triggered,
                threshold_initial=high_threshold,
                threshold_final=final_threshold,
                min_results=min_results,
                reason_when_zero=reason_when_zero,
            ),
            live_state=live_state_payload,
        )
        if dedupe_enabled and run_mode == "scheduled":
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
                window_rows_count=window_rows_count,
                selection_pool_count=selection_pool_count,
                selected_count=selected_count,
                top_count=len(channel_selection.top_matches),
                data_only_count=len(
                    channel_selection.data_only_best_picks
                ),
                digest_mode=digest_mode,
                anti_zero_triggered=anti_zero_triggered,
                threshold_initial=high_threshold,
                threshold_final=final_threshold,
                min_results=min_results,
                reason_when_zero=reason_when_zero,
            ),
            live_state=live_state_payload,
        )
    outcome_reason = None
    if digest_count == 0:
        outcome_reason = "no_matches"
    elif not sent:
        outcome_reason = reason

    diagnostics = {
        "run_mode": run_mode,
        "timezone": timezone_name,
        "window_rows_count": window_rows_count,
        "selection_pool_count": selection_pool_count,
        "selected_count": selected_count,
        "digest_count": digest_count,
        "digest_scope": digest_scope,
        "digest_mode": digest_mode,
        "threshold_final": final_threshold,
    }
    if chat_check_payload is not None:
        diagnostics["chat_check"] = chat_check_payload
    if send_responses:
        diagnostics["send_response_count"] = len(send_responses)
    return NotificationResult(
        notified_count=len(notified_rows) if sent else 0,
        notification_mode="daily_window",
        skipped_reason=outcome_reason,
        notified=bool(sent),
        digest_date_local=digest_date,
        window_start=window_start.isoformat(),
        window_end=now.isoformat(),
        diagnostics=diagnostics,
        telegram_attempted=telegram_attempted,
        telegram_ok=telegram_ok,
        telegram_message_id=telegram_message_id,
        telegram_chat_id_fingerprint=telegram_chat_fingerprint,
        telegram_thread_id=telegram_thread_id,
        telegram_error_code=telegram_error_code,
        telegram_description=telegram_description,
        digest_mode=digest_mode,
        anti_zero_triggered=anti_zero_triggered,
        threshold_initial=high_threshold,
        threshold_final=final_threshold,
        min_results=min_results,
        window_rows_count=window_rows_count,
        selection_pool_count=selection_pool_count,
        selected_count=selected_count,
        digest_top_matches_count=len(channel_selection.top_matches),
        digest_data_only_count=len(
            channel_selection.data_only_best_picks
        ),
        digest_count=digest_count,
        selected_min_score=selected_min_score,
        selected_max_score=selected_max_score,
        digest_min_score=digest_min_score,
        digest_max_score=digest_max_score,
        reason_when_zero=reason_when_zero,
        selection_window_days=selection_window_days,
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


def _select_digest_date_rows(
    rows: Iterable[ReportRow],
    *,
    target_date_local: object,
    timezone_name: str,
    minimum_score: int,
) -> list[ReportRow]:
    candidates: list[ReportRow] = []
    digest_tz = ZoneInfo(timezone_name)
    for row in rows:
        if not row.match.matches_all:
            continue
        if (row.match.score or 0) < minimum_score:
            continue
        posted_at = getattr(row.posting, "posted_at", None)
        if not isinstance(posted_at, datetime) or posted_at.tzinfo is None:
            continue
        if posted_at.astimezone(digest_tz).date() != target_date_local:
            continue
        candidates.append(row)
    return candidates


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
    digest_count: int,
    window_hours: int,
    digest_scope: str,
    digest_mode: str,
    data_only_reasons: Mapping[str, list[str]] | None = None,
    selection_window_days: int = 1,
) -> str:
    if digest_count == 0:
        return "No new job postings published in the last 24 hours."
    lines: list[str] = []
    if digest_scope == "fallback_recent":
        lines.append("Job Scout — Daily Digest (fallback)")
        lines.append(
            "No new postings in the last 24h; showing latest accepted matches."
        )
        lines.append(f"Total in digest: {digest_count}")
    else:
        if digest_scope == "manual_since_days":
            lines.append(
                f"Job Scout — Manual Digest (last {selection_window_days}d)"
            )
            lines.append("Published in the selected manual range")
        else:
            lines.append(f"Job Scout — Daily Digest (last {window_hours}h)")
            lines.append("Published yesterday")
        lines.append(f"Total in digest: {digest_count}")
    mode_label = digest_mode
    if digest_mode == "LOW_CONFIDENCE":
        mode_label = "LOW_CONFIDENCE (anti-zero)"
    lines.append(f"Mode: {mode_label}")
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
        _format_why(row),
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


def _format_why(row: ReportRow) -> str:
    if not row.match.why:
        return "   Why: broad recall fallback"
    return "   Why: " + "; ".join(row.match.why[:3])


def _build_feedback_keyboard_for_job(
    run_id: str, short_id: str, job_hash: str
) -> dict[str, object]:
    keyboard = [
        [
            {
                "text": "👍 Mi piace",
                "callback_data": build_callback_data(
                    run_id, short_id, "L", job_hash
                ),
            },
            {
                "text": "🤔 Forse",
                "callback_data": build_callback_data(
                    run_id, short_id, "M", job_hash
                ),
            },
            {
                "text": "👎 Non mi piace",
                "callback_data": build_callback_data(
                    run_id, short_id, "D", job_hash
                ),
            },
            {
                "text": "🚫 Non rilevante",
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


def _resolve_telegram_send_mode(
    telegram_config: Mapping[str, object],
) -> str:
    configured_mode = str(
        telegram_config.get("send_mode", "fake")
    ).strip().lower()
    env_mode = os.getenv("JOB_SCOUT_TELEGRAM_MODE", "").strip().lower()
    send_mode = configured_mode
    if env_mode in {"fake", "real"}:
        send_mode = env_mode
    if send_mode == "real" and os.getenv("JOB_SCOUT_E2E_REAL_TELEGRAM") != "1":
        logger.warning(
            "JOB_SCOUT_TELEGRAM_MODE=real ignored because JOB_SCOUT_E2E_REAL_TELEGRAM!=1; falling back to fake mode."
        )
        return "fake"
    if send_mode not in {"fake", "real"}:
        return "fake"
    return send_mode


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
    selection_window_days: int,
    total_in_window: int,
    digest_mode: str,
    anti_zero_triggered: bool,
    threshold_initial: int,
    threshold_final: int,
    min_results: int,
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
        "selection_window_days": selection_window_days,
        "scope": digest_scope,
        "digest_mode": digest_mode,
        "anti_zero_triggered": anti_zero_triggered,
        "threshold_initial": threshold_initial,
        "threshold_final": threshold_final,
        "min_results": min_results,
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
    window_rows_count: int,
    selection_pool_count: int,
    selected_count: int,
    top_count: int,
    data_only_count: int,
    digest_mode: str,
    anti_zero_triggered: bool,
    threshold_initial: int,
    threshold_final: int,
    min_results: int,
    reason_when_zero: str | None = None,
    notified_count: int = 0,
) -> dict[str, int | bool | str]:
    summary: dict[str, int | bool | str] = {
        "window_rows_count": window_rows_count,
        "selection_pool_count": selection_pool_count,
        "selected_count": selected_count,
        "top_matches_count": top_count,
        "data_only_count": data_only_count,
        "digest_count": top_count + data_only_count,
        "notified_count": notified_count,
        "digest_mode": digest_mode,
        "anti_zero_triggered": anti_zero_triggered,
        "threshold_initial": threshold_initial,
        "threshold_final": threshold_final,
        "min_results": min_results,
    }
    if reason_when_zero:
        summary["reason_when_zero"] = reason_when_zero
    return summary


def _is_candidate_after_hard_filters(row: ReportRow) -> bool:
    """Return True when a row survives hard filters for digest candidate pool."""

    return is_candidate_after_hard_filters(row)

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
    digest_count: int,
    window_hours: int,
    digest_scope: str,
    digest_mode: str,
    selection_window_days: int,
    run_id: str,
    short_ids: Mapping[str, str],
    digest_hash: str,
    send_header: bool,
    send_per_job: bool,
    run_mode: str,
    force_send: bool,
    profession_query: str = "",
    location_scope: str = "",
    reason_when_zero: str | None = None,
) -> list[dict[str, object]]:
    if digest_count == 0:
        headline = "🔎 Oggi non ho trovato offerte davvero in linea."
        detail = (
            "📚 Ho controllato le fonti configurate, ma nessun annuncio è entrato nel digest finale."
        )
        context_line = (
            f"Contesto: digest=0, run_mode={run_mode}, "
            f"force_send={str(force_send).lower()}"
        )
        if run_mode == "manual" and selection_window_days > 1:
            headline = (
                f"🔎 Negli ultimi {selection_window_days} giorni non ho trovato offerte davvero in linea."
            )
            detail = (
                "📚 Ho controllato le fonti configurate sull'intera finestra richiesta, "
                "ma nessun annuncio è entrato nel digest finale."
            )
            context_line = (
                f"Contesto: digest=0, run_mode={run_mode}, "
                f"finestra={selection_window_days}d, "
                f"force_send={str(force_send).lower()}"
            )
        if reason_when_zero == "no_candidates_after_hard_filters":
            headline = "🧭 Oggi non ho trovato offerte che superano i filtri principali."
            detail = (
                "🧱 Le offerte viste ci sono state, ma nessuna ha passato i vincoli più importanti."
            )
            if run_mode == "manual" and selection_window_days > 1:
                headline = (
                    f"🧭 Negli ultimi {selection_window_days} giorni non ho trovato offerte che superano i filtri principali."
                )
                detail = (
                    "🧱 Le offerte viste ci sono state nella finestra richiesta, "
                    "ma nessuna ha passato i vincoli più importanti."
                )
        return [{
            "text": (
                f"{headline}\n"
                f"{detail}\n"
                f"{_format_profession_focus_line(profession_query)}\n"
                f"{_format_location_scope_line(location_scope)}\n"
                f"{context_line}\n"
                "📄 Se vuoi approfondire, controlla `out/run_summary.json`."
            )
        }]
    payloads: list[dict[str, object]] = []
    if send_header:
        payloads.append(
            {
                "text": _format_digest_header(
                    digest_count=digest_count,
                    window_hours=window_hours,
                    digest_scope=digest_scope,
                    digest_mode=digest_mode,
                    selection_window_days=selection_window_days,
                    profession_query=profession_query,
                    location_scope=location_scope,
                )
            }
        )
    if not send_per_job:
        payloads.append(
            {
                "text": _format_dual_channel_digest(
                    top_rows,
                    data_only_rows,
                    digest_count=digest_count,
                    window_hours=window_hours,
                    digest_scope=digest_scope,
                    digest_mode=digest_mode,
                    data_only_reasons=data_only_reasons,
                    selection_window_days=selection_window_days,
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
    *,
    digest_count: int,
    window_hours: int,
    digest_scope: str,
    digest_mode: str,
    selection_window_days: int,
    profession_query: str = "",
    location_scope: str = "",
) -> str:
    mode_label = digest_mode
    if digest_mode == "LOW_CONFIDENCE":
        mode_label = "LOW_CONFIDENCE (anti-zero)"
    focus_line = _format_profession_focus_line(profession_query)
    location_line = _format_location_scope_line(location_scope)
    if digest_scope == "fallback_recent":
        return (
            "Job Scout — Daily Digest (fallback)\n"
            f"Total in digest: {digest_count}\n"
            f"{focus_line}\n"
            f"{location_line}\n"
            f"Mode: {mode_label}"
        )
    if digest_scope == "manual_since_days":
        return (
            f"Job Scout — Manual Digest (last {selection_window_days}d)\n"
            f"Total in digest: {digest_count}\n"
            f"{focus_line}\n"
            f"{location_line}\n"
            f"Mode: {mode_label}"
        )
    return (
        f"Job Scout — Daily Digest (last {window_hours}h)\n"
        f"Total in digest: {digest_count}\n"
        f"{focus_line}\n"
        f"{location_line}\n"
        f"Mode: {mode_label}"
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


def _format_profession_focus_line(profession_query: str) -> str:
    cleaned = str(profession_query or "").strip()
    if not cleaned:
        return "🎯 Focus: profilo CV predefinito"
    return f"🎯 Focus: {cleaned}"


def _format_location_scope_line(location_scope: str) -> str:
    scope = str(location_scope or "").strip().lower()
    labels = {
        "italy": "🇮🇹 Italia",
        "europe": "🇪🇺 Europa",
        "usa": "🇺🇸 USA",
        "world": "🌍 Mondo",
    }
    return f"🌐 Area: {labels.get(scope, 'profilo CV predefinito')}"


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


def _annotate_report_mode(
    *, output_dir: Path, digest_mode: str, threshold_final: int
) -> None:
    report_path = output_dir / "report.md"
    if not report_path.exists():
        return
    current = report_path.read_text(encoding="utf-8")
    mode_label = digest_mode
    if digest_mode == "LOW_CONFIDENCE":
        mode_label = "LOW_CONFIDENCE (anti-zero)"
    annotation = (
        f"Digest mode: {mode_label} | Threshold final: {threshold_final}\n\n"
    )
    if current.startswith(annotation):
        return
    report_path.write_text(annotation + current, encoding="utf-8")


def _write_telegram_send_response(
    *, output_dir: Path, responses: Sequence[Mapping[str, object]]
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "telegram_send_response.json"
    path.write_text(
        json.dumps({"responses": list(responses)}, sort_keys=True, indent=2),
        encoding="utf-8",
    )


def _write_telegram_chat_check(
    *, output_dir: Path, chat_check: Mapping[str, object]
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "telegram_chat_check.json"
    path.write_text(
        json.dumps(dict(chat_check), sort_keys=True, indent=2),
        encoding="utf-8",
    )


def _last_send_message_response(
    responses: Sequence[Mapping[str, object]],
) -> Mapping[str, object] | None:
    for entry in reversed(list(responses)):
        if entry.get("method") != "sendMessage":
            continue
        response = entry.get("response")
        if isinstance(response, Mapping):
            return response
    return None


def _write_feedback_registration_result(
    *, output_dir: Path, result: FeedbackRegistrationResult
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "feedback_registration_result.log"
    lines = [
        f"ok={str(result.ok).lower()}",
        f"reason={result.reason or 'ok'}",
        f"endpoint={result.endpoint}",
        f"method={result.method}",
        f"headers={','.join(result.headers)}",
        f"status={result.status if result.status is not None else 'none'}",
        f"body_excerpt={result.body_excerpt}",
        f"user_agent_sent={str(result.user_agent_sent).lower()}",
    ]
    result_path.write_text("\n".join(lines) + "\n", encoding="utf-8")




def _save_fake_run_payload(
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
    logger.info("Fake Telegram run payload written to %s.", output_dir)
    return True, "fake_run"


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
