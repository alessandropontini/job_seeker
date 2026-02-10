"""Feedback window registration and ingestion helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping
import urllib.error
import urllib.request
import uuid

from job_scout.preferences import PreferenceProfile, apply_feedback
from job_scout.state import resolve_state_path

logger = logging.getLogger(__name__)

FEEDBACK_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


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


@dataclass(frozen=True)
class FeedbackRegistrationResult:
    """Structured result of feedback window registration calls."""

    ok: bool
    reason: str | None
    endpoint: str
    method: str
    headers: tuple[str, ...]
    status: int | None
    body_excerpt: str
    user_agent_sent: bool = False


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


def build_callback_data(
    run_id: str, short_id: str, action: str, job_hash: str
) -> str:
    """Build compact callback data for Telegram feedback buttons."""

    payload = f"fb|{run_id}|{short_id}|{action}|{job_hash}"
    if len(payload.encode("utf-8")) >= 64:
        raise ValueError("callback_data exceeds Telegram limit")
    return payload


def build_job_hash(job_key: str, digest_hash: str) -> str:
    """Build a compact hash for job identifiers."""

    payload = f"{job_key}:{digest_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


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


def is_window_open(
    open_at: str, close_at: str, now: datetime
) -> bool:
    """Return True when the timestamp is within the feedback window."""

    try:
        open_dt = datetime.fromisoformat(open_at)
        close_dt = datetime.fromisoformat(close_at)
    except ValueError:
        return False
    if open_dt.tzinfo is None or close_dt.tzinfo is None:
        return False
    return open_dt <= now <= close_dt


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
) -> FeedbackRegistrationResult:
    """Register the feedback window and job mapping with the worker."""

    feedback_config = _feedback_config(config)
    endpoint = ""
    method = "POST"
    headers = (
        "Content-Type",
        "Accept",
        "Accept-Language",
        "User-Agent",
        "X-Webhook-Timestamp",
        "X-Webhook-Id",
        "X-Webhook-Signature",
    )
    if not feedback_config.get("enabled", False):
        return FeedbackRegistrationResult(
            ok=False,
            reason="feedback_disabled",
            endpoint=endpoint,
            method=method,
            headers=headers,
            status=None,
            body_excerpt="",
            user_agent_sent=True,
        )
    base_url = _resolve_feedback_base_url(feedback_config)
    if not base_url:
        return FeedbackRegistrationResult(
            ok=False,
            reason="missing_feedback_base_url",
            endpoint=endpoint,
            method=method,
            headers=headers,
            status=None,
            body_excerpt="",
            user_agent_sent=True,
        )
    secret = _resolve_feedback_secret(feedback_config)
    if not secret:
        return FeedbackRegistrationResult(
            ok=False,
            reason="missing_feedback_secret",
            endpoint=endpoint,
            method=method,
            headers=headers,
            status=None,
            body_excerpt="",
            user_agent_sent=True,
        )
    endpoint = f"{base_url.rstrip('/')}/window/open"
    payload = {
        "run_id": run_id,
        "open_at": open_at,
        "close_at": close_at,
        "jobs": jobs,
    }
    status, body = _post_json(
        endpoint,
        payload,
        secret,
    )
    if status is None:
        return FeedbackRegistrationResult(
            ok=False,
            reason="connection_error",
            endpoint=endpoint,
            method=method,
            headers=headers,
            status=None,
            body_excerpt=_body_excerpt(body),
            user_agent_sent=True,
        )
    if status != 200:
        return FeedbackRegistrationResult(
            ok=False,
            reason=f"status_{status}",
            endpoint=endpoint,
            method=method,
            headers=headers,
            status=status,
            body_excerpt=_body_excerpt(body),
            user_agent_sent=True,
        )
    return FeedbackRegistrationResult(
        ok=True,
        reason=None,
        endpoint=endpoint,
        method=method,
        headers=headers,
        status=status,
        body_excerpt=_body_excerpt(body),
        user_agent_sent=True,
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
    url = f"{base_url.rstrip('/')}/feedback"
    payload = {"run_id": run_id}
    status, body = _post_json(
        url,
        payload,
        secret,
        expect_json=True,
    )
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

    counts: dict[str, int] = {
        "like": 0,
        "maybe": 0,
        "dislike": 0,
        "love": 0,
        "duplicate": 0,
    }
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


def record_feedback_in_last_run(
    output_dir: Path,
    config: Mapping[str, object],
    counts: Mapping[str, int],
) -> None:
    """Persist feedback counts in last_run.json for traceability."""

    state_config = _as_dict(config.get("state"))
    path = resolve_state_path(
        output_dir,
        "last_run.json",
        state_dir=state_config.get("dir"),
        state_suffix=state_config.get("suffix"),
    )
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    payload["feedback_counts"] = dict(counts)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2),
        encoding="utf-8",
    )


def _map_feedback_action(action: str) -> str | None:
    action_map = {
        "L": "like",
        "M": "maybe",
        "D": "dislike",
        "S": "love",
        "X": "duplicate",
        "like": "like",
        "maybe": "maybe",
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
    url: str,
    payload: Mapping[str, object],
    secret: str,
    *,
    expect_json: bool = False,
) -> tuple[int | None, object]:
    data = json.dumps(payload).encode("utf-8")
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    request_id = str(uuid.uuid4())
    signature = _sign_payload(secret, timestamp, data)
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": FEEDBACK_USER_AGENT,
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Id": request_id,
            "X-Webhook-Signature": signature,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
            decoded = body.decode("utf-8", errors="replace")
            if expect_json:
                try:
                    parsed = json.loads(decoded)
                except json.JSONDecodeError:
                    parsed = {}
                return response.status, parsed
            return response.status, decoded
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if expect_json:
            try:
                parsed_body = json.loads(body)
            except json.JSONDecodeError:
                parsed_body = {}
            return exc.code, parsed_body
        return exc.code, body
    except Exception as exc:
        logger.warning("Feedback request failed (%s).", exc.__class__.__name__)
        return None, {}


def parse_callback_data(data: str) -> tuple[str, str, str, str] | None:
    """Parse compact feedback callback payloads in the Worker-compatible format."""

    if not data.startswith("fb|"):
        return None
    parts = data.split("|")
    if len(parts) != 5:
        return None
    _, run_id, short_id, action, job_hash = parts
    if not all((run_id, short_id, action, job_hash)):
        return None
    return run_id, short_id, action, job_hash


def session_storage_key(run_id: str) -> str:
    """Return the Worker KV key used for session windows."""

    return f"session:{run_id}"


def _as_dict(raw: object) -> dict[str, object]:
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _sign_payload(secret: str, timestamp: str, body: bytes) -> str:
    payload = timestamp.encode("utf-8") + b"." + body
    digest = hmac.new(
        secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()
    return digest


def _feedback_window_minutes(config: Mapping[str, object]) -> int:
    env_minutes = os.getenv("FEEDBACK_WINDOW_MINUTES")
    if env_minutes:
        try:
            minutes = int(env_minutes)
            return max(minutes, 1)
        except ValueError:
            pass
    return _parse_int(config.get("window_minutes", 60), 60)


def _parse_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _body_excerpt(body: object, *, limit: int = 200) -> str:
    if isinstance(body, str):
        return body[:limit]
    if isinstance(body, (dict, list)):
        return json.dumps(body, sort_keys=True)[:limit]
    return str(body)[:limit]
