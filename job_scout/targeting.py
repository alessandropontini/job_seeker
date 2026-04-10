"""Targeting helpers for CV-driven data governance matching."""

from __future__ import annotations

import re

from job_scout.models import JobPosting

CORE_KEYWORDS = [
    "data governance",
    "data quality",
    "metadata",
    "data management",
    "data steward",
    "data owner",
    "data catalog",
    "data platform",
    "master data",
    "mdm",
    "lineage",
    "data controls",
    "compliance",
    "gdpr",
    "privacy",
    "risk data",
    "bcbs 239",
    "bigquery",
    "gcp",
    "google cloud",
]

PLATFORM_KEYWORDS = [
    "gcp",
    "bigquery",
    "google cloud",
    "kafka",
    "etl",
    "elt",
    "data pipeline",
    "data lake",
    "data warehouse",
    "airflow",
    "dbt",
    "sql",
]

ROLE_BONUS_KEYWORDS = [
    "data governance manager",
    "data governance specialist",
    "data manager",
    "data platform",
    "data product",
    "data owner",
    "data lead",
]

NEGATIVE_DOMAIN_KEYWORDS = [
    "brand manager",
    "marketing",
    "growth",
    "sales",
    "affiliate",
    "seo",
    "paid media",
]

NEGATIVE_SOFT_PENALTY_TITLES = [
    "quantitative",
    "trading",
    "hedge fund",
    "portfolio",
]


def build_search_text(posting: JobPosting) -> str:
    """Return lowercased title+description text for keyword matching."""

    return f"{posting.title}\n{posting.description_snippet}".lower()


def contains_phrase(text: str, keyword: str) -> bool:
    """Return True when a keyword appears as a phrase with token boundaries."""

    normalized = keyword.strip().lower()
    if not normalized:
        return False
    raw_parts = [part for part in normalized.split() if part]
    parts: list[str] = []
    for index, part in enumerate(raw_parts):
        escaped = re.escape(part)
        if (
            index == len(raw_parts) - 1
            and part.isalpha()
            and len(part) >= 4
            and not part.endswith("s")
        ):
            escaped = f"{escaped}s?"
        parts.append(escaped)
    if not parts:
        return False
    pattern = r"(?<!\w)" + r"[\W_]+".join(parts) + r"(?!\w)"
    return re.search(pattern, text.lower()) is not None


def find_matches(text: str, keywords: list[str]) -> list[str]:
    """Return sorted keyword matches found in the provided text."""

    return sorted(
        {kw for kw in keywords if kw and contains_phrase(text, kw)},
        key=str.lower,
    )


def has_any(text: str, keywords: list[str]) -> bool:
    """Return True when at least one keyword appears in the text."""

    return any(contains_phrase(text, keyword) for keyword in keywords)


def title_matches_target_titles(title: str, include_titles: list[str]) -> bool:
    """Return True when the title contains at least one targeted role term."""

    return bool(find_role_keyword_matches(title, include_titles))


def find_role_keyword_matches(title: str, include_titles: list[str]) -> list[str]:
    """Return targeted role/title keyword matches for a posting title."""

    lowered = title.lower()
    return find_matches(lowered, include_titles)


def passes_core_gate(posting: JobPosting) -> bool:
    """Gate acceptance for targeted channels using title/description core terms."""

    return bool(find_domain_keyword_matches(posting))


def find_core_keyword_matches(posting: JobPosting) -> list[str]:
    """Return unique core keyword matches from title or description."""

    return find_domain_keyword_matches(posting)


def find_domain_keyword_matches(posting: JobPosting) -> list[str]:
    """Return unique domain keyword matches from title or description."""

    text = build_search_text(posting)
    return find_matches(text, CORE_KEYWORDS)


def has_negative_domain_penalty(posting: JobPosting) -> bool:
    """Return True when title matches marketing/sales role families."""

    return has_any(posting.title.lower(), NEGATIVE_DOMAIN_KEYWORDS)


def has_negative_soft_penalty(posting: JobPosting) -> bool:
    """Return True when title matches quant/trading role families."""

    return has_any(posting.title.lower(), NEGATIVE_SOFT_PENALTY_TITLES)
