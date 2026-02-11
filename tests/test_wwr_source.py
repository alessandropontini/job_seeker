from pathlib import Path

from job_scout.sources.wwr import parse_wwr_rss


def test_parse_wwr_rss_fixture():
    payload = Path("tests/fixtures/wwr_sample.xml").read_text(encoding="utf-8")
    postings = parse_wwr_rss(payload, since_days=4000)

    assert len(postings) == 2
    first = postings[0]
    assert first.source == "wwr"
    assert first.title == "Data Governance Specialist"
    assert first.company == "DataCo"
    assert first.location_text == "Europe"
    assert first.remote_type == "full-remote"
    assert first.salary_text == "€75k-€90k"
    assert first.url.startswith("https://weworkremotely.com/")
