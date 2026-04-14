from copy import deepcopy
from datetime import datetime, timezone

import pytest

from job_scout.config import DEFAULT_CONFIG
from job_scout.matcher import match_posting
from job_scout.models import JobPosting
from job_scout.normalize import normalize_remote_level
from job_scout.regions import load_region_data
from job_scout.targeting import passes_core_gate


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
        description_snippet="Lead data governance, metadata, and data quality initiatives.",
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




def test_accepts_worldwide_when_full_remote(base_config, region_data):
    posting = _posting(location_text="Worldwide", location_country="Worldwide")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert "location_not_allowed" not in result.hard_reject_reasons


def test_accepts_europe_when_full_remote(base_config, region_data):
    posting = _posting(location_text="Europe", location_country="")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert "location_not_allowed" not in result.hard_reject_reasons


def test_accepts_eu_when_full_remote(base_config, region_data):
    posting = _posting(location_text="Remote - EU only", location_country="")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert "location_not_allowed" not in result.hard_reject_reasons


def test_rejects_uk_when_full_remote(base_config, region_data):
    posting = _posting(
        location_text="Remote - United Kingdom", location_country="United Kingdom"
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert "excluded_country" in result.hard_reject_reasons
    assert "excluded_country_text" in result.hard_reject_reasons


def test_rejects_usa_only_when_full_remote(base_config, region_data):
    posting = _posting(location_text="Remote - USA only", location_country="USA")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert "location_not_allowed" in result.hard_reject_reasons


def test_rejects_emea_when_full_remote(base_config, region_data):
    posting = _posting(location_text="Remote - EMEA", location_country="")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "location_not_allowed" in result.hard_reject_reasons

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
    assert result.location_fit == "allowed_eu_country"


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


def test_accepts_unknown_location_when_not_strict(
    base_config, region_data
):
    posting = _posting(location_text="", location_country="")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert result.matches_all is True
    assert "unknown_location" in result.penalties


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


def test_manual_soft_penalty_for_location_and_title(base_config, region_data):
    base_config["runtime"]["run_mode"] = "manual"
    posting = _posting(
        title="Senior Engineer",
        location_text="Toronto, Canada",
        location_country="Canada",
        description_snippet="Platform engineering leadership",
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "cv_alignment_missing" in result.hard_reject_reasons
    assert result.role_fit == "not_targeted"
    assert result.domain_fit == "not_targeted"
    assert result.location_fit == "not_targeted"


def test_accepts_manager_title_with_core_signal(base_config, region_data):
    posting = _posting(
        title="Product Manager",
        description_snippet="Own data governance roadmap and metadata standards",
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"


def test_accepts_architecture_role_with_enterprise_system_signal(base_config, region_data):
    posting = _posting(
        title="Workday Solutions Architect",
        location_text="Milan, Italy",
        location_country="Italy",
        description_snippet=(
            "Evolve the enterprise information system and application landscape, "
            "implementing Workday integrations and business systems architecture."
        ),
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert result.domain_fit == "targeted"


def test_accepts_head_of_application_services_with_internal_it_signal(base_config, region_data):
    posting = _posting(
        title="Head of Application Services",
        location_text="Berlin, Germany",
        location_country="Germany",
        description_snippet=(
            "Lead a complex IT landscape across enterprise applications, "
            "corporate IT and application services."
        ),
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert result.domain_fit == "targeted"


def test_rejects_client_facing_services_architect(base_config, region_data):
    posting = _posting(
        title="Services Architect 3 - New York",
        location_text="New York, NY",
        location_country="US",
        description_snippet=(
            "Implementation Services team helping customers deploy the platform, "
            "leading discovery, design and launch for customer-facing engagements."
        ),
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "client_facing_architect" in result.hard_reject_reasons
    assert "title_not_targeted" not in result.hard_reject_reasons
    assert result.role_fit == "targeted"
    assert result.domain_fit == "not_targeted"


def test_rejects_product_solutions_architect_with_field_engagement_signal(
    base_config, region_data
):
    posting = _posting(
        title="Product Solutions Architect - Product Analytics and Experimentation",
        location_text="New York, NY",
        location_country="US",
        description_snippet=(
            "The Product Solutions Architecture team partners with Field teams on "
            "complex customer use cases across pre- and post-sales engagements."
        ),
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "client_facing_architect" in result.hard_reject_reasons
    assert "solutions architect" in result.role_matches


def test_profession_query_rejects_non_matching_role(base_config, region_data):
    base_config["runtime"]["profession_query"] = "IT Solution Architect"
    posting = _posting(
        title="Head of Data Governance",
        description_snippet="Own metadata, lineage and data quality strategy.",
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "profession_not_targeted" in result.hard_reject_reasons


def test_profession_query_accepts_matching_architect_role(base_config, region_data):
    base_config["runtime"]["profession_query"] = "IT Solution Architect"
    posting = _posting(
        title="Workday Solutions Architect",
        location_text="Paris, France",
        location_country="France",
        description_snippet=(
            "Own enterprise systems, application architecture and Workday "
            "integrations across corporate IT."
        ),
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert "profession_not_targeted" not in result.hard_reject_reasons


def test_location_rules_allow_anywhere_when_scope_is_world(base_config, region_data):
    base_config["location_rules"]["include_regions"] = []
    base_config["location_rules"]["include_countries"] = []
    base_config["location_rules"]["include_cities"] = []
    posting = _posting(
        title="Head of Data Governance",
        location_text="Toronto, Canada",
        location_country="Canada",
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert result.location_fit == "allowed_anywhere"


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
    posting = _posting(
        title="Head of Engineering",
        description_snippet="Lead data platform and data quality modernization",
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert result.matches_all is True


def test_accepts_solution_architect_with_data_signal(base_config, region_data):
    posting = _posting(
        title="IT Solution Architect",
        description_snippet=(
            "Define data governance, metadata management, BigQuery and Dataflow "
            "architecture across cloud platforms."
        ),
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert result.role_fit == "targeted"
    assert result.domain_fit == "targeted"


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


def test_rejects_generic_product_owner_without_data_architecture_signal(
    base_config, region_data
):
    posting = _posting(
        title="Product Owner",
        description_snippet="Own the product backlog for customer growth tools.",
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "title_not_targeted" in result.hard_reject_reasons


def test_does_not_match_lead_inside_leadership_word(base_config, region_data):
    posting = _posting(
        title="Data Leadership Coach",
        description_snippet="Data governance mentoring and metadata coaching.",
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "title_not_targeted" in result.hard_reject_reasons


def test_matches_head_as_role_phrase(base_config, region_data):
    posting = _posting(
        title="Head of Data Governance",
        description_snippet="Own metadata, data quality, and compliance standards.",
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert "title_not_targeted" not in result.hard_reject_reasons


def test_accepts_pluralized_domain_phrase(base_config, region_data):
    posting = _posting(
        title="Engineering Manager",
        description_snippet="Lead a team delivering patient data platforms.",
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert "cv_domain_not_targeted" not in result.hard_reject_reasons
    assert "data platform" in result.domain_matches


def test_rejects_data_governance_specialist_title_without_management_seniority(
    base_config, region_data
):
    posting = _posting(title="Data Governance Specialist")
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert "title_not_targeted" in result.hard_reject_reasons
    assert result.decision == "rejected"


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


def test_missing_salary_strict_allowed(base_config, region_data):
    posting = _posting(salary_text=None, currency=None)
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=True,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert result.missing_salary is True
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
    assert result.decision == "accepted"
    assert result.missing_salary is True
    assert "missing_salary" not in result.penalties


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


def test_rejects_marketing_brand_titles_with_hard_block(base_config, region_data):
    posting = _posting(
        title="Senior Amazon Brand Manager",
        description_snippet="Remote brand strategy",
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "negative_domain" in result.hard_reject_reasons


def test_missing_salary_does_not_reject(base_config, region_data):
    base_config["runtime"]["run_mode"] = "manual"
    posting = _posting(salary_text=None, currency=None)
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "accepted"
    assert result.missing_salary is True


def test_salary_below_minimum_manual_penalty_scheduled_reject(base_config, region_data):
    posting = _posting(salary_text="€40k-€45k", currency=None)
    _, scheduled = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert scheduled.decision == "rejected"
    assert "salary_below_minimum" in scheduled.hard_reject_reasons

    base_config["runtime"]["run_mode"] = "manual"
    _, manual = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert manual.decision == "accepted"
    assert "salary_below_minimum" in manual.penalties


def test_non_core_keyword_role_fails_channel_gate(base_config, region_data):
    posting = _posting(
        title="Engineering Manager",
        description_snippet="Platform engineering leadership",
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "cv_domain_not_targeted" in result.hard_reject_reasons
    assert passes_core_gate(posting) is False


def test_manual_rejects_postings_with_no_role_and_no_data_alignment(base_config, region_data):
    base_config["runtime"]["run_mode"] = "manual"
    posting = _posting(
        title="Finance and Compliance Officer",
        description_snippet="Compliance controls for finance processes.",
    )
    _, result = match_posting(
        posting,
        base_config,
        region_data,
        strict=False,
        allow_missing_salary=True,
    )
    assert result.decision == "rejected"
    assert "cv_alignment_missing" in result.hard_reject_reasons
