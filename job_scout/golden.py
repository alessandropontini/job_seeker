"""Helpers for deterministic golden output normalization."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import io


def normalize_text(text: str) -> str:
    """Normalize line endings and trailing whitespace."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def normalize_csv_text(text: str) -> str:
    """Normalize CSV output for golden comparisons."""

    normalized = normalize_text(text)
    reader = csv.DictReader(io.StringIO(normalized))
    rows = list(reader)
    fieldnames = reader.fieldnames or []
    for row in rows:
        posted_at = row.get("posted_at")
        if posted_at:
            parsed = datetime.fromisoformat(posted_at)
            row["posted_at"] = parsed.astimezone(timezone.utc).isoformat()

    rows.sort(key=_stable_csv_sort_key)

    output = io.StringIO()
    writer = csv.DictWriter(
        output, fieldnames=fieldnames, lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return normalize_text(output.getvalue())


def normalize_markdown_text(text: str) -> str:
    """Normalize Markdown output for golden comparisons."""

    return normalize_text(text)


def _stable_csv_sort_key(row: dict) -> tuple:
    score_raw = row.get("score")
    try:
        score = int(score_raw)
    except (TypeError, ValueError):
        score = 0
    return (
        row.get("decision") or "",
        -score,
        row.get("posted_at") or "",
        row.get("id") or "",
    )
