"""Ashby public job board connector (non-authenticated posting API)."""

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

ASHBY_BOARD_API_TEMPLATE = (
    "https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"
)
ASHBY_DEFAULT_BOARDS = [
    "Ashby",
    "Omnea",
    "Pleo",
    "Vanta",
    "Writer",
    "Airbyte",
    "Astronomer",
    "Linear",
]
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


class AshbySourceError(RuntimeError):
    """Raised when Ashby fetch or parse fails."""


def fetch_ashby(
    since_days: int,
    config: Mapping[str, object] | None = None,
) -> list[SourceJob]:
    """Fetch job postings from curated Ashby public boards."""

    fixture_payload = _load_fixture_payload()
    if fixture_payload is not None:
        return _parse_fixture_payload(fixture_payload, since_days)

    boards = _resolve_boards(config)
    postings: list[SourceJob] = []
    for board in boards:
        try:
            payload = _fetch_ashby_payload(board)
        except AshbySourceError:
            continue
        postings.extend(_parse_ashby_payload(payload, since_days, board))
    return postings


def parse_ashby_payload(
    payload: dict, since_days: int, board: str
) -> list[SourceJob]:
    """Parse an Ashby payload for unit testing."""

    return _parse_ashby_payload(payload, since_days, board)


def _resolve_boards(config: Mapping[str, object] | None) -> list[str]:
    env_value = os.getenv("JOB_SCOUT_ASHBY_BOARDS", "").strip()
    if env_value:
        boards = [item.strip() for item in env_value.split(",") if item.strip()]
        if boards:
            return boards
    if isinstance(config, Mapping):
        sources = config.get("sources")
        if isinstance(sources, Mapping):
            ashby = sources.get("ashby")
            if isinstance(ashby, Mapping):
                boards = ashby.get("boards")
                if isinstance(boards, list):
                    normalized = [
                        str(item).strip()
                        for item in boards
                        if str(item).strip()
                    ]
                    if normalized:
                        return normalized
    return list(ASHBY_DEFAULT_BOARDS)


def _fetch_ashby_payload(board: str) -> dict:
    if os.getenv("NO_NETWORK") == "1":
        raise AshbySourceError(
            "Network disabled (NO_NETWORK=1); use fixtures or integration tests."
        )
    url = ASHBY_BOARD_API_TEMPLATE.format(board=board)
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
        raise AshbySourceError(
            f"Ashby HTTP error: {exc.code} for {board}"
        ) from exc
    except urllib.error.URLError as exc:
        raise AshbySourceError(
            f"Ashby connection error for {board}: {exc.reason}"
        ) from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AshbySourceError(
            f"Ashby returned invalid JSON for {board}"
        ) from exc
    if not isinstance(payload, dict):
        raise AshbySourceError(f"Ashby returned unexpected payload for {board}")
    return payload


def _parse_ashby_payload(
    payload: dict, since_days: int, board: str
) -> list[SourceJob]:
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - since_days * 86400

    postings: list[SourceJob] = []
    for job in payload.get("jobs", []):
        if not isinstance(job, Mapping):
            continue
        posted_at = _parse_ashby_date(job.get("publishedAt"))
        if posted_at is None or posted_at.timestamp() < cutoff:
            continue

        location_text = _extract_location_text(job)
        remote_type = _extract_remote_type(job, location_text)
        company = _humanize_company(board)
        description = _extract_description(job)
        tags = _extract_tags(job)

        postings.append(
            SourceJob(
                id=f"ashby-{board}-{job.get('id')}",
                source="ashby",
                company=company,
                title=str(job.get("title") or ""),
                location_text=location_text or "Unknown",
                location_country=_extract_country(job, location_text),
                location_city=_extract_city(job, location_text),
                remote_type=remote_type,
                url=str(job.get("jobUrl") or job.get("applyUrl") or ""),
                posted_at=posted_at,
                salary_text=_extract_salary_text(job.get("compensation")),
                currency=_extract_salary_currency(job.get("compensation")),
                tags=tags,
                description_snippet=description[:220].strip(),
            )
        )
    return postings


def _parse_fixture_payload(payload: object, since_days: int) -> list[SourceJob]:
    if isinstance(payload, dict) and "jobs" in payload:
        return _parse_ashby_payload(payload, since_days, "fixture")
    postings: list[SourceJob] = []
    if isinstance(payload, dict):
        for board, board_payload in payload.items():
            if isinstance(board_payload, dict):
                postings.extend(
                    _parse_ashby_payload(board_payload, since_days, str(board))
                )
    return postings


def _parse_ashby_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_location_text(job: Mapping[str, object]) -> str:
    location = str(job.get("location") or "").strip()
    secondary = job.get("secondaryLocations")
    if not isinstance(secondary, list) or not secondary:
        return location
    secondary_names = []
    for entry in secondary[:3]:
        if isinstance(entry, Mapping):
            name = str(entry.get("location") or "").strip()
            if name:
                secondary_names.append(name)
    if not secondary_names:
        return location
    if location:
        return "; ".join([location, *secondary_names])
    return "; ".join(secondary_names)


def _extract_remote_type(
    job: Mapping[str, object], location_text: str
) -> str:
    workplace_type = str(job.get("workplaceType") or "").lower()
    if workplace_type == "remote":
        return "full-remote"
    if workplace_type == "hybrid":
        return "hybrid"
    if workplace_type in {"onsite", "on-site"}:
        return "onsite"
    if bool(job.get("isRemote")):
        return "full-remote"
    if "remote" in location_text.lower():
        return "full-remote"
    if location_text:
        return "onsite"
    return "unknown"


def _extract_country(job: Mapping[str, object], location_text: str) -> str:
    address = job.get("address")
    country = _extract_address_country(address)
    if country:
        return country
    primary_location = _first_location_token(location_text)
    lowered = primary_location.lower()
    if "remote u.s" in lowered or "united states" in lowered or lowered.endswith(" usa"):
        return "USA"
    if "remote uk" in lowered:
        return "United Kingdom"
    parts = [part.strip() for part in primary_location.split(",") if part.strip()]
    if len(parts) >= 2:
        return parts[-1]
    return ""


def _extract_city(job: Mapping[str, object], location_text: str) -> str:
    address = job.get("address")
    city = _extract_address_locality(address)
    if city:
        return city
    primary_location = _first_location_token(location_text)
    parts = [part.strip() for part in primary_location.split(",") if part.strip()]
    if not parts:
        return ""
    return parts[0]


def _extract_description(job: Mapping[str, object]) -> str:
    description = str(job.get("descriptionPlain") or "").strip()
    if description:
        return _normalize_text(description)
    html = str(job.get("descriptionHtml") or "")
    plain = _TAG_RE.sub(" ", html)
    return _normalize_text(plain)


def _extract_tags(job: Mapping[str, object]) -> list[str]:
    tags: list[str] = []
    for key in ("department", "team", "employmentType"):
        value = job.get(key)
        if isinstance(value, str) and value.strip():
            tags.append(value.strip())
    compensation = job.get("compensation")
    if isinstance(compensation, Mapping):
        summary = compensation.get("scrapeableCompensationSalarySummary")
        if isinstance(summary, str) and summary.strip():
            tags.append("salary_listed")
    return sorted(set(tags), key=str.lower)


def _extract_salary_text(compensation: object) -> str | None:
    if not isinstance(compensation, Mapping):
        return None
    for key in (
        "scrapeableCompensationSalarySummary",
        "compensationTierSummary",
    ):
        value = compensation.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_salary_currency(compensation: object) -> str | None:
    if not isinstance(compensation, Mapping):
        return None
    summary_components = compensation.get("summaryComponents")
    if isinstance(summary_components, list):
        for component in summary_components:
            if not isinstance(component, Mapping):
                continue
            currency = component.get("currencyCode")
            if isinstance(currency, str) and currency.strip():
                return currency.strip().upper()
    compensation_tiers = compensation.get("compensationTiers")
    if isinstance(compensation_tiers, list):
        for tier in compensation_tiers:
            if not isinstance(tier, Mapping):
                continue
            components = tier.get("components")
            if not isinstance(components, list):
                continue
            for component in components:
                if not isinstance(component, Mapping):
                    continue
                currency = component.get("currencyCode")
                if isinstance(currency, str) and currency.strip():
                    return currency.strip().upper()
    return None


def _extract_address_country(address: object) -> str:
    if not isinstance(address, Mapping):
        return ""
    postal = address.get("postalAddress")
    if not isinstance(postal, Mapping):
        return ""
    country = postal.get("addressCountry")
    if isinstance(country, str) and country.strip():
        return country.strip()
    return ""


def _extract_address_locality(address: object) -> str:
    if not isinstance(address, Mapping):
        return ""
    postal = address.get("postalAddress")
    if not isinstance(postal, Mapping):
        return ""
    city = postal.get("addressLocality")
    if isinstance(city, str) and city.strip():
        return city.strip()
    return ""


def _first_location_token(location_text: str) -> str:
    return str(location_text.split(";", 1)[0]).strip()


def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _humanize_company(board: str) -> str:
    return board.replace("-", " ").replace("_", " ").strip()


def _load_fixture_payload() -> object | None:
    fixture_dir = os.getenv("JOB_SCOUT_FIXTURE_DIR")
    if not fixture_dir:
        return None
    fixture_path = Path(fixture_dir) / "ashby_sample.json"
    if not fixture_path.exists():
        return None
    return json.loads(fixture_path.read_text(encoding="utf-8"))
