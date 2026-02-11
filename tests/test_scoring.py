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
        title="Data Governance Manager",
        location_text="Rome, Italy",
        location_country="Italy",
        remote_type="full-remote",
        url="https://example.com/job",
        posted_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        salary_text="€80k-€95k",
        currency="EUR",
        tags=[],
        description_snippet="Data quality and metadata strategy on GCP BigQuery.",
    )
    data.update(overrides)
    return JobPosting(**data)


def test_scoring_prioritizes_title_and_description_keywords():
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
    scored = apply_scoring(posting, match, config)

    assert scored.score and scored.score >= 100
    assert any(bonus.startswith("title_keywords:") for bonus in scored.score_bonuses)
    assert any(
        bonus.startswith("description_keywords:") for bonus in scored.score_bonuses
    )


def test_scoring_skips_rejected_postings():
    config = deepcopy(DEFAULT_CONFIG)
    posting = _posting(title="Senior Engineer", description_snippet="backend")
    region_data = load_region_data("config/regions.json")
    _, match = match_posting(
        posting,
        config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    scored = apply_scoring(posting, match, config)

    assert scored.score is None
    assert scored.score_penalties == []
    assert scored.score_bonuses == []


def test_quantitative_title_gets_soft_penalty_and_is_not_top_score():
    config = deepcopy(DEFAULT_CONFIG)
    posting = _posting(
        title="Quantitative Research Team Lead",
        description_snippet="Lead quantitative research for trading portfolios.",
    )
    region_data = load_region_data("config/regions.json")
    _, match = match_posting(
        posting,
        config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    scored = apply_scoring(posting, match, config)

    assert "negative_soft_penalty" in scored.score_penalties
    assert scored.score is not None
    assert scored.score < 70
