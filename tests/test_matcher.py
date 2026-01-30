from copy import deepcopy
from datetime import datetime, timezone

import pytest

from job_scout.config import DEFAULT_CONFIG
from job_scout.matcher import match_posting
from job_scout.models import JobPosting
from job_scout.normalize import normalize_remote_level
from job_scout.regions import load_region_data


@pytest.fixture()
def base_config():
    return deepcopy(DEFAULT_CONFIG)


@pytest.fixture()
def region_data():
    return load_region_data("config/regions.json")

def _posting(**overrides) -> JobPosting:
    data = dict(
        id="unit",
        source="dummy",
        company="Example Co",
        title="Engineering Manager",
        location_text="Rome, Italy",
        location_country="Italy",
        remote_type="full-remote",
        url="https://example.com/job",
        posted_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        salary_text="€80k-€95k",
        currency="EUR",
        tags=[],
        description_snippet="Example",
    )
    data.update(overrides)
    return JobPosting(**data)


def test_excludes_uk_by_country(base_config, region_data):
    posting = _posting(location_text="London", location_country="UK")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "excluded_country" in result.hard_reject_reasons


def test_excludes_uk_by_text(base_config, region_data):
    posting = _posting(location_text="Remote - United Kingdom", location_country="")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "excluded_country_text" in result.hard_reject_reasons


def test_accepts_eu_country(base_config, region_data):
    posting = _posting(location_text="Berlin, Germany", location_country="Germany")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert result.matches_all is True


def test_accepts_city_match(base_config, region_data):
    posting = _posting(location_text="New York, NY", location_country="US")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert result.matches_all is True


def test_accepts_italy_country(base_config, region_data):
    posting = _posting(location_text="Milan, Italy", location_country="Italy")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert result.matches_all is True


def test_rejects_unknown_location_in_strict(base_config, region_data):
    posting = _posting(location_text="", location_country="")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=True,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "location_missing_strict" in result.hard_reject_reasons
    assert "location" in result.missing_fields


def test_rejects_location_not_allowed_when_not_strict(
    base_config, region_data
):
    posting = _posting(location_text="Toronto, Canada", location_country="Canada")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "location_not_allowed" in result.hard_reject_reasons


def test_accepts_manager_title(base_config, region_data):
    posting = _posting(title="Product Manager")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert "title_not_targeted" not in result.hard_reject_reasons


def test_accepts_lead_title(base_config, region_data):
    posting = _posting(title="Data Lead")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert result.matches_all is True


def test_accepts_head_title(base_config, region_data):
    posting = _posting(title="Head of Engineering")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert result.matches_all is True


def test_rejects_non_target_title(base_config, region_data):
    posting = _posting(title="Senior Engineer")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "title_not_targeted" in result.hard_reject_reasons


def test_parses_eur_salary_range(base_config, region_data):
    posting = _posting(salary_text="€80k-€95k", currency=None)
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.salary_min_eur == 80000
    assert result.salary_max_eur == 95000


def test_parses_usd_salary_range(base_config, region_data):
    posting = _posting(salary_text="$140k-$165k", currency=None)
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.salary_min_eur == 128800
    assert result.salary_max_eur == 151800


def test_parses_gbp_salary_range(base_config, region_data):
    posting = _posting(salary_text="£90k–£110k", currency=None)
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.salary_min_eur == 105300
    assert result.salary_max_eur == 128700


def test_parses_numeric_range_with_code(base_config, region_data):
    posting = _posting(salary_text="90000-110000 EUR", currency=None)
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.salary_min_eur == 90000
    assert result.salary_max_eur == 110000


def test_salary_below_minimum_rejected(base_config, region_data):
    posting = _posting(salary_text="€40k-€45k", currency=None)
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "salary_below_minimum" in result.hard_reject_reasons


def test_missing_salary_strict_rejected(base_config, region_data):
    posting = _posting(salary_text=None, currency=None)
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=True,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "missing_salary_strict" in result.hard_reject_reasons
    assert "salary" in result.missing_fields


def test_missing_salary_allowed_with_tag(base_config, region_data):
    posting = _posting(salary_text=None, currency=None)
    updated, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.matches_all is True
    assert result.decision == "accepted"
    assert result.missing_salary is True
    assert "missing_salary" in result.penalties
    assert "salary" in result.missing_fields
    assert "missing_salary" in updated.tags
    assert "missing_salary" not in posting.tags


def test_missing_salary_disallowed(base_config, region_data):
    posting = _posting(salary_text=None, currency=None)
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=False,
    )
    assert result.decision == "rejected"
    assert "missing_salary_disallowed" in result.hard_reject_reasons


def test_prefer_full_remote_penalty_allows_match(
    base_config, region_data
):
    posting = _posting(remote_type="hybrid")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert result.matches_all is True
    assert "prefer_full_remote" in result.penalties
    assert not result.hard_reject_reasons


def test_remote_level_full_remote():
    assert normalize_remote_level("Remote") == "full-remote"


def test_remote_level_hybrid():
    assert normalize_remote_level("Hybrid") == "hybrid"


def test_remote_level_onsite():
    assert normalize_remote_level("On-site") == "onsite"


def test_remote_level_unknown():
    assert normalize_remote_level("") == "unknown"
