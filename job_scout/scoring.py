"""Deterministic scoring for accepted job postings."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from job_scout.matcher import MatchResult
from job_scout.models import JobPosting
from job_scout.targeting import (
    CORE_KEYWORDS,
    SUPPORTING_DOMAIN_KEYWORDS,
    ARCHITECTURE_DOMAIN_KEYWORDS,
    MANAGERIAL_TITLE_KEYWORDS,
    PLATFORM_KEYWORDS,
    ROLE_BONUS_KEYWORDS,
    contains_phrase,
    find_profession_query_matches,
    find_managerial_keyword_matches,
    has_client_facing_architect_penalty,
    has_negative_domain_penalty,
    has_negative_soft_penalty,
)


def apply_scoring(
    posting: JobPosting,
    match: MatchResult,
    config: dict[str, object] | object,
) -> MatchResult:
    """Return a MatchResult with score metadata applied."""

    score, score_penalties, score_bonuses, why, cv_coverage_pct = compute_score(
        posting, match, config
    )
    return replace(
        match,
        score=score,
        score_penalties=score_penalties,
        score_bonuses=score_bonuses,
        why=why,
        cv_coverage_pct=cv_coverage_pct,
    )


def compute_score(
    posting: JobPosting,
    match: MatchResult,
    config: dict[str, object] | object = None,
) -> tuple[int | None, list[str], list[str], list[str], int]:
    """Compute deterministic score with wide recall and explainable penalties."""

    if match.decision != "accepted":
        return None, [], [], [], 0

    title_text = posting.title.lower()
    description_text = posting.description_snippet.lower()
    search_text = _build_search_text(posting)

    score = 0
    applied_penalties: list[str] = []
    applied_bonuses: list[str] = []

    title_core_matches = _find_keywords(title_text, CORE_KEYWORDS)
    description_core_matches = _find_keywords(description_text, CORE_KEYWORDS)
    supporting_matches = _find_keywords(search_text, SUPPORTING_DOMAIN_KEYWORDS)
    architecture_matches = _find_keywords(search_text, ARCHITECTURE_DOMAIN_KEYWORDS)
    platform_matches = _find_keywords(search_text, PLATFORM_KEYWORDS)
    role_matches = _find_keywords(title_text, ROLE_BONUS_KEYWORDS)
    managerial_matches = find_managerial_keyword_matches(posting.title)
    profession_matches = find_profession_query_matches(
        posting, _resolve_profession_query(config)
    )

    score += min(40, len(title_core_matches) * 12)
    if title_core_matches:
        applied_bonuses.append(
            _format_keyword_bonus("core_title", title_core_matches)
        )

    score += min(28, len(description_core_matches) * 7)
    if description_core_matches:
        applied_bonuses.append(
            _format_keyword_bonus("core_description", description_core_matches)
        )

    score += min(10, len(supporting_matches) * 3)
    if supporting_matches:
        applied_bonuses.append(
            _format_keyword_bonus("supporting_domain", supporting_matches)
        )

    score += min(16, len(architecture_matches) * 4)
    if architecture_matches:
        applied_bonuses.append(
            _format_keyword_bonus("architecture_domain", architecture_matches)
        )

    score += min(20, len(platform_matches) * 5)
    if platform_matches:
        applied_bonuses.append(
            _format_keyword_bonus("platform", platform_matches)
        )

    if role_matches:
        score += 10
        applied_bonuses.append(
            _format_keyword_bonus("target_role", role_matches)
        )
    if profession_matches:
        score += min(18, len(profession_matches) * 6)
        applied_bonuses.append(
            _format_keyword_bonus("profession_query", profession_matches)
        )

    if managerial_matches:
        score += 15
        applied_bonuses.append(
            _format_keyword_bonus("seniority_title", managerial_matches)
        )
    else:
        score -= 25
        applied_penalties.append("non_managerial_title")

    if managerial_matches and title_core_matches:
        score += 15
        applied_bonuses.append("seniority_data_title")

    if match.remote_level == "full-remote":
        score += 8
        applied_bonuses.append("remote_full")

    for penalty in match.penalties:
        if penalty == "location_not_allowed":
            score -= 12
            applied_penalties.append(penalty)
        elif penalty == "title_not_targeted":
            score -= 20
            applied_penalties.append(penalty)
        elif penalty == "salary_below_minimum":
            score -= 15
            applied_penalties.append(penalty)
        elif penalty == "prefer_full_remote":
            score -= 6
            applied_penalties.append(penalty)
        elif penalty == "negative_domain":
            score -= 40
            applied_penalties.append(penalty)
        elif penalty == "cv_domain_not_targeted":
            score -= 25
            applied_penalties.append(penalty)

    if has_negative_domain_penalty(posting):
        if "negative_domain" not in applied_penalties:
            applied_penalties.append("negative_domain")
        score -= 40
    if has_client_facing_architect_penalty(posting):
        score -= 45
        applied_penalties.append("client_facing_architect")
    if has_negative_soft_penalty(posting):
        score -= 30
        applied_penalties.append("negative_soft_penalty")

    final_score = min(max(score, 0), 100)
    why = _build_why(match, applied_bonuses, applied_penalties)
    cv_coverage_pct = _compute_cv_coverage_pct(
        title_core_matches=title_core_matches,
        description_core_matches=description_core_matches,
        supporting_matches=supporting_matches,
        architecture_matches=architecture_matches,
        platform_matches=platform_matches,
    )
    return (
        final_score,
        applied_penalties,
        applied_bonuses,
        why,
        cv_coverage_pct,
    )


def _build_search_text(posting: JobPosting) -> str:
    tags = " ".join(posting.tags or [])
    return f"{posting.title}\n{posting.description_snippet}\n{tags}".lower()


def _find_keywords(text: str, keywords: object) -> list[str]:
    if not isinstance(keywords, Iterable) or isinstance(keywords, str):
        return []
    matches: list[str] = []
    for entry in keywords:
        if not isinstance(entry, str):
            continue
        lowered = entry.lower()
        if lowered and contains_phrase(text, lowered):
            matches.append(entry)
    return sorted(set(matches), key=str.lower)


def _format_keyword_bonus(prefix: str, keywords: list[str]) -> str:
    return f"{prefix}: {', '.join(keywords)}"


def _build_why(
    match: MatchResult, bonuses: list[str], penalties: list[str]
) -> list[str]:
    reasons: list[str] = []
    if match.role_fit == "targeted":
        reasons.append("fit role_targeted")
    if match.domain_fit == "targeted":
        reasons.append("fit domain_targeted")
    if match.location_fit.startswith("allowed") or match.location_fit == "missing_allowed":
        reasons.append(f"fit location_{match.location_fit}")
    for bonus in bonuses[:2]:
        reasons.append(f"match {bonus}")
    if penalties:
        reasons.append(f"penalty {penalties[0]}")
    return reasons[:3]


def _compute_cv_coverage_pct(
    *,
    title_core_matches: list[str],
    description_core_matches: list[str],
    supporting_matches: list[str],
    architecture_matches: list[str],
    platform_matches: list[str],
) -> int:
    """Estimate overlap between a job and the user's CV domain/stack."""

    coverage = 0
    coverage += min(40, len(title_core_matches) * 20)
    coverage += min(25, len(description_core_matches) * 8)
    coverage += min(15, len(architecture_matches) * 6)
    coverage += min(15, len(platform_matches) * 5)
    coverage += min(5, len(supporting_matches) * 2)
    return min(max(coverage, 0), 100)


def _resolve_profession_query(config: dict[str, object] | object) -> str | None:
    if not isinstance(config, dict):
        return None
    runtime = config.get("runtime")
    if not isinstance(runtime, dict):
        return None
    value = runtime.get("profession_query")
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
