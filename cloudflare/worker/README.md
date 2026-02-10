# Cloudflare Worker — Telegram Feedback Gateway + Live Runner

This Worker provides:
- secure Telegram feedback webhook handling
- signed feedback/session endpoints used by `job_scout`
- live daily digest orchestration (Cron 08:00 Europe/Rome)

## Endpoints

### `POST /telegram/feedback`
Receives Telegram `callback_query` updates, validates time window/session/job hash, and writes feedback to KV.
Requires `X-Telegram-Bot-Api-Secret-Token`.

Callback data contract:
- `fb|<run_id>|<job_short_id>|<action>|<job_hash>`
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
- Vars: `JOB_SCOUT_ENV`, `FEEDBACK_WINDOW_MINUTES`

See `docs/runbook_live.md` for operational checklist and troubleshooting.
