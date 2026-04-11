"""Greenhouse Job Board API connector (public, non-authenticated)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

from job_scout.normalize import SourceJob

GREENHOUSE_BOARD_API_TEMPLATE = (
    "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
)
GREENHOUSE_DEFAULT_BOARDS = [
    "datadog",
    "mongodb",
    "sumup",
    "doctolib",
    "elastic",
    "monzo",
    "contentful",
    "n26",
]
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


class GreenhouseSourceError(RuntimeError):
    """Raised when Greenhouse fetch or parse fails."""


def fetch_greenhouse(
    since_days: int,
    config: Mapping[str, object] | None = None,
) -> list[SourceJob]:
    """Fetch job postings from curated Greenhouse boards."""

    fixture_payload = _load_fixture_payload()
    if fixture_payload is not None:
        return _parse_fixture_payload(fixture_payload, since_days)

    boards = _resolve_boards(config)
    postings: list[SourceJob] = []
    for board in boards:
        try:
            payload = _fetch_greenhouse_payload(board)
        except GreenhouseSourceError:
            continue
        postings.extend(_parse_greenhouse_payload(payload, since_days, board))
    return postings


def parse_greenhouse_payload(
    payload: dict, since_days: int, board: str
) -> list[SourceJob]:
    """Parse a Greenhouse board payload for unit testing."""

    return _parse_greenhouse_payload(payload, since_days, board)


def _resolve_boards(config: Mapping[str, object] | None) -> list[str]:
    env_value = os.getenv("JOB_SCOUT_GREENHOUSE_BOARDS", "").strip()
    if env_value:
        boards = [item.strip().lower() for item in env_value.split(",") if item.strip()]
        if boards:
            return boards
    if isinstance(config, Mapping):
        sources = config.get("sources")
        if isinstance(sources, Mapping):
            greenhouse = sources.get("greenhouse")
            if isinstance(greenhouse, Mapping):
                boards = greenhouse.get("boards")
                if isinstance(boards, list):
                    normalized = [
                        str(item).strip().lower()
                        for item in boards
                        if str(item).strip()
                    ]
                    if normalized:
                        return normalized
    return list(GREENHOUSE_DEFAULT_BOARDS)


def _fetch_greenhouse_payload(board: str) -> dict:
    if os.getenv("NO_NETWORK") == "1":
        raise GreenhouseSourceError(
            "Network disabled (NO_NETWORK=1); use fixtures or integration tests."
        )
    url = GREENHOUSE_BOARD_API_TEMPLATE.format(board=board)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "job_scout/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise GreenhouseSourceError(
            f"Greenhouse HTTP error: {exc.code} for {board}"
        ) from exc
    except urllib.error.URLError as exc:
        raise GreenhouseSourceError(
            f"Greenhouse connection error for {board}: {exc.reason}"
        ) from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise GreenhouseSourceError(
            f"Greenhouse returned invalid JSON for {board}"
        ) from exc


def _parse_greenhouse_payload(
    payload: dict, since_days: int, board: str
) -> list[SourceJob]:
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - since_days * 86400

    postings: list[SourceJob] = []
    for job in payload.get("jobs", []):
        posted_at = _parse_greenhouse_date(
            job.get("first_published") or job.get("updated_at")
        )
        if posted_at is None or posted_at.timestamp() < cutoff:
            continue

        location_text = _extract_location_text(job.get("location"))
        remote_type = _extract_remote_type(location_text)
        company = str(job.get("company_name") or _humanize_company(board))
        description = _html_to_text(str(job.get("content") or ""))
        tags = _extract_tags(job)

        postings.append(
            SourceJob(
                id=f"greenhouse-{board}-{job.get('id')}",
                source="greenhouse",
                company=company,
                title=str(job.get("title") or ""),
                location_text=location_text or "Unknown",
                location_country=_extract_country(location_text),
                location_city=_extract_city(location_text),
                remote_type=remote_type,
                url=str(job.get("absolute_url") or ""),
                posted_at=posted_at,
                salary_text=_extract_salary_text(job.get("metadata")),
                currency=None,
                tags=tags,
                description_snippet=description[:220].strip(),
            )
        )
    return postings


def _parse_fixture_payload(payload: dict, since_days: int) -> list[SourceJob]:
    if "jobs" in payload:
        return _parse_greenhouse_payload(payload, since_days, "fixture")
    postings: list[SourceJob] = []
    for board, board_payload in payload.items():
        if isinstance(board_payload, dict):
            postings.extend(_parse_greenhouse_payload(board_payload, since_days, str(board)))
    return postings


def _parse_greenhouse_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_location_text(value: object) -> str:
    if isinstance(value, Mapping):
        name = value.get("name")
        if isinstance(name, str):
            return name.strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def _extract_remote_type(location_text: str) -> str:
    lowered = location_text.lower()
    if "hybrid" in lowered:
        return "hybrid"
    if "remote" in lowered:
        return "full-remote"
    if location_text:
        return "onsite"
    return "unknown"


def _extract_country(location_text: str) -> str:
    if not location_text:
        return ""
    cleaned = location_text.replace("Remote", "").replace("remote", "").strip(" -")
    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    if not parts:
        return ""
    return parts[-1]


def _extract_city(location_text: str) -> str:
    if not location_text:
        return ""
    cleaned = location_text.replace("Remote", "").replace("remote", "").strip(" -")
    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    if not parts:
        return ""
    return parts[0]


def _extract_tags(job: Mapping[str, object]) -> list[str]:
    tags: list[str] = []
    for collection_key in ("departments", "offices"):
        collection = job.get(collection_key)
        if not isinstance(collection, list):
            continue
        for entry in collection:
            if isinstance(entry, Mapping):
                name = entry.get("name")
                if isinstance(name, str) and name.strip():
                    tags.append(name.strip())
    metadata = job.get("metadata")
    if isinstance(metadata, list):
        for entry in metadata:
            if not isinstance(entry, Mapping):
                continue
            value = entry.get("value")
            if isinstance(value, str) and value.strip():
                tags.append(value.strip())
    return sorted(set(tags), key=str.lower)


def _extract_salary_text(metadata: object) -> str | None:
    if not isinstance(metadata, list):
        return None
    for entry in metadata:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name") or "").lower()
        value = entry.get("value")
        if "pay transparency" not in name and "salary" not in name:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _humanize_company(board: str) -> str:
    return board.replace("-", " ").replace("_", " ").title()


def _html_to_text(value: str) -> str:
    text = html.unescape(value).replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = _TAG_RE.sub(" ", text)
    lines = [_WHITESPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _load_fixture_payload() -> dict | None:
    fixture_dir = os.getenv("JOB_SCOUT_FIXTURE_DIR")
    if not fixture_dir:
        return None
    fixture_path = Path(fixture_dir) / "greenhouse_sample.json"
    if not fixture_path.exists():
        return None
    return json.loads(fixture_path.read_text(encoding="utf-8"))
