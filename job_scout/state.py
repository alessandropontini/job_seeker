"""Snapshot and diff helpers for notification workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Iterable, Mapping

from job_scout.writers import ReportRow

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class Snapshot:
    """Lightweight snapshot of job scores from a prior run."""

    generated_at: str
    jobs: dict[str, dict[str, str | int]]


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
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Snapshot load failed (%s); starting fresh.", exc)
        return Snapshot(generated_at="", jobs={})
    jobs_raw = payload.get("jobs", {})
    jobs: dict[str, dict[str, str | int]] = {}
    if isinstance(jobs_raw, dict):
        for key, value in jobs_raw.items():
            if not isinstance(value, dict):
                continue
            score = value.get("score")
            notified_at = value.get("notified_at")
            try:
                score_int = int(score)
            except (TypeError, ValueError):
                continue
            jobs[str(key)] = {
                "score": score_int,
                "notified_at": str(notified_at or ""),
            }
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
    min_improvement: int,
) -> SnapshotDiff:
    """Compare current rows to a previous snapshot."""

    current_jobs: dict[str, dict[str, str | int]] = {}
    new_rows: list[ReportRow] = []
    improved_rows: list[ReportRow] = []

    for row in rows:
        if not row.match.matches_all or row.match.score is None:
            continue
        key = _snapshot_key(row)
        previous_entry = previous.jobs.get(key, {})
        notified_at = ""
        if isinstance(previous_entry, dict):
            notified_at = str(previous_entry.get("notified_at", ""))
        current_jobs[key] = {
            "score": int(row.match.score),
            "notified_at": notified_at,
        }
        previous_entry = previous.jobs.get(key)
        if not previous_entry:
            new_rows.append(row)
            continue
        previous_score = int(previous_entry.get("score", 0))
        if row.match.score >= previous_score + min_improvement:
            improved_rows.append(row)

    snapshot = Snapshot(generated_at=_now_iso(), jobs=current_jobs)
    return SnapshotDiff(
        new_rows=_sort_rows(new_rows),
        improved_rows=_sort_rows(improved_rows),
        previous_scores={
            key: int(value.get("score", 0))
            for key, value in previous.jobs.items()
            if isinstance(value, dict)
        },
        current_snapshot=snapshot,
    )


def mark_notified(
    snapshot: Snapshot, notified_rows: Iterable[object]
) -> Snapshot:
    """Return a snapshot with notified timestamps applied."""

    jobs = {
        key: dict(value)
        for key, value in snapshot.jobs.items()
        if isinstance(value, dict)
    }
    now = _now_iso()
    for row in notified_rows:
        key, score = _extract_notified_fields(row)
        if not key:
            logger.warning(
                "Unable to determine job_id for notified row; skipping."
            )
            continue
        if score is None:
            existing = jobs.get(key)
            if isinstance(existing, dict):
                score = _coerce_score(existing.get("score"))
        if score is None:
            logger.warning(
                "Unable to determine score for notified row %s; skipping.",
                key,
            )
            continue
        jobs[key] = {
            "score": int(score),
            "notified_at": now,
        }
    return Snapshot(generated_at=now, jobs=jobs)


def _snapshot_key(row: ReportRow) -> str:
    return f"{row.posting.source}:{row.posting.id}"


def _extract_notified_fields(row: object) -> tuple[str | None, int | None]:
    if row is None:
        return None, None

    if hasattr(row, "_asdict"):
        try:
            return _extract_from_mapping(row._asdict())
        except Exception:  # pragma: no cover - defensive
            return None, None

    if isinstance(row, Mapping):
        return _extract_from_mapping(row)

    if isinstance(row, (tuple, list)):
        if len(row) >= 2 and isinstance(row[0], str):
            if row[0] in {"new", "improved"}:
                return _extract_notified_fields(row[1])
            return _normalize_snapshot_key(row[0], None), _coerce_score(
                row[1]
            )
        for item in row:
            key, score = _extract_notified_fields(item)
            if key:
                return key, score
        return None, None

    posting = getattr(row, "posting", None)
    match = getattr(row, "match", None)
    if posting is not None or match is not None:
        job_id = getattr(posting, "id", None) if posting else None
        source = getattr(posting, "source", None) if posting else None
        score = getattr(match, "score", None) if match else None
        return _normalize_snapshot_key(job_id, source), _coerce_score(
            score
        )

    job_id = getattr(row, "id", None) or getattr(row, "job_id", None)
    source = getattr(row, "source", None)
    score = getattr(row, "score", None)
    return _normalize_snapshot_key(job_id, source), _coerce_score(score)


def _extract_from_mapping(
    payload: Mapping[object, object]
) -> tuple[str | None, int | None]:
    posting = payload.get("posting")
    match = payload.get("match")
    job_id = None
    source = None
    score = None
    if isinstance(posting, Mapping):
        job_id = posting.get("id")
        source = posting.get("source")
    if isinstance(match, Mapping):
        score = match.get("score")
    if job_id is None:
        job_id = payload.get("id") or payload.get("job_id")
    if source is None:
        source = payload.get("source")
    if score is None:
        score = payload.get("score")
    return _normalize_snapshot_key(job_id, source), _coerce_score(score)


def _normalize_snapshot_key(
    job_id: object, source: object | None
) -> str | None:
    if job_id is None:
        return None
    job_id_str = str(job_id)
    if source:
        return f"{source}:{job_id_str}"
    if ":" in job_id_str:
        return job_id_str
    return None


def _coerce_score(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sort_rows(rows: Iterable[ReportRow]) -> list[ReportRow]:
    return sorted(
        list(rows),
        key=lambda row: (
            -(row.match.score or 0),
            row.posting.id,
            row.posting.source,
        ),
    )
