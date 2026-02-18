from datetime import datetime, timezone

from job_scout.matcher import MatchResult
from job_scout.models import JobPosting
from job_scout.writers import ReportRow, SourceStatus, write_reports


def test_write_reports_creates_files(tmp_path):
    posting = JobPosting(
        id="unit-2",
        source="dummy",
        company="Example Co",
        title="Product Lead",
        location_text="Rome, Italy",
        location_country="Italy",
        remote_type="full-remote",
        url="https://example.com/job-2",
        posted_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
        salary_text=None,
        currency=None,
        tags=["missing_salary"],
        description_snippet="Test posting.",
    )

    row = ReportRow(
        posting=posting,
        match=MatchResult(
            matches_all=True,
            decision="accepted",
            hard_reject_reasons=[],
            penalties=["missing_salary"],
            missing_fields=["salary"],
            reject_reasons=[],
            missing_salary=True,
            salary_min_eur=None,
            salary_max_eur=None,
            remote_level="full-remote",
            score=95,
            score_penalties=["missing_salary"],
            score_bonuses=["full_remote"],
            why=["match core_title: data governance", "penalty missing_salary"],
        ),
    )

    write_reports(
        [row],
        [],
        [],
        tmp_path,
        top_matches=[row],
        data_only_best_picks=[row],
        channel_reasons={"dummy:unit-2": ["data keyword: data"]},
        source_statuses=[SourceStatus(name="dummy", ok=True, count=1)],
    )

    csv_path = tmp_path / "report.csv"
    md_path = tmp_path / "report.md"
    assert csv_path.exists()
    assert md_path.exists()

    csv_content = csv_path.read_text(encoding="utf-8")
    md_content = md_path.read_text(encoding="utf-8")

    assert "unit-2" in csv_content
    assert "penalties_applied" in csv_content.splitlines()[0]
    assert "why" in csv_content.splitlines()[0]
    assert "Product Lead" in md_content
    assert "Salary: Missing" in md_content
    assert "Penalties: missing_salary" in md_content
    assert "Score: 95" in md_content
    assert "Why:" in md_content
    assert "## TOP_MATCHES" in md_content
    assert "## DATA_ONLY_BEST_PICKS" in md_content
    assert "## Matches" in md_content
    assert "## Source Status" in md_content


def test_write_reports_orders_by_score(tmp_path):
    first_posting = JobPosting(
        id="unit-a",
        source="dummy",
        company="Score High",
        title="Product Lead",
        location_text="Milan, Italy",
        location_country="Italy",
        remote_type="full-remote",
        url="https://example.com/high",
        posted_at=datetime(2024, 2, 3, tzinfo=timezone.utc),
        salary_text="€90k",
        currency="EUR",
        tags=[],
        description_snippet="High score.",
    )
    second_posting = JobPosting(
        id="unit-b",
        source="dummy",
        company="Score Low",
        title="Product Lead",
        location_text="Milan, Italy",
        location_country="Italy",
        remote_type="hybrid",
        url="https://example.com/low",
        posted_at=datetime(2024, 2, 4, tzinfo=timezone.utc),
        salary_text="€90k",
        currency="EUR",
        tags=[],
        description_snippet="Low score.",
    )

    high_row = ReportRow(
        posting=first_posting,
        match=MatchResult(
            matches_all=True,
            decision="accepted",
            hard_reject_reasons=[],
            penalties=[],
            missing_fields=[],
            reject_reasons=[],
            missing_salary=False,
            salary_min_eur=90000,
            salary_max_eur=90000,
            remote_level="full-remote",
            score=110,
            score_penalties=[],
            score_bonuses=["full_remote"],
            why=["match core_title"],
        ),
    )
    low_row = ReportRow(
        posting=second_posting,
        match=MatchResult(
            matches_all=True,
            decision="accepted",
            hard_reject_reasons=[],
            penalties=["prefer_full_remote"],
            missing_fields=[],
            reject_reasons=[],
            missing_salary=False,
            salary_min_eur=90000,
            salary_max_eur=90000,
            remote_level="hybrid",
            score=85,
            score_penalties=["prefer_full_remote"],
            score_bonuses=[],
            why=["penalty prefer_full_remote"],
        ),
    )

    write_reports([low_row, high_row], [], [], tmp_path)

    md_path = tmp_path / "report.md"
    md_content = md_path.read_text(encoding="utf-8")

    first_index = md_content.find("Score High")
    second_index = md_content.find("Score Low")
    assert first_index != -1
    assert second_index != -1
    assert first_index < second_index
