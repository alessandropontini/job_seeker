"""Snapshot and diff helpers for notification workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping

from job_scout.writers import ReportRow


@dataclass(frozen=True)
class Snapshot:
    """Lightweight snapshot of job scores from a prior run."""

    generated_at: str
    jobs: dict[str, int]


@dataclass(frozen=True)
class SnapshotDiff:
    """Diff of current rows versus a previous snapshot."""

    new_rows: list[ReportRow]
    improved_rows: list[ReportRow]
    previous_scores: Mapping[str, int]
    current_snapshot: Snapshot


def load_snapshot(path: Path) -> Snapshot:
    """Load a snapshot from disk, returning an empty snapshot if missing."""

    if not path.exists():
        return Snapshot(generated_at="", jobs={})
    payload = json.loads(path.read_text(encoding="utf-8"))
    jobs_raw = payload.get("jobs", {})
    jobs: dict[str, int] = {}
    if isinstance(jobs_raw, dict):
        for key, value in jobs_raw.items():
            try:
                jobs[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
    generated_at = str(payload.get("generated_at", ""))
    return Snapshot(generated_at=generated_at, jobs=jobs)


def save_snapshot(path: Path, snapshot: Snapshot) -> None:
    """Persist a snapshot to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": snapshot.generated_at,
        "jobs": snapshot.jobs,
    }
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2),
        encoding="utf-8",
    )


def diff_rows(
    previous: Snapshot,
    rows: Iterable[ReportRow],
) -> SnapshotDiff:
    """Compare current rows to a previous snapshot."""

    current_jobs: dict[str, int] = {}
    new_rows: list[ReportRow] = []
    improved_rows: list[ReportRow] = []

    for row in rows:
        if not row.match.matches_all or row.match.score is None:
            continue
        key = _snapshot_key(row)
        current_jobs[key] = int(row.match.score)
        if key not in previous.jobs:
            new_rows.append(row)
            continue
        if row.match.score > previous.jobs[key]:
            improved_rows.append(row)

    snapshot = Snapshot(
        generated_at=_now_iso(),
        jobs=current_jobs,
    )
    return SnapshotDiff(
        new_rows=_sort_rows(new_rows),
        improved_rows=_sort_rows(improved_rows),
        previous_scores=previous.jobs,
        current_snapshot=snapshot,
    )


def _snapshot_key(row: ReportRow) -> str:
    return f"{row.posting.source}:{row.posting.id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sort_rows(rows: Iterable[ReportRow]) -> list[ReportRow]:
    return sorted(
        list(rows),
        key=lambda row: (
            row.match.score or 0,
            row.posting.posted_at,
            row.posting.id,
        ),
        reverse=True,
    )
