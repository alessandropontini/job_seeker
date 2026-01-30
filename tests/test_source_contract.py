from datetime import timezone

from job_scout.normalize import normalize_source_job
from job_scout.regions import load_region_data
from job_scout.sources import AVAILABLE_SOURCES


def test_sources_meet_normalization_contract(monkeypatch):
    monkeypatch.setenv("JOB_SCOUT_FIXTURE_DIR", "tests/fixtures")
    region_data = load_region_data("config/regions.json")
    for name, fetcher in AVAILABLE_SOURCES.items():
        jobs = fetcher(4000)
        assert jobs, f"{name} returned no jobs"
        for job in jobs:
            normalized = normalize_source_job(job, region_data)
            assert normalized.id
            assert normalized.title
            assert normalized.company
            assert normalized.location_text
            assert normalized.posted_at.tzinfo == timezone.utc
            assert normalized.remote_level in {
                "full-remote",
                "hybrid",
                "onsite",
                "unknown",
            }
            assert normalized.location_country is not None
            assert normalized.location_city is not None
