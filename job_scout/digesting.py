"""Shared helpers for digest candidate selection and score diagnostics."""

from __future__ import annotations

from collections.abc import Iterable

from job_scout.writers import ReportRow

_CANDIDATE_SOFT_REJECT_REASONS = frozenset({"title_not_targeted"})


def is_candidate_after_hard_filters(row: ReportRow) -> bool:
    """Return True when a row survives hard filters for digest candidate pools."""

    reasons = set(row.match.reject_reasons or [])
    reasons.difference_update(_CANDIDATE_SOFT_REJECT_REASONS)
    return not reasons


def score_bounds(rows: Iterable[ReportRow]) -> tuple[int, int]:
    """Return min/max score for rows with a score, or `(0, 0)` when empty."""

    scores = [row.match.score or 0 for row in rows if row.match.score is not None]
    if not scores:
        return 0, 0
    return min(scores), max(scores)
