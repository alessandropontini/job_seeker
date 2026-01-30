"""Dummy source returning fake job postings for offline testing."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from job_scout.normalize import SourceJob


def fetch_dummy(since_days: int) -> list[SourceJob]:
    """Return a list of fake but realistic job postings."""

    fixture_jobs = _load_fixture_jobs()
    if fixture_jobs is not None:
        return _filter_since_days(fixture_jobs, since_days)

    now = datetime.now(timezone.utc)
    postings = [
        SourceJob(
            id="dummy-ny-001",
            source="dummy",
            company="Atlas Health",
            title="Engineering Manager",
            location_text="New York, NY",
            location_country="US",
            location_city="New York",
            remote_type="hybrid",
            url="https://example.com/jobs/atlas-health-eng-manager",
            posted_at=now - timedelta(days=1, hours=3),
            salary_text="$140k-$165k",
            currency="USD",
            tags=["health-tech"],
            description_snippet="Lead a team delivering patient data platforms.",
        ),
        SourceJob(
            id="dummy-it-002",
            source="dummy",
            company="Luna Retail",
            title="Product Lead",
            location_text="Milan, Italy",
            location_country="Italy",
            location_city="Milan",
            remote_type="full-remote",
            url="https://example.com/jobs/luna-retail-product-lead",
            posted_at=now - timedelta(days=2, hours=5),
            salary_text="€80k-€95k",
            currency="EUR",
            tags=["ecommerce"],
            description_snippet="Own the roadmap for EU retail experiences.",
        ),
        SourceJob(
            id="dummy-eu-003",
            source="dummy",
            company="Aurora Energy",
            title="Operations Lead",
            location_text="Berlin, Germany",
            location_country="Germany",
            location_city="Berlin",
            remote_type="full-remote",
            url="https://example.com/jobs/aurora-energy-ops-lead",
            posted_at=now - timedelta(days=3),
            salary_text="€70k-€85k",
            currency="EUR",
            tags=["energy"],
            description_snippet="Scale field operations across EU markets.",
        ),
        SourceJob(
            id="dummy-it-004",
            source="dummy",
            company="Vento Mobility",
            title="Customer Success Manager",
            location_text="Rome, Italy",
            location_country="Italy",
            location_city="Rome",
            remote_type="full-remote",
            url="https://example.com/jobs/vento-mobility-csm",
            posted_at=now - timedelta(days=4, hours=2),
            salary_text="€60k-€72k",
            currency="EUR",
            tags=["mobility"],
            description_snippet="Lead enterprise success programs for fleet clients.",
        ),
        SourceJob(
            id="dummy-eu-005",
            source="dummy",
            company="Polar Analytics",
            title="Data Engineering Lead",
            location_text="Amsterdam, Netherlands",
            location_country="Netherlands",
            location_city="Amsterdam",
            remote_type="full-remote",
            url="https://example.com/jobs/polar-analytics-data-lead",
            posted_at=now - timedelta(days=5, hours=4),
            salary_text=None,
            currency=None,
            tags=["analytics"],
            description_snippet="Guide the data platform team for EU clients.",
        ),
        SourceJob(
            id="dummy-eu-006",
            source="dummy",
            company="Sage Cloud",
            title="Platform Engineering Manager",
            location_text="Paris, France",
            location_country="France",
            location_city="Paris",
            remote_type="hybrid",
            url="https://example.com/jobs/sage-cloud-platform-manager",
            posted_at=now - timedelta(days=6, hours=6),
            salary_text="€90k-€110k",
            currency="EUR",
            tags=["cloud"],
            description_snippet="Lead the platform team modernizing infra tooling.",
        ),
        SourceJob(
            id="dummy-uk-007",
            source="dummy",
            company="Thames Fintech",
            title="Engineering Manager",
            location_text="London, UK",
            location_country="UK",
            location_city="London",
            remote_type="onsite",
            url="https://example.com/jobs/thames-fintech-manager",
            posted_at=now - timedelta(days=2, hours=1),
            salary_text="£90k-£110k",
            currency="GBP",
            tags=["fintech"],
            description_snippet="Own delivery for the payments platform team.",
        ),
    ]

    return _filter_since_days(postings, since_days, now=now)


def _filter_since_days(
    postings: list[SourceJob],
    since_days: int,
    now: datetime | None = None,
) -> list[SourceJob]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=since_days)
    return [posting for posting in postings if posting.posted_at >= cutoff]


def _load_fixture_jobs() -> list[SourceJob] | None:
    fixture_dir = os.getenv("JOB_SCOUT_FIXTURE_DIR")
    if not fixture_dir:
        return None
    fixture_path = Path(fixture_dir) / "dummy_jobs.json"
    if not fixture_path.exists():
        return None
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    jobs = payload if isinstance(payload, list) else payload.get("jobs", [])
    parsed_jobs: list[SourceJob] = []
    for entry in jobs:
        posted_at = datetime.fromisoformat(entry["posted_at"])
        parsed_jobs.append(
            SourceJob(
                id=entry["id"],
                source=entry["source"],
                company=entry["company"],
                title=entry["title"],
                location_text=entry["location_text"],
                location_country=entry.get("location_country"),
                location_city=entry.get("location_city"),
                remote_type=entry.get("remote_type"),
                url=entry["url"],
                posted_at=posted_at,
                salary_text=entry.get("salary_text"),
                currency=entry.get("currency"),
                tags=list(entry.get("tags", [])),
                description_snippet=entry.get("description_snippet", ""),
            )
        )
    return parsed_jobs
