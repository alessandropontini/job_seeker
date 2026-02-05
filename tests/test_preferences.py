from copy import deepcopy
from datetime import datetime, timezone

from job_scout.config import DEFAULT_CONFIG
from job_scout.matcher import MatchResult
from job_scout.models import JobPosting
from job_scout.preferences import (
    PreferenceProfile,
    apply_feedback,
    apply_preferences,
)


def _make_match(score: int) -> MatchResult:
    return MatchResult(
        matches_all=True,
        decision="accepted",
        hard_reject_reasons=[],
        penalties=[],
        missing_fields=[],
        reject_reasons=[],
        missing_salary=False,
        salary_min_eur=70000,
        salary_max_eur=90000,
        remote_level="full-remote",
        score=score,
        score_penalties=[],
        score_bonuses=[],
    )


def test_feedback_updates_profile_and_ranking():
    config = deepcopy(DEFAULT_CONFIG)
    config["personalization"]["enabled"] = True

    profile = PreferenceProfile(
        token_weights={},
        tag_weights={},
        remote_level_weights={},
        seniority_weights={},
        duplicate_ids=set(),
        last_update_id=None,
        feedback_cache={},
        updated_at="",
    )

    cached_item = {
        "title": "Data Governance Manager",
        "description_snippet": "Lead data quality initiatives.",
        "tags": ["governance"],
        "remote_level": "full-remote",
    }
    profile = apply_feedback(
        profile,
        action="like",
        job_key="dummy:alpha",
        cached_item=cached_item,
        config=config,
    )

    data_posting = JobPosting(
        id="alpha",
        source="dummy",
        company="Nimbus",
        title="Data Governance Manager",
        location_text="Milan, Italy",
        location_country="Italy",
        remote_type="full-remote",
        url="https://example.com/alpha",
        posted_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        salary_text="€70,000 - €90,000",
        currency="EUR",
        tags=["governance"],
    )
    generic_posting = JobPosting(
        id="beta",
        source="dummy",
        company="Nimbus",
        title="Customer Success Manager",
        location_text="Milan, Italy",
        location_country="Italy",
        remote_type="full-remote",
        url="https://example.com/beta",
        posted_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        salary_text="€70,000 - €90,000",
        currency="EUR",
        tags=["success"],
    )

    data_match = apply_preferences(
        data_posting, _make_match(100), profile, config
    )
    generic_match = apply_preferences(
        generic_posting, _make_match(100), profile, config
    )

    assert data_match.score > generic_match.score
    assert any("preference" in bonus for bonus in data_match.score_bonuses)
