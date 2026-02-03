# QA Runbook — Offline & Online Validation

This runbook provides deterministic offline validation and an explicit opt-in path for online integration testing.

## A) OFFLINE (default)
Use this path for reproducible, deterministic QA checks without network access.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
export NO_NETWORK=1
pytest -q
pytest -q
```

## B) ONLINE (opt-in integration validation)
Use this path only when you explicitly want to validate real external sources.

**Notes**
- Requires network access.
- Integration tests are gated and skipped by default.

**Discover markers**
```bash
pytest --markers
```

**Enable integration tests**
```bash
export JOB_SCOUT_RUN_INTEGRATION=1
```

**Run integration tests**
```bash
pytest -q -m integration
```

**Anti-flake recommendations**
- Keep timeouts explicit in source calls.
- Handle HTTP errors or rate limits (e.g., 429) with clear, explicit test messaging.
- Do not treat temporary API downtime as a silent pass; surface the reason clearly in the test output.

**Troubleshooting (HTTP 403/429)**
Reproduce with curl (capture output in QA notes):
```bash
curl -i "https://remotive.com/api/remote-jobs?limit=1"
curl -i -H "User-Agent: job_scout_integration_test/1.0" -H "Accept: application/json" \
  "https://remotive.com/api/remote-jobs?limit=1"
```
See `QA_NOTES.md` for evidence captured during investigation.
