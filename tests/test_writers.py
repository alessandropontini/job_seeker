from datetime import datetime, timezone

from job_scout.matcher import MatchResult
from job_scout.models import JobPosting
from job_scout.writers import ReportRow, write_reports


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
            reject_reasons=[],
            missing_salary=True,
            salary_min_eur=None,
            salary_max_eur=None,
            remote_level="full-remote",
        ),
    )

    write_reports([row], [], [], tmp_path)

    csv_path = tmp_path / "report.csv"
    md_path = tmp_path / "report.md"
    assert csv_path.exists()
    assert md_path.exists()

    csv_content = csv_path.read_text(encoding="utf-8")
    md_content = md_path.read_text(encoding="utf-8")

    assert "unit-2" in csv_content
    assert "Product Lead" in md_content
    assert "Salary: Missing" in md_content
    assert "## Matches" in md_content
