"""Deterministic scoring for accepted job postings."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Mapping

from job_scout.matcher import MatchResult
from job_scout.models import JobPosting


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

    scoring_rules = _as_dict(config.get("scoring"))
    base_score = int(scoring_rules.get("base_score", 100))
    penalty_weights = _parse_weights(scoring_rules.get("penalty_weights"))
    bonus_weights = _parse_weights(scoring_rules.get("bonus_weights"))

    applied_penalties = [
        penalty
        for penalty in match.penalties
        if penalty in penalty_weights
    ]

    applied_bonuses: list[str] = []
    location_rules = _as_dict(config.get("location_rules"))
    prefer_full_remote = bool(location_rules.get("prefer_full_remote", False))
    if (
        prefer_full_remote
        and match.remote_level == "full-remote"
        and "full_remote" in bonus_weights
    ):
        applied_bonuses.append("full_remote")

    score = base_score
    for penalty in applied_penalties:
        score -= penalty_weights[penalty]
    for bonus in applied_bonuses:
        score += bonus_weights[bonus]

    data_governance_boost = _parse_int(
        scoring_rules.get("data_governance_boost")
    )
    data_governance_secondary_boost = _parse_int(
        scoring_rules.get("data_governance_secondary_boost")
    )
    search_text = _build_search_text(posting)
    primary_matches = _find_keywords(
        search_text, scoring_rules.get("data_governance_keywords", [])
    )
    secondary_matches = _find_keywords(
        search_text,
        scoring_rules.get("data_governance_secondary_keywords", []),
    )
    if primary_matches and data_governance_boost:
        score += data_governance_boost
        applied_bonuses.append(
            _format_keyword_bonus("data_governance", primary_matches)
        )
    if secondary_matches and data_governance_secondary_boost:
        score += data_governance_secondary_boost
        applied_bonuses.append(
            _format_keyword_bonus(
                "data_governance_secondary", secondary_matches
            )
        )

    return score, applied_penalties, applied_bonuses


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
