"""Writers for CSV and Markdown job reports."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

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
    "score",
    "score_penalties",
    "score_bonuses",
]


@dataclass(frozen=True)
class ReportRow:
    """Combined job posting and match metadata for report exports."""

    posting: JobPosting
    match: MatchResult


@dataclass(frozen=True)
class SourceStatus:
    """Status summary for a pipeline source."""

    name: str
    ok: bool
    count: int = 0
    error: str | None = None


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
    data["score"] = row.match.score
    data["score_penalties"] = ";".join(row.match.score_penalties)
    data["score_bonuses"] = ";".join(row.match.score_bonuses)
    return data


def write_reports(
    matches: Iterable[ReportRow],
    missing_salary_allowed: Iterable[ReportRow],
    rejected: Iterable[ReportRow],
    output_dir: Path,
    top_matches: Iterable[ReportRow] | None = None,
    data_only_best_picks: Iterable[ReportRow] | None = None,
    channel_reasons: Mapping[str, list[str]] | None = None,
    source_statuses: Iterable[SourceStatus] | None = None,
) -> None:
    """Write CSV and Markdown reports to the output directory."""

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "report.csv"
    md_path = output_dir / "report.md"

    matches_list = _sort_rows(matches)
    missing_salary_list = _sort_rows(missing_salary_allowed)
    rejected_list = _sort_rows(rejected)
    all_rows = matches_list + missing_salary_list + rejected_list

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in all_rows:
            writer.writerow(_serialize_for_csv(row))

    with md_path.open("w", encoding="utf-8") as handle:
        handle.write("# Job Scout Report\n\n")
        if source_statuses:
            _write_source_status(handle, source_statuses)
        if not all_rows:
            handle.write("No postings found.\n")
            return
        if top_matches is not None:
            _write_section(
                handle,
                "TOP_MATCHES (strict)",
                _sort_rows(top_matches),
                channel_reasons=channel_reasons,
            )
        if data_only_best_picks is not None:
            _write_section(
                handle,
                "DATA_ONLY_BEST_PICKS (wide)",
                _sort_rows(data_only_best_picks),
                channel_reasons=channel_reasons,
            )
        _write_section(handle, "Matches", matches_list)
        _write_section(
            handle, "Missing Salary (allowed)", missing_salary_list
        )
        _write_section(handle, "Rejected", rejected_list)


def _write_section(
    handle,
    title: str,
    rows: Iterable[ReportRow],
    channel_reasons: Mapping[str, list[str]] | None = None,
) -> None:
    handle.write(f"## {title}\n\n")
    rows_list = _sort_rows(rows)
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
        if row.match.score is not None and row.match.decision == "accepted":
            handle.write(f"  - Score: {row.match.score}\n")
            adjustments = []
            if row.match.score_bonuses:
                adjustments.append(
                    f"+{', +'.join(row.match.score_bonuses)}"
                )
            if row.match.score_penalties:
                adjustments.append(
                    f"-{', -'.join(row.match.score_penalties)}"
                )
            if adjustments:
                handle.write(
                    "  - Score adjustments: "
                    f"{'; '.join(adjustments)}\n"
                )
        if channel_reasons:
            reasons = channel_reasons.get(_snapshot_key(row))
            if reasons:
                handle.write(
                    "  - Channel reasons: "
                    f"{'; '.join(reasons)}\n"
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


def _write_source_status(
    handle, statuses: Iterable[SourceStatus]
) -> None:
    handle.write("## Source Status\n\n")
    status_list = sorted(statuses, key=lambda s: s.name)
    if not status_list:
        handle.write("No sources configured.\n\n")
        return
    for status in status_list:
        if status.ok:
            handle.write(
                f"- {status.name}: ok ({status.count} postings)\n"
            )
        else:
            error = status.error or "unknown error"
            handle.write(
                f"- {status.name}: error ({error})\n"
            )
    handle.write("\n")


def _sort_rows(rows: Iterable[ReportRow]) -> list[ReportRow]:
    rows_list = list(rows)
    if not rows_list:
        return []

    if rows_list[0].match.decision == "accepted":
        return sorted(
            rows_list,
            key=lambda r: (
                r.match.score or 0,
                r.posting.posted_at,
                r.posting.id,
            ),
            reverse=True,
        )
    return sorted(
        rows_list, key=lambda r: r.posting.posted_at, reverse=True
    )


def _snapshot_key(row: ReportRow) -> str:
    return f"{row.posting.source}:{row.posting.id}"
