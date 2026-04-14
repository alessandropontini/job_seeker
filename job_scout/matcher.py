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
from job_scout.targeting import (
    contains_phrase,
    has_client_facing_architect_penalty,
    find_domain_keyword_matches,
    matches_profession_query,
    find_role_keyword_matches,
    has_negative_domain_penalty,
)

ALLOWED_FULL_REMOTE_REGION_TOKENS = (
    "worldwide",
    "europe",
    "eu",
    "european union",
)
EXCLUDED_UK_TEXT_TOKENS = (
    "uk",
    "united kingdom",
    "england",
    "scotland",
    "wales",
    "northern ireland",
    "great britain",
)
NON_TARGET_REGION_TEXT_TOKENS = (
    "usa only",
    "us only",
    "united states only",
    "north america",
    "canada only",
    "latin america",
    "latam",
    "apac",
    "asia pacific",
    "asia only",
    "india only",
    "middle east",
    "africa",
    "emea",
)


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
    why: list[str] = field(default_factory=list)
    role_fit: str = "unknown"
    domain_fit: str = "unknown"
    location_fit: str = "unknown"
    role_matches: list[str] = field(default_factory=list)
    domain_matches: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LocationMatchResult:
    """Outcome of evaluating location rules for a posting."""

    allowed: bool
    missing: bool
    fit: str
    matched_signals: list[str]
    hard_reject_reasons: list[str]


def match_posting(
    posting: JobPosting,
    config: Mapping[str, object],
    region_data: RegionData,
    strict: bool,
    allow_missing_salary: bool,
) -> tuple[JobPosting, MatchResult]:
    """Return a posting copy with match metadata based on configured rules."""

    run_mode = _resolve_run_mode(config)
    (
        hard_reject_reasons,
        soft_penalties,
        missing_fields,
        salary_min_eur,
        salary_max_eur,
        missing_salary,
        remote_level,
    ) = evaluate_hard_constraints(
        posting,
        config,
        region_data,
        strict,
        run_mode=run_mode,
    )
    decision = "rejected" if hard_reject_reasons else "accepted"
    missing_salary_allowed = missing_salary and allow_missing_salary
    penalties = list(soft_penalties)
    penalties.extend(
        evaluate_soft_preferences(
            config, missing_salary_allowed, missing_fields, remote_level
        )
    )
    matches_all = decision == "accepted"
    role_matches = find_role_keyword_matches(
        posting.title,
        [
            title.lower()
            for title in config.get("role_targeting", {}).get(
                "include_titles", []
            )
        ],
    )
    domain_matches = find_domain_keyword_matches(posting)
    location_fit = _evaluate_location_fit(
        location_country=normalize_country(
            posting.location_country, region_data
        ).lower(),
        location_text=(posting.location_text or "").lower(),
        remote_level=remote_level,
        include_regions={
            region.lower()
            for region in config.get("location_rules", {}).get(
                "include_regions", []
            )
        },
        include_countries=_normalize_country_list(
            config.get("location_rules", {}).get("include_countries", []),
            region_data,
        ),
        include_cities=[
            city.lower()
            for city in config.get("location_rules", {}).get(
                "include_cities", []
            )
        ],
        exclude_countries=_normalize_country_list(
            config.get("location_rules", {}).get("exclude_countries", []),
            region_data,
        ),
        allow_unknown_location=bool(
            config.get("location_rules", {}).get(
                "allow_unknown_location", True
            )
        ),
        region_data=region_data,
        strict=strict,
        run_mode=run_mode,
    )

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
            role_fit="targeted" if role_matches else "not_targeted",
            domain_fit="targeted" if domain_matches else "not_targeted",
            location_fit=location_fit.fit,
            role_matches=role_matches,
            domain_matches=domain_matches,
        ),
    )


def evaluate_hard_constraints(
    posting: JobPosting,
    config: Mapping[str, object],
    region_data: RegionData,
    strict: bool,
    run_mode: str,
) -> tuple[
    list[str],
    list[str],
    list[str],
    int | None,
    int | None,
    bool,
    str,
]:
    """Evaluate hard constraints and return reasons plus derived metadata."""

    hard_reject_reasons: list[str] = []
    soft_penalties: list[str] = []
    missing_fields: list[str] = []
    location_rules = config.get("location_rules", {})
    role_rules = config.get("role_targeting", {})
    salary_rules = config.get("salary_rules", {})
    runtime = config.get("runtime", {})

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
    profession_query = None
    if isinstance(runtime, Mapping):
        raw_profession_query = runtime.get("profession_query")
        if isinstance(raw_profession_query, str):
            profession_query = raw_profession_query.strip()
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

    if not posting.url or not posting.url.strip():
        hard_reject_reasons.append("missing_url")

    location_result = _evaluate_location_fit(
        location_country=location_country_lower,
        location_text=location_text_lower,
        remote_level=remote_level,
        include_regions=include_regions,
        include_countries=include_countries,
        include_cities=include_cities,
        exclude_countries=exclude_countries,
        allow_unknown_location=allow_unknown_location,
        region_data=region_data,
        strict=strict,
        run_mode=run_mode,
    )
    location_missing = location_result.missing
    if location_missing:
        missing_fields.append("location")
    hard_reject_reasons.extend(location_result.hard_reject_reasons)
    if not location_result.allowed and not location_result.hard_reject_reasons:
        if run_mode == "manual":
            soft_penalties.append("location_not_allowed")
        else:
            hard_reject_reasons.append("location_not_allowed")

    if has_negative_domain_penalty(posting):
        hard_reject_reasons.append("negative_domain")
    if has_client_facing_architect_penalty(posting):
        hard_reject_reasons.append("client_facing_architect")
    if profession_query and not matches_profession_query(posting, profession_query):
        hard_reject_reasons.append("profession_not_targeted")

    role_matches = find_role_keyword_matches(posting.title, include_titles)
    if not role_matches:
        if run_mode == "manual":
            soft_penalties.append("title_not_targeted")
        else:
            hard_reject_reasons.append("title_not_targeted")

    domain_matches = find_domain_keyword_matches(posting)
    if not domain_matches:
        if run_mode == "manual":
            soft_penalties.append("cv_domain_not_targeted")
        else:
            hard_reject_reasons.append("cv_domain_not_targeted")

    if run_mode == "manual" and not role_matches and not domain_matches:
        hard_reject_reasons.append("cv_alignment_missing")

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
            if run_mode == "manual":
                soft_penalties.append("salary_below_minimum")
            else:
                hard_reject_reasons.append("salary_below_minimum")

    if missing_salary:
        missing_fields.append("salary")

    return (
        hard_reject_reasons,
        soft_penalties,
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


def _evaluate_location_fit(
    *,
    location_country: str,
    location_text: str,
    remote_level: str,
    include_regions: set[str],
    include_countries: set[str],
    include_cities: list[str],
    exclude_countries: set[str],
    allow_unknown_location: bool,
    region_data: RegionData,
    strict: bool,
    run_mode: str,
) -> LocationMatchResult:
    """Return the location decision using explicit allow/deny signals."""

    missing = not location_country and not location_text
    reject_reasons: list[str] = []

    if location_country in exclude_countries:
        reject_reasons.append("excluded_country")
    if _location_has_any_token(location_text, EXCLUDED_UK_TEXT_TOKENS):
        reject_reasons.append("excluded_country_text")
    if reject_reasons:
        return LocationMatchResult(
            allowed=False,
            missing=missing,
            fit="excluded",
            matched_signals=[],
            hard_reject_reasons=reject_reasons,
        )

    if missing:
        if strict or not allow_unknown_location:
            return LocationMatchResult(
                allowed=False,
                missing=True,
                fit="missing_strict",
                matched_signals=[],
                hard_reject_reasons=["location_missing_strict"],
            )
        return LocationMatchResult(
            allowed=True,
            missing=True,
            fit="missing_allowed",
            matched_signals=[],
            hard_reject_reasons=[],
        )

    if location_country in include_countries:
        return LocationMatchResult(
            True, False, "allowed_country", [location_country], []
        )
    if _location_text_has_city_match(location_text, include_cities):
        return LocationMatchResult(
            True,
            False,
            "allowed_city",
            _location_text_match_tokens(location_text, include_cities),
            [],
        )
    if (
        "eu" in include_regions
        and location_country in region_data.eu_countries
    ):
        return LocationMatchResult(
            True, False, "allowed_eu_country", [location_country], []
        )

    if remote_level == "full-remote":
        blocked_regions = _location_text_match_tokens(
            location_text, NON_TARGET_REGION_TEXT_TOKENS
        )
        if blocked_regions:
            return LocationMatchResult(
                False, False, "non_target_region", blocked_regions, []
            )
        allowed_regions = _location_text_match_tokens(
            f"{location_country}\n{location_text}",
            ALLOWED_FULL_REMOTE_REGION_TOKENS,
        )
        if allowed_regions:
            return LocationMatchResult(
                True, False, "allowed_remote_region", allowed_regions, []
            )

    if run_mode == "manual" and location_country in {"us", "usa", "united states"}:
        if _location_text_has_city_match(location_text, include_cities):
            return LocationMatchResult(
                True,
                False,
                "allowed_city",
                _location_text_match_tokens(location_text, include_cities),
                [],
            )

    return LocationMatchResult(False, False, "not_targeted", [], [])


def _location_text_has_city_match(
    location_text: str, include_cities: list[str]
) -> bool:
    """Return True when location text contains one of the configured cities."""

    return any(
        contains_phrase(location_text, city.lower()) for city in include_cities
    )


def _location_has_any_token(text: str, tokens: Iterable[str]) -> bool:
    """Return True when any token appears in location text."""

    return any(contains_phrase(text, token) for token in tokens)


def _location_text_match_tokens(
    text: str, tokens: Iterable[str]
) -> list[str]:
    """Return matched location tokens in deterministic order."""

    return [token for token in tokens if contains_phrase(text, token)]


def _resolve_run_mode(config: Mapping[str, object]) -> str:
    runtime = config.get("runtime", {})
    if isinstance(runtime, Mapping):
        value = str(runtime.get("run_mode", "scheduled")).strip().lower()
        if value in {"manual", "scheduled"}:
            return value
    return "scheduled"
