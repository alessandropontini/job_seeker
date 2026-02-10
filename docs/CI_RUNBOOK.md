# CI Runbook

## Active workflows (rationalized)

- `deploy-feedback-worker` (`.github/workflows/deploy_worker.yml`)
  - **Trigger:** `workflow_dispatch` only.
  - **Purpose:** Deploy Cloudflare Worker and upload required Worker secrets.
- `cf_worker_smoke` (`.github/workflows/cf_worker_smoke.yml`)
  - **Trigger:** `workflow_dispatch` only.
  - **Purpose:** Webhook reachability/auth smoke check against `/telegram/feedback`.
- `scheduled-remotive` (`.github/workflows/scheduled_remotive.yml`)
  - **Trigger:** `workflow_dispatch` only.
  - **Purpose:** Manual remotive pipeline run that can send Telegram notifications.
- `telegram_webhook_set` (`.github/workflows/telegram_webhook_set.yml`)
  - **Trigger:** `workflow_dispatch` only.
  - **Purpose:** Configure Telegram webhook URL + secret token.
- `telegram_webhook_get` (`.github/workflows/telegram_webhook_get.yml`)
  - **Trigger:** `workflow_dispatch` only.
  - **Purpose:** Read current Telegram webhook status.
- `dummy-e2e` (`.github/workflows/dummy_e2e.yml`)
  - **Trigger:** `workflow_dispatch` only.
  - **Purpose:** Manual non-production validation flow.

## Manual operations

### 1) Deploy feedback worker
1. Open **Actions → deploy-feedback-worker → Run workflow**.
2. Confirm successful deploy + secret upload steps.
3. Optionally run `telegram_webhook_get` to confirm current webhook status.

### 2) Run webhook smoke check
1. Open **Actions → cf_worker_smoke → Run workflow**.
2. Validate logs show a returned HTTP status and body snippet.
3. Treat smoke as **PASS** when:
   - Request reaches endpoint and returns a response.
   - Status is not `401`, `403`, or `404`.
   - No timeout/network failure occurred.

> This smoke is intentionally **not** a full E2E session flow. It verifies endpoint reachability and webhook secret auth guardrails.

### 3) Run remotive pipeline manually
1. Open **Actions → scheduled-remotive → Run workflow**.
2. Set optional inputs (`since_days`, `sources`, `strict`, `allow_missing_salary`).
3. Run and inspect uploaded artifacts in the workflow summary.

## Required repository secrets (names only)

- `ALLOWED_TELEGRAM_USER_ID`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_KV_NAMESPACE_ID`
- `JOB_SCOUT_WEBHOOK_BASE_URL`
- `JOB_SCOUT_WEBHOOK_SECRET`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

No additional secrets are required for the smoke workflow.

## Scheduled notifications policy

Automated cron scheduling for notification workflows is disabled.

To re-enable scheduled notifications safely:
1. Add back an `on.schedule` block only in the intended workflow.
2. Keep webhook/auth workflows (`cf_worker_smoke`, `telegram_webhook_*`, deploy) manual.
3. Validate secrets and dry-run manually before enabling cron.
4. Document the cron expression and rollback steps in this runbook.
