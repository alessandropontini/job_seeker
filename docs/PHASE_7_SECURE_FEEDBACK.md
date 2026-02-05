# Phase 7 — Secure, Time-Gated Telegram Feedback

## Overview
Phase 7 introduces a secure, time-boxed feedback loop between GitHub Actions, Telegram, and a
Cloudflare Worker + KV storage. Each job is sent as a separate Telegram message with four buttons
(Mi piace, Forse, Non mi piace, Non rilevante). Feedback is accepted only within a limited window
and is applied to ranking/duplicate suppression on the next run without bypassing hard rejects.

## Security model
- GitHub Actions → Worker requests are **HMAC SHA-256 signed** using `JOB_SCOUT_WEBHOOK_SECRET`.
- Worker validates:
  - Signature (`X-Webhook-Signature`)
  - Timestamp freshness (`X-Webhook-Timestamp`, ±5 minutes)
  - Idempotency (`X-Webhook-Id` stored in KV)
- Unsigned, stale, or duplicate requests are rejected.
- Secrets are never logged or written to artifacts.

## Time-gated feedback
- The feedback window is capped by `FEEDBACK_WINDOW_MINUTES` (default 60).
- Worker enforces the window for Telegram callback queries. Outside the window it replies with
  “⏱ Session expired” and returns HTTP 410.

## Data model (KV)
- `session:<run_id>`: feedback window metadata + job mapping
- `feedback:<run_id>:<job_short_id>:<user_id>`: feedback action, timestamp, source
- `req:<request_id>`: dedupe keys for signed requests

## Endpoints
- `POST /window/open` (signed, JSON) — register run window + job mapping
- `POST /feedback` (signed, JSON) — fetch feedback by `run_id`
- `POST /telegram/feedback` — Telegram callback query webhook

## Actions secrets
Required:
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `JOB_SCOUT_WEBHOOK_BASE_URL`, `JOB_SCOUT_WEBHOOK_SECRET`
- `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_KV_NAMESPACE_ID`

## Dummy vs Remotive separation
Dummy E2E runs use a state suffix (`dummy_e2e`) to isolate dedupe and preference state. The
feedback flow is identical but uses the dummy dataset for deterministic UX validation.

## Troubleshooting
- **Buttons not working:** verify Telegram webhook to `/telegram/feedback` and Worker secrets.
- **Feedback not applied:** ensure `feedback.run_id` exists in `last_run.json` and Worker returns
  feedback for the run.
- **Signature errors:** verify `JOB_SCOUT_WEBHOOK_SECRET` matches between Actions and Worker.
