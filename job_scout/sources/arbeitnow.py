"""Arbeitnow API source connector (public, non-authenticated)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

from job_scout.normalize import SourceJob

ARBEITNOW_API_URL = "https://www.arbeitnow.com/api/job-board-api"
_COUNTRY_RE = re.compile(
    r"Country:\s*([A-Za-z .-]+?)(?:\s+City:|$)",
    re.IGNORECASE,
)
_GERMANY_HINT_RE = re.compile(
    r"\bGermany\b|\bGerman\b|\bDeutschland\b",
    re.IGNORECASE,
)


class ArbeitnowSourceError(RuntimeError):
    """Raised when Arbeitnow fetch or parse fails."""


def fetch_arbeitnow(since_days: int) -> list[SourceJob]:
    """Fetch job postings from Arbeitnow within the given time window."""

    payload = _fetch_arbeitnow_payload()
    return _parse_arbeitnow_payload(payload, since_days)


def _fetch_arbeitnow_payload() -> dict:
    fixture_payload = _load_fixture_payload()
    if fixture_payload is not None:
        return fixture_payload
    if os.getenv("NO_NETWORK") == "1":
        raise ArbeitnowSourceError(
            "Network disabled (NO_NETWORK=1); use fixtures or integration tests."
        )
    request = urllib.request.Request(
        ARBEITNOW_API_URL,
        headers={
            "User-Agent": "job_scout/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise ArbeitnowSourceError(
            f"Arbeitnow HTTP error: {exc.code} for {ARBEITNOW_API_URL}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ArbeitnowSourceError(
            f"Arbeitnow connection error: {exc.reason}"
        ) from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ArbeitnowSourceError(
            "Arbeitnow returned invalid JSON"
        ) from exc


def _parse_arbeitnow_payload(
    payload: dict, since_days: int
) -> list[SourceJob]:
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - since_days * 86400

    postings: list[SourceJob] = []
    for job in payload.get("data", []):
        posted_at = _parse_created_at(job.get("created_at"))
        if posted_at is None:
            continue
        if posted_at.timestamp() < cutoff:
            continue

        location_text = str(job.get("location") or "").strip()
        location_country = _extract_country(
            job.get("description", ""),
            location_text,
        )
        location_city = _extract_city(location_text)
        remote_type = "full-remote" if bool(job.get("remote")) else "unknown"
        description = _strip_html(str(job.get("description") or ""))
        tags = [str(tag) for tag in job.get("tags", []) if str(tag).strip()]

        postings.append(
            SourceJob(
                id=f"arbeitnow-{job.get('slug') or job.get('url')}",
                source="arbeitnow",
                company=str(job.get("company_name") or "Unknown"),
                title=str(job.get("title") or ""),
                location_text=location_text or "Unknown",
                location_country=location_country,
                location_city=location_city,
                remote_type=remote_type,
                url=str(job.get("url") or ""),
                posted_at=posted_at,
                salary_text=None,
                currency=None,
                tags=tags,
                description_snippet=description[:140].strip(),
            )
        )
    return postings


def parse_arbeitnow_payload(
    payload: dict, since_days: int
) -> list[SourceJob]:
    """Parse Arbeitnow payloads for unit testing."""

    return _parse_arbeitnow_payload(payload, since_days)


def _parse_created_at(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str) and value.strip().isdigit():
        return datetime.fromtimestamp(int(value.strip()), tz=timezone.utc)
    return None


def _extract_country(description: str, location_text: str) -> str:
    plain_description = _strip_html(description)
    match = _COUNTRY_RE.search(plain_description)
    if match:
        return match.group(1).strip()
    if (
        location_text
        and "," not in location_text
        and _GERMANY_HINT_RE.search(plain_description)
    ):
        return "Germany"
    if "," in location_text:
        parts = [part.strip() for part in location_text.split(",") if part.strip()]
        if parts:
            return parts[-1]
    return ""


def _extract_city(location_text: str) -> str:
    if not location_text:
        return ""
    parts = [part.strip() for part in location_text.split(",") if part.strip()]
    if not parts:
        return ""
    return parts[0]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).replace("&nbsp;", " ").strip()


def _load_fixture_payload() -> dict | None:
    fixture_dir = os.getenv("JOB_SCOUT_FIXTURE_DIR")
    if not fixture_dir:
        return None
    fixture_path = Path(fixture_dir) / "arbeitnow_sample.json"
    if not fixture_path.exists():
        return None
    return json.loads(fixture_path.read_text(encoding="utf-8"))
