"""Normalization helpers and source contract models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Mapping, Optional

from job_scout.models import JobPosting
from job_scout.regions import RegionData, normalize_country

DEFAULT_CURRENCY_RATES = {
    "EUR": 1.0,
    "USD": 0.92,
    "GBP": 1.17,
}


@dataclass(frozen=True)
class SourceJob:
    """Raw job data emitted by a source connector."""

    id: str
    source: str
    company: str
    title: str
    location_text: str
    location_country: Optional[str]
    location_city: Optional[str]
    remote_type: Optional[str]
    url: str
    posted_at: datetime
    salary_text: Optional[str]
    currency: Optional[str]
    tags: list[str] = field(default_factory=list)
    description_snippet: str = ""


@dataclass(frozen=True)
class NormalizedJob:
    """Normalized source contract representation."""

    id: str
    source: str
    company: str
    title: str
    location_text: str
    location_country: str
    location_city: str
    remote_type: str
    remote_level: str
    url: str
    posted_at: datetime
    salary_text: Optional[str]
    salary_min: Optional[int]
    salary_max: Optional[int]
    currency: Optional[str]
    tags: list[str]
    description_snippet: str


def normalize_source_job(
    job: SourceJob,
    region_data: RegionData,
) -> NormalizedJob:
    """Normalize a source job into the canonical contract."""

    posted_at = normalize_datetime_utc(job.posted_at)
    location_country = normalize_country(job.location_country, region_data)
    location_city = job.location_city or _extract_city(job.location_text)
    remote_type = (job.remote_type or "").strip()
    remote_level = normalize_remote_level(remote_type)
    salary_min, salary_max, currency = parse_salary_range(
        job.salary_text, job.currency
    )
    currency = normalize_currency(currency)
    return NormalizedJob(
        id=job.id,
        source=job.source,
        company=job.company,
        title=job.title,
        location_text=job.location_text,
        location_country=location_country,
        location_city=location_city,
        remote_type=remote_type,
        remote_level=remote_level,
        url=job.url,
        posted_at=posted_at,
        salary_text=job.salary_text,
        salary_min=salary_min,
        salary_max=salary_max,
        currency=currency,
        tags=list(job.tags),
        description_snippet=job.description_snippet,
    )


def job_posting_from_normalized(job: NormalizedJob) -> JobPosting:
    """Convert a normalized job into the reporting JobPosting model."""

    return JobPosting(
        id=job.id,
        source=job.source,
        company=job.company,
        title=job.title,
        location_text=job.location_text,
        location_country=job.location_country,
        remote_type=job.remote_type,
        url=job.url,
        posted_at=job.posted_at,
        salary_text=job.salary_text,
        currency=job.currency,
        tags=list(job.tags),
        description_snippet=job.description_snippet,
    )


def normalize_remote_level(remote_type: str) -> str:
    """Normalize remote type strings into canonical levels."""

    lowered = (remote_type or "").strip().lower()
    if not lowered:
        return "unknown"
    if "full" in lowered and "remote" in lowered:
        return "full-remote"
    if "hybrid" in lowered:
        return "hybrid"
    if "remote" in lowered:
        return "full-remote"
    if any(keyword in lowered for keyword in {"onsite", "on-site", "office"}):
        return "onsite"
    return "unknown"


def normalize_datetime_utc(value: datetime) -> datetime:
    """Ensure a datetime is timezone-aware and normalized to UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def merge_currency_rates(rates: object) -> dict[str, float]:
    """Merge configured currency rates with defaults."""

    if not isinstance(rates, Mapping):
        return dict(DEFAULT_CURRENCY_RATES)
    merged = dict(DEFAULT_CURRENCY_RATES)
    for key, value in rates.items():
        try:
            merged[str(key).upper()] = float(value)
        except (TypeError, ValueError):
            continue
    return merged


def parse_salary_range(
    salary_text: str | None, currency: str | None
) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """Parse salary min/max and detect currency from a string."""

    if not salary_text:
        return None, None, normalize_currency(currency)

    normalized_text = salary_text.replace("–", "-")
    detected_currency = normalize_currency(currency) or detect_currency(
        normalized_text
    )

    numbers = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)(\s*k)?", normalized_text):
        number = float(match.group(1))
        if match.group(2):
            number *= 1000
        numbers.append(int(number))

    if not numbers:
        return None, None, detected_currency
    if len(numbers) == 1:
        return numbers[0], numbers[0], detected_currency
    return min(numbers[0], numbers[1]), max(numbers[0], numbers[1]), detected_currency


def detect_currency(text: str) -> Optional[str]:
    lowered = text.lower()
    if "€" in text or "eur" in lowered:
        return "EUR"
    if "$" in text or "usd" in lowered:
        return "USD"
    if "£" in text or "gbp" in lowered:
        return "GBP"
    return None


def normalize_currency(currency: str | None) -> Optional[str]:
    if not currency:
        return None
    return currency.strip().upper()


def convert_to_eur(
    amount: int, currency: str, rates: Mapping[str, float]
) -> int:
    rate = rates.get(currency.upper())
    if rate is None:
        return amount
    return int(round(amount * rate))


def _extract_city(location_text: str) -> str:
    if not location_text:
        return ""
    parts = [part.strip() for part in location_text.split(",") if part.strip()]
    if not parts:
        return ""
    return parts[0]
