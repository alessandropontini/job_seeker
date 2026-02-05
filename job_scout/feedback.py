"""Feedback window registration and ingestion helpers."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping
import urllib.parse
import urllib.request

from job_scout.preferences import PreferenceProfile, apply_feedback
from job_scout.state import resolve_state_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedbackWindow:
    """Window metadata for time-gated feedback."""

    run_id: str
    open_at: str
    close_at: str


@dataclass(frozen=True)
class FeedbackResult:
    """Summary of feedback ingestion."""

    updated_profile: PreferenceProfile
    counts: dict[str, int]


def build_run_id(now: datetime, digest_hash: str) -> str:
    """Build a short run id that fits Telegram callback payloads."""

    timestamp = now.strftime("%y%m%d%H")
    digest_stub = digest_hash[:4]
    return f"{timestamp}{digest_stub}"


def build_short_id(job_key: str, used: set[str]) -> str:
    """Generate a deterministic short id for a job key."""

    digest = hashlib.sha256(job_key.encode("utf-8")).hexdigest()
    for length in (8, 10, 12, 16):
        short_id = digest[:length]
        if short_id not in used:
            used.add(short_id)
            return short_id
    suffix = 0
    while True:
        candidate = f"{digest[:12]}{suffix:x}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        suffix += 1


def build_callback_data(run_id: str, short_id: str, action: str) -> str:
    """Build compact callback data for Telegram feedback buttons."""

    payload = f"fb|{run_id}|{short_id}|{action}"
    if len(payload.encode("utf-8")) >= 64:
        raise ValueError("callback_data exceeds Telegram limit")
    return payload


def build_feedback_window(
    now: datetime, window_hours: int
) -> FeedbackWindow:
    """Return feedback window timestamps based on the current time."""

    open_at = now.astimezone(timezone.utc)
    close_at = open_at + timedelta(hours=window_hours)
    return FeedbackWindow(
        run_id="",
        open_at=open_at.isoformat(),
        close_at=close_at.isoformat(),
    )


def load_previous_run(
    output_dir: Path, config: Mapping[str, object]
) -> tuple[str | None, dict[str, dict[str, object]]]:
    """Return the previous run_id and short-id lookup from last_run.json."""

    state_config = _as_dict(config.get("state"))
    path = resolve_state_path(
        output_dir,
        "last_run.json",
        state_dir=state_config.get("dir"),
        state_suffix=state_config.get("suffix"),
    )
    if not path.exists():
        return None, {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Previous run load failed (%s).", exc)
        return None, {}
    digest = payload.get("digest", {})
    if not isinstance(digest, Mapping):
        return None, {}
    run_id = digest.get("run_id")
    jobs = digest.get("jobs", [])
    lookup: dict[str, dict[str, object]] = {}
    if isinstance(jobs, Iterable):
        for entry in jobs:
            if not isinstance(entry, Mapping):
                continue
            short_id = entry.get("short_id")
            if not isinstance(short_id, str):
                continue
            lookup[short_id] = dict(entry)
    return str(run_id) if run_id else None, lookup


def register_feedback_window(
    *,
    run_id: str,
    open_at: str,
    close_at: str,
    jobs: list[dict[str, object]],
    config: Mapping[str, object],
) -> tuple[bool, str | None]:
    """Register the feedback window and job mapping with the worker."""

    feedback_config = _feedback_config(config)
    if not feedback_config.get("enabled", False):
        return False, "feedback_disabled"
    base_url = _resolve_feedback_base_url(feedback_config)
    if not base_url:
        return False, "missing_feedback_base_url"
    secret = _resolve_feedback_secret(feedback_config)
    if not secret:
        return False, "missing_feedback_secret"
    payload = {
        "run_id": run_id,
        "open_at": open_at,
        "close_at": close_at,
        "jobs": jobs,
    }
    return _post_json(
        f"{base_url.rstrip('/')}/window/open",
        payload,
        secret,
    )


def fetch_feedback(
    *, run_id: str, config: Mapping[str, object]
) -> tuple[list[dict[str, object]], str | None]:
    """Fetch feedback entries for a prior run."""

    feedback_config = _feedback_config(config)
    if not feedback_config.get("enabled", False):
        return [], "feedback_disabled"
    base_url = _resolve_feedback_base_url(feedback_config)
    if not base_url:
        return [], "missing_feedback_base_url"
    secret = _resolve_feedback_secret(feedback_config)
    if not secret:
        return [], "missing_feedback_secret"
    url = f"{base_url.rstrip('/')}/feedback?run_id={urllib.parse.quote(run_id)}"
    status, body = _get_json(url, secret)
    if status is None:
        return [], "connection_error"
    if status != 200:
        return [], f"status_{status}"
    if not isinstance(body, list):
        return [], "invalid_payload"
    parsed = [entry for entry in body if isinstance(entry, Mapping)]
    return [dict(entry) for entry in parsed], None


def apply_feedback_items(
    profile: PreferenceProfile,
    feedback_items: Iterable[Mapping[str, object]],
    job_lookup: Mapping[str, Mapping[str, object]],
    config: Mapping[str, object],
) -> FeedbackResult:
    """Apply feedback to a preference profile."""

    counts: dict[str, int] = {"like": 0, "dislike": 0, "love": 0, "duplicate": 0}
    updated_profile = profile
    for entry in feedback_items:
        short_id = entry.get("job_short_id") or entry.get("job_id")
        action = entry.get("action")
        if not isinstance(short_id, str) or not isinstance(action, str):
            continue
        mapped_action = _map_feedback_action(action)
        if not mapped_action:
            continue
        job_payload = job_lookup.get(short_id)
        if not job_payload:
            continue
        job_key = job_payload.get("job_key")
        if not isinstance(job_key, str):
            continue
        cached_item = {
            "title": job_payload.get("title", ""),
            "description_snippet": job_payload.get("description_snippet", ""),
            "tags": job_payload.get("tags", []),
            "remote_level": job_payload.get("remote_level", ""),
        }
        updated_profile = apply_feedback(
            updated_profile,
            action=mapped_action,
            job_key=job_key,
            cached_item=cached_item,
            config=config,
        )
        counts[mapped_action] = counts.get(mapped_action, 0) + 1
    return FeedbackResult(updated_profile=updated_profile, counts=counts)


def write_feedback_summary(
    output_dir: Path,
    config: Mapping[str, object],
    counts: Mapping[str, int],
) -> Path:
    """Persist feedback summary counts."""

    state_config = _as_dict(config.get("state"))
    path = resolve_state_path(
        output_dir,
        "feedback_summary.json",
        state_dir=state_config.get("dir"),
        state_suffix=state_config.get("suffix"),
    )
    payload = dict(counts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return path


def _map_feedback_action(action: str) -> str | None:
    action_map = {
        "L": "like",
        "D": "dislike",
        "S": "love",
        "X": "duplicate",
        "like": "like",
        "dislike": "dislike",
        "love": "love",
        "duplicate": "duplicate",
    }
    return action_map.get(action)


def _feedback_config(config: Mapping[str, object]) -> dict[str, object]:
    return _as_dict(config.get("feedback"))


def _resolve_feedback_base_url(config: Mapping[str, object]) -> str | None:
    env_value = os.getenv("JOB_SCOUT_WEBHOOK_BASE_URL")
    return env_value or _string_or_none(config.get("webhook_base_url"))


def _resolve_feedback_secret(config: Mapping[str, object]) -> str | None:
    env_value = os.getenv("JOB_SCOUT_WEBHOOK_SECRET")
    return env_value or _string_or_none(config.get("webhook_secret"))


def _post_json(
    url: str, payload: Mapping[str, object], secret: str
) -> tuple[bool, str | None]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Secret": secret,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                return False, f"status_{response.status}"
    except Exception as exc:
        return False, f"error_{exc.__class__.__name__}"
    return True, None


def _get_json(url: str, secret: str) -> tuple[int | None, object]:
    request = urllib.request.Request(
        url,
        headers={"X-Webhook-Secret": secret},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
            try:
                parsed = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                parsed = {}
            return response.status, parsed
    except Exception as exc:
        logger.warning("Feedback fetch failed (%s).", exc.__class__.__name__)
        return None, {}


def _as_dict(raw: object) -> dict[str, object]:
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None
