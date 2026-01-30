from job_scout.config import DEFAULT_CONFIG
from job_scout.pipeline import run_pipeline


def test_pipeline_groups_and_reports(tmp_path):
    output_dir = tmp_path / "out"
    config = dict(DEFAULT_CONFIG)

    rows = run_pipeline(
        since_days=7,
        output_dir=output_dir,
        config=config,
        strict=False,
        allow_missing_salary=True,
        sources=["dummy"],
    )

    csv_path = output_dir / "report.csv"
    md_path = output_dir / "report.md"
    assert csv_path.exists()
    assert md_path.exists()

    csv_header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert "matches_all" in csv_header
    assert "decision" in csv_header
    assert "hard_reject_reasons" in csv_header
    assert "penalties" in csv_header
    assert "missing_fields" in csv_header
    assert "reject_reasons" in csv_header
    assert "missing_salary" in csv_header
    assert "score" in csv_header

    md_content = md_path.read_text(encoding="utf-8")
    assert "## Matches" in md_content
    assert "## Missing Salary (allowed)" in md_content
    assert "## Rejected" in md_content
    assert "Penalties:" in md_content
    assert "Score:" in md_content

    rejected = [row for row in rows if not row.match.matches_all]
    assert rejected
    assert any(row.match.hard_reject_reasons for row in rejected)

    missing_salary = [
        row for row in rows if row.match.missing_salary and row.match.matches_all
    ]
    assert missing_salary
    assert any("missing_salary" in row.posting.tags for row in missing_salary)
