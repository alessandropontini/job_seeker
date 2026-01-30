import json
from datetime import timezone

from job_scout.sources.remotive import parse_remotive_payload


def test_parse_remotive_payload_fixture():
    with open("tests/fixtures/remotive_sample.json", encoding="utf-8") as handle:
        payload = json.load(handle)

    postings = parse_remotive_payload(payload, since_days=4000)

    assert len(postings) == 2
    first = postings[0]
    assert first.source == "remotive"
    assert first.remote_type == "full-remote"
    assert first.location_country == "USA"
    assert first.currency == "USD"
    assert first.posted_at.tzinfo == timezone.utc
