"""Preference learning helpers for Job Scout personalization."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Iterable, Mapping

from job_scout.matcher import MatchResult
from job_scout.models import JobPosting
from job_scout.notifier import telegram as telegram_notifier
from job_scout.state import resolve_state_path

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class PreferenceProfile:
    """Persisted preference weights and feedback cache."""

    token_weights: dict[str, int]
    tag_weights: dict[str, int]
    remote_level_weights: dict[str, int]
    seniority_weights: dict[str, int]
    duplicate_ids: set[str]
    last_update_id: int | None
    feedback_cache: dict[str, dict[str, object]]
    updated_at: str


def resolve_profile_path(
    config: Mapping[str, object],
    output_dir: Path,
    *,
    state_dir: str | Path | None = None,
    state_suffix: str | None = None,
) -> Path:
    personalization = _as_dict(config.get("personalization"))
    raw_path = personalization.get("profile_path", "out/preferences.json")
    return resolve_state_path(
        output_dir,
        raw_path,
        state_dir=state_dir,
        state_suffix=state_suffix,
    )


def load_profile(path: Path) -> PreferenceProfile:
    """Load a preference profile from disk, defaulting to empty."""

    if not path.exists():
        return _empty_profile()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Preference profile load failed (%s); resetting.", exc)
        return _empty_profile()
    return _parse_profile(payload)


def save_profile(path: Path, profile: PreferenceProfile) -> None:
    """Persist a preference profile to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "token_weights": profile.token_weights,
        "tag_weights": profile.tag_weights,
        "remote_level_weights": profile.remote_level_weights,
        "seniority_weights": profile.seniority_weights,
        "duplicate_ids": sorted(profile.duplicate_ids),
        "last_update_id": profile.last_update_id,
        "feedback_cache": profile.feedback_cache,
        "updated_at": profile.updated_at,
    }
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2),
        encoding="utf-8",
    )


def apply_preferences(
    posting: JobPosting,
    match: MatchResult,
    profile: PreferenceProfile,
    config: Mapping[str, object],
) -> MatchResult:
    """Return a match with preference-based score adjustments applied."""

    personalization = _as_dict(config.get("personalization"))
    if not bool(personalization.get("enabled", False)):
        return match
    if match.decision != "accepted":
        return match

    base_score = match.score or 0
    score_delta, label = _compute_preference_delta(
        posting, match, profile, personalization
    )
    if score_delta == 0:
        return match

    updated_score = base_score + score_delta
    if score_delta > 0:
        bonuses = list(match.score_bonuses) + [label]
        return replace(match, score=updated_score, score_bonuses=bonuses)
    penalties = list(match.score_penalties) + [label]
    return replace(match, score=updated_score, score_penalties=penalties)


def apply_telegram_feedback(
    profile: PreferenceProfile,
    config: Mapping[str, object],
) -> PreferenceProfile:
    """Update profile weights from Telegram feedback callbacks."""

    personalization = _as_dict(config.get("personalization"))
    if not bool(personalization.get("enabled", False)):
        return profile
    if not bool(personalization.get("feedback_enabled", True)):
        return profile
    notifications = _as_dict(config.get("notifications"))
    telegram_config = _as_dict(notifications.get("telegram"))
    if not bool(telegram_config.get("enabled", True)):
        return profile

    offset = profile.last_update_id + 1 if profile.last_update_id else None
    updates, reason = telegram_notifier.get_updates(offset=offset)
    if reason:
        logger.info("Telegram feedback skipped: %s.", reason)
        return profile
    if not updates:
        return profile

    max_update_id = profile.last_update_id or 0
    updated_profile = profile
    for update in updates:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            max_update_id = max(max_update_id, update_id)
        callback = update.get("callback_query")
        if not isinstance(callback, Mapping):
            continue
        callback_id = callback.get("id")
        data = callback.get("data")
        if not isinstance(data, str):
            continue
        action, job_key = _parse_callback_data(data)
        if not action or not job_key:
            continue
        if callback_id:
            telegram_notifier.answer_callback_query(str(callback_id))
        updated_profile = _apply_feedback_action(
            updated_profile,
            action,
            job_key,
            personalization,
        )
    return replace(
        updated_profile,
        last_update_id=max_update_id,
        updated_at=_now_iso(),
    )


def apply_feedback(
    profile: PreferenceProfile,
    *,
    action: str,
    job_key: str,
    cached_item: Mapping[str, object],
    config: Mapping[str, object],
) -> PreferenceProfile:
    """Apply a feedback action using cached item metadata."""

    personalization = _as_dict(config.get("personalization"))
    enriched = replace(
        profile, feedback_cache={job_key: dict(cached_item)}
    )
    return _apply_feedback_action(
        enriched, action, job_key, personalization
    )


def update_feedback_cache(
    profile: PreferenceProfile,
    rows: Iterable[object],
    max_items: int,
) -> PreferenceProfile:
    """Store features for the latest digest items."""

    cache = dict(profile.feedback_cache)
    for row in rows:
        posting = getattr(row, "posting", None)
        match = getattr(row, "match", None)
        if not posting or not match:
            continue
        key = f"{posting.source}:{posting.id}"
        cache[key] = {
            "title": posting.title,
            "description_snippet": posting.description_snippet,
            "tags": list(posting.tags),
            "remote_level": match.remote_level,
        }
    if max_items > 0 and len(cache) > max_items:
        trimmed = dict(list(cache.items())[-max_items:])
    else:
        trimmed = cache
    return replace(
        profile,
        feedback_cache=trimmed,
        updated_at=_now_iso(),
    )


def _compute_preference_delta(
    posting: JobPosting,
    match: MatchResult,
    profile: PreferenceProfile,
    personalization: Mapping[str, object],
) -> tuple[int, str]:
    max_abs = _parse_int(personalization.get("max_abs_weight"), 10)
    min_length = _parse_int(personalization.get("min_token_length"), 3)
    tokens = _extract_tokens(
        f"{posting.title} {posting.description_snippet}".lower(),
        min_length,
    )
    token_matches = sorted(
        [
            token
            for token in profile.token_weights
            if token in tokens
        ]
    )
    tag_matches = sorted(
        [tag for tag in posting.tags if tag in profile.tag_weights]
    )

    token_score = sum(
        profile.token_weights[token] for token in token_matches
    )
    tag_score = sum(profile.tag_weights[tag] for tag in tag_matches)

    remote_level = match.remote_level or ""
    remote_score = profile.remote_level_weights.get(remote_level, 0)

    seniority_matches = _extract_seniority_matches(
        posting.title, personalization
    )
    seniority_score = sum(
        profile.seniority_weights.get(label, 0)
        for label in seniority_matches
    )

    total = token_score + tag_score + remote_score + seniority_score
    if total > max_abs:
        total = max_abs
    if total < -max_abs:
        total = -max_abs

    details: list[str] = []
    if token_matches:
        details.append(f"tokens: {', '.join(token_matches)}")
    if tag_matches:
        details.append(f"tags: {', '.join(tag_matches)}")
    if remote_score:
        details.append(f"remote: {remote_level}")
    if seniority_matches:
        details.append(f"seniority: {', '.join(seniority_matches)}")
    label = (
        f"preference:{total:+d}"
        + (f" ({'; '.join(details)})" if details else "")
    )
    return total, label


def _apply_feedback_action(
    profile: PreferenceProfile,
    action: str,
    job_key: str,
    personalization: Mapping[str, object],
) -> PreferenceProfile:
    token_delta = _feedback_delta(
        action, personalization, "token_weight_step"
    )
    tag_delta = _feedback_delta(
        action, personalization, "tag_weight_step"
    )
    remote_delta = _feedback_delta(
        action, personalization, "remote_level_step"
    )
    seniority_delta = _feedback_delta(
        action, personalization, "seniority_step"
    )
    duplicate_ids = set(profile.duplicate_ids)
    if action == "duplicate":
        duplicate_ids.add(job_key)
    cached = profile.feedback_cache.get(job_key, {})
    if not cached:
        return replace(profile, duplicate_ids=duplicate_ids)

    title = str(cached.get("title", ""))
    snippet = str(cached.get("description_snippet", ""))
    tags = cached.get("tags", []) or []
    remote_level = str(cached.get("remote_level", ""))

    min_length = _parse_int(personalization.get("min_token_length"), 3)
    tokens = _extract_tokens(
        f"{title} {snippet}".lower(), min_length
    )
    token_weights = _adjust_weights(
        profile.token_weights, tokens, token_delta, personalization
    )
    tag_weights = _adjust_weights(
        profile.tag_weights, tags, tag_delta, personalization
    )
    remote_weights = _adjust_weights(
        profile.remote_level_weights,
        [remote_level] if remote_level else [],
        remote_delta,
        personalization,
    )
    seniority_matches = _extract_seniority_matches(
        title, personalization
    )
    seniority_weights = _adjust_weights(
        profile.seniority_weights,
        seniority_matches,
        seniority_delta,
        personalization,
    )

    return replace(
        profile,
        token_weights=token_weights,
        tag_weights=tag_weights,
        remote_level_weights=remote_weights,
        seniority_weights=seniority_weights,
        duplicate_ids=duplicate_ids,
    )


def _feedback_delta(
    action: str,
    personalization: Mapping[str, object],
    step_key: str,
) -> int:
    step = _parse_int(personalization.get(step_key), 2)
    if action == "like":
        return step
    if action == "love":
        return step * 2
    if action == "dislike":
        return -step
    return 0


def _adjust_weights(
    weights: dict[str, int],
    keys: Iterable[str],
    delta: int,
    personalization: Mapping[str, object],
) -> dict[str, int]:
    max_abs = _parse_int(personalization.get("max_abs_weight"), 10)
    if not delta:
        return dict(weights)
    updated = dict(weights)
    for key in keys:
        if not isinstance(key, str) or not key:
            continue
        key = key.lower()
        updated[key] = max(
            min(updated.get(key, 0) + delta, max_abs), -max_abs
        )
        if updated[key] == 0:
            updated.pop(key, None)
    return updated


def _extract_tokens(text: str, min_length: int) -> set[str]:
    tokens = {
        token
        for token in _TOKEN_RE.findall(text)
        if len(token) >= min_length
    }
    return tokens


def _extract_seniority_matches(
    title: str, personalization: Mapping[str, object]
) -> list[str]:
    keywords = personalization.get("seniority_keywords")
    if not isinstance(keywords, Iterable) or isinstance(keywords, str):
        keywords = ["manager", "lead", "head"]
    title_lower = title.lower()
    matches = [
        str(keyword).lower()
        for keyword in keywords
        if isinstance(keyword, str) and keyword.lower() in title_lower
    ]
    return sorted(set(matches))


def _parse_callback_data(data: str) -> tuple[str | None, str | None]:
    if not data.startswith("pref:"):
        return None, None
    parts = data.split(":", 3)
    if len(parts) != 4:
        return None, None
    action_map = {
        "up": "like",
        "down": "dislike",
        "star": "love",
        "dup": "duplicate",
    }
    action = action_map.get(parts[1])
    job_key = f"{parts[2]}:{parts[3]}" if parts[2] and parts[3] else None
    return action, job_key


def _empty_profile() -> PreferenceProfile:
    return PreferenceProfile(
        token_weights={},
        tag_weights={},
        remote_level_weights={},
        seniority_weights={},
        duplicate_ids=set(),
        last_update_id=None,
        feedback_cache={},
        updated_at=_now_iso(),
    )


def _parse_profile(payload: Mapping[str, object]) -> PreferenceProfile:
    return PreferenceProfile(
        token_weights=_coerce_weights(payload.get("token_weights")),
        tag_weights=_coerce_weights(payload.get("tag_weights")),
        remote_level_weights=_coerce_weights(
            payload.get("remote_level_weights")
        ),
        seniority_weights=_coerce_weights(
            payload.get("seniority_weights")
        ),
        duplicate_ids=set(
            str(item)
            for item in payload.get("duplicate_ids", [])
            if item
        ),
        last_update_id=_coerce_int(payload.get("last_update_id")),
        feedback_cache=_coerce_cache(payload.get("feedback_cache")),
        updated_at=str(payload.get("updated_at") or _now_iso()),
    )


def _coerce_weights(raw: object) -> dict[str, int]:
    if not isinstance(raw, Mapping):
        return {}
    parsed: dict[str, int] = {}
    for key, value in raw.items():
        if not key:
            continue
        try:
            parsed[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return parsed


def _coerce_cache(raw: object) -> dict[str, dict[str, object]]:
    if not isinstance(raw, Mapping):
        return {}
    cache: dict[str, dict[str, object]] = {}
    for key, value in raw.items():
        if not isinstance(value, Mapping):
            continue
        cache[str(key)] = {
            "title": value.get("title", ""),
            "description_snippet": value.get("description_snippet", ""),
            "tags": value.get("tags", []) or [],
            "remote_level": value.get("remote_level", ""),
        }
    return cache


def _coerce_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(raw: object) -> dict[str, object]:
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}
