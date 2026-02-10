# CI Runbook

## Workflow inventory (manual-only)

| Workflow | File | Purpose | When to use | Trigger policy |
|---|---|---|---|---|
| `offline_qa` | `.github/workflows/offline_qa.yml` | Offline Python QA suite (`tools/run_tests_offline.sh`). | Before merge / regression checks without external services. | `workflow_dispatch` only |
| `wheelhouse` | `.github/workflows/wheelhouse.yml` | Build and upload Python wheelhouse artifact for deterministic installs. | Dependency refresh or cache pre-warm. | `workflow_dispatch` only |
| `cf_worker_smoke` | `.github/workflows/cf_worker_smoke.yml` | Worker reachability + auth smoke on `/telegram/feedback`. | After Worker deploy or webhook auth changes. | `workflow_dispatch` only |
| `e2e_fake` | `.github/workflows/e2e_fake.yml` | Deterministic fixture E2E with fake Telegram send and callback replay checks. | Contract checks without real Telegram messages. | `workflow_dispatch` only |
| `e2e-telegram-real` | `.github/workflows/e2e_telegram_real.yml` | Real Telegram E2E (send + callback + persistence + feedback fetch). | Full production-path verification. | `workflow_dispatch` only |
| `deploy-feedback-worker` | `.github/workflows/deploy_worker.yml` | Deploy Cloudflare Worker + bindings/secrets upload. | Publish Worker code/config changes. | `workflow_dispatch` only |

## Removed workflows

The following workflows were removed because they were redundant or superseded by runbooks/manual operator steps:
- `dummy-e2e`
- `scheduled-remotive`
- `telegram_webhook_set`
- `telegram_webhook_get`

No GitHub scheduled (`on.schedule`) workflow is enabled.

## Smoke semantics

`cf_worker_smoke` remains intentionally minimal:
- validates endpoint reachability
- validates auth header handling
- does **not** run Cloudflare provider E2E

## Required secrets (names only)

- `ALLOWED_TELEGRAM_USER_ID`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_KV_NAMESPACE_ID`
- `JOB_SCOUT_WEBHOOK_BASE_URL`
- `JOB_SCOUT_WEBHOOK_SECRET`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
