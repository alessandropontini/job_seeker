# Cloudflare Worker — Telegram Feedback Gateway

This Worker provides a time-gated webhook endpoint for Telegram callback queries and a protected
feedback export endpoint for the Job Scout pipeline.

## Endpoints
### `POST /telegram/feedback`
Receives Telegram `callback_query` updates, validates the run window, writes feedback to KV, and
always responds with `answerCallbackQuery` to clear the loading spinner. Requires
`X-Telegram-Bot-Api-Secret-Token`; missing or invalid headers return **401**.

### `POST /window/open`
Registers the feedback window and job mapping for a run. Requires HMAC signature headers.

### `POST /feedback`
Returns feedback entries for a run. Requires HMAC signature headers.

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
The workflow pins Wrangler to the latest release so Worker code stays aligned with Cloudflare CLI updates.

## Configure Telegram webhook
Point Telegram to the Worker endpoint and include the secret token header:
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

## Verification (manual)
1. Run the dummy E2E pipeline to send a Telegram digest with feedback buttons.
2. Tap 👍/👎/⭐/🧻 — the spinner should disappear immediately with a confirmation toast.
3. In Cloudflare KV, confirm a key like `feedback:<run_id>:<short_id>:<user_id>` exists
   and contains the action + timestamp payload.
