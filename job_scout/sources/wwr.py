"""We Work Remotely RSS source connector (public, non-authenticated).

Attribution: data is sourced from We Work Remotely public RSS feeds.
"""

from __future__ import annotations

from datetime import datetime, timezone
import email.utils
import os
from pathlib import Path
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from job_scout.normalize import SourceJob

WWR_RSS_URL = "https://weworkremotely.com/remote-jobs.rss"


class WWRSourceError(RuntimeError):
    """Raised when We Work Remotely fetch or parse fails."""


def fetch_wwr(since_days: int) -> list[SourceJob]:
    """Fetch job postings from We Work Remotely RSS within the given window."""

    payload = _fetch_wwr_rss()
    return _parse_wwr_rss(payload, since_days)


def _fetch_wwr_rss() -> str:
    fixture_payload = _load_fixture_payload()
    if fixture_payload is not None:
        return fixture_payload
    if os.getenv("NO_NETWORK") == "1":
        raise WWRSourceError(
            "Network disabled (NO_NETWORK=1); use fixtures or integration tests."
        )
    request = urllib.request.Request(
        WWR_RSS_URL,
        headers={
            "User-Agent": "job_scout/1.0",
            "Accept": "application/rss+xml, application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise WWRSourceError(f"WWR HTTP error: {exc.code} for {WWR_RSS_URL}") from exc
    except urllib.error.URLError as exc:
        raise WWRSourceError(f"WWR connection error: {exc.reason}") from exc


def _parse_wwr_rss(payload: str, since_days: int) -> list[SourceJob]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise WWRSourceError("WWR returned invalid RSS/XML") from exc

    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - since_days * 86400

    postings: list[SourceJob] = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or url).strip()
        company = _extract_company_name(item.findtext("description") or "")

        posted_at = _parse_rfc2822(item.findtext("pubDate"))
        if posted_at is None or posted_at.timestamp() < cutoff:
            continue

        location_text = _extract_location(title)
        salary_text = _extract_salary(item.findtext("description") or "")

        postings.append(
            SourceJob(
                id=f"wwr-{guid}",
                source="wwr",
                company=company,
                title=_extract_title(title),
                location_text=location_text,
                location_country=_extract_country(location_text),
                location_city=_extract_city(location_text),
                remote_type="full-remote",
                url=url,
                posted_at=posted_at,
                salary_text=salary_text,
                currency=_extract_currency(salary_text),
                tags=[],
                description_snippet=(item.findtext("description") or "")[:140].strip(),
            )
        )
    return postings


def parse_wwr_rss(payload: str, since_days: int) -> list[SourceJob]:
    """Parse We Work Remotely RSS payloads for unit testing."""

    return _parse_wwr_rss(payload, since_days)


def _parse_rfc2822(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = email.utils.parsedate_to_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_title(raw_title: str) -> str:
    if "(" in raw_title and raw_title.endswith(")"):
        return raw_title[: raw_title.rfind("(")].strip(" -")
    return raw_title


def _extract_location(raw_title: str) -> str:
    if "(" not in raw_title or not raw_title.endswith(")"):
        return "Worldwide"
    return raw_title[raw_title.rfind("(") + 1 : -1].strip() or "Worldwide"


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


def _extract_salary(description: str) -> str | None:
    lowered = description.lower()
    marker = "salary:"
    if marker not in lowered:
        return None
    start = lowered.find(marker) + len(marker)
    tail = description[start:].strip()
    return tail.split("<", 1)[0].strip() or None


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


def _extract_company_name(description: str) -> str:
    if not description:
        return "Unknown"
    # WWR RSS usually starts with the company name before the first ' - '.
    cleaned = description.replace("\n", " ").strip()
    if " - " in cleaned:
        return cleaned.split(" - ", 1)[0].strip() or "Unknown"
    return cleaned[:80].strip() or "Unknown"


def _load_fixture_payload() -> str | None:
    fixture_dir = os.getenv("JOB_SCOUT_FIXTURE_DIR")
    if not fixture_dir:
        return None
    fixture_path = Path(fixture_dir) / "wwr_sample.xml"
    if not fixture_path.exists():
        return None
    return fixture_path.read_text(encoding="utf-8")
