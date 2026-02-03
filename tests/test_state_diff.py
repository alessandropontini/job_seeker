from datetime import datetime, timezone

from job_scout.matcher import MatchResult
from job_scout.models import JobPosting
from job_scout.state import Snapshot, diff_rows
from job_scout.writers import ReportRow


def _make_row(job_id: str, score: int) -> ReportRow:
    posting = JobPosting(
        id=job_id,
        source="dummy",
        company="Acme",
        title=f"Lead {job_id}",
        location_text="Rome, Italy",
        location_country="Italy",
        remote_type="full-remote",
        url=f"https://example.com/{job_id}",
        posted_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        salary_text="€60,000 - €80,000",
        currency="EUR",
        tags=[],
    )
    match = MatchResult(
        matches_all=True,
        decision="accepted",
        hard_reject_reasons=[],
        penalties=[],
        missing_fields=[],
        reject_reasons=[],
        missing_salary=False,
        salary_min_eur=60000,
        salary_max_eur=80000,
        remote_level="full-remote",
        score=score,
        score_penalties=[],
        score_bonuses=["full_remote"],
    )
    return ReportRow(posting=posting, match=match)


def test_diff_rows_tracks_new_and_improved():
    previous = Snapshot(
        generated_at="2024-01-01T00:00:00+00:00",
        jobs={"dummy:alpha": 100, "dummy:beta": 90},
    )
    rows = [
        _make_row("alpha", 110),
        _make_row("beta", 85),
        _make_row("gamma", 95),
    ]

    diff = diff_rows(previous, rows)

    assert [row.posting.id for row in diff.new_rows] == ["gamma"]
    assert [row.posting.id for row in diff.improved_rows] == ["alpha"]
