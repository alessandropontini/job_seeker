"""Lever Postings API connector (public, non-authenticated)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

from job_scout.normalize import SourceJob

LEVER_POSTINGS_API_TEMPLATE = "https://api.lever.co/v0/postings/{company}?mode=json"
LEVER_DEFAULT_COMPANIES: list[str] = []
_WHITESPACE_RE = re.compile(r"\s+")


class LeverSourceError(RuntimeError):
    """Raised when Lever fetch or parse fails."""


def fetch_lever(
    since_days: int,
    config: Mapping[str, object] | None = None,
) -> list[SourceJob]:
    """Fetch job postings from configured Lever companies."""

    fixture_payload = _load_fixture_payload()
    if fixture_payload is not None:
        return _parse_fixture_payload(fixture_payload, since_days)

    companies = _resolve_companies(config)
    postings: list[SourceJob] = []
    for company in companies:
        try:
            payload = _fetch_lever_payload(company)
        except LeverSourceError:
            continue
        postings.extend(_parse_lever_payload(payload, since_days, company))
    return postings


def parse_lever_payload(
    payload: list[dict], since_days: int, company: str
) -> list[SourceJob]:
    """Parse a Lever postings payload for unit testing."""

    return _parse_lever_payload(payload, since_days, company)


def _resolve_companies(config: Mapping[str, object] | None) -> list[str]:
    env_value = os.getenv("JOB_SCOUT_LEVER_COMPANIES", "").strip()
    if env_value:
        companies = [item.strip().lower() for item in env_value.split(",") if item.strip()]
        if companies:
            return companies
    if isinstance(config, Mapping):
        sources = config.get("sources")
        if isinstance(sources, Mapping):
            lever = sources.get("lever")
            if isinstance(lever, Mapping):
                companies = lever.get("companies")
                if isinstance(companies, list):
                    normalized = [
                        str(item).strip().lower()
                        for item in companies
                        if str(item).strip()
                    ]
                    if normalized:
                        return normalized
    return list(LEVER_DEFAULT_COMPANIES)


def _fetch_lever_payload(company: str) -> list[dict]:
    if os.getenv("NO_NETWORK") == "1":
        raise LeverSourceError(
            "Network disabled (NO_NETWORK=1); use fixtures or integration tests."
        )
    url = LEVER_POSTINGS_API_TEMPLATE.format(company=company)
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
        raise LeverSourceError(
            f"Lever HTTP error: {exc.code} for {company}"
        ) from exc
    except urllib.error.URLError as exc:
        raise LeverSourceError(
            f"Lever connection error for {company}: {exc.reason}"
        ) from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LeverSourceError(f"Lever returned invalid JSON for {company}") from exc
    if not isinstance(payload, list):
        raise LeverSourceError(f"Lever returned unexpected payload for {company}")
    return payload


def _parse_lever_payload(
    payload: list[dict], since_days: int, company: str
) -> list[SourceJob]:
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - since_days * 86400

    postings: list[SourceJob] = []
    for job in payload:
        posted_at = _parse_created_at(job.get("createdAt"))
        if posted_at is None or posted_at.timestamp() < cutoff:
            continue
        categories = job.get("categories") if isinstance(job.get("categories"), Mapping) else {}
        location_text = str(categories.get("location") or job.get("country") or "").strip()
        remote_type = _extract_remote_type(job, location_text)
        description = _normalize_text(
            f"{job.get('descriptionPlain') or ''}\n{job.get('openingPlain') or ''}\n{job.get('additionalPlain') or ''}"
        )

        postings.append(
            SourceJob(
                id=f"lever-{company}-{job.get('id')}",
                source="lever",
                company=_humanize_company(company),
                title=str(job.get("text") or ""),
                location_text=location_text or "Unknown",
                location_country=str(job.get("country") or ""),
                location_city=_extract_city(location_text),
                remote_type=remote_type,
                url=str(job.get("hostedUrl") or ""),
                posted_at=posted_at,
                salary_text=_extract_salary_text(job.get("salaryRange")),
                currency=_extract_salary_currency(job.get("salaryRange")),
                tags=_extract_tags(categories),
                description_snippet=description[:220].strip(),
            )
        )
    return postings


def _parse_fixture_payload(payload: object, since_days: int) -> list[SourceJob]:
    if isinstance(payload, list):
        return _parse_lever_payload(payload, since_days, "fixture")
    postings: list[SourceJob] = []
    if isinstance(payload, dict):
        for company, company_payload in payload.items():
            if isinstance(company_payload, list):
                postings.extend(_parse_lever_payload(company_payload, since_days, str(company)))
    return postings


def _parse_created_at(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return None


def _extract_remote_type(job: Mapping[str, object], location_text: str) -> str:
    workplace_type = str(job.get("workplaceType") or "").lower()
    if workplace_type == "remote":
        return "full-remote"
    if workplace_type == "hybrid":
        return "hybrid"
    if workplace_type == "on-site":
        return "onsite"
    if "remote" in location_text.lower():
        return "full-remote"
    if location_text:
        return "onsite"
    return "unknown"


def _extract_salary_text(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    minimum = value.get("min")
    maximum = value.get("max")
    currency = value.get("currency")
    if minimum is None and maximum is None:
        return None
    low = int(minimum) if isinstance(minimum, (int, float)) else None
    high = int(maximum) if isinstance(maximum, (int, float)) else None
    if low is None and high is None:
        return None
    currency_label = str(currency).upper() if currency else ""
    if low is not None and high is not None:
        return f"{currency_label} {low}-{high}".strip()
    return f"{currency_label} {low or high}".strip()


def _extract_salary_currency(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    currency = value.get("currency")
    if isinstance(currency, str) and currency.strip():
        return currency.strip().upper()
    return None


def _extract_city(location_text: str) -> str:
    if not location_text:
        return ""
    parts = [part.strip() for part in location_text.split(",") if part.strip()]
    return parts[0] if parts else ""


def _extract_tags(categories: Mapping[str, object]) -> list[str]:
    tags: list[str] = []
    for value in categories.values():
        if isinstance(value, str) and value.strip():
            tags.append(value.strip())
        elif isinstance(value, list):
            tags.extend(
                item.strip()
                for item in value
                if isinstance(item, str) and item.strip()
            )
    return sorted(set(tags), key=str.lower)


def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _humanize_company(company: str) -> str:
    return company.replace("-", " ").replace("_", " ").title()


def _load_fixture_payload() -> object | None:
    fixture_dir = os.getenv("JOB_SCOUT_FIXTURE_DIR")
    if not fixture_dir:
        return None
    fixture_path = Path(fixture_dir) / "lever_sample.json"
    if not fixture_path.exists():
        return None
    return json.loads(fixture_path.read_text(encoding="utf-8"))
