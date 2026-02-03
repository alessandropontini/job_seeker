# Job Scout

Offline-first job scouting pipeline with configurable matching rules and reporting.

## Project status
- **Done:** Sprint 1 — Minimal runnable pipeline; Sprint 2 — Real sources + matching rules.
- **Done:** Phase 1 — Rule Definition & Enforcement.
- **Done:** Phase 2 — Decision Transparency & Explainability.
- **Done:** Phase 3 — Hard vs Soft Rules Separation.
- **Done:** Phase 4 — Scoring & Ranking.
- **Done:** Phase 5 — Reliability & Extensibility (QA & hardening complete).
- **In validation:** Phase 6 — Automation & Notifications (manual trigger only).

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
- `location_rules.allow_unknown_location`: keep jobs with unknown location (adds a penalty).
- `role_targeting.include_titles`: manager/lead/head keywords to match.
- `salary_rules.minimum_eur`: minimum salary threshold (converted to EUR).
- `salary_rules.allow_missing_salary`: keep jobs missing salary (tagged as `missing_salary`).
- `salary_rules.currency_rates`: approximate rates used for conversion (EUR=1.0, USD=0.92, GBP=1.17).
- `scoring.base_score`: starting score for accepted postings.
- `scoring.penalty_weights`: per-penalty score deductions (e.g., `prefer_full_remote`).
- `scoring.bonus_weights`: per-bonus score additions (e.g., `full_remote`).
- `scoring.data_governance_boost`: bonus score for data governance keyword matches.
- `scoring.data_governance_keywords`: primary keyword list for data governance boosts.
- `scoring.data_governance_secondary_boost`: smaller bonus for secondary keywords.
- `scoring.data_governance_secondary_keywords`: secondary keyword list (cloud platform signals).
- `notifications.telegram.enabled`: enable Telegram notifications (default: true).
- `notifications.telegram.top_n`: number of items in the digest.
- `notifications.telegram.min_score`: minimum score required to notify.
- `notifications.telegram.min_score_improvement`: minimum score delta to notify.

## Usage
Run the pipeline (defaults to configured sources or `dummy`):
```bash
python -m job_scout run
python -m job_scout run --since-days 7
```

Run in strict mode (reject missing location data; salary gaps are still allowed):
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
- Confirmed deterministic pipeline behavior with offline execution support.
- Introduced a source normalization contract and centralized salary/remote normalization.
- Externalized region/country mappings into `config/regions.json`.
- Added source failure reporting in `out/report.md` under **Source Status**.
- Documented external dependency failure handling (HTTP 403/429, NO_NETWORK) as
  environment limitations rather than project defects.

## Phase 6 — Automation & Notifications (in validation)
- Manual-only GitHub Actions runs (no push/PR/schedule triggers).
- The **only** active workflow is `job-scout` and it must be triggered manually
  via **Actions → job-scout → Run workflow**.
- CI tests and build workflows are intentionally removed/disabled in Phase 6.
- Lightweight state snapshot + diff to detect new/improved matches.
- Digest notifications (Telegram always enabled by default) and deterministic.
- Daily digest fallback when there are no new/improved matches.
- Snapshot updates tolerate missing/malformed notification rows; warnings are
  logged and the run continues without crashing.
- **Phase 6 includes automatic Telegram notifications by default.** If secrets are
  missing, the run completes with a warning and no notification.

## Matching rules overview
- **Location:** allow EU countries, Italy, or city match (default: New York). Explicitly reject UK.
- **Role:** only manager/lead/head titles are accepted.
- **Salary:** minimum 52,000 EUR; missing salary is flagged and kept in results.
- **Remote:** remote level is normalized and reported; non-remote roles are not rejected by default.
  `prefer_full_remote` is treated as a soft preference and records a penalty when not met.
- **Unknown location:** accepted in non-strict runs with an `unknown_location` penalty.

## Scoring & ranking
- Scores apply only to **accepted** postings.
- Score = `scoring.base_score` + bonuses − penalties (all weights configured in `scoring`).
- Data governance keyword matches add a configurable boost, recorded in score bonuses.
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
- `out/last_run.json` stores the last run snapshot (job IDs + scores) for diff-based
  notifications and is updated even when some notification rows are malformed.
When running in GitHub Actions, these files are uploaded as workflow artifacts:
`report.csv`, `report.md`, and `last_run.json`.

## Source connectors
- `dummy`: offline test data.
- `remotive`: public Remotive API (no authentication). This connector **does not** scrape
  behind logins or paywalls.

## Notes
- Prefer full-remote roles when available, but do not exclude non-remote roles by default.
- Missing salaries are tagged with `missing_salary` when `allow_missing_salary` is enabled.
- Scores are deterministic and derived from configured preference weights.
- External dependency failures (HTTP 403/429, NO_NETWORK) are treated as environment
  limitations during QA validation, not project defects.

## Telegram notifications (Phase 6)
- Telegram is always enabled by default (`notifications.telegram.enabled: true`).
- Configure GitHub Actions secrets: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
- If secrets are missing or invalid, the run completes with a warning and skips
  the notification (no secrets are printed).
- Each run sends exactly one digest message:
  - **New/Improved** when there are new/improved matches.
  - **Top matches today** (daily digest) when there are no deltas.
- If the notification payload contains missing fields, snapshot updates fall back
  safely with warnings and the run completes.
- Diagnostics are safe: logs show `getMe` validation results and
  `sendMessage` failures with Telegram's status/description, plus
  boolean `token_present`/`chat_id_present` indicators only.

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
Provide the wheelhouse zip manually when CI/build workflows are disabled.

#### PyPI blocked / wheelhouse fallback (copy/paste)
```bash
python -m venv .venv
source .venv/bin/activate
export JOB_SCOUT_WHEELHOUSE_URL=</path/or/url/to/wheelhouse-py311.zip>
bash tools/install_dev_deps.sh
NO_NETWORK=1 python -m pytest -q
NO_NETWORK=1 python -m pytest -q
JOB_SCOUT_RUN_INTEGRATION=1 python -m pytest -q -m integration
```

Wheelhouse downloads are not automated in Phase 6; provide the archive via a
local path or URL.

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

## Notifications (Phase 6)
Telegram notifications are enabled by default. Configure in `config/config.yaml`:
- `notifications.telegram.enabled`: keep Telegram enabled (default: true).
- `notifications.telegram.top_n`: number of jobs to include in the digest.
- `notifications.telegram.min_score`: minimum score required to notify.
- `notifications.telegram.min_score_improvement`: minimum score delta to notify.

Telegram credentials must be set via environment variables (or GitHub Actions secrets):
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

If credentials are missing or invalid, notifications are skipped with a warning and the run continues.

### GitHub Actions secrets & manual trigger
Add repository secrets in GitHub:
1. **Settings → Secrets and variables → Actions → New repository secret**
2. Create `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`

To run manually: go to **Actions → job-scout** → **Run workflow** and set inputs
(`since_days`, `sources`, `strict`, `allow_missing_salary`). You can also trigger via
`gh workflow run job_scout.yml` (no secrets shown in CLI output).
