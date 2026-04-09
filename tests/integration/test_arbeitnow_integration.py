import os

import pytest

from job_scout.sources.arbeitnow import ArbeitnowSourceError, fetch_arbeitnow


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("JOB_SCOUT_RUN_INTEGRATION"),
    reason="Set JOB_SCOUT_RUN_INTEGRATION=1 to enable live tests.",
)
def test_arbeitnow_live_fetch(monkeypatch):
    monkeypatch.delenv("JOB_SCOUT_FIXTURE_DIR", raising=False)
    try:
        jobs = fetch_arbeitnow(1)
    except ArbeitnowSourceError as exc:
        message = str(exc)
        if "HTTP error: 429" in message:
            pytest.skip("Arbeitnow rate limited (HTTP 429); rerun later.")
        pytest.fail(f"Arbeitnow integration fetch failed: {message}")
    assert isinstance(jobs, list)

