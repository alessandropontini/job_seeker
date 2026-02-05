# Job Scout

Offline-first job scouting pipeline with configurable matching rules and reporting.

## Project status
- **Done:** Sprint 1 — Minimal runnable pipeline; Sprint 2 — Real sources + matching rules.
- **Done:** Phase 1 — Rule Definition & Enforcement.
- **Done:** Phase 2 — Decision Transparency & Explainability.
- **Done:** Phase 3 — Hard vs Soft Rules Separation.
- **Done:** Phase 4 — Scoring & Ranking.
- **Done:** Phase 5 — Reliability & Extensibility (QA & hardening complete).
- **Live:** Phase 6 — Refinement: dual-channel output, Telegram feedback, and anti-dup digest (08:00 Europe/Rome).

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
- `channels.top_matches`: strict channel settings (top N, minimum score, missing salary handling).
- `channels.data_only_best_picks`: wide channel settings plus data keyword lists.
- `personalization.enabled`: toggle preference learning (default: `false`).
- `personalization.profile_path`: preference profile location (default: `out/preferences.json`).
- `personalization.*_step`: per-feedback weight deltas for tokens, tags, remote level, seniority.
- `scoring.base_score`: starting score for accepted postings.
- `scoring.penalty_weights`: per-penalty score deductions (e.g., `prefer_full_remote`).
- `scoring.bonus_weights`: per-bonus score additions (e.g., `full_remote`).
- `scoring.data_governance_boost`: bonus score for data governance keyword matches.
- `scoring.data_governance_keywords`: primary keyword list for data governance boosts.
- `scoring.data_governance_secondary_boost`: smaller bonus for secondary keywords.
- `scoring.data_governance_secondary_keywords`: secondary keyword list (cloud platform signals).
- `notifications.telegram.enabled`: Telegram is always-on in production (defaults to true).
- `notifications.telegram.top_n`: fallback max items per digest.
- `notifications.telegram.min_score`: minimum score required to notify.
- `notifications.dedupe.enabled`: stateful daily digest de-duplication.
- `notifications.dedupe.state_path`: file name for digest dedupe state (default: `out/last_notified.json`).
- `digest.mode`: `daily_window` for the scheduled digest behavior.
- `digest.window_hours`: size of the daily window (24 hours).
- `digest.top_n`: number of items in the daily digest.

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

## Phase 6 — Automation & Notifications (live)
- GitHub Actions runs daily at **08:00 Europe/Rome** (CET/CEST schedule in UTC).
- Manual runs remain available via **Actions → job-scout → Run workflow**.
- CI tests and build workflows remain intentionally removed/disabled.
- Daily digest uses a 24-hour window (UTC) based on `posted_at` timestamps.
- Telegram notifications are always on and send exactly one message per run.
- Inline feedback buttons are attached to each digest item (👍/👎/⭐/🧻).
- Snapshot updates tolerate missing/malformed entries; warnings are logged and the
  run continues without crashing.
- If secrets are missing or invalid, the run completes with a warning and no notification.

## Matching rules overview
- **Location:** allow EU countries, Italy, or city match (default: New York). Explicitly reject UK.
- **Role:** only manager/lead/head titles are accepted.
- **Salary:** minimum 52,000 EUR; missing salary is flagged and kept in results.
- **Remote:** remote level is normalized and reported; non-remote roles are not rejected by default.
  `prefer_full_remote` is treated as a soft preference and records a penalty when not met.
- **Unknown location:** accepted in non-strict runs with an `unknown_location` penalty.

## Dual-channel output
- **TOP_MATCHES (strict):** the primary channel of accepted matches, ordered by score.
- **DATA_ONLY_BEST_PICKS (wide):** a secondary channel filtered by data keywords
  (title/snippet/tags), still respecting the manager/lead role constraints.

## Scoring & ranking
- Scores apply only to **accepted** postings.
- Score = `scoring.base_score` + bonuses − penalties (all weights configured in `scoring`).
- Data governance keyword matches add a configurable boost, recorded in score bonuses.
- Reports order accepted postings by score (desc), then by newest `posted_at`.

## Personalization (optional)
- Enable with `personalization.enabled: true` to apply lightweight preference learning.
- Telegram feedback buttons update a local profile file with token/tag/remote/seniority weights.
- Preference scores **only** adjust ranking; hard rejects remain enforced.
- The profile is stored at `out/preferences.json` by default and is safe to delete/reset.

## Outputs
The pipeline writes reports to `out/`:
- `out/report.csv` includes matcher fields:
  - `matches_all`, `decision`, `hard_reject_reasons`, `penalties`,
    `missing_fields`, `reject_reasons`, `missing_salary`, `remote_level`,
    `salary_min_eur`, `salary_max_eur`, `score`, `score_penalties`,
    `score_bonuses`.
- `out/report.md` has sections:
  - `## TOP_MATCHES (strict)`
  - `## DATA_ONLY_BEST_PICKS (wide)`
  - `## Source Status`
  - `## Matches`
  - `## Missing Salary (allowed)`
  - `## Rejected`
  - Accepted postings include a score line and score adjustments.
- `out/last_run.json` stores the latest digest payload **and** the notification snapshot
  (job IDs + scores + notification timestamps). The digest section mirrors the report
  content used for Telegram and includes summary counts plus a digest hash.
- `out/last_notified.json` stores the last daily digest hash for anti-dup notifications.
- `out/preferences.json` stores the preference profile and last feedback cache.
- `out/telegram_payload.json` stores the dry-run Telegram payload when
  `notifications.telegram.dry_run: true` is enabled (no network calls).
- `out/digest.md` stores the plain-text digest in dry-run mode.
When running in GitHub Actions, these files are uploaded as workflow artifacts:
`report.csv`, `report.md`, `last_run.json`, `last_notified.json`, `preferences.json`,
plus `telegram_payload.json`/`digest.md` for dummy dry-run workflows.

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

## Telegram notifications (Phase 6 live)
- Telegram is always enabled by default (`notifications.telegram.enabled: true`).
- Use `notifications.telegram.dry_run: true` to write the payload to disk without
  contacting Telegram (offline-safe dummy runs).
- Configure GitHub Actions secrets: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
- If secrets are missing or invalid, the run completes with a warning and skips
  the notification (no secrets are printed).
- Each run sends exactly one daily digest message using the last 24 hours
  (`digest.window_hours`) of `posted_at` timestamps in UTC. The daily window
  always includes the full digest; dedupe prevents re-sending identical digests
  on the same date.
- If there are no jobs in the 24h window, the message states:
  “No new job postings published in the last 24 hours.”
- Each digest item includes inline feedback buttons:
  👍 Interested, 👎 Not a fit, ⭐ Very interesting, 🧻 Duplicate/seen.
- Snapshot updates tolerate missing fields; warnings are logged and the run completes.
- Diagnostics are safe: logs show `getMe` validation results and
  `sendMessage` failures with Telegram's status/description, plus
  boolean `token_present`/`chat_id_present` indicators only.

## GitHub Actions workflows
- **Daily (08:00 Europe/Rome)**: `.github/workflows/daily_job_scout.yml`
  runs `remotive` and sends the real Telegram digest (secrets required).
- **Dummy E2E (manual-only)**: `.github/workflows/dummy_e2e.yml`
  runs the dummy source with `notifications.telegram.dry_run: true` to validate
  the full pipeline offline (no Telegram network calls).

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

### Dummy E2E dry-run (local)
Run the offline-safe dummy workflow locally without Telegram:
```bash
python -m job_scout run --config config/dummy_e2e.yaml --since-days 7 --source dummy --output-dir out
```
Inspect `out/telegram_payload.json`, `out/digest.md`, and `out/last_run.json` to validate
the digest payload and dedupe state.

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
Telegram notifications are always on by default. Configure in `config/config.yaml`:
- `notifications.telegram.enabled`: keep Telegram enabled (default: true).
- `notifications.telegram.dry_run`: write the payload to disk without sending to Telegram.
- `notifications.telegram.top_n`: fallback number of jobs to include in the digest.
- `notifications.telegram.min_score`: minimum score required to notify.
- `digest.mode`: `daily_window` for the daily scheduled digest.
- `digest.window_hours`: number of hours in the daily digest window (24).
- `digest.top_n`: number of jobs to include in the daily digest.

Telegram credentials must be set via environment variables (or GitHub Actions secrets):
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

If credentials are missing or invalid, notifications are skipped with a warning and the run continues.
Each run sends exactly one message; when there are no eligible jobs in the last 24 hours the message is:
“No new job postings published in the last 24 hours.”

### GitHub Actions secrets & manual trigger
Add repository secrets in GitHub:
1. **Settings → Secrets and variables → Actions → New repository secret**
2. Create `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`

The daily workflow runs at 08:00 Europe/Rome. To run manually: go to
**Actions → daily-job-scout** → **Run workflow** and set inputs
(`since_days`, `sources`, `strict`, `allow_missing_salary`). You can also trigger via
`gh workflow run daily_job_scout.yml` (no secrets shown in CLI output).

The dummy E2E workflow is manual-only:
**Actions → dummy-e2e** → **Run workflow** or
`gh workflow run dummy_e2e.yml`.
