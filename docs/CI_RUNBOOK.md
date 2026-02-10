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
- `e2e-telegram-real` (`.github/workflows/e2e_telegram_real.yml`)
  - **Trigger:** `workflow_dispatch` only.
  - **Purpose:** Fixture-based E2E with real Telegram send and callback validation (manual click default, optional automatic replay).

## Manual operations

### 1) Deploy feedback worker
1. Open **Actions → deploy-feedback-worker → Run workflow**.
2. Confirm successful deploy + secret upload steps.
3. Optionally run `telegram_webhook_get` to confirm current webhook status.

### 2) Run webhook smoke check
1. Open **Actions → cf_worker_smoke → Run workflow**.
2. Validate logs show a returned HTTP status and body snippet (max 120 chars).
3. Treat smoke as **PASS** when:
   - Status is `200` or `204`.
4. Treat smoke as **FAIL** when:
   - Status is `401`, `403`, `404`, or `405`.
   - `curl` fails (timeout, DNS error, connection refused, TLS/connect error).
   - Any status other than `200`/`204` is returned.

> The smoke workflow sends one POST to `${JOB_SCOUT_WEBHOOK_BASE_URL}/telegram/feedback`
> with a minimal Telegram callback payload and the `X-Telegram-Bot-Api-Secret-Token`
> header. Response body text such as `Invalid callback data` or `Session missing`
> does **not** affect PASS/FAIL.

> This smoke is intentionally **not** a full E2E session flow. It verifies endpoint
> reachability + webhook auth only.

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
