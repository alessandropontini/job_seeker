import json
from datetime import timezone

from job_scout.sources.ashby import parse_ashby_payload


def test_parse_ashby_payload_fixture():
    with open("tests/fixtures/ashby_sample.json", encoding="utf-8") as handle:
        payload = json.load(handle)

    postings = parse_ashby_payload(payload["Vanta"], since_days=4000, board="Vanta")

    assert len(postings) == 1
    first = postings[0]
    assert first.source == "ashby"
    assert first.company == "Vanta"
    assert first.title == "Senior Data Governance Architect"
    assert first.location_text == "Dublin, Ireland"
    assert first.location_country == "Ireland"
    assert first.remote_type == "full-remote"
    assert first.currency == "EUR"
    assert first.posted_at.tzinfo == timezone.utc
    assert "Data Platform" in first.tags
    assert first.url.startswith("https://jobs.ashbyhq.com/Vanta/")
