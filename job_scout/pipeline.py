"""Pipeline runner for fetching, matching, and reporting job postings."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from job_scout.matcher import match_posting
from job_scout.normalize import (
    job_posting_from_normalized,
    normalize_source_job,
)
from job_scout.regions import load_region_data
from job_scout.sources import AVAILABLE_SOURCES
from job_scout.scoring import apply_scoring
from job_scout.writers import ReportRow, SourceStatus, write_reports

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineSummary:
    """Aggregate counts from a pipeline run."""

    fetched_count: int
    normalized_count: int
    candidates_count: int
    matches_count: int
    source_counts: dict[str, int]


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
) -> tuple[list[ReportRow], PipelineSummary]:
    """Run the job scouting pipeline end-to-end."""

    source_names = _resolve_sources(sources)
    if not source_names:
        config_sources = config.get("sources", {})
        if isinstance(config_sources, Mapping):
            source_names = list(config_sources.get("enabled", []))
    if not source_names:
        source_names = ["dummy"]

    regions_path = config.get("regions_path", "config/regions.json")
    region_data = load_region_data(regions_path)

    all_rows: list[ReportRow] = []
    source_statuses: list[SourceStatus] = []
    fetched_total = 0
    normalized_total = 0
    source_counts: dict[str, int] = {}
    for name in source_names:
        fetcher = AVAILABLE_SOURCES.get(name)
        if not fetcher:
            logger.warning("Unknown source '%s'", name)
            source_statuses.append(
                SourceStatus(
                    name=name,
                    ok=False,
                    count=0,
                    error="unknown_source",
                )
            )
            continue
        logger.info("Fetching from source: %s", name)
        try:
            source_jobs = fetcher(since_days)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Source %s failed: %s", name, exc)
            source_statuses.append(
                SourceStatus(
                    name=name,
                    ok=False,
                    count=0,
                    error=str(exc),
                )
            )
            continue
        fetched_total += len(source_jobs)
        source_counts[name] = len(source_jobs)
        normalized_jobs = [
            normalize_source_job(job, region_data) for job in source_jobs
        ]
        normalized_total += len(normalized_jobs)
        postings = [
            job_posting_from_normalized(job)
            for job in normalized_jobs
        ]
        source_statuses.append(
            SourceStatus(
                name=name,
                ok=True,
                count=len(postings),
                error=None,
            )
        )
        logger.info("Fetched %d postings from %s", len(postings), name)
        for posting in postings:
            updated_posting, match = match_posting(
                posting,
                config,
                region_data,
                strict,
                allow_missing_salary,
            )
            scored_match = apply_scoring(updated_posting, match, config)
            all_rows.append(
                ReportRow(posting=updated_posting, match=scored_match)
            )

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

    write_reports(
        matches,
        missing_salary_allowed,
        rejected,
        output_dir,
        source_statuses=source_statuses,
    )
    logger.info("Wrote reports to %s", output_dir)
    summary = PipelineSummary(
        fetched_count=fetched_total,
        normalized_count=normalized_total,
        candidates_count=len(matches) + len(missing_salary_allowed),
        matches_count=len(matches),
        source_counts=source_counts,
    )
    return all_rows, summary
