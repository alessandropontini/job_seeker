"""Remotive API source connector (public, non-authenticated)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

import urllib.error
import urllib.request

from job_scout.normalize import SourceJob

REMOTIVE_API_URL = "https://remotive.com/api/remote-jobs"


class RemotiveSourceError(RuntimeError):
    """Raised when Remotive fetch or parse fails."""


def fetch_remotive(since_days: int) -> list[SourceJob]:
    """Fetch job postings from Remotive API within the given window."""

    payload = _fetch_remotive_payload()
    return _parse_remotive_payload(payload, since_days)


def _fetch_remotive_payload() -> dict:
    fixture_payload = _load_fixture_payload()
    if fixture_payload is not None:
        return fixture_payload
    if os.getenv("NO_NETWORK") == "1":
        raise RemotiveSourceError(
            "Network disabled (NO_NETWORK=1); use fixtures or integration tests."
        )
    try:
        with urllib.request.urlopen(
            REMOTIVE_API_URL, timeout=30
        ) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RemotiveSourceError(
            f"Remotive HTTP error: {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RemotiveSourceError(
            f"Remotive connection error: {exc.reason}"
        ) from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RemotiveSourceError("Remotive returned invalid JSON") from exc


def _parse_remotive_payload(
    payload: dict, since_days: int
) -> list[SourceJob]:
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - since_days * 86400

    postings: list[SourceJob] = []
    for job in payload.get("jobs", []):
        posted_at = _parse_remotive_date(job.get("publication_date"))
        if posted_at is None:
            continue
        if posted_at.timestamp() < cutoff:
            continue
        postings.append(
            SourceJob(
                id=f"remotive-{job.get('id')}",
                source="remotive",
                company=job.get("company_name", "Unknown"),
                title=job.get("title", ""),
                location_text=job.get("candidate_required_location", ""),
                location_country=_extract_country(
                    job.get("candidate_required_location", "")
                ),
                location_city=_extract_city(
                    job.get("candidate_required_location", "")
                ),
                remote_type="full-remote",
                url=job.get("url", ""),
                posted_at=posted_at,
                salary_text=job.get("salary") or None,
                currency=_extract_currency(job.get("salary")),
                tags=list(job.get("tags", [])),
                description_snippet=(
                    job.get("description", "")[:140].strip()
                ),
            )
        )
    return postings


def _parse_remotive_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_country(location: str) -> str:
    if not location:
        return ""
    parts = [part.strip() for part in location.split(",") if part.strip()]
    if not parts:
        return ""
    return parts[-1]


def _extract_city(location: str) -> str:
    if not location:
        return ""
    parts = [part.strip() for part in location.split(",") if part.strip()]
    if not parts:
        return ""
    return parts[0]


def _extract_currency(salary_text: str | None) -> str | None:
    if not salary_text:
        return None
    lowered = salary_text.lower()
    if "€" in salary_text or "eur" in lowered:
        return "EUR"
    if "$" in salary_text or "usd" in lowered:
        return "USD"
    if "£" in salary_text or "gbp" in lowered:
        return "GBP"
    return None


def parse_remotive_payload(
    payload: dict, since_days: int
) -> list[SourceJob]:
    """Parse Remotive payloads (public API) for unit testing."""

    return _parse_remotive_payload(payload, since_days)


def _load_fixture_payload() -> dict | None:
    fixture_dir = os.getenv("JOB_SCOUT_FIXTURE_DIR")
    if not fixture_dir:
        return None
    fixture_path = Path(fixture_dir) / "remotive_sample.json"
    if not fixture_path.exists():
        return None
    return json.loads(fixture_path.read_text(encoding="utf-8"))
