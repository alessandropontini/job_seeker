# Job Scout

Offline-first job scouting pipeline with configurable matching rules and reporting.

## Requirements
- Python 3.11
- Dependencies in `requirements.txt`

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration
Edit `config/config.yaml` to adjust defaults. Missing fields fall back to defaults in `job_scout/config.py`.

Key sections:
- `sources.enabled`: list of source names to run (`dummy`, `remotive`).
- `location_rules`: include EU/Italy/New York only; `exclude_countries` must include `UK`.
- `role_targeting.include_titles`: manager/lead/head keywords to match.
- `salary_rules.minimum_eur`: minimum salary threshold (converted to EUR).
- `salary_rules.allow_missing_salary`: keep jobs missing salary (tagged as `missing_salary`).
- `salary_rules.currency_rates`: approximate rates used for conversion (EUR=1.0, USD=0.92, GBP=1.17).

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

## Matching rules overview
- **Location:** allow EU countries, Italy, or city match (default: New York). Explicitly reject UK.
- **Role:** only manager/lead/head titles are accepted.
- **Salary:** minimum 52,000 EUR; missing salary is flagged unless strict mode rejects it.
- **Remote:** remote level is normalized and reported; non-remote roles are not rejected by default.

## Outputs
The pipeline writes reports to `out/`:
- `out/report.csv` includes matcher fields:
  - `matches_all`, `reject_reasons`, `missing_salary`, `remote_level`,
    `salary_min_eur`, `salary_max_eur`.
- `out/report.md` has sections:
  - `## Matches`
  - `## Missing Salary (allowed)`
  - `## Rejected`

## Source connectors
- `dummy`: offline test data.
- `remotive`: public Remotive API (no authentication). This connector **does not** scrape
  behind logins or paywalls.

## Notes
- Prefer full-remote roles when available, but do not exclude non-remote roles by default.
- Missing salaries are tagged with `missing_salary` unless strict mode is enabled.
