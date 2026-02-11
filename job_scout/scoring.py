"""Deterministic scoring for accepted job postings."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Mapping

from job_scout.matcher import MatchResult
from job_scout.models import JobPosting
from job_scout.targeting import (
    CORE_KEYWORDS,
    has_negative_soft_penalty,
)


def apply_scoring(
    posting: JobPosting,
    match: MatchResult,
    config: Mapping[str, object],
) -> MatchResult:
    """Return a MatchResult with score metadata applied."""

    score, score_penalties, score_bonuses = compute_score(
        posting, match, config
    )
    return replace(
        match,
        score=score,
        score_penalties=score_penalties,
        score_bonuses=score_bonuses,
    )


def compute_score(
    posting: JobPosting,
    match: MatchResult,
    config: Mapping[str, object],
) -> tuple[int | None, list[str], list[str]]:
    """Compute deterministic score and applied preference labels."""

    if match.decision != "accepted":
        return None, [], []

    search_text = _build_search_text(posting)
    title_text = posting.title.lower()
    description_text = posting.description_snippet.lower()

    title_matches = _find_keywords(title_text, CORE_KEYWORDS)
    description_matches = _find_keywords(description_text, CORE_KEYWORDS)

    score = 0
    applied_penalties: list[str] = []
    applied_bonuses: list[str] = []

    if title_matches:
        score += 60
        applied_bonuses.append(
            _format_keyword_bonus("title_keywords", title_matches)
        )
    if description_matches:
        score += 30
        applied_bonuses.append(
            _format_keyword_bonus(
                "description_keywords", description_matches
            )
        )

    if match.remote_level == "full-remote":
        score += 5
        applied_bonuses.append("remote_bonus")
    if not match.missing_salary:
        score += 5
        applied_bonuses.append("salary_bonus")

    gcp_matches = _find_keywords(search_text, ["gcp", "google cloud", "bigquery"])
    governance_matches = _find_keywords(
        search_text,
        ["governance", "quality", "metadata", "lineage", "catalog"],
    )
    compliance_matches = _find_keywords(
        search_text,
        ["compliance", "controls", "policy", "standards"],
    )
    if gcp_matches:
        score += 10
        applied_bonuses.append(_format_keyword_bonus("gcp_stack", gcp_matches))
    if governance_matches:
        score += 15
        applied_bonuses.append(
            _format_keyword_bonus("governance_focus", governance_matches)
        )
    if compliance_matches:
        score += 10
        applied_bonuses.append(
            _format_keyword_bonus("compliance_focus", compliance_matches)
        )

    if has_negative_soft_penalty(posting):
        score -= 50
        applied_penalties.append("negative_soft_penalty")

    return max(score, 0), applied_penalties, applied_bonuses


def _parse_weights(raw: object) -> dict[str, int]:
    if not isinstance(raw, Mapping):
        return {}
    parsed: dict[str, int] = {}
    for key, value in raw.items():
        try:
            parsed[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return parsed


def _parse_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_search_text(posting: JobPosting) -> str:
    return f"{posting.title}\n{posting.description_snippet}".lower()


def _find_keywords(text: str, keywords: object) -> list[str]:
    if not isinstance(keywords, Iterable) or isinstance(keywords, str):
        return []
    matches: list[str] = []
    for entry in keywords:
        if not isinstance(entry, str):
            continue
        lowered = entry.lower()
        if lowered and lowered in text:
            matches.append(entry)
    return sorted(set(matches), key=str.lower)


def _format_keyword_bonus(prefix: str, keywords: list[str]) -> str:
    return f"{prefix}: {', '.join(keywords)}"


def _as_dict(raw: object) -> dict[str, object]:
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}
