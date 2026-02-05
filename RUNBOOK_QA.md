# QA Runbook — Offline & Online Validation

This runbook provides deterministic offline validation and an explicit opt-in path for online integration testing.
Phase 5 (QA & hardening) is complete: the pipeline is deterministic, offline execution is supported, and golden
snapshot tests validate CSV/Markdown outputs. External dependency failures (HTTP 403/429, `NO_NETWORK`) are
documented as environment limitations rather than project defects.

## Phase 6 Automation Notes
GitHub Actions runs are scheduled daily via `scheduled_remotive.yml`, and manual runs remain available.
The dummy end-to-end workflow (`dummy_e2e.yml`) is manual-only and sends a real Telegram digest so
the full pipeline (pipeline → digest → Telegram) is validated end-to-end. Dummy state files are
isolated with a `dummy_e2e` suffix to avoid impacting the 08:00 Remotive run.
Telegram credentials must be stored as GitHub Actions secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)
and are never printed in logs. If secrets are missing, notifications are skipped while the pipeline still runs.
Worker credentials are also required for feedback ingestion (`JOB_SCOUT_WEBHOOK_BASE_URL`,
`JOB_SCOUT_WEBHOOK_SECRET`). Worker deploys require `CLOUDFLARE_API_TOKEN`,
`CLOUDFLARE_ACCOUNT_ID`, and `CLOUDFLARE_KV_NAMESPACE_ID`.
CI/build workflows are intentionally removed in Phase 6 due to environment constraints.
Phase 6 refinement adds dual-channel outputs, Telegram feedback buttons, and a stateful anti-dup digest
(`last_notified.json`) persisted between runs via Actions cache.
Phase 7 adds Cloudflare Worker-backed, time-gated feedback ingestion with per-job Telegram messages.
Worker deployments are handled via the `deploy-feedback-worker` workflow.

## Production operations (live schedule)
The workflow now runs daily at **08:00 Europe/Rome** using UTC-based cron entries in
`.github/workflows/scheduled_remotive.yml`:
- `0 7 * * *` → 08:00 CET (winter)
- `0 6 * * *` → 08:00 CEST (summer)

### Daily digest behavior (yesterday window)
- Each scheduled run uses a UTC window of the last 24 hours (`now_utc - 24h → now_utc`).
- Only jobs with valid `posted_at` timestamps are eligible for the digest.
- The daily digest always includes **all** eligible jobs in the window.
- A daily digest hash is stored in `out/last_notified.json` to avoid re-sending the
  same digest on the same UTC date.

### What happens when no jobs are found
- A Telegram message is still sent with the exact text:
  “No new job postings published in the last 24 hours.”

### Interpreting Telegram messages
- Title: **Job Scout — Daily Digest (last 24h)**.
- Subtitle: **Published yesterday**.
- “Total in window” reflects the number of eligible jobs in the last 24 hours.
- Entries list job title, company, remote level, location, score, and rationale
  (bonuses/penalties, including data governance boosts).
- Two sections are shown: **Top matches** and **Data-only best picks**.
- Inline feedback buttons (👍/👎/⭐/🧻) are attached for preference learning.

### Temporarily disabling the schedule
- Edit `.github/workflows/scheduled_remotive.yml` and comment out or remove the `schedule` block.
- Keep `workflow_dispatch` to allow manual runs while the schedule is disabled.

### Phase 6 validation checklist
- Confirm the daily workflow has only `workflow_dispatch` and `schedule` triggers.
- Verify the cron schedule aligns with 08:00 Europe/Rome (CET/CEST).
- Trigger a manual run via **Actions → scheduled-remotive → Run workflow**.
- Verify artifacts are uploaded: `report.csv`, `report.md`, `last_run.json`,
  `last_notified.json`, `preferences.json`.
- Trigger a manual run via **Actions → dummy-e2e → Run workflow** and verify
  `last_run_dummy_e2e.json`, `last_notified_dummy_e2e.json`, and `report.*` artifacts exist.
- Trigger a manual run with valid Telegram secrets and verify the dummy digest is delivered.
- Click feedback buttons within 1 hour and rerun to validate feedback ingestion.
- Confirm the workflow runs twice and the second run skips with `duplicate_digest`.
- Verify `feedback_summary_dummy_e2e.json` is uploaded when feedback is applied.
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

### Troubleshooting: Telegram empty but report populated
- Inspect `out/last_run.json` and confirm `digest.jobs` is non-empty for the run.
  If `digest.jobs` is empty, check `digest.top_matches` and
  `digest.data_only_best_picks` (schema aliases).
- If `digest.scope` is `fallback_recent`, the daily window had no recent postings.
  Confirm the daily window matches the expected time range and that `posted_at`
  timestamps are present in `report.csv`.
- If `digest.jobs` is present but Telegram is empty, verify the payload in
  `out/telegram_payload.json` (dry-run) or check action logs for send failures.

### Troubleshooting: feedback buttons do nothing
- Confirm the Telegram webhook is set to the Worker endpoint (`/telegram/feedback`).
- Ensure the Worker has `TELEGRAM_BOT_TOKEN` and `JOB_SCOUT_WEBHOOK_SECRET` configured.
- Confirm the Telegram webhook was configured with `secret_token` matching `JOB_SCOUT_WEBHOOK_SECRET`.
- Verify the callback arrives within the 1-hour feedback window; outside the window the Worker
  answers with “⏱ Feedback window closed” and returns HTTP 410.
- Check the Worker logs for `window` or `job` validation failures.

### Troubleshooting: deploy workflow fails before wrangler deploy
- If logs show `kv_namespaces[0]... id:""` or `Missing CLOUDFLARE_KV_NAMESPACE_ID`, ensure the
  GitHub Actions secret `CLOUDFLARE_KV_NAMESPACE_ID` is set and matches your Cloudflare KV namespace.

### Troubleshooting: dummy E2E artifact check failure
- The guard-rail validates that accepted matches imply a non-empty digest.
- Check `out/last_run_dummy_e2e.json` for `digest.jobs`, or the channel-specific lists
  `digest.top_matches` / `digest.data_only_best_picks`.
- If all digest lists are empty but `report.csv` shows accepted rows, inspect
  `posted_at` timestamps and the daily window; a fallback digest should be used
  when the 24h window is empty.

### Troubleshooting: dummy E2E does not send Telegram
- Ensure GitHub Actions secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` exist and are valid.
- Confirm the dummy run is using the isolated state suffix (`dummy_e2e`) so a prior digest
  from the daily workflow is not treated as a duplicate.
- If the second (rerun) step skips with `duplicate_digest`, this is expected and confirms
  dedupe is working for the dummy workflow only.

### Troubleshooting: feedback not applied on next run
- Confirm `JOB_SCOUT_WEBHOOK_BASE_URL` and `JOB_SCOUT_WEBHOOK_SECRET` are set in Actions secrets.
- Check `out/last_run*.json` for a `digest.run_id` value.
- Verify `POST /feedback` returns entries (Worker is storing feedback).
- Ensure personalization is enabled (`personalization.enabled: true`) and that
  `feedback_summary*.json` reports non-zero counts.
- If Worker logs show “Invalid signature” or “Stale signature,” verify clock drift and the
  shared secret used in GitHub Actions matches the Worker secret.

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
- **Dual-channel volume:** adjust `channels.top_matches.top_n` and
  `channels.data_only_best_picks.top_n` plus the data keyword lists.

### Feedback & personalization checks
- Ensure `personalization.enabled: true` if you want ranking adjustments from feedback.
- Confirm `out/preferences.json` is updated after receiving feedback buttons.
- Use the 🧻 button to suppress duplicate items from future digests.

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
