# Cloudflare Worker — Telegram Feedback Gateway + Live Runner

This Worker provides:
- secure Telegram feedback webhook handling
- signed feedback/session endpoints used by `job_scout`
- live daily digest orchestration (Cron 08:00 Europe/Rome)
- Telegram bot command handling for source probe tests and future GitHub dispatch

## Endpoints

### `POST /telegram/feedback`
Receives Telegram `callback_query` updates, validates time window/session/job hash, and writes feedback to KV.
Requires `X-Telegram-Bot-Api-Secret-Token`.

The same webhook also accepts Telegram `message` updates containing bot commands.
Supported command today:
- `/jobscout mode=test sources=remotive,wwr,arbeitnow since_days=7`
- `/jobscout mode=github sources=remotive,wwr,arbeitnow since_days=7`

`mode=test` performs an in-Worker source probe and replies on Telegram with source counts.
`mode=github` dispatches the configured GitHub Actions workflow and replies with an acknowledgement.

Callback data contract:
- `fb|<run_id>|<action>|<job_short_id>` (v1, backward compatible)
- `fb|<run_id>|<action>|<job_short_id>|<job_hash8>` (v2, preferred)
- max 64 bytes

### `POST /window/open`
Signed endpoint to register a feedback session (`run_id`, window, jobs).

### `POST /feedback`
Signed endpoint to fetch feedback items by `run_id` (used by `fetch_feedback`).

### `POST /run_daily`
Protected manual trigger (requires `X-Smoke-Token` / `JOB_SCOUT_SMOKE_TOKEN`) for the same live flow used by cron.

### `GET /healthz`
Simple liveness endpoint.

## Live scheduling at 08:00 Europe/Rome

Cloudflare cron is UTC-based. Worker config uses:
- `0 6 * * *`
- `0 7 * * *`

The runtime applies a Rome local-hour guard and executes only when local hour is `08`.
This avoids GitHub scheduled workflows and keeps scheduling in Cloudflare.

## Live safety and dedupe

- Live send is enabled only when `JOB_SCOUT_ENV=live`.
- Dedup key `live:last_sent_date` prevents duplicate sends for the same digest date.
- Daily window is `yesterday` in `Europe/Rome`; fallback is used and labeled if empty.
- Live run state is stored in KV under `live:run:<run_id>`.

## Required bindings/secrets

- KV binding: `JOB_SCOUT_KV`
- Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `JOB_SCOUT_WEBHOOK_SECRET`, `ALLOWED_TELEGRAM_USER_ID`, `JOB_SCOUT_SMOKE_TOKEN`
- Vars: `JOB_SCOUT_ENV`, `FEEDBACK_WINDOW_MINUTES` (`1440` recommended in production, i.e. 24h)

Additional vars for GitHub dispatch mode:
- `GITHUB_OWNER`
- `GITHUB_REPO`
- `GITHUB_WORKFLOW_ID` (default can be `live-daily-telegram.yml`)
- `GITHUB_TOKEN`
- `GITHUB_REF` (defaults to `main`)

See `docs/runbook_live.md` for operational checklist and troubleshooting.


## Observability and Workers Logs

`wrangler.toml` enables Cloudflare Observability and persisted Workers Logs:
- `[observability].enabled = true`
- `[observability.logs].enabled = true`
- `[observability.logs].invocation_logs = true`

After deploy, open **Cloudflare Dashboard → Workers & Pages → job-scout-telegram-feedback → Logs**.
Filter by `request_id` (header `X-Request-Id`) or `run_id` to trace callback outcomes (`ok`, `invalid_callback`, `session_missing`, `forbidden`, `error`).

## Deploy Worker (GitHub Actions)

Use workflow `.github/workflows/deploy_worker.yml` to deploy `job-scout-telegram-feedback` reliably.

### Required GitHub Secrets
Create these repository secrets before running deploy:
- `CLOUDFLARE_API_TOKEN` (token with Workers deploy permissions)
- `CLOUDFLARE_ACCOUNT_ID` (Cloudflare account id)
- `CLOUDFLARE_KV_NAMESPACE_ID` (the KV namespace id injected into `wrangler.toml` at deploy time)

### How to run deploy
1. Open **GitHub → Actions → deploy-feedback-worker**.
2. Click **Run workflow**.
3. Choose `environment`:
   - `staging` (default)
   - `prod`
4. Start the workflow.

The workflow pins Wrangler to `4.41.0`, verifies `wrangler --version` is `4.41.x`, validates worker name in `wrangler.toml`, runs `node --check worker.js`, and executes:
- `wrangler deploy --config wrangler.toml` (staging)
- `wrangler deploy --config wrangler.toml --env <environment>` (non-staging)

The workflow also replaces the staging placeholder `REPLACE_WITH_NAMESPACE_ID` in
`wrangler.toml` with the repository secret `CLOUDFLARE_KV_NAMESPACE_ID` before deploy,
so the checked-in config can stay non-sensitive.

### How to verify Active Deployment in Cloudflare
1. Open **Cloudflare Dashboard → Workers & Pages → job-scout-telegram-feedback**.
2. Confirm **Active Deployment** timestamp is recent.
3. Compare script/version metadata with the commit SHA printed in workflow logs.
4. Optionally verify from workflow logs using `wrangler deployments list` output.
