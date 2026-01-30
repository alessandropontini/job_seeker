"""Matching engine for filtering job postings against config rules."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable, Mapping

from job_scout.models import JobPosting

EU_COUNTRIES = {
    "austria",
    "belgium",
    "bulgaria",
    "croatia",
    "cyprus",
    "czech republic",
    "denmark",
    "estonia",
    "finland",
    "france",
    "germany",
    "greece",
    "hungary",
    "ireland",
    "italy",
    "latvia",
    "lithuania",
    "luxembourg",
    "malta",
    "netherlands",
    "poland",
    "portugal",
    "romania",
    "slovakia",
    "slovenia",
    "spain",
    "sweden",
}

DEFAULT_CURRENCY_RATES = {
    "EUR": 1.0,
    "USD": 0.92,
    "GBP": 1.17,
}


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


def match_posting(
    posting: JobPosting,
    config: Mapping[str, object],
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
    ) = evaluate_hard_constraints(posting, config, strict, allow_missing_salary)
    decision = "rejected" if hard_reject_reasons else "accepted"
    missing_salary_allowed = (
        missing_salary and allow_missing_salary and not strict
    )
    penalties = evaluate_soft_preferences(
        posting, config, missing_salary_allowed, remote_level
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
    strict: bool,
    allow_missing_salary: bool,
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
    include_countries = {
        country.lower()
        for country in location_rules.get("include_countries", [])
    }
    include_cities = [
        city.lower() for city in location_rules.get("include_cities", [])
    ]
    exclude_countries = {
        country.lower()
        for country in location_rules.get("exclude_countries", [])
    }
    include_titles = [
        title.lower() for title in role_rules.get("include_titles", [])
    ]
    minimum_eur = int(salary_rules.get("minimum_eur", 52000))
    currency_rates = _merge_currency_rates(
        salary_rules.get("currency_rates")
    )

    location_country = (posting.location_country or "").strip()
    location_text = posting.location_text or ""
    location_country_lower = location_country.lower()
    location_text_lower = location_text.lower()

    if not location_country_lower and not location_text_lower:
        missing_fields.append("location")
    if location_country_lower in exclude_countries:
        hard_reject_reasons.append("excluded_country")
    if "uk" in location_text_lower or "united kingdom" in location_text_lower:
        hard_reject_reasons.append("excluded_country_text")

    location_allowed = False
    if location_country_lower in include_countries:
        location_allowed = True
    if any(city in location_text_lower for city in include_cities):
        location_allowed = True
    if "eu" in include_regions and location_country_lower in EU_COUNTRIES:
        location_allowed = True

    if not location_allowed:
        if strict and not location_country_lower and not location_text_lower:
            hard_reject_reasons.append("location_missing_strict")
        else:
            hard_reject_reasons.append("location_not_allowed")

    title_lower = posting.title.lower()
    if not any(target in title_lower for target in include_titles):
        hard_reject_reasons.append("title_not_targeted")

    salary_min_eur = None
    salary_max_eur = None
    missing_salary = False

    salary_min, salary_max, currency = _parse_salary_range(
        posting.salary_text, posting.currency
    )

    if salary_min is None or salary_max is None or currency is None:
        missing_salary = True
    else:
        salary_min_eur = _convert_to_eur(salary_min, currency, currency_rates)
        salary_max_eur = _convert_to_eur(salary_max, currency, currency_rates)
        if salary_max_eur < minimum_eur:
            hard_reject_reasons.append("salary_below_minimum")

    if missing_salary:
        missing_fields.append("salary")
        if strict:
            hard_reject_reasons.append("missing_salary_strict")
        elif not allow_missing_salary:
            hard_reject_reasons.append("missing_salary_disallowed")

    remote_level = normalize_remote_level(posting.remote_type)

    return (
        hard_reject_reasons,
        missing_fields,
        salary_min_eur,
        salary_max_eur,
        missing_salary,
        remote_level,
    )


def evaluate_soft_preferences(
    posting: JobPosting,
    config: Mapping[str, object],
    missing_salary_allowed: bool,
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
    return penalties


def _merge_currency_rates(rates: object) -> dict[str, float]:
    if not isinstance(rates, Mapping):
        return dict(DEFAULT_CURRENCY_RATES)
    merged = dict(DEFAULT_CURRENCY_RATES)
    for key, value in rates.items():
        try:
            merged[str(key).upper()] = float(value)
        except (TypeError, ValueError):
            continue
    return merged


def _parse_salary_range(
    salary_text: str | None, currency: str | None
) -> tuple[int | None, int | None, str | None]:
    if not salary_text:
        return None, None, _normalize_currency(currency)

    normalized_text = salary_text.replace("–", "-")
    detected_currency = _normalize_currency(currency) or _detect_currency(
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


def _detect_currency(text: str) -> str | None:
    lowered = text.lower()
    if "€" in text or "eur" in lowered:
        return "EUR"
    if "$" in text or "usd" in lowered:
        return "USD"
    if "£" in text or "gbp" in lowered:
        return "GBP"
    return None


def _normalize_currency(currency: str | None) -> str | None:
    if not currency:
        return None
    return currency.strip().upper()


def _convert_to_eur(amount: int, currency: str, rates: Mapping[str, float]) -> int:
    rate = rates.get(currency.upper())
    if rate is None:
        return amount
    return int(round(amount * rate))
