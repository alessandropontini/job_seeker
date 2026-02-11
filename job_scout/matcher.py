"""Matching engine for filtering job postings against config rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from job_scout.models import JobPosting
from job_scout.normalize import (
    convert_to_eur,
    merge_currency_rates,
    normalize_remote_level,
    parse_salary_range,
)
from job_scout.regions import RegionData, normalize_country


@dataclass(frozen=True)
class MatchResult:
    """Outcome of applying matching rules to a posting."""

    matches_all: bool
    decision: str
    hard_reject_reasons: list[str]
    penalties: list[str]
    missing_fields: list[str]
    reject_reasons: list[str]
    missing_salary: bool
    salary_min_eur: int | None
    salary_max_eur: int | None
    remote_level: str
    score: int | None = None
    score_penalties: list[str] = field(default_factory=list)
    score_bonuses: list[str] = field(default_factory=list)


def match_posting(
    posting: JobPosting,
    config: Mapping[str, object],
    region_data: RegionData,
    strict: bool,
    allow_missing_salary: bool,
) -> tuple[JobPosting, MatchResult]:
    """Return a posting copy with match metadata based on configured rules."""

    (
        hard_reject_reasons,
        missing_fields,
        salary_min_eur,
        salary_max_eur,
        missing_salary,
        remote_level,
    ) = evaluate_hard_constraints(posting, config, region_data, strict)
    decision = "rejected" if hard_reject_reasons else "accepted"
    missing_salary_allowed = missing_salary and allow_missing_salary
    penalties = evaluate_soft_preferences(
        config, missing_salary_allowed, missing_fields, remote_level
    )
    matches_all = decision == "accepted"

    updated_posting = posting
    if missing_salary_allowed:
        updated_posting = posting.with_tags(["missing_salary"])

    return (
        updated_posting,
        MatchResult(
            matches_all=matches_all,
            decision=decision,
            hard_reject_reasons=list(hard_reject_reasons),
            penalties=penalties,
            missing_fields=missing_fields,
            reject_reasons=list(hard_reject_reasons),
            missing_salary=missing_salary,
            salary_min_eur=salary_min_eur,
            salary_max_eur=salary_max_eur,
            remote_level=remote_level,
        ),
    )


def evaluate_hard_constraints(
    posting: JobPosting,
    config: Mapping[str, object],
    region_data: RegionData,
    strict: bool,
) -> tuple[
    list[str],
    list[str],
    int | None,
    int | None,
    bool,
    str,
]:
    """Evaluate hard constraints and return reasons plus derived metadata."""

    hard_reject_reasons: list[str] = []
    missing_fields: list[str] = []
    location_rules = config.get("location_rules", {})
    role_rules = config.get("role_targeting", {})
    salary_rules = config.get("salary_rules", {})

    include_regions = {
        region.lower() for region in location_rules.get("include_regions", [])
    }
    include_countries = _normalize_country_list(
        location_rules.get("include_countries", []), region_data
    )
    include_cities = [
        city.lower() for city in location_rules.get("include_cities", [])
    ]
    exclude_countries = _normalize_country_list(
        location_rules.get("exclude_countries", []), region_data
    )
    include_titles = [
        title.lower() for title in role_rules.get("include_titles", [])
    ]
    minimum_eur = int(salary_rules.get("minimum_eur", 52000))
    currency_rates = merge_currency_rates(
        salary_rules.get("currency_rates")
    )
    allow_unknown_location = bool(
        location_rules.get("allow_unknown_location", True)
    )

    remote_level = normalize_remote_level(posting.remote_type)

    location_country = normalize_country(
        posting.location_country, region_data
    )
    location_text = posting.location_text or ""
    location_country_lower = location_country.lower()
    location_text_lower = location_text.lower()

    location_missing = (
        not location_country_lower and not location_text_lower
    )
    if location_missing:
        missing_fields.append("location")
    if location_country_lower in exclude_countries:
        hard_reject_reasons.append("excluded_country")
    if "uk" in location_text_lower or "united kingdom" in location_text_lower:
        hard_reject_reasons.append("excluded_country_text")

    location_allowed = False
    worldwide_full_remote = (
        remote_level == "full-remote"
        and _location_matches_token(
            location_country_lower, location_text_lower, "worldwide"
        )
    )
    europe_full_remote = (
        remote_level == "full-remote"
        and _location_matches_token(
            location_country_lower, location_text_lower, "europe"
        )
    )
    if worldwide_full_remote or europe_full_remote:
        location_allowed = True
    if location_country_lower in include_countries:
        location_allowed = True
    if any(city in location_text_lower for city in include_cities):
        location_allowed = True
    if (
        "eu" in include_regions
        and location_country_lower in region_data.eu_countries
    ):
        location_allowed = True

    if not location_allowed:
        if location_missing:
            if strict or not allow_unknown_location:
                hard_reject_reasons.append("location_missing_strict")
        else:
            hard_reject_reasons.append("location_not_allowed")

    title_lower = posting.title.lower()
    if not any(target in title_lower for target in include_titles):
        hard_reject_reasons.append("title_not_targeted")

    salary_min_eur = None
    salary_max_eur = None
    missing_salary = False

    salary_min, salary_max, currency = parse_salary_range(
        posting.salary_text, posting.currency
    )

    if salary_min is None or salary_max is None or currency is None:
        missing_salary = True
    else:
        salary_min_eur = convert_to_eur(
            salary_min, currency, currency_rates
        )
        salary_max_eur = convert_to_eur(
            salary_max, currency, currency_rates
        )
        if salary_max_eur < minimum_eur:
            hard_reject_reasons.append("salary_below_minimum")

    if missing_salary:
        missing_fields.append("salary")

    return (
        hard_reject_reasons,
        missing_fields,
        salary_min_eur,
        salary_max_eur,
        missing_salary,
        remote_level,
    )


def evaluate_soft_preferences(
    config: Mapping[str, object],
    missing_salary_allowed: bool,
    missing_fields: list[str],
    remote_level: str,
) -> list[str]:
    """Evaluate soft preferences, returning deterministic penalty labels."""

    penalties: list[str] = []
    location_rules = config.get("location_rules", {})
    prefer_full_remote = bool(location_rules.get("prefer_full_remote", False))
    if prefer_full_remote and remote_level != "full-remote":
        penalties.append("prefer_full_remote")
    if missing_salary_allowed:
        penalties.append("missing_salary")
    if "location" in missing_fields:
        penalties.append("unknown_location")
    return penalties


def _normalize_country_list(
    values: Iterable[str], region_data: RegionData
) -> set[str]:
    normalized: set[str] = set()
    for country in values:
        normalized.add(
            normalize_country(country, region_data).lower()
        )
    return normalized


def _location_matches_token(
    country: str,
    location_text: str,
    token: str,
) -> bool:
    """Return true when a location token appears as country or text fragment."""

    normalized_token = token.lower()
    return country == normalized_token or normalized_token in location_text
