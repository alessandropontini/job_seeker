# QA Runbook — Offline & Online Validation

This runbook provides deterministic offline validation and an explicit opt-in path for online integration testing.
Phase 5 (QA & hardening) is complete: the pipeline is deterministic, offline execution is supported, and golden
snapshot tests validate CSV/Markdown outputs. External dependency failures (HTTP 403/429, `NO_NETWORK`) are
documented as environment limitations rather than project defects.

## Phase 6 Automation Notes
GitHub Actions runs are scheduled daily via `job_scout.yml`, and manual runs remain available.
Telegram credentials must be stored as GitHub Actions secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)
and are never printed in logs. If secrets are missing, notifications are skipped while the pipeline still runs.
CI/build workflows are intentionally removed in Phase 6 due to environment constraints.

## Production operations (live schedule)
The workflow now runs daily at **08:00 Europe/Rome** using UTC-based cron entries in
`.github/workflows/job_scout.yml`:
- `0 7 * * *` → 08:00 CET (winter)
- `0 6 * * *` → 08:00 CEST (summer)

### Daily digest behavior (yesterday window)
- Each scheduled run uses a UTC window of the last 24 hours (`now_utc - 24h → now_utc`).
- Only jobs with valid `posted_at` timestamps are eligible for the digest.
- Jobs already notified in previous runs are excluded to prevent duplicate alerts.

### What happens when no jobs are found
- A Telegram message is still sent with the exact text:
  “No new job postings published in the last 24 hours.”

### Interpreting Telegram messages
- Title: **Job Scout — Daily Digest (last 24h)**.
- Subtitle: **Published yesterday**.
- “Total in window” reflects the number of eligible jobs in the last 24 hours.
- Entries list job title, company, remote level, location, score, and rationale
  (bonuses/penalties, including data governance boosts).

### Temporarily disabling the schedule
- Edit `.github/workflows/job_scout.yml` and comment out or remove the `schedule` block.
- Keep `workflow_dispatch` to allow manual runs while the schedule is disabled.

### Phase 6 validation checklist
- Confirm the workflow has only `workflow_dispatch` and `schedule` triggers.
- Verify the cron schedule aligns with 08:00 Europe/Rome (CET/CEST).
- Trigger a manual run via **Actions → job-scout → Run workflow**.
- Verify artifacts are uploaded: `report.csv`, `report.md`, `last_run.json`.
- Trigger a manual run with valid Telegram secrets and verify the digest is delivered.
- Trigger a manual run with missing or invalid Telegram secrets and verify logs warn about
  the specific missing/invalid secret(s) and that the run completes without a notification.
- Confirm snapshot updates complete even if notification rows have missing fields
  (warnings are logged, `last_run.json` still updates, and the run exits successfully).

### Phase 6 common log meanings
- **Token OK + chat_id OK + sendMessage OK:** Telegram delivery succeeded.
- **Token OK + chat_id missing/invalid:** Notification skipped; check `TELEGRAM_CHAT_ID`.
- **Token missing/invalid:** Notification skipped; check `TELEGRAM_BOT_TOKEN`.
- **Snapshot warning about missing job_id/score:** A notification row was malformed; the
  run still completes and `last_run.json` is updated using valid rows.

### Remotive validation & tuning (Phase 6)
Use this checklist when Remotive runs return too few candidates or notifications feel empty.

**Validate a Remotive run**
1. Trigger a run with `--source remotive` (or enable in `config/config.yaml`).
2. Inspect `out/report.csv` and `out/report.md` to confirm:
   - Candidates are present in **Matches** or **Missing Salary (allowed)**.
   - Data governance bonuses appear in `score_bonuses` when keywords match.
3. Confirm the summary log line includes:
   - `fetched_count`, `normalized_count`, `candidates_count`, `matches_count`,
     `notified_count`, and `notification_mode` (`daily_window`).

**Interpreting the summary log**
- `fetched_count`: raw source items fetched per run.
- `normalized_count`: items that passed normalization.
- `candidates_count`: postings not hard-rejected (accepted + missing salary).
- `matches_count`: accepted postings with salaries meeting minimums.
- `notified_count`: jobs included in the Telegram digest (top N).
- `notification_mode`: `daily_window` for the daily digest window.

**Tuning strictness (config-first)**
- **Relax location strictness:** keep `location_rules.allow_unknown_location: true`
  and tune `scoring.penalty_weights.unknown_location` to control ranking impact.
- **Remote preferences:** adjust `scoring.penalty_weights.prefer_full_remote`
  instead of rejecting hybrid/onsite.
- **Salary gaps:** keep `salary_rules.allow_missing_salary: true` and use the
  `missing_salary` penalty weight to control ranking impact.
- **Data governance boost:** tune `scoring.data_governance_boost`,
  `scoring.data_governance_keywords`, and the secondary boost/keywords to increase
  relevance for governance roles.
- **Notifications:** raise/lower `digest.top_n` or `notifications.telegram.min_score`
  to control digest size and sensitivity.

## A) OFFLINE (default)
Use this path for reproducible, deterministic QA checks without network access.

```bash
python -m venv .venv
source .venv/bin/activate
export JOB_SCOUT_WHEELHOUSE_URL=path-or-url-to-wheelhouse-py311.zip
bash tools/run_tests_offline.sh
```

### PyPI blocked / wheelhouse fallback (required commands)
If PyPI is blocked, use the wheelhouse fallback below (copy/paste ready). This
sequence installs pytest without PyPI access and runs deterministic offline tests
twice, then runs opt-in integration tests.

```bash
python -m venv .venv
source .venv/bin/activate
export JOB_SCOUT_WHEELHOUSE_URL=</path/or/url/to/wheelhouse-py311.zip>
bash tools/install_dev_deps.sh
NO_NETWORK=1 python -m pytest -q
NO_NETWORK=1 python -m pytest -q
JOB_SCOUT_RUN_INTEGRATION=1 python -m pytest -q -m integration
```

#### How to obtain the wheelhouse artifact
Wheelhouse archives must be provided manually in Phase 6, because build workflows
are intentionally removed even while automation is live.

You may provide a local path if the file is already available:
```bash
export JOB_SCOUT_WHEELHOUSE_URL=/absolute/path/to/wheelhouse-py311.zip
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
Use a locally provided `wheelhouse-py311.zip`. Pass a direct URL, `file://` URL, or local path.

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
tests must report them deterministically (skip vs fail) and must never crash. When `NO_NETWORK=1` is set,
offline runs must pass without network access; failures in restricted environments are external limitations.

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
