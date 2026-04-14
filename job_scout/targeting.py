"""Targeting helpers for CV-driven data governance matching."""

from __future__ import annotations

import re

from job_scout.models import JobPosting

CORE_KEYWORDS = [
    "data governance",
    "data quality",
    "metadata",
    "metadata management",
    "data management",
    "data steward",
    "data owner",
    "data catalog",
    "data platform",
    "master data",
    "mdm",
    "lineage",
    "data controls",
    "risk data",
    "bcbs 239",
    "reference data",
    "business glossary",
    "information governance",
    "data office",
    "data architecture",
    "solution architecture",
    "enterprise architecture",
    "cloud governance",
    "governance controls",
    "data standards",
    "data operating model",
    "operating model",
    "data strategy",
    "regulatory data",
    "collibra",
    "axon",
    "alation",
    "informatica",
    "purview",
    "erwin",
    "edc",
    "bigquery",
    "gcp",
    "google cloud",
]

ARCHITECTURE_DOMAIN_KEYWORDS = [
    "application architecture",
    "applications architecture",
    "solution architecture",
    "solutions architecture",
    "enterprise architecture",
    "platform architecture",
    "systems architecture",
    "integration architecture",
    "enterprise application",
    "enterprise applications",
    "enterprise systems",
    "business systems",
    "information system",
    "information systems",
    "corporate it",
    "application services",
    "application landscape",
    "it landscape",
    "technology landscape",
    "device landscape",
    "endpoint",
    "device management",
    "identity",
    "access management",
    "workday",
    "integration",
]

SUPPORTING_DOMAIN_KEYWORDS = [
    "compliance",
    "gdpr",
    "privacy",
]

PLATFORM_KEYWORDS = [
    "gcp",
    "bigquery",
    "google cloud",
    "dataflow",
    "dataproc",
    "databricks",
    "kafka",
    "etl",
    "elt",
    "data pipeline",
    "data lake",
    "data warehouse",
    "airflow",
    "dbt",
    "sql",
    "python",
    "r",
    "superset",
    "power bi",
    "tableau",
    "postgresql",
    "mysql",
]

ROLE_BONUS_KEYWORDS = [
    "data governance manager",
    "data governance lead",
    "head of data governance",
    "data manager",
    "data platform",
    "data product",
    "data owner",
    "data lead",
    "data architect",
    "solution architect",
    "solutions architect",
    "enterprise architect",
    "cloud architect",
    "platform architect",
    "data technology owner",
    "technology owner",
]

MANAGERIAL_TITLE_KEYWORDS = [
    "manager",
    "lead",
    "head",
    "director",
    "architect",
    "solution architect",
    "solutions architect",
    "enterprise architect",
    "data architect",
    "cloud architect",
    "platform architect",
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
    "junior",
    "graduate",
    "intern",
    "trainee",
]

CLIENT_FACING_ARCHITECT_KEYWORDS = [
    "pre-sales",
    "presales",
    "post-sales",
    "customer-facing",
    "implementation services",
    "services architect",
    "product solutions architect",
    "technical solutions team",
    "technical solutions",
    "partner with field teams",
    "field teams",
    "customer use cases",
    "potential clients",
    "existing customers",
    "sales engineer",
    "sales engineering",
    "solutions consultant",
    "professional services",
    "partner solutions architect",
    "field cto",
    "client-facing",
]

PROFESSION_QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "the",
    "to",
}

GENERIC_PROFESSION_TOKENS = {
    "architect",
    "consultant",
    "director",
    "engineer",
    "head",
    "lead",
    "manager",
    "officer",
    "owner",
    "principal",
    "senior",
    "specialist",
    "staff",
}


def build_search_text(posting: JobPosting) -> str:
    """Return lowercased title+description text for keyword matching."""

    tags = " ".join(posting.tags or [])
    return f"{posting.title}\n{posting.description_snippet}\n{tags}".lower()


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
    core_matches = find_matches(text, CORE_KEYWORDS)
    if core_matches:
        return core_matches
    if is_architecture_role_title(posting.title) and not has_client_facing_architect_penalty(posting):
        return find_matches(text, ARCHITECTURE_DOMAIN_KEYWORDS)
    return []


def find_supporting_domain_keyword_matches(posting: JobPosting) -> list[str]:
    """Return secondary domain matches that help ranking but do not open the gate."""

    text = build_search_text(posting)
    return find_matches(text, SUPPORTING_DOMAIN_KEYWORDS)


def find_managerial_keyword_matches(title: str) -> list[str]:
    """Return management-seniority keyword matches for a title."""

    return find_matches(title.lower(), MANAGERIAL_TITLE_KEYWORDS)


def has_negative_domain_penalty(posting: JobPosting) -> bool:
    """Return True when title matches marketing/sales role families."""

    return has_any(posting.title.lower(), NEGATIVE_DOMAIN_KEYWORDS)


def is_architecture_role_title(title: str) -> bool:
    """Return True when the title clearly targets architecture-oriented roles."""

    lowered = title.lower()
    return has_any(
        lowered,
        [
            "architect",
            "architecture",
            "application services",
            "technology owner",
            "data technology owner",
        ],
    )


def has_client_facing_architect_penalty(posting: JobPosting) -> bool:
    """Return True for customer-facing / pre-sales architecture roles."""

    text = build_search_text(posting)
    return has_any(text, CLIENT_FACING_ARCHITECT_KEYWORDS)


def normalize_profession_query(query: str | None) -> str:
    """Return a normalized runtime profession query string."""

    return re.sub(r"\s+", " ", str(query or "").strip().lower())


def split_profession_queries(query: str | None) -> list[str]:
    """Return normalized profession-focus entries split by comma/semicolon/pipe."""

    normalized = normalize_profession_query(query)
    if not normalized:
        return []
    parts = [
        re.sub(r"\s+", " ", part).strip()
        for part in re.split(r"[,;|\n]+", normalized)
    ]
    ordered: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part or part in seen:
            continue
        ordered.append(part)
        seen.add(part)
    return ordered


def extract_profession_query_tokens(query: str | None) -> list[str]:
    """Return profession query tokens without trivial stopwords."""

    phrases = split_profession_queries(query)
    if not phrases:
        normalized = normalize_profession_query(query)
        phrases = [normalized] if normalized else []
    tokens = [
        token
        for phrase in phrases
        for token in re.split(r"[^a-z0-9+#]+", phrase)
        if len(token) >= 3 and token not in PROFESSION_QUERY_STOPWORDS
    ]
    ordered: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token not in seen:
            ordered.append(token)
            seen.add(token)
    return ordered


def find_profession_query_matches(
    posting: JobPosting, query: str | None
) -> list[str]:
    """Return exact phrase or token matches for a runtime profession query."""

    phrases = split_profession_queries(query)
    if not phrases:
        return []

    title_text = posting.title.lower()
    search_text = build_search_text(posting)
    matches: list[str] = []
    for phrase in phrases:
        if contains_phrase(title_text, phrase):
            matches.append(f"title:{phrase}")
        elif contains_phrase(search_text, phrase):
            matches.append(phrase)

        for token in extract_profession_query_tokens(phrase):
            if contains_phrase(title_text, token):
                matches.append(f"title:{token}")
            elif contains_phrase(search_text, token):
                matches.append(token)

    ordered: list[str] = []
    seen: set[str] = set()
    for match in matches:
        if match not in seen:
            ordered.append(match)
            seen.add(match)
    return ordered


def matches_profession_query(posting: JobPosting, query: str | None) -> bool:
    """Return True when a posting aligns with the runtime profession focus."""

    phrases = split_profession_queries(query)
    if not phrases:
        return True

    return any(_matches_single_profession_query(posting, phrase) for phrase in phrases)


def _matches_single_profession_query(posting: JobPosting, query: str) -> bool:
    """Return True when a posting aligns with one normalized profession phrase."""

    normalized = normalize_profession_query(query)
    if not normalized:
        return True

    title_text = posting.title.lower()
    search_text = build_search_text(posting)
    if contains_phrase(title_text, normalized) or contains_phrase(search_text, normalized):
        return True

    tokens = extract_profession_query_tokens(normalized)
    if not tokens:
        return True

    matched_tokens = [
        token for token in tokens if contains_phrase(search_text, token)
    ]
    core_tokens = [
        token for token in tokens if token not in GENERIC_PROFESSION_TOKENS
    ]
    matched_core_tokens = [
        token for token in core_tokens if contains_phrase(search_text, token)
    ]

    if len(matched_core_tokens) >= 2:
        return True
    if len(matched_core_tokens) >= 1 and len(matched_tokens) >= max(2, min(len(tokens), 3)):
        return True
    if not core_tokens and len(matched_tokens) >= 2:
        return True
    return False


def has_negative_soft_penalty(posting: JobPosting) -> bool:
    """Return True when title matches quant/trading role families."""

    return has_any(posting.title.lower(), NEGATIVE_SOFT_PENALTY_TITLES)
