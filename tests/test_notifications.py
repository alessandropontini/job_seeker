from datetime import datetime, timezone

from job_scout.matcher import MatchResult
from job_scout.models import JobPosting
from job_scout.notifications import build_digest, select_top_matches
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


def test_build_digest_delta_includes_reasons_and_scores():
    previous = Snapshot(
        generated_at="2024-01-01T00:00:00+00:00",
        jobs={
            "dummy:alpha": {"score": 95, "notified_at": "2024-01-01T00:00:00+00:00"}
        },
    )
    rows = [
        _make_row("alpha", 105, ["prefer_full_remote"]),
        _make_row("beta", 110, []),
    ]
    diff = diff_rows(previous, rows, min_improvement=5)
    digest, mode, _ = build_digest(
        diff, rows, top_n=1, minimum_score=0
    )

    assert digest
    assert mode == "delta_digest"
    assert "New/Improved" in digest
    assert "[NEW]" in digest or "[IMPROVED]" in digest
    assert "Score: 110" in digest
    assert "bonuses: full_remote" in digest


def test_build_digest_daily_when_no_delta():
    previous = Snapshot(
        generated_at="2024-01-01T00:00:00+00:00",
        jobs={
            "dummy:alpha": {"score": 100, "notified_at": "2024-01-01T00:00:00+00:00"},
            "dummy:beta": {"score": 90, "notified_at": "2024-01-01T00:00:00+00:00"},
        },
    )
    rows = [
        _make_row("alpha", 100, []),
        _make_row("beta", 90, []),
    ]
    diff = diff_rows(previous, rows, min_improvement=5)

    digest, mode, notified_rows = build_digest(
        diff, rows, top_n=2, minimum_score=0
    )

    assert digest
    assert mode == "daily_digest"
    assert notified_rows
    assert "Top matches today" in digest


def test_select_top_matches_ordering_deterministic():
    rows = [
        _make_row("bravo", 100, []),
        _make_row("alpha", 100, []),
    ]
    ranked = select_top_matches(rows, top_n=2, minimum_score=0)

    assert [row.posting.id for row in ranked] == ["alpha", "bravo"]
