"""Writers for CSV and Markdown job reports."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

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
]


def _serialize_for_csv(posting: JobPosting) -> dict:
    data = posting.to_dict()
    data["tags"] = ";".join(posting.tags)
    return data


def write_reports(postings: Iterable[JobPosting], output_dir: Path) -> None:
    """Write CSV and Markdown reports to the output directory."""

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "report.csv"
    md_path = output_dir / "report.md"

    postings_list = list(postings)

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for posting in postings_list:
            writer.writerow(_serialize_for_csv(posting))

    sorted_postings = sorted(
        postings_list, key=lambda p: p.posted_at, reverse=True
    )
    with md_path.open("w", encoding="utf-8") as handle:
        handle.write("# Job Scout Report\n\n")
        if not sorted_postings:
            handle.write("No postings found.\n")
            return

        for posting in sorted_postings:
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
            if posting.tags:
                handle.write(f"  - Tags: {', '.join(posting.tags)}\n")
            handle.write(f"  - Link: {posting.url}\n")
            if posting.description_snippet:
                handle.write(f"  - Note: {posting.description_snippet}\n")
            handle.write("\n")
