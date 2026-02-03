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
- [RUNBOOK_QA.md](RUNBOOK_QA.md)

## Requirements
- Python 3.11
- Runtime dependencies: **stdlib-only**
- Test/dev dependencies in `requirements-dev.txt` (pytest only)

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
bash tools/install_dev_deps.sh
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
NO_NETWORK=1 pytest -q
```

Run optional online integration tests (required to validate real sources):
```bash
JOB_SCOUT_RUN_INTEGRATION=1 pytest -q -m integration
```

### Offline & online QA runner scripts
Offline deterministic QA (wheelhouse fallback supported):
```bash
export NO_NETWORK=1
export JOB_SCOUT_WHEELHOUSE_URL=path-or-url-to-wheelhouse-py311.zip
bash tools/run_tests_offline.sh
```

Online integration QA (wheelhouse fallback supported):
```bash
export JOB_SCOUT_RUN_INTEGRATION=1
export JOB_SCOUT_WHEELHOUSE_URL=path-or-url-to-wheelhouse-py311.zip
bash tools/run_tests_integration.sh
```

### Troubleshooting (PyPI blocked)
If PyPI is blocked or pip has no cache, provide a wheelhouse zip and rerun:
```bash
export JOB_SCOUT_WHEELHOUSE_URL=path-or-url-to-wheelhouse-py311.zip
bash tools/install_dev_deps.sh
```
The install script will try PyPI first, then fall back to the wheelhouse using
`--no-index --find-links` once the archive is downloaded or extracted.
Build the wheelhouse with `.github/workflows/build-wheelhouse.yml` and download
the `wheelhouse-py311.zip` artifact for reuse.

### Integration troubleshooting
If live integration returns HTTP 403 or 429, reproduce with curl:
```bash
curl -i "https://remotive.com/api/remote-jobs?limit=1"
curl -i -H "User-Agent: job_scout_integration_test/1.0" -H "Accept: application/json" \
  "https://remotive.com/api/remote-jobs?limit=1"
```
See `QA_NOTES.md` for captured evidence and notes.

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
