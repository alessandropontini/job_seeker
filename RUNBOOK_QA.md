# QA Runbook — Offline & Online Validation

This runbook provides deterministic offline validation and an explicit opt-in path for online integration testing.

## A) OFFLINE (default)
Use this path for reproducible, deterministic QA checks without network access.

```bash
python -m venv .venv
source .venv/bin/activate
export JOB_SCOUT_WHEELHOUSE_URL=path-or-url-to-wheelhouse-py311.zip
bash tools/run_tests_offline.sh
```

### Offline installation (air-gapped)
If PyPI is blocked or pip has no cache, use the wheelhouse fallback and keep
`JOB_SCOUT_WHEELHOUSE_URL` set for all QA runs.

```bash
python -m venv .venv
source .venv/bin/activate
export JOB_SCOUT_WHEELHOUSE_URL=path-or-url-to-wheelhouse-py311.zip
bash tools/install_dev_deps.sh
python -m pytest -q
```

**Wheelhouse source**
Use the workflow artifact from `.github/workflows/build-wheelhouse.yml` or a locally
provided `wheelhouse-py311.zip`. Pass a direct URL, `file://` URL, or local path.

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
export JOB_SCOUT_WHEELHOUSE_URL=path-or-url-to-wheelhouse-py311.zip
bash tools/run_tests_integration.sh
```

**Expected outcomes (integration tests)**
- **HTTP 200:** integration tests pass and validate minimal schema/fields.
- **HTTP 429 (rate limit):** integration tests are skipped with a clear reason (rate limited).
- **HTTP 403 (forbidden/blocked):** integration tests fail with a diagnostic message including
  the status code and a response snippet, because access is denied and live validation
  cannot be performed.

These outcomes are environment-dependent. A 429 or 403 is not a project-logic bug, but
tests must report them deterministically (skip vs fail) and must never crash.

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
