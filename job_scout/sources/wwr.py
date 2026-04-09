"""We Work Remotely RSS source connector (public, non-authenticated).

Attribution: data is sourced from We Work Remotely public RSS feeds.
"""

from __future__ import annotations

from datetime import datetime, timezone
import email.utils
import html
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from job_scout.normalize import SourceJob

WWR_RSS_URL = "https://weworkremotely.com/remote-jobs.rss"
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_HEADQUARTERS_RE = re.compile(r"Headquarters:\s*([^\n|]+)", re.IGNORECASE)
_SALARY_RE = re.compile(r"Salary:\s*([^\n]+)", re.IGNORECASE)


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
        raw_title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or url).strip()
        raw_description = item.findtext("description") or ""
        plain_description = _html_to_text(raw_description)
        company = _extract_company_name(raw_title, plain_description)

        posted_at = _parse_rfc2822(item.findtext("pubDate"))
        if posted_at is None or posted_at.timestamp() < cutoff:
            continue

        location_text = _extract_location(raw_title, plain_description)
        salary_text = _extract_salary(plain_description)

        postings.append(
            SourceJob(
                id=f"wwr-{guid}",
                source="wwr",
                company=company,
                title=_extract_title(raw_title),
                location_text=location_text,
                location_country=_extract_country(location_text),
                location_city=_extract_city(location_text),
                remote_type="full-remote",
                url=url,
                posted_at=posted_at,
                salary_text=salary_text,
                currency=_extract_currency(salary_text),
                tags=[],
                description_snippet=plain_description[:140].strip(),
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
    candidate = raw_title.strip()
    if ":" in candidate:
        candidate = candidate.split(":", 1)[1].strip()
    if "(" in candidate and candidate.endswith(")"):
        paren_value = candidate[candidate.rfind("(") + 1 : -1].strip()
        if _looks_like_location(paren_value):
            candidate = candidate[: candidate.rfind("(")].strip(" -")
    return candidate


def _extract_location(raw_title: str, plain_description: str) -> str:
    description_location = _extract_headquarters_location(plain_description)
    if description_location:
        return description_location
    if "(" in raw_title and raw_title.endswith(")"):
        paren_value = raw_title[raw_title.rfind("(") + 1 : -1].strip()
        if _looks_like_location(paren_value):
            return paren_value
    return "Worldwide"


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


def _extract_salary(plain_description: str) -> str | None:
    match = _SALARY_RE.search(plain_description)
    if not match:
        return None
    return match.group(1).strip() or None


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


def _extract_company_name(raw_title: str, plain_description: str) -> str:
    if ":" in raw_title:
        company = raw_title.split(":", 1)[0].strip()
        if company:
            return company
    if not plain_description:
        return "Unknown"
    if " - " in plain_description:
        return plain_description.split(" - ", 1)[0].strip() or "Unknown"
    return plain_description[:80].strip() or "Unknown"


def _html_to_text(value: str) -> str:
    text = html.unescape(value)
    text = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = _TAG_RE.sub(" ", text)
    lines = [
        _WHITESPACE_RE.sub(" ", line).strip()
        for line in text.splitlines()
    ]
    return "\n".join(line for line in lines if line).strip()


def _extract_headquarters_location(plain_description: str) -> str | None:
    match = _HEADQUARTERS_RE.search(plain_description)
    if not match:
        return None
    location = match.group(1).strip(" -")
    if location.lower().startswith("remote - "):
        return location[9:].strip() or "Worldwide"
    if location.lower().startswith("remote, "):
        return location[8:].strip() or "Worldwide"
    if location.lower() == "remote":
        return "Worldwide"
    return location or None


def _looks_like_location(value: str) -> bool:
    lowered = value.lower()
    location_tokens = {
        "worldwide",
        "europe",
        "remote",
        "usa",
        "us",
        "united states",
        "united kingdom",
        "uk",
        "canada",
        "germany",
        "france",
        "italy",
        "netherlands",
    }
    if lowered in location_tokens:
        return True
    return "," in value


def _load_fixture_payload() -> str | None:
    fixture_dir = os.getenv("JOB_SCOUT_FIXTURE_DIR")
    if not fixture_dir:
        return None
    fixture_path = Path(fixture_dir) / "wwr_sample.xml"
    if not fixture_path.exists():
        return None
    return fixture_path.read_text(encoding="utf-8")
