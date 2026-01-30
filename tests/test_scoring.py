from copy import deepcopy
from datetime import datetime, timezone

from job_scout.config import DEFAULT_CONFIG
from job_scout.matcher import match_posting
from job_scout.models import JobPosting
from job_scout.regions import load_region_data
from job_scout.scoring import apply_scoring


def _posting(**overrides) -> JobPosting:
    data = dict(
        id="score-1",
        source="dummy",
        company="Example Co",
        title="Engineering Manager",
        location_text="Rome, Italy",
        location_country="Italy",
        remote_type="full-remote",
        url="https://example.com/job",
        posted_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        salary_text=None,
        currency=None,
        tags=[],
        description_snippet="Example",
    )
    data.update(overrides)
    return JobPosting(**data)


def test_scoring_applies_penalties_and_bonuses():
    config = deepcopy(DEFAULT_CONFIG)
    posting = _posting()
    region_data = load_region_data("config/regions.json")
    _, match = match_posting(
        posting,
        config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    scored = apply_scoring(match, config)

    assert scored.score == 95
    assert scored.score_penalties == ["missing_salary"]
    assert scored.score_bonuses == ["full_remote"]


def test_scoring_skips_rejected_postings():
    config = deepcopy(DEFAULT_CONFIG)
    posting = _posting(title="Senior Engineer")
    region_data = load_region_data("config/regions.json")
    _, match = match_posting(
        posting,
        config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    scored = apply_scoring(match, config)

    assert scored.score is None
    assert scored.score_penalties == []
    assert scored.score_bonuses == []
