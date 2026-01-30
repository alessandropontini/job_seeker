"""Writers for CSV and Markdown job reports."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from job_scout.matcher import MatchResult
from job_scout.models import JobPosting

CSV_FIELDS = [
    "id",
    "source",
    "company",
    "title",
    "location_text",
    "location_country",
    "remote_type",
    "url",
    "posted_at",
    "salary_text",
    "currency",
    "tags",
    "description_snippet",
    "matches_all",
    "decision",
    "hard_reject_reasons",
    "penalties",
    "missing_fields",
    "reject_reasons",
    "missing_salary",
    "remote_level",
    "salary_min_eur",
    "salary_max_eur",
]


@dataclass(frozen=True)
class ReportRow:
    """Combined job posting and match metadata for report exports."""

    posting: JobPosting
    match: MatchResult


def _serialize_for_csv(row: ReportRow) -> dict:
    data = row.posting.to_dict()
    data["tags"] = ";".join(row.posting.tags)
    data["matches_all"] = row.match.matches_all
    data["decision"] = row.match.decision
    data["hard_reject_reasons"] = ";".join(row.match.hard_reject_reasons)
    data["penalties"] = ";".join(row.match.penalties)
    data["missing_fields"] = ";".join(row.match.missing_fields)
    data["reject_reasons"] = ";".join(row.match.reject_reasons)
    data["missing_salary"] = row.match.missing_salary
    data["remote_level"] = row.match.remote_level
    data["salary_min_eur"] = row.match.salary_min_eur
    data["salary_max_eur"] = row.match.salary_max_eur
    return data


def write_reports(
    matches: Iterable[ReportRow],
    missing_salary_allowed: Iterable[ReportRow],
    rejected: Iterable[ReportRow],
    output_dir: Path,
) -> None:
    """Write CSV and Markdown reports to the output directory."""

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "report.csv"
    md_path = output_dir / "report.md"

    matches_list = list(matches)
    missing_salary_list = list(missing_salary_allowed)
    rejected_list = list(rejected)
    all_rows = matches_list + missing_salary_list + rejected_list

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in all_rows:
            writer.writerow(_serialize_for_csv(row))

    with md_path.open("w", encoding="utf-8") as handle:
        handle.write("# Job Scout Report\n\n")
        if not all_rows:
            handle.write("No postings found.\n")
            return

        _write_section(handle, "Matches", matches_list)
        _write_section(
            handle, "Missing Salary (allowed)", missing_salary_list
        )
        _write_section(handle, "Rejected", rejected_list)


def _write_section(
    handle, title: str, rows: Iterable[ReportRow]
) -> None:
    handle.write(f"## {title}\n\n")
    rows_list = sorted(
        rows, key=lambda r: r.posting.posted_at, reverse=True
    )
    if not rows_list:
        handle.write("No postings found.\n\n")
        return

    for row in rows_list:
        posting = row.posting
        handle.write(
            f"- **{posting.title}** at **{posting.company}** "
            f"({posting.location_text}) - "
            f"{posting.remote_type}\n"
        )
        handle.write(f"  - Posted: {posting.posted_at.date()}\n")
        if posting.salary_text:
            handle.write(f"  - Salary: {posting.salary_text}\n")
        else:
            handle.write("  - Salary: Missing\n")
        if row.match.remote_level:
            handle.write(f"  - Remote level: {row.match.remote_level}\n")
        if posting.tags:
            handle.write(f"  - Tags: {', '.join(posting.tags)}\n")
        if row.match.penalties and row.match.decision == "accepted":
            handle.write(
                "  - Penalties: "
                f"{', '.join(row.match.penalties)}\n"
            )
        if row.match.decision == "rejected":
            handle.write("  - Decision: rejected\n")
        if row.match.hard_reject_reasons:
            handle.write(
                "  - Reject reasons: "
                f"{', '.join(row.match.hard_reject_reasons)}\n"
            )
        handle.write(f"  - Link: {posting.url}\n")
        if posting.description_snippet:
            handle.write(f"  - Note: {posting.description_snippet}\n")
        handle.write("\n")
