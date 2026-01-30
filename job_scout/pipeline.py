"""Pipeline runner for fetching, matching, and reporting job postings."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Mapping

from job_scout.matcher import MatchResult, match_posting
from job_scout.models import JobPosting
from job_scout.sources import AVAILABLE_SOURCES
from job_scout.writers import ReportRow, write_reports

logger = logging.getLogger(__name__)


def _resolve_sources(selected: Iterable[str] | None) -> list[str]:
    if not selected:
        return []
    resolved: list[str] = []
    for entry in selected:
        for name in entry.split(","):
            name = name.strip()
            if name and name not in resolved:
                resolved.append(name)
    return resolved


def run_pipeline(
    since_days: int,
    output_dir: Path,
    config: Mapping[str, object],
    strict: bool,
    allow_missing_salary: bool,
    sources: Iterable[str] | None,
) -> list[ReportRow]:
    """Run the job scouting pipeline end-to-end."""

    source_names = _resolve_sources(sources)
    if not source_names:
        config_sources = config.get("sources", {})
        if isinstance(config_sources, Mapping):
            source_names = list(config_sources.get("enabled", []))
    if not source_names:
        source_names = ["dummy"]

    all_rows: list[ReportRow] = []
    for name in source_names:
        fetcher = AVAILABLE_SOURCES.get(name)
        if not fetcher:
            logger.warning("Unknown source '%s'", name)
            continue
        logger.info("Fetching from source: %s", name)
        postings = fetcher(since_days)
        logger.info("Fetched %d postings from %s", len(postings), name)
        for posting in postings:
            updated_posting, match = match_posting(
                posting, config, strict, allow_missing_salary
            )
            all_rows.append(ReportRow(posting=updated_posting, match=match))

    matches: list[ReportRow] = []
    missing_salary_allowed: list[ReportRow] = []
    rejected: list[ReportRow] = []

    for row in all_rows:
        if row.match.matches_all:
            if row.match.missing_salary:
                missing_salary_allowed.append(row)
            else:
                matches.append(row)
        else:
            rejected.append(row)

    write_reports(matches, missing_salary_allowed, rejected, output_dir)
    logger.info("Wrote reports to %s", output_dir)
    return all_rows
