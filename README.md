# Job Scout

Offline-first job scouting pipeline with configurable matching rules and reporting.

## Project status
- **Done:** Sprint 1 — Minimal runnable pipeline; Sprint 2 — Real sources + matching rules.
- **Done:** Phase 1 — Rule Definition & Enforcement.
- **Done:** Phase 2 — Decision Transparency & Explainability.
- **Done:** Phase 3 — Hard vs Soft Rules Separation.
- **Done:** Phase 4 — Scoring & Ranking.
- **Done:** Phase 5 — Reliability & Extensibility.
- **Optional:** Phase 6 — Automation & Notifications.

Project docs:
- [ROADMAP.md](ROADMAP.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)

## Requirements
- Python 3.11
- Runtime dependencies in `requirements.txt`
- Test/dev dependencies in `requirements-dev.txt`

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install test/dev tooling:
```bash
pip install -r requirements-dev.txt
```

## Configuration
Edit `config/config.yaml` to adjust defaults. Missing fields fall back to defaults in `job_scout/config.py`.

Key sections:
- `sources.enabled`: list of source names to run (`dummy`, `remotive`).
- `regions_path`: path to region/country mapping data (default: `config/regions.json`).
- `location_rules`: include EU/Italy/New York only; `exclude_countries` must include `UK`.
- `role_targeting.include_titles`: manager/lead/head keywords to match.
- `salary_rules.minimum_eur`: minimum salary threshold (converted to EUR).
- `salary_rules.allow_missing_salary`: keep jobs missing salary (tagged as `missing_salary`).
- `salary_rules.currency_rates`: approximate rates used for conversion (EUR=1.0, USD=0.92, GBP=1.17).
- `scoring.base_score`: starting score for accepted postings.
- `scoring.penalty_weights`: per-penalty score deductions (e.g., `prefer_full_remote`).
- `scoring.bonus_weights`: per-bonus score additions (e.g., `full_remote`).

## Usage
Run the pipeline (defaults to configured sources or `dummy`):
```bash
python -m job_scout run
python -m job_scout run --since-days 7
```

Run in strict mode (reject missing salary or missing location data):
```bash
python -m job_scout run --strict
```

Allow missing salaries via CLI override:
```bash
python -m job_scout run --allow-missing-salary
```

Run specific sources (repeatable or comma-separated):
```bash
python -m job_scout run --source dummy
python -m job_scout run --source remotive --source dummy
python -m job_scout run --source remotive,dummy
```

Inspect sources:
```bash
python -m job_scout sources --list
python -m job_scout sources --test
python -m job_scout sources --test remotive --since-days 7
```

## Phase 5 — Reliability & Extensibility (overview)
- Added golden snapshot tests to validate deterministic CSV/Markdown outputs offline.
- Introduced a source normalization contract and centralized salary/remote normalization.
- Externalized region/country mappings into `config/regions.json`.
- Added source failure reporting in `out/report.md` under **Source Status**.

## Matching rules overview
- **Location:** allow EU countries, Italy, or city match (default: New York). Explicitly reject UK.
- **Role:** only manager/lead/head titles are accepted.
- **Salary:** minimum 52,000 EUR; missing salary is flagged unless strict mode rejects it.
- **Remote:** remote level is normalized and reported; non-remote roles are not rejected by default.
  `prefer_full_remote` is treated as a soft preference and records a penalty when not met.

## Scoring & ranking
- Scores apply only to **accepted** postings.
- Score = `scoring.base_score` + bonuses − penalties (all weights configured in `scoring`).
- Reports order accepted postings by score (desc), then by newest `posted_at`.

## Outputs
The pipeline writes reports to `out/`:
- `out/report.csv` includes matcher fields:
  - `matches_all`, `decision`, `hard_reject_reasons`, `penalties`,
    `missing_fields`, `reject_reasons`, `missing_salary`, `remote_level`,
    `salary_min_eur`, `salary_max_eur`, `score`, `score_penalties`,
    `score_bonuses`.
- `out/report.md` has sections:
  - `## Source Status`
  - `## Matches`
  - `## Missing Salary (allowed)`
  - `## Rejected`
  - Accepted postings include a score line and score adjustments.

## Source connectors
- `dummy`: offline test data.
- `remotive`: public Remotive API (no authentication). This connector **does not** scrape
  behind logins or paywalls.

## Notes
- Prefer full-remote roles when available, but do not exclude non-remote roles by default.
- Missing salaries are tagged with `missing_salary` unless strict mode is enabled.
- Scores are deterministic and derived from configured preference weights.

## Testing
Run offline tests (default, deterministic):
```bash
pytest -q
```

Run offline tests with network guardrails enabled:
```bash
NO_NETWORK=1 pytest -q
```

Run optional online integration tests (requires network access):
```bash
JOB_SCOUT_RUN_INTEGRATION=1 pytest -q -m integration
```

### Golden tests vs online integration tests
- Golden tests are offline and compare pipeline outputs against committed fixtures.
- Integration tests are opt-in, hit real APIs, and are skipped by default.

### Regenerating golden outputs
When intentional output changes are expected, regenerate goldens with fixtures:
```bash
python tools/update_goldens.py
```

### Environment variables & markers
- `NO_NETWORK=1`: disable HTTP calls during tests (raises controlled errors).
- `JOB_SCOUT_RUN_INTEGRATION=1`: opt-in to live API integration tests.
- `JOB_SCOUT_FIXTURE_DIR=tests/fixtures`: use fixture payloads instead of live APIs.
- Pytest marker: `integration` for live-network tests.
