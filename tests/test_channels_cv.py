from datetime import datetime, timezone

from job_scout.channels import select_channels
from job_scout.config import DEFAULT_CONFIG
from job_scout.matcher import MatchResult
from job_scout.models import JobPosting
from job_scout.writers import ReportRow


def _row(title: str, description: str, score: int) -> ReportRow:
    posting = JobPosting(
        id=title.lower().replace(" ", "-"),
        source="dummy",
        company="Acme",
        title=title,
        location_text="Rome, Italy",
        location_country="Italy",
        remote_type="full-remote",
        url="https://example.com/job",
        posted_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        salary_text="€80k-€90k",
        currency="EUR",
        tags=[],
        description_snippet=description,
    )
    match = MatchResult(
        matches_all=True,
        decision="accepted",
        hard_reject_reasons=[],
        penalties=[],
        missing_fields=[],
        reject_reasons=[],
        missing_salary=False,
        salary_min_eur=80000,
        salary_max_eur=90000,
        remote_level="full-remote",
        score=score,
        score_penalties=[],
        score_bonuses=[],
    )
    return ReportRow(posting=posting, match=match)


def test_brand_manager_not_in_top_matches():
    selection = select_channels(
        [
            _row("Senior Amazon Brand Manager", "Brand growth and paid media", 95),
            _row("Data Governance Specialist", "Data governance and metadata", 92),
        ],
        DEFAULT_CONFIG,
    )

    titles = [row.posting.title for row in selection.top_matches]
    assert "Senior Amazon Brand Manager" not in titles
    assert "Data Governance Specialist" in titles


def test_quantitative_team_lead_not_in_top_matches_without_core_keywords():
    selection = select_channels(
        [
            _row(
                "Quantitative Research Team Lead",
                "Lead quant trading portfolio research",
                75,
            )
        ],
        DEFAULT_CONFIG,
    )

    assert selection.top_matches == []
    assert selection.data_only_best_picks == []
