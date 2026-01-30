"""Dummy source returning fake job postings for offline testing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from job_scout.models import JobPosting


def fetch_dummy(since_days: int) -> list[JobPosting]:
    """Return a list of fake but realistic job postings."""

    now = datetime.now(timezone.utc)
    postings = [
        JobPosting(
            id="dummy-ny-001",
            source="dummy",
            company="Atlas Health",
            title="Engineering Manager",
            location_text="New York, NY",
            location_country="US",
            remote_type="hybrid",
            url="https://example.com/jobs/atlas-health-eng-manager",
            posted_at=now - timedelta(days=1, hours=3),
            salary_text="$140k-$165k",
            currency="USD",
            tags=["health-tech"],
            description_snippet="Lead a team delivering patient data platforms.",
        ),
        JobPosting(
            id="dummy-it-002",
            source="dummy",
            company="Luna Retail",
            title="Product Lead",
            location_text="Milan, Italy",
            location_country="Italy",
            remote_type="full-remote",
            url="https://example.com/jobs/luna-retail-product-lead",
            posted_at=now - timedelta(days=2, hours=5),
            salary_text="€80k-€95k",
            currency="EUR",
            tags=["ecommerce"],
            description_snippet="Own the roadmap for EU retail experiences.",
        ),
        JobPosting(
            id="dummy-eu-003",
            source="dummy",
            company="Aurora Energy",
            title="Operations Lead",
            location_text="Berlin, Germany",
            location_country="Germany",
            remote_type="full-remote",
            url="https://example.com/jobs/aurora-energy-ops-lead",
            posted_at=now - timedelta(days=3),
            salary_text="€70k-€85k",
            currency="EUR",
            tags=["energy"],
            description_snippet="Scale field operations across EU markets.",
        ),
        JobPosting(
            id="dummy-it-004",
            source="dummy",
            company="Vento Mobility",
            title="Customer Success Manager",
            location_text="Rome, Italy",
            location_country="Italy",
            remote_type="full-remote",
            url="https://example.com/jobs/vento-mobility-csm",
            posted_at=now - timedelta(days=4, hours=2),
            salary_text="€60k-€72k",
            currency="EUR",
            tags=["mobility"],
            description_snippet="Lead enterprise success programs for fleet clients.",
        ),
        JobPosting(
            id="dummy-eu-005",
            source="dummy",
            company="Polar Analytics",
            title="Data Engineering Lead",
            location_text="Amsterdam, Netherlands",
            location_country="Netherlands",
            remote_type="full-remote",
            url="https://example.com/jobs/polar-analytics-data-lead",
            posted_at=now - timedelta(days=5, hours=4),
            salary_text=None,
            currency=None,
            tags=["analytics"],
            description_snippet="Guide the data platform team for EU clients.",
        ),
        JobPosting(
            id="dummy-eu-006",
            source="dummy",
            company="Sage Cloud",
            title="Platform Engineering Manager",
            location_text="Paris, France",
            location_country="France",
            remote_type="hybrid",
            url="https://example.com/jobs/sage-cloud-platform-manager",
            posted_at=now - timedelta(days=6, hours=6),
            salary_text="€90k-€110k",
            currency="EUR",
            tags=["cloud"],
            description_snippet="Lead the platform team modernizing infra tooling.",
        ),
        JobPosting(
            id="dummy-uk-007",
            source="dummy",
            company="Thames Fintech",
            title="Engineering Manager",
            location_text="London, UK",
            location_country="UK",
            remote_type="onsite",
            url="https://example.com/jobs/thames-fintech-manager",
            posted_at=now - timedelta(days=2, hours=1),
            salary_text="£90k-£110k",
            currency="GBP",
            tags=["fintech"],
            description_snippet="Own delivery for the payments platform team.",
        ),
    ]

    cutoff = now - timedelta(days=since_days)
    return [posting for posting in postings if posting.posted_at >= cutoff]
