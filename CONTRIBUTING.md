# Contributing to Job Scout

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run Tests
```bash
pytest
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
2. Implement `fetch_acme(since_days: int) -> list[JobPosting]`.
3. Register it in `job_scout/sources/__init__.py` under `AVAILABLE_SOURCES`.
4. Add fixtures and tests to `tests/` for payload parsing.

## Determinism & Truthfulness Rules
- No hidden network calls in tests; use fixtures for external payloads.
- Sort outputs explicitly when ordering matters.
- Avoid non-deterministic data in tests (timestamps should be fixed or mocked).
- Never claim a feature exists unless backed by code/tests.

## Coding Standards
- Prefer small, typed functions and clear return values.
- Keep error handling explicit and readable.
- Avoid mixing IO with decision logic when possible.
