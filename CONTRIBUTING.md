# Contributing to Job Scout

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Testing Matrix
- **Offline (default, deterministic):** always runnable with network disabled.
- **Online integration (opt-in):** validates live external APIs; requires explicit enablement.

## Run Tests
Offline tests (default, deterministic):
```bash
NO_NETWORK=1 pytest -q
```

Run optional integration tests (network required, opt-in):
```bash
JOB_SCOUT_RUN_INTEGRATION=1 pytest -q -m integration
```

## Run the Pipeline
Dummy source:
```bash
python -m job_scout run --source dummy
```

Remotive source:
```bash
python -m job_scout run --source remotive --since-days 7
```

## Adding a New Source
1. Create a new module in `job_scout/sources/` (e.g., `acme.py`).
2. Implement `fetch_acme(since_days: int) -> list[SourceJob]`.
3. Populate required fields for the normalization contract (see `job_scout/normalize.py`).
4. Register it in `job_scout/sources/__init__.py` under `AVAILABLE_SOURCES`.
5. Add fixtures and tests to `tests/` for payload parsing.

## Determinism & Truthfulness Rules
- No hidden network calls in tests; use fixtures for external payloads.
- Sort outputs explicitly when ordering matters.
- Avoid non-deterministic data in tests (timestamps should be fixed or mocked).
- Never claim a feature exists unless backed by code/tests.

## Fixtures & Golden Files
- Store source fixtures in `tests/fixtures/`.
- Golden outputs live in `tests/golden/` and are compared in offline tests.
- Regenerate goldens intentionally with:
  ```bash
  python tools/update_goldens.py
  ```

## Integration Tests
- Mark live-network tests with `@pytest.mark.integration`.
- Gate them behind `JOB_SCOUT_RUN_INTEGRATION=1` so offline runs stay deterministic.
- Use `NO_NETWORK=1` for extra safety when validating offline determinism.

## Coding Standards
- Prefer small, typed functions and clear return values.
- Keep error handling explicit and readable.
- Avoid mixing IO with decision logic when possible.
