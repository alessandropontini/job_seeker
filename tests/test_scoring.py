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

    assert scored.score and 0 <= scored.score <= 100
    assert any(bonus.startswith("core_title:") for bonus in scored.score_bonuses)
    assert any(
        bonus.startswith("core_description:") for bonus in scored.score_bonuses
    )
    assert scored.why
    assert any(reason.startswith("fit role_targeted") for reason in scored.why)
    assert any(reason.startswith("fit domain_targeted") for reason in scored.why)


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
        description_snippet=(
            "Lead quantitative research for trading portfolios while defining "
            "data governance and metadata controls for the platform."
        ),
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


def test_non_managerial_compliance_title_is_heavily_downranked():
    config = deepcopy(DEFAULT_CONFIG)
    config["runtime"]["run_mode"] = "manual"
    posting = _posting(
        title="Finance and Compliance Officer",
        description_snippet="Compliance controls for finance processes.",
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

    assert match.decision == "rejected"
    assert "cv_alignment_missing" in match.hard_reject_reasons
    assert scored.score is None


def test_managerial_data_title_scores_above_generic_data_specialist():
    config = deepcopy(DEFAULT_CONFIG)
    region_data = load_region_data("config/regions.json")
    posting = _posting(
        title="Head of Data Governance",
        description_snippet="Own metadata, lineage and data quality across the enterprise platform.",
    )

    _, match = match_posting(
        posting,
        config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    scored = apply_scoring(posting, match, config)

    assert scored.score is not None
    assert "seniority_data_title" in scored.score_bonuses


def test_solution_architect_with_data_stack_scores_as_technical_target():
    config = deepcopy(DEFAULT_CONFIG)
    posting = _posting(
        title="IT Solution Architect",
        description_snippet=(
            "Design metadata management, lineage and governance controls on "
            "GCP BigQuery, Dataflow and Databricks."
        ),
        tags=["Axon", "Erwin", "Power BI"],
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

    assert scored.score is not None
    assert any(bonus.startswith("seniority_title:") for bonus in scored.score_bonuses)
    assert any(bonus.startswith("platform:") for bonus in scored.score_bonuses)
    assert scored.score >= 50
