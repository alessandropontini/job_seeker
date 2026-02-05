"""Channel selection helpers for Job Scout outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from job_scout.writers import ReportRow


@dataclass(frozen=True)
class ChannelSelection:
    """Selections for the dual-channel output."""

    top_matches: list[ReportRow]
    data_only_best_picks: list[ReportRow]
    data_only_reasons: dict[str, list[str]]


def select_channels(
    rows: Iterable[ReportRow],
    config: Mapping[str, object],
    *,
    exclude_ids: set[str] | None = None,
) -> ChannelSelection:
    """Select the strict and wide channels for reporting/notifications."""

    channel_config = _as_dict(config.get("channels"))
    top_config = _as_dict(channel_config.get("top_matches"))
    data_config = _as_dict(channel_config.get("data_only_best_picks"))
    top_n = _parse_int(top_config.get("top_n", 10), 10)
    top_min_score = _parse_int(top_config.get("min_score", 0), 0)
    include_missing_salary = bool(
        top_config.get("include_missing_salary", True)
    )

    data_top_n = _parse_int(data_config.get("top_n", 10), 10)
    data_min_score = _parse_int(data_config.get("min_score", 0), 0)
    require_data_signal = bool(
        data_config.get("require_data_signal", True)
    )
    exclude_top_matches = bool(
        data_config.get("exclude_top_matches", True)
    )

    exclude_ids = exclude_ids or set()

    accepted_rows = [
        row
        for row in rows
        if row.match.decision == "accepted"
        and (row.match.score or 0) >= min(top_min_score, data_min_score)
        and _snapshot_key(row) not in exclude_ids
    ]

    top_candidates = [
        row
        for row in accepted_rows
        if (row.match.score or 0) >= top_min_score
        and (
            include_missing_salary
            or (not row.match.missing_salary)
        )
    ]
    top_matches = _sort_rows(top_candidates)[: max(top_n, 1)] if top_candidates else []

    top_keys = {_snapshot_key(row) for row in top_matches}
    data_only_reasons: dict[str, list[str]] = {}
    data_candidates: list[ReportRow] = []
    for row in accepted_rows:
        if (row.match.score or 0) < data_min_score:
            continue
        key = _snapshot_key(row)
        if exclude_top_matches and key in top_keys:
            continue
        signals = _data_signals(row, data_config, config)
        if require_data_signal and not signals:
            continue
        if signals:
            data_only_reasons[key] = signals
        data_candidates.append(row)

    data_only_best_picks = (
        _sort_rows(data_candidates)[: max(data_top_n, 1)]
        if data_candidates
        else []
    )
    return ChannelSelection(
        top_matches=top_matches,
        data_only_best_picks=data_only_best_picks,
        data_only_reasons=data_only_reasons,
    )


def _data_signals(
    row: ReportRow,
    data_config: Mapping[str, object],
    config: Mapping[str, object],
) -> list[str]:
    search_text = _build_search_text(row)
    keywords = data_config.get("keywords")
    if keywords is None:
        scoring = _as_dict(config.get("scoring"))
        keywords = scoring.get("data_governance_keywords", [])
    secondary = data_config.get("secondary_keywords")
    if secondary is None:
        scoring = _as_dict(config.get("scoring"))
        secondary = scoring.get(
            "data_governance_secondary_keywords", []
        )
    matches = _find_keywords(search_text, keywords)
    secondary_matches = _find_keywords(search_text, secondary)
    reasons: list[str] = []
    if matches:
        reasons.append(f"data keywords: {', '.join(matches)}")
    if secondary_matches:
        reasons.append(
            f"data signals: {', '.join(secondary_matches)}"
        )
    if "data" in search_text and not matches:
        reasons.append("data keyword: data")
    return reasons


def _build_search_text(row: ReportRow) -> str:
    posting = row.posting
    tags = " ".join(posting.tags)
    return f"{posting.title}\n{posting.description_snippet}\n{tags}".lower()


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


def _snapshot_key(row: ReportRow) -> str:
    return f"{row.posting.source}:{row.posting.id}"


def _sort_rows(rows: Iterable[ReportRow]) -> list[ReportRow]:
    return sorted(
        list(rows),
        key=lambda row: (
            -(row.match.score or 0),
            row.posting.id,
            row.posting.source,
        ),
    )


def _as_dict(raw: object) -> dict[str, object]:
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}


def _parse_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
