# Security Notes — Telegram Feedback Control Plane

## Threat model (minimum)
**Trust boundaries**
- GitHub Actions → Cloudflare Worker (signed requests, HMAC).
- Telegram → Cloudflare Worker (webhook callbacks with secret token).
- Cloudflare Worker → KV store (feedback persistence).

**Key threats**
- **Spoofed callbacks:** Attackers post fake Telegram `callback_query` payloads to the Worker.
- **Replay attacks:** Valid signed requests are replayed outside the intended window.
- **Secret leakage:** Secrets exposed in logs, build artifacts, or client-visible responses.
- **Boundary confusion:** Mixing job-run traffic (signed) with Telegram webhook traffic (token-auth).

## Mitigations
- **Telegram webhook authentication:** Require `X-Telegram-Bot-Api-Secret-Token` to match
  `JOB_SCOUT_WEBHOOK_SECRET` for all Telegram webhook routes before any KV write occurs.
- **Signed Job Scout requests:** Worker enforces `X-Webhook-*` HMAC verification, timestamp
  freshness, and request-id idempotency stored in KV.
- **Time-gated feedback window:** Feedback is accepted only while the window is open.
- **Secret management:** Secrets are provided via GitHub Actions and Cloudflare Worker secrets;
  no secrets are logged or persisted to artifacts.

## Operational guidance
- Rotate `JOB_SCOUT_WEBHOOK_SECRET` in GitHub Actions **and** Cloudflare Worker together.
- Re-run Telegram `setWebhook` with the updated `secret_token` after rotation.
- Monitor for spikes in 403 responses from `/telegram/feedback` as potential probing attempts.
