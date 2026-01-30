import os

import pytest

from job_scout.sources.remotive import fetch_remotive


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("JOB_SCOUT_RUN_INTEGRATION"),
    reason="Set JOB_SCOUT_RUN_INTEGRATION=1 to enable live tests.",
)
def test_remotive_live_fetch(monkeypatch):
    monkeypatch.delenv("JOB_SCOUT_FIXTURE_DIR", raising=False)
    jobs = fetch_remotive(1)
    assert isinstance(jobs, list)
