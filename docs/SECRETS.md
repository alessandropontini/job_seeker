# Secrets Reference

This repository uses GitHub Actions secrets by name only. Never commit or print secret values.

| Secret name | Used by | Purpose |
|---|---|---|
| `ALLOWED_TELEGRAM_USER_ID` | `cf_worker_smoke`, `deploy-feedback-worker` | Restrict Telegram callback ownership and build valid smoke payload user id. |
| `CLOUDFLARE_ACCOUNT_ID` | `deploy-feedback-worker` | Cloudflare account target for Worker deploy. |
| `CLOUDFLARE_API_TOKEN` | `deploy-feedback-worker` | Authenticate Wrangler deploy + secret upload. |
| `CLOUDFLARE_KV_NAMESPACE_ID` | `deploy-feedback-worker` | Bind Worker to the configured KV namespace. |
| `JOB_SCOUT_WEBHOOK_BASE_URL` | `cf_worker_smoke`, `scheduled-remotive`, `dummy-e2e`, `telegram_webhook_set` | Base HTTPS URL for Telegram feedback webhook endpoint. |
| `JOB_SCOUT_WEBHOOK_SECRET` | `cf_worker_smoke`, `scheduled-remotive`, `dummy-e2e`, `deploy-feedback-worker`, `telegram_webhook_set` | Shared secret for Telegram webhook header validation. |
| `TELEGRAM_BOT_TOKEN` | `scheduled-remotive`, `dummy-e2e`, `deploy-feedback-worker`, `telegram_webhook_set`, `telegram_webhook_get` | Telegram Bot API authentication. |
| `TELEGRAM_CHAT_ID` | `scheduled-remotive`, `dummy-e2e` | Telegram destination chat for notifications. |

## Anti-leak logging rules

- Never `echo` secret values in workflow logs.
- Never print full environment dumps (`env`, `printenv`) in CI.
- Prefer non-sensitive diagnostics (HTTP code, response size, masked identifiers).
- Use GitHub Actions secret store only; do not hardcode credentials in repository files.

