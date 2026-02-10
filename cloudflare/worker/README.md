# Cloudflare Worker — Telegram Feedback Gateway

This Worker provides a time-gated webhook endpoint for Telegram callback queries and a protected
feedback export endpoint for the Job Scout pipeline.

## Endpoints
### `POST /telegram/feedback`
Receives Telegram `callback_query` updates, validates the run window, writes feedback to KV, and
always responds with `answerCallbackQuery` to clear the loading spinner. Requires
`X-Telegram-Bot-Api-Secret-Token`; missing or invalid headers return **401**.

Callback data contract (must be compact, under Telegram's ~64 byte limit):
- Format: `fb|<run_id>|<job_short_id>|<action>|<job_hash>`
- Valid actions: `L`, `M`, `D`, `S`, `X`, or their long forms (`like`, `maybe`, `dislike`, `love`, `duplicate`)
- Any other value returns `Invalid callback data` (HTTP 200) and does not write KV.

### `GET /telegram/feedback`
Returns `200 OK` to verify reachability and generate logs without touching KV.

### `GET /healthz`
Returns `200 OK` for quick liveness checks (useful for log verification).

### `POST /window/open`
Registers the feedback window and job mapping for a run. Requires HMAC signature headers.

### `POST /feedback`
Returns feedback entries for a run. Requires HMAC signature headers.

### `POST /internal/smoke/session`
CI-only endpoint that creates a short-lived feedback session and returns callback data for the
smoke workflow. Requires `X-Smoke-Token` matching `JOB_SCOUT_SMOKE_TOKEN`. Missing/invalid tokens
return 404.

### HMAC headers
Signed requests must include:
- `X-Webhook-Timestamp` (unix seconds)
- `X-Webhook-Id` (unique per request)
- `X-Webhook-Signature` (hex HMAC SHA-256 of `timestamp.body`)

## Required secrets (Worker)
Set these as Worker secrets in Cloudflare:
- `TELEGRAM_BOT_TOKEN` (the same bot used by Job Scout)
- `JOB_SCOUT_WEBHOOK_SECRET` (shared secret used by Job Scout to sign requests and by Telegram webhook authentication)
- `TELEGRAM_WEBHOOK_SECRET` (optional override for Telegram `secret_token`; falls back to `JOB_SCOUT_WEBHOOK_SECRET`)
- `ALLOWED_TELEGRAM_USER_ID` (numeric Telegram user ID allowed to record feedback)
- `JOB_SCOUT_SMOKE_TOKEN` (shared secret for the CI-only smoke session endpoint)

Optional Worker env vars:
- `FEEDBACK_WINDOW_MINUTES` (default: 60)

## KV Namespace
Create a KV namespace and update `wrangler.toml`:
```toml
kv_namespaces = [
  { binding = "JOB_SCOUT_KV", id = "REPLACE_WITH_NAMESPACE_ID" }
]
```

## Deploy
Worker deploys are handled via GitHub Actions using `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
See `.github/workflows/deploy_worker.yml` and repository secrets setup in the main README.
The Worker name is `job-scout-telegram-feedback` (matches the Telegram webhook route binding).
The workflow pins Wrangler to the latest release so Worker code stays aligned with Cloudflare CLI updates.

## Configure Telegram webhook
Point Telegram to the Worker endpoint and include the secret token header. You can use the helper
script to set + verify the webhook without printing secrets:
```bash
export TELEGRAM_BOT_TOKEN=...
export JOB_SCOUT_WEBHOOK_SECRET=...
export JOB_SCOUT_WEBHOOK_BASE_URL=https://<your-worker-domain>
tools/telegram_set_webhook.sh
```

Manual curl (avoid printing secrets in logs):
```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url":"https://<your-worker-domain>/telegram/feedback",
    "secret_token":"<TELEGRAM_WEBHOOK_SECRET or JOB_SCOUT_WEBHOOK_SECRET>"
  }'
```

## Job Scout integration
Set these environment variables in GitHub Actions (or local shell):
- `JOB_SCOUT_WEBHOOK_BASE_URL` (e.g., `https://<your-worker-domain>`)
- `JOB_SCOUT_WEBHOOK_SECRET` (same as `JOB_SCOUT_WEBHOOK_SECRET` in Worker)
- `FEEDBACK_WINDOW_MINUTES` (optional override, default 60)

## Allowlist behavior
Only the user whose Telegram ID matches `ALLOWED_TELEGRAM_USER_ID` can store feedback.
To discover your numeric user ID, message `@userinfobot` on Telegram and copy the `id` value.
Other users will see `🚫 Not authorized`, the spinner will clear, and no KV entry is written.

Telegram servers (not your phone) call the webhook, so IP allowlists based on a mobile device
will block callbacks. Use the secret header + allowlisted user ID instead.

## Verification (manual)
1. Run the dummy E2E pipeline to send a Telegram digest with feedback buttons.
2. Tap 👍/👎/⭐/🧻 — the spinner should disappear immediately with a confirmation toast.
3. In Cloudflare KV, confirm a key like `feedback:<run_id>:<short_id>:<user_id>` exists
   and contains the action + timestamp payload.

## Logs & troubleshooting
To view Worker logs in Cloudflare:
1. Open **Workers & Pages → job-scout-telegram-feedback → Observability → Events/Logs**.
2. Confirm `console.log`/`console.error` events are enabled (logs appear only when the Worker emits
   console output).
3. Filter by `event` (e.g., `telegram_webhook_rejected`, `kv_write_failed`) to debug the callback path.

Optional local tail (no secrets printed):
```bash
wrangler tail --format json
```
Use your terminal history or exported environment to provide secrets; never echo tokens in shared logs.
