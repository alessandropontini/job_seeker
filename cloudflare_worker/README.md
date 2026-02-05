# Cloudflare Worker — Telegram Feedback Gateway

This Worker provides a time-gated webhook endpoint for Telegram callback queries and a protected
feedback export endpoint for the Job Scout pipeline.

## Endpoints
### `POST /telegram/webhook`
Receives Telegram `callback_query` updates, validates the run window, writes feedback to KV, and
always responds with `answerCallbackQuery` to clear the loading spinner.

### `POST /window/open`
Registers the feedback window and job mapping for a run. Requires `X-Webhook-Secret` header.

### `GET /feedback?run_id=...`
Returns feedback entries for a run. Requires `X-Webhook-Secret` header.

## Required secrets (Worker)
Set these as Worker secrets in Cloudflare:
- `TELEGRAM_BOT_TOKEN` (the same bot used by Job Scout)
- `WEBHOOK_SECRET` (shared secret used by Job Scout to call `/window/open` and `/feedback`)

## KV Namespace
Create a KV namespace and update `wrangler.toml`:
```toml
kv_namespaces = [
  { binding = "JOB_SCOUT_KV", id = "REPLACE_WITH_NAMESPACE_ID" }
]
```

## Deploy
```bash
cd cloudflare_worker
npm install -g wrangler
wrangler login
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put WEBHOOK_SECRET
wrangler deploy
```

## Configure Telegram webhook
Point Telegram to the Worker endpoint:
```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://<your-worker-domain>/telegram/webhook"}'
```

## Job Scout integration
Set these environment variables in GitHub Actions (or local shell):
- `JOB_SCOUT_WEBHOOK_BASE_URL` (e.g., `https://<your-worker-domain>`)
- `JOB_SCOUT_WEBHOOK_SECRET` (same as `WEBHOOK_SECRET`)
