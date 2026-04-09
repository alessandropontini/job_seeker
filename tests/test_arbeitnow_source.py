import json
from datetime import timezone

from job_scout.sources.arbeitnow import parse_arbeitnow_payload


def test_parse_arbeitnow_payload_fixture():
    with open("tests/fixtures/arbeitnow_sample.json", encoding="utf-8") as handle:
        payload = json.load(handle)

    postings = parse_arbeitnow_payload(payload, since_days=4000)

    assert len(postings) == 2
    first = postings[0]
    assert first.source == "arbeitnow"
    assert first.title == "Data Governance Manager"
    assert first.company == "DataCo"
    assert first.location_text == "Berlin"
    assert first.location_country == "Germany"
    assert first.remote_type == "full-remote"
    assert first.url.startswith("https://www.arbeitnow.com/jobs/")
    assert first.posted_at.tzinfo == timezone.utc

