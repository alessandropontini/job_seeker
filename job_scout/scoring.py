"""Deterministic scoring for accepted job postings."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from job_scout.matcher import MatchResult


def apply_scoring(
    match: MatchResult, config: Mapping[str, object]
) -> MatchResult:
    """Return a MatchResult with score metadata applied."""

    score, score_penalties, score_bonuses = compute_score(match, config)
    return replace(
        match,
        score=score,
        score_penalties=score_penalties,
        score_bonuses=score_bonuses,
    )


def compute_score(
    match: MatchResult, config: Mapping[str, object]
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


def _as_dict(raw: object) -> dict[str, object]:
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}
