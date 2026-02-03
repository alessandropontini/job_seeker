from datetime import datetime, timezone

from job_scout.matcher import MatchResult
from job_scout.models import JobPosting
from job_scout.notifications import format_digest
from job_scout.state import Snapshot, diff_rows
from job_scout.writers import ReportRow


def _make_row(job_id: str, score: int, penalties: list[str]) -> ReportRow:
    posting = JobPosting(
        id=job_id,
        source="dummy",
        company="Nimbus",
        title=f"Manager {job_id}",
        location_text="Milan, Italy",
        location_country="Italy",
        remote_type="full-remote",
        url=f"https://example.com/{job_id}",
        posted_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        salary_text="€70,000 - €90,000",
        currency="EUR",
        tags=[],
    )
    match = MatchResult(
        matches_all=True,
        decision="accepted",
        hard_reject_reasons=[],
        penalties=penalties,
        missing_fields=[],
        reject_reasons=[],
        missing_salary=False,
        salary_min_eur=70000,
        salary_max_eur=90000,
        remote_level="full-remote",
        score=score,
        score_penalties=penalties,
        score_bonuses=["full_remote"],
    )
    return ReportRow(posting=posting, match=match)


def test_format_digest_includes_reasons_and_scores():
    previous = Snapshot(
        generated_at="2024-01-01T00:00:00+00:00",
        jobs={"dummy:alpha": 95},
    )
    rows = [
        _make_row("alpha", 105, ["prefer_full_remote"]),
        _make_row("beta", 110, []),
    ]
    diff = diff_rows(previous, rows)

    digest = format_digest(diff, top_n=1, minimum_score=0)

    assert digest is not None
    assert "Job Scout updates" in digest
    assert "[NEW]" in digest or "[IMPROVED]" in digest
    assert "score 110" in digest
    assert "Bonuses: full_remote" in digest
