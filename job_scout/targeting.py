"""Targeting helpers for CV-driven data governance matching."""

from __future__ import annotations

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

NEGATIVE_HARD_BLOCK_TITLES = [
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


def find_matches(text: str, keywords: list[str]) -> list[str]:
    """Return sorted keyword matches found in the provided text."""

    return sorted({kw for kw in keywords if kw and kw in text}, key=str.lower)


def has_any(text: str, keywords: list[str]) -> bool:
    """Return True when at least one keyword appears in the text."""

    return any(keyword in text for keyword in keywords)


def passes_core_gate(posting: JobPosting) -> bool:
    """Gate acceptance for targeted channels using title/description core terms."""

    return bool(find_core_keyword_matches(posting))


def find_core_keyword_matches(posting: JobPosting) -> list[str]:
    """Return unique core keyword matches from title or description."""

    text = build_search_text(posting)
    return find_matches(text, CORE_KEYWORDS)


def has_negative_hard_block(posting: JobPosting) -> bool:
    """Return True when title matches hard-blocked role families."""

    return has_any(posting.title.lower(), NEGATIVE_HARD_BLOCK_TITLES)


def has_negative_soft_penalty(posting: JobPosting) -> bool:
    """Return True when title matches quant/trading role families."""

    return has_any(posting.title.lower(), NEGATIVE_SOFT_PENALTY_TITLES)

