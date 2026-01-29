"""Pipeline runner for fetching, annotating, and writing job postings."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from job_scout.models import JobPosting
from job_scout.sources import AVAILABLE_SOURCES
from job_scout.writers import write_reports

logger = logging.getLogger(__name__)


def apply_missing_salary_flag(
    postings: Iterable[JobPosting], flag_missing_salary: bool
) -> list[JobPosting]:
    """Append a missing-salary tag when salaries are absent and flagging is on."""

    tagged: list[JobPosting] = []
    for posting in postings:
        if flag_missing_salary and not posting.salary_text:
            tagged.append(posting.with_tags(["missing_salary"]))
        else:
            tagged.append(posting)
    return tagged


def run_pipeline(
    since_days: int,
    output_dir: Path,
    flag_missing_salary: bool,
) -> list[JobPosting]:
    """Run the minimal end-to-end pipeline and write reports."""

    logger.info("Starting pipeline with dummy source")
    fetcher = AVAILABLE_SOURCES["dummy"]
    postings = fetcher(since_days)
    logger.info("Fetched %d postings", len(postings))

    postings = apply_missing_salary_flag(postings, flag_missing_salary)
    write_reports(postings, output_dir)
    logger.info("Wrote reports to %s", output_dir)
    return postings
