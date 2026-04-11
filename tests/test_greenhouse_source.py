import json
from datetime import timezone

from job_scout.sources.greenhouse import parse_greenhouse_payload


def test_parse_greenhouse_payload_fixture():
    with open("tests/fixtures/greenhouse_sample.json", encoding="utf-8") as handle:
        payload = json.load(handle)

    postings = parse_greenhouse_payload(payload["datadog"], since_days=4000, board="datadog")

    assert len(postings) == 1
    first = postings[0]
    assert first.source == "greenhouse"
    assert first.company == "Datadog"
    assert first.title == "Senior Data Governance Manager"
    assert first.location_text == "Paris, France"
    assert first.location_country == "France"
    assert first.remote_type == "onsite"
    assert first.posted_at.tzinfo == timezone.utc
    assert "Data Platform" in first.tags
    assert first.url.startswith("https://careers.datadoghq.com/")
