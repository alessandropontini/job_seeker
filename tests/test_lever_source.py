import json
from datetime import timezone

from job_scout.sources.lever import parse_lever_payload


def test_parse_lever_payload_fixture():
    with open("tests/fixtures/lever_sample.json", encoding="utf-8") as handle:
        payload = json.load(handle)

    postings = parse_lever_payload(payload["fixtureco"], since_days=4000, company="fixtureco")

    assert len(postings) == 1
    first = postings[0]
    assert first.source == "lever"
    assert first.company == "Fixtureco"
    assert first.title == "Data Platform Lead"
    assert first.location_text == "Berlin, Germany"
    assert first.location_country == "Germany"
    assert first.remote_type == "full-remote"
    assert first.currency == "EUR"
    assert first.posted_at.tzinfo == timezone.utc
    assert first.url.startswith("https://jobs.lever.co/fixtureco/")
