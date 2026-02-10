# Job Scout

Offline-first job scouting pipeline with configurable matching rules and reporting.

## Project status
- **Done:** Sprint 1 — Minimal runnable pipeline; Sprint 2 — Real sources + matching rules.
- **Done:** Phase 1 — Rule Definition & Enforcement.
- **Done:** Phase 2 — Decision Transparency & Explainability.
- **Done:** Phase 3 — Hard vs Soft Rules Separation.
- **Done:** Phase 4 — Scoring & Ranking.
- **Done:** Phase 5 — Reliability & Extensibility (QA & hardening complete).
- **Live:** Phase 6 — Refinement: dual-channel output, Telegram feedback, and anti-dup digest (manual trigger).
- **In progress:** Phase 7 — Interactive Telegram feedback via Cloudflare Worker (time-gated) and per-job UX.

Project docs:
- [ROADMAP.md](ROADMAP.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [RUNBOOK_QA.md](RUNBOOK_QA.md)
- [docs/CI_RUNBOOK.md](docs/CI_RUNBOOK.md)
- [docs/SECRETS.md](docs/SECRETS.md)

> CI note: cron-based notification workflows are disabled; operations run manual-only via `workflow_dispatch`. See [docs/CI_RUNBOOK.md](docs/CI_RUNBOOK.md).

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
- `notifications.telegram.send_per_job`: send one Telegram message per job (default: true).
- `notifications.telegram.send_header`: send a digest header message before jobs (default: true).
- `notifications.telegram.persist_payload`: persist the outgoing Telegram payload to disk.
- `notifications.telegram.send_mode`: `live` (default) for real Telegram sends, `fake` for E2E payload generation + feedback session bootstrap without Telegram API calls.
- `state.suffix`: suffix appended to state files (e.g., `last_run_dummy_e2e.json`).
- `state.dir`: optional base directory for state files (relative paths resolve under `out/`).
- `feedback.enabled`: enable the Cloudflare Worker feedback integration.
- `feedback.webhook_base_url`: Worker base URL (or set `JOB_SCOUT_WEBHOOK_BASE_URL` env var).
- `feedback.webhook_secret`: shared secret (or set `JOB_SCOUT_WEBHOOK_SECRET` env var).
- `feedback.window_minutes`: open feedback window duration (default: 60m).
- `feedback.use_telegram_updates`: optional legacy Telegram polling (default: false).
- `digest.mode`: `daily_window` for the scheduled digest behavior.
- `digest.window_hours`: size of the daily window (24 hours).
- `digest.top_n`: number of items in the daily digest.

## Usage
Run the pipeline (defaults to configured sources or `dummy`):
```bash
python -m job_scout run
python -m job_scout run --since-days 7
```

Run the pipeline with isolated state files:
```bash
python -m job_scout run --state-suffix dummy_e2e
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

Run with a deterministic dummy fixture file (useful for CI/E2E):
```bash
python -m job_scout run --config config/e2e_fake.yaml --source dummy --fixture-file tests/fixtures/e2e_fake_jobs.json --since-days 3650
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
- GitHub Actions notification workflows are **manual-only** (no cron-triggered sends).
- Run notifications on demand via **Actions → scheduled-remotive → Run workflow**.
- CI tests and build workflows remain intentionally removed/disabled.
- Daily digest uses a 24-hour window (UTC) based on `posted_at` timestamps.
- Telegram notifications are always on and send exactly one message per run.
- Inline feedback buttons are attached to each digest item (👍/👎/⭐/🧻).
- Snapshot updates tolerate missing/malformed entries; warnings are logged and the
  run continues without crashing.
- If secrets are missing or invalid, the run completes with a warning and no notification.

## Phase 7 — Interactive feedback (Cloudflare Worker)
- Each job is sent as its own Telegram message with a 4-button inline keyboard
  (Mi piace, Forse, Non mi piace, Non rilevante).
- A time-gated feedback window opens for 1 hour after the digest is sent.
- Telegram callbacks are handled by a free Cloudflare Worker + KV store.
- Feedback is applied on the next run to influence ranking and duplicate suppression (no hard rejects bypassed).
- Callback data uses compact IDs (`fb|<run>|<short_job>|<act>|<hash>`) to stay under the 64-byte limit.
  Actions are one of `L`, `M`, `D`, `S`, `X`, or their long forms (`like`, `maybe`, `dislike`,
  `love`, `duplicate`).
- GitHub Actions requests to the Worker are signed with HMAC SHA-256 (no secrets in logs).

Architecture (Phase 7 feedback flow):
```
job_scout run
  -> build digest + short ids + open/close window
  -> POST /window/open (Worker + KV, HMAC signed)
  -> send per-job Telegram messages (buttons)
  -> user taps button -> Worker /telegram/feedback
  -> Worker stores feedback in KV
  -> next run fetches POST /feedback (HMAC signed)
  -> preferences updated (ranking/duplicate suppression)
```
See `docs/PHASE_7_SECURE_FEEDBACK.md` and the diagram in
`docs/diagrams/phase7_feedback_flow.md` for the secure feedback flow.

## Telegram webhook management (Phase 1 & 2)
- `telegram_webhook_get` (workflow_dispatch) is read-only and prints the current webhook status.
- `telegram_webhook_set` (workflow_dispatch) sets the webhook to
  `${JOB_SCOUT_WEBHOOK_BASE_URL}/telegram/feedback` and then re-reads the webhook status.
- The Cloudflare Worker validates the `X-Telegram-Bot-Api-Secret-Token` header against
  `JOB_SCOUT_WEBHOOK_SECRET` for authenticated callback delivery.

Run the workflows from **GitHub Actions**:
1. Run `telegram_webhook_set`.
2. Run `telegram_webhook_get` and confirm the `url` ends with `/telegram/feedback`.
3. Click 👍 in a Telegram digest message and confirm Cloudflare logs show
   `POST /telegram/feedback`.

If `telegram_webhook_set` fails, the logs now include non-sensitive diagnostics to
help you pinpoint the issue:
- `http_code`: HTTP response code returned by the Telegram API.
- `response_bytes`: size of the raw response body.
- `raw_response`: the raw JSON (or text) response returned by Telegram.
- `ok`, `error_code`, `description`: parsed fields from the Telegram API response.
- `token_sha256_prefix`: a non-reversible hash prefix of the bot token (useful to
  confirm `telegram_webhook_set` and `telegram_webhook_get` are using the same secret).

**Troubleshooting checklist**
- **`http_code: 404`** → bot token is incorrect or points to a non-existent bot.
- **`http_code: 400`** → invalid request (often non-HTTPS URL or invalid `secret_token`).
- **`http_code: 401/403`** → invalid or unauthorized bot token.
- **`ERROR: empty response` + curl stderr** → network/egress blocked, DNS failure,
  or Telegram API unreachable.
- Ensure `JOB_SCOUT_WEBHOOK_BASE_URL` starts with `https://` and contains no spaces
  (Telegram requires HTTPS).

**Webhook troubleshooting (getWebhookInfo)**
- If `telegram_webhook_set` reports success but `getWebhookInfo.url` is empty, compare
  `token_sha256_prefix` from both workflows. A mismatch indicates a different secret
  or environment is in use.
- `raw_response` should be valid JSON. If it is empty or not JSON, inspect `curl_stderr`
  to identify network errors, DNS issues, or TLS failures.
- `http_code` and `raw_response` together indicate Telegram-side errors (e.g., 401/403
  invalid token) vs. transport problems (empty response + curl stderr).

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
  content used for Telegram and includes summary counts plus a digest hash. The digest
  schema is stable and includes:
  - `digest.jobs`: flattened list of jobs with `channel` values (`top_matches`,
    `data_only_best_picks`).
  - `digest.top_matches` / `digest.data_only_best_picks`: channel-specific lists.
  - `digest.scope`: `daily_window` (default) or `fallback_recent` when no jobs fall
    inside the 24h window.
  - `digest.run_id` and `digest.feedback_open_at` / `digest.feedback_close_at` for
    time-gated feedback collection.
  - `digest.jobs[].short_id` for compact feedback button identifiers.
  - Top-level aliases: `counts` (run summary) and `digest_hash`.
- `out/last_notified.json` stores the last daily digest hash for anti-dup notifications.
- `out/preferences.json` stores the preference profile and last feedback cache.
- When `state.suffix` (or `--state-suffix`) is used, these state files are suffixed
  (for example `out/last_run_dummy_e2e.json`).
- `out/telegram_payload.json` stores the dry-run Telegram payload when
  `notifications.telegram.dry_run: true` is enabled (no network calls).
- `out/digest.md` stores the plain-text digest in dry-run mode.
- `out/feedback_summary.json` stores feedback action counts when feedback is applied.
- `out/last_run.json` also includes `feedback_counts` when feedback is applied.
When running in GitHub Actions, these files are uploaded as workflow artifacts:
`report.csv`, `report.md`, `last_run.json`, `last_notified.json`, `preferences.json`,
plus `telegram_payload.json`/`digest.md` when dry-run mode is enabled.

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
- Each run sends a header message (optional) and one message per job using the last
  24 hours (`digest.window_hours`) of `posted_at` timestamps in UTC. The daily window
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
- **Remotive (manual-only)**: `.github/workflows/scheduled_remotive.yml`
  runs `remotive` and sends the real Telegram digest on explicit operator trigger (secrets required).
- **Dummy E2E (manual-only)**: `.github/workflows/dummy_e2e.yml`
  runs the dummy source and sends a real Telegram digest to validate the full
  pipeline end-to-end. State files are isolated with the `dummy_e2e` suffix and
  the workflow executes twice to confirm dedupe without impacting production.

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

### Dummy E2E (local, real Telegram)
Run the dummy E2E configuration locally with real Telegram delivery:
```bash
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
export JOB_SCOUT_WEBHOOK_BASE_URL=...
export JOB_SCOUT_WEBHOOK_SECRET=...
python -m job_scout run --config config/dummy_e2e.yaml --since-days 7 --source dummy --state-suffix dummy_e2e --output-dir out
```
Inspect `out/last_run_dummy_e2e.json` and `out/last_notified_dummy_e2e.json` to validate
the digest payload and dedupe state. To perform an offline dry run, set
`notifications.telegram.dry_run: true` in `config/dummy_e2e.yaml`.

### Cloudflare Worker setup (Phase 7)
Deploy the Worker in `cloudflare/worker/` and set repository secrets:
- `JOB_SCOUT_WEBHOOK_BASE_URL` (Worker URL)
- `JOB_SCOUT_WEBHOOK_SECRET` (shared secret for HMAC + Telegram webhook authentication)
- `TELEGRAM_WEBHOOK_SECRET` (optional override for Telegram `secret_token`; defaults to `JOB_SCOUT_WEBHOOK_SECRET`)
- `TELEGRAM_BOT_TOKEN` (Telegram bot for feedback callbacks)
- `ALLOWED_TELEGRAM_USER_ID` (numeric Telegram user ID allowed to record feedback)
- `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_KV_NAMESPACE_ID`
Worker deploys run via **Actions → deploy-feedback-worker**. See
`cloudflare/worker/README.md` for deployment details.
The deploy workflow intentionally runs in multiple steps (bootstrap deploy, secret
uploads, then a final deploy) to avoid the known wrangler-action issue where bulk
secret uploads fail before the Worker script exists. This makes the workflow
idempotent for both first-time and repeat deploys.
The workflow now tracks the latest Wrangler CLI release for more predictable Cloudflare deploys.
The Cloudflare Worker name is `job-scout-telegram-feedback` and should match the Telegram webhook route.

**Secure webhook enabled checklist**
- ✅ `JOB_SCOUT_WEBHOOK_SECRET` exists in GitHub Actions secrets and Cloudflare Worker secrets.
- ✅ Telegram webhook configured with `secret_token` matching `TELEGRAM_WEBHOOK_SECRET` or `JOB_SCOUT_WEBHOOK_SECRET`.
- ✅ `POST /telegram/feedback` rejects missing/invalid `X-Telegram-Bot-Api-Secret-Token`.

**Configure Telegram webhook**
Run the helper script to configure + verify the Telegram webhook without logging secrets:
```bash
export TELEGRAM_BOT_TOKEN=...
export JOB_SCOUT_WEBHOOK_SECRET=...
export JOB_SCOUT_WEBHOOK_BASE_URL=https://<your-worker-domain>
tools/telegram_set_webhook.sh
```
The script sets the webhook to `POST /telegram/feedback` and prints non-sensitive fields from
`getWebhookInfo` so you can confirm the URL.

**Debug: Telegram webhook status (Phase 1)**
Use the manual GitHub Actions workflow to read the current Telegram webhook configuration
without exposing secrets. Run **Actions → telegram_webhook_get → Run workflow**.

The logs print only non-sensitive fields (`url`, `pending_update_count`, optional error/IP/cert flags).
In a correct setup, `url` should be `https://<worker-domain>/telegram/feedback`. If `url` is empty
or different, Telegram is not sending callbacks to the Worker and button clicks will not reach
`/telegram/feedback`.

Security note: the workflow reads `TELEGRAM_BOT_TOKEN` from GitHub Secrets and never prints it.

**Manual feedback verification**
1. Run the dummy E2E pipeline (see above) to send a Telegram digest with inline feedback buttons.
2. Tap 👍/👎/⭐/🧻 and confirm the spinner disappears immediately with a “Feedback salvato” toast.
3. In Cloudflare KV, verify a key like `feedback:<run_id>:<short_id>:<user_id>` was created/updated.

**Worker logs (Observability)**
1. Open **Workers & Pages → job-scout-telegram-feedback → Observability → Events/Logs**.
2. Logs appear only when the Worker emits `console.log`/`console.error` output.
3. Filter by `event` (example: `telegram_webhook_rejected`, `kv_write_failed`) to inspect callback flow.

Optional local tail (no secrets printed):
```bash
wrangler tail --format json
```

**Security note (Telegram callbacks)**
Telegram servers—not your phone—invoke the webhook. IP allowlists based on a mobile device will
block callbacks. The correct protection is the `X-Telegram-Bot-Api-Secret-Token` header (matched
against `JOB_SCOUT_WEBHOOK_SECRET`) plus `ALLOWED_TELEGRAM_USER_ID` for callback ownership.

**Debug flow (no local PC required)**
1. Deploy the Worker (`deploy-feedback-worker` workflow).
2. Run **Actions → cf_worker_smoke → Run workflow** to send an authenticated webhook callback
   payload and verify reachability/auth.
3. Run **Actions → telegram_webhook_set → Run workflow** to confirm the webhook configuration.
4. Tap a feedback button in Telegram and verify the Worker logs + “OK” checkmark appear.

**CI smoke test (Telegram feedback)**
The GitHub Actions smoke test is an auth/reachability check (not a full E2E feedback session):
1. `POST /telegram/feedback` using `X-Telegram-Bot-Api-Secret-Token: ${JOB_SCOUT_WEBHOOK_SECRET}`.
2. The payload is a minimal valid Telegram callback (`update_id`, `callback_query`, `from.id`).
3. PASS conditions: non-401/403/404 response returned without timeout/network errors.

Required secrets for the smoke workflow:
- `JOB_SCOUT_WEBHOOK_BASE_URL`
- `JOB_SCOUT_WEBHOOK_SECRET`
- `ALLOWED_TELEGRAM_USER_ID`

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

## Notifications (Phase 6 + Phase 7)
Telegram notifications are always on by default. Configure in `config/config.yaml`:
- `notifications.telegram.enabled`: keep Telegram enabled (default: true).
- `notifications.telegram.dry_run`: write the payload to disk without sending to Telegram.
- `notifications.telegram.send_per_job`: send one message per job.
- `notifications.telegram.top_n`: fallback number of jobs to include in the digest.
- `notifications.telegram.min_score`: minimum score required to notify.
- `digest.mode`: `daily_window` for the daily scheduled digest.
- `digest.window_hours`: number of hours in the daily digest window (24).
- `digest.top_n`: number of jobs to include in the daily digest.

Telegram credentials must be set via environment variables (or GitHub Actions secrets):
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `JOB_SCOUT_WEBHOOK_BASE_URL` (Cloudflare Worker)
- `JOB_SCOUT_WEBHOOK_SECRET` (shared secret)
- `FEEDBACK_WINDOW_MINUTES` (optional override, default 60)

If credentials are missing or invalid, notifications are skipped with a warning and the run continues.
Each run sends one message per job (plus an optional header message); when there are no eligible jobs in the last 24 hours the message is:
“No new job postings published in the last 24 hours.”

### GitHub Actions secrets & manual trigger
Repository secrets are documented in [`docs/SECRETS.md`](docs/SECRETS.md).
Workflow operations are documented in [`docs/CI_RUNBOOK.md`](docs/CI_RUNBOOK.md).

The remotive notification workflow is manual-only (`workflow_dispatch` only) and cron is disabled. To run manually: go to
**Actions → scheduled-remotive** → **Run workflow** and set inputs
(`since_days`, `sources`, `strict`, `allow_missing_salary`). You can also trigger via
`gh workflow run scheduled_remotive.yml` (no secrets shown in CLI output).

The dummy E2E workflow is manual-only:
**Actions → dummy-e2e** → **Run workflow** or
`gh workflow run dummy_e2e.yml`.

## Fake E2E workflow (manual)
- Use GitHub Actions workflow `e2e_fake` (manual `workflow_dispatch`) to run a full fake-data integration: pipeline + fake Telegram payload + feedback callback webhook validation.
- Operational details, artifacts, and troubleshooting are documented in `docs/e2e_fake.md`.
