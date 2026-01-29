from datetime import datetime, timezone

from job_scout.models import JobPosting


def test_job_posting_serialization():
    posted_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    posting = JobPosting(
        id="unit-1",
        source="dummy",
        company="Example Co",
        title="Engineering Manager",
        location_text="Milan, Italy",
        location_country="Italy",
        remote_type="full-remote",
        url="https://example.com/job",
        posted_at=posted_at,
        salary_text="€80k-€90k",
        currency="EUR",
        tags=["test"],
        description_snippet="Lead a small team.",
    )

    data = posting.to_dict()

    assert data["id"] == "unit-1"
    assert data["posted_at"] == posted_at.isoformat()
    assert data["tags"] == ["test"]
