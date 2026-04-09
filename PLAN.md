# Daily Job-Matching System Plan

## Milestones & Acceptance Criteria

### 1) Repository scaffolding
**Acceptance Criteria**
- Required documentation files exist: `AGENTS.md`, `PLAN.md`.
- Configuration scaffold exists at `config/config.yaml` with placeholders.
- `.gitignore` includes `out/` and `data/` entries.

### Sprint 1: Minimal runnable pipeline (complete)
**Status:** ✅ Done

**Completed scope**
- Added a runnable `job_scout` package with CLI entry points.
- Implemented a dummy source with normalized job postings.
- Added CSV/Markdown writers and basic config loader defaults.
- Added pytest coverage for model serialization, writers, and CLI smoke tests.
- Updated README with local setup and run instructions.

### Sprint 2: Real sources + matching rules (complete)
**Status:** ✅ Done

**Shipped scope**
- Added Remotive public API connector with fixtures and parser tests.
- Implemented matcher engine for location, role, salary, and remote annotations.
- Expanded pipeline filtering and reporting (CSV columns + Markdown sections).
- Extended CLI flags for strict mode, missing-salary override, and source selection.
- Added matcher, pipeline filtering, and connector tests.

### Phase 3 — Decision Engine (complete)
**Status:** ✅ Done

**Shipped scope**
- Split hard constraints from soft preferences in matcher flow.
- Added structured decision rationale fields (decision, hard reject reasons, penalties, missing fields).
- Preserved report formats while adding rationale columns and markdown notes.
- Ensured deterministic ordering for rationale lists and outputs.
- Updated tests and documentation to reflect the decision engine contract.

### Phase 4 — Scoring & Ranking
**Status:** ✅ Done
**Acceptance Criteria**
- Deterministic scoring function with documented inputs.
- Configurable weights for preference signals (no ML).
- Report ordering reflects score plus deterministic tie-breaks.
- Scores are included in CSV/Markdown outputs.
- Unit tests cover scoring edge cases and tie-break rules.

### Phase 5 — Reliability & Extensibility
**Status:** ✅ Done
**Completed scope**
- Added deterministic golden tests for end-to-end pipeline outputs.
- Enforced a source normalization contract with centralized normalization helpers.
- Externalized region/country mapping to `config/regions.json`.
- Added network source error handling + source status reporting.
- Added offline CI coverage with network disabled and integration tests gated.
- Added explicit no-network guardrails for offline testing and documentation updates.
- Updated documentation for contracts, tests, and failure modes.
- Documented offline-first QA runbook with opt-in online integration validation.
- Added Remotive integration troubleshooting notes and curl evidence capture.
- Added a wheelhouse-based pytest install fallback and QA scripts for air-gapped runs.
- Refreshed wheelhouse QA instructions for PyPI-blocked environments.
- QA close-out confirmed deterministic pipeline, offline execution support, and golden snapshots.
- External dependency failures (HTTP 403/429, NO_NETWORK) documented as environment limits.

### Phase 6 — Automation & Notifications
**Status:** ✅ LIVE — Manual dispatch workflows for Telegram + feedback operations
**Acceptance Criteria**
- Manual GitHub Actions workflow dispatch (`workflow_dispatch` only; cron disabled).
- Telegram notifications enabled by default with explicit logs for sent vs skipped.
- Missing/invalid secrets yield warnings without failing the run.
- Daily digest uses the last 24 hours of `posted_at` timestamps in UTC.
- State snapshot tracks notified job IDs and prevents duplicate alerts.

**Recent updates**
- Disabled notification cron; remotive workflow now runs only via manual dispatch.
- Enforced daily-window digest logic (last 24h UTC) and always-on Telegram.
- Added snapshot de-duplication across days using notification timestamps.
- Documented live operations and daily digest behavior.
- Hardened Telegram callback smoke workflow YAML with bash-only body truncation and curl retry/timeout diagnostics.

**Phase 6 refinement (current)**
- Added dual-channel outputs: TOP_MATCHES (strict) + DATA_ONLY_BEST_PICKS (wide).
- Implemented Telegram feedback buttons with a lightweight preference profile.
- Added stateful digest dedupe (`last_notified.json`) and cache persistence in Actions.
- Expanded documentation (README + runbook) and refreshed goldens/tests for no regressions.
- Persisted full digest payloads in `last_run.json` and wired daily notifications to the
  complete daily window digest.
- Split GitHub Actions workflows into daily remotive runs and manual dummy E2E runs.
- Stabilized `last_run.json` digest schema with channel aliases and added a fallback
  digest scope when the daily window is empty.
- Switched dummy E2E to real Telegram delivery with isolated state suffixing.
- Expanded deterministic dummy postings to guarantee data-only picks for governance roles.
- Phase 7 kickoff: per-job Telegram UX with time-gated feedback via Cloudflare Worker + KV.
- Phase 7 security: HMAC-signed Worker requests, idempotency checks, and 60-minute feedback window.
- Phase 7 ops: stabilized Cloudflare Worker deploy workflow with staged deploy + secret upload.
- Phase 7 security hardening: Telegram webhook secret-token auth, aligned secret naming, and
  updated runbooks/tests for authenticated callbacks.
- Phase 7 ops fix: ensured Node is installed in deploy workflow so Wrangler secrets upload succeeds.
- Phase 7 ops fix: added explicit secret validation to fail fast when KV namespace ID is missing.
- Phase 7 ops docs: clarified Wrangler action warnings and expected behavior in the runbook.
- Phase 7 feedback fix: immediate Telegram ACK with KV persistence queued, plus callback parsing tests
  and verification steps documented.
- Phase 7 ops: updated Worker deploy workflow to track latest Wrangler CLI and added test runtime
  guardrails for Node VM module availability.
- Phase 7 ops fix: aligned Cloudflare Worker name with the Telegram webhook route and added
  non-sensitive deploy diagnostics to confirm the deployed worker.
- Phase 7 security: enforce feedback allowlist via `ALLOWED_TELEGRAM_USER_ID` and document
  the authorization behavior for Telegram callbacks.
- Phase 7 ops: added a helper script + docs to configure Telegram webhook to `/telegram/feedback`
  with non-sensitive verification output.
- Phase 7 ops: added a manual GitHub Actions workflow to read Telegram webhook status (Phase 1)
  and documented the expected `/telegram/feedback` URL.
- Phase 7 ops: added a manual GitHub Actions workflow to set the Telegram webhook with a secret
  token and non-sensitive verification output (Phase 2).
- Phase 7 ops: improved Telegram webhook setup diagnostics with HTTP status, raw response logging,
  and HTTPS base URL validation for faster troubleshooting.
- Phase 7 ops: expanded `telegram_webhook_get` diagnostics with HTTP status, raw response, curl
  stderr, and non-sensitive token fingerprinting to detect secret mismatches.
- Phase 7 observability: structured Cloudflare Worker logs for Telegram feedback routes, with
  privacy-safe fields, request correlation IDs, and troubleshooting guidance.
- Phase 7 observability: added Telegram callback smoke workflow and hardened auth/GET probe for
  webhook debugging without local tooling.
- Phase 7 ops: aligned Telegram callback smoke payload with the `fb|run|short|action|hash` contract
  and documented the callback format for webhook troubleshooting.
- Phase 7 ops: added an internal CI-only smoke session endpoint plus two-step smoke workflow to
  validate real feedback sessions end-to-end.
- Phase 7 CI/security: removed `JOB_SCOUT_SMOKE_TOKEN` dependency from webhook smoke and converted
  smoke to authenticated reachability validation against `/telegram/feedback`.
- Phase 7 CI/ops: disabled scheduled notification cron to keep remotive dispatch manual-only.
- Phase 7 docs: added CI runbook + secrets matrix documentation for workflow usage and safe operations.
- Phase 7 CI/ops: hardened `cf_worker_smoke` pass/fail logic (200/204 pass; explicit curl/status failure paths) with minimal callback payload and safe logs.
- Phase 7 CI/ops: added manual `e2e_fake` workflow with deterministic fixture pipeline run, Telegram fake-send payload artifacts, feedback session bootstrap, and `/telegram/feedback` callback validation against session/callback errors.
- Phase 7 CI/ops: made fake-mode feedback registration fail-fast with explicit endpoint/method/status/body diagnostics in `out/feedback_registration_result.log`, added callback/session contract unit coverage, and enforced registration checks in `e2e_fake` workflow before webhook callback replay.
- Phase 7 CI/ops: added browser-like `User-Agent` + `Accept` headers on fake-mode `/window/open` registration to reduce Cloudflare 1010 blocks, and extended diagnostics with `user_agent_sent` metadata for CI troubleshooting.
- Phase 7 CI/ops: added manual-only `e2e-telegram-real` workflow using deterministic fixture jobs with explicit E2E real-Telegram gate (`JOB_SCOUT_E2E_REAL_TELEGRAM=1` + `JOB_SCOUT_TELEGRAM_MODE=real`), plus manual/automatic callback validation paths and full `out/` artifact upload.
- Phase 7 safety: introduced CLI `--telegram-real` and runtime send-mode resolution with fake-by-default behavior, requiring explicit E2E gate before real Telegram sends.
- Phase 7 feedback contract: enforced callback payload byte limit as `<=64` (Python + Worker helper) and documented real Telegram E2E runbook in `docs/e2e_telegram_real.md`.
- Phase 7 live ops: added Cloudflare Worker live runner (`/run_daily` + cron handler) for daily 08:00 Europe/Rome execution with runtime TZ guard.
- Phase 7 live ops: implemented Worker-side dedup (`live:last_sent_date`), yesterday Rome daily window filtering, and explicit fallback labeling when window is empty.
- Phase 7 contract hardening: feedback KV payload now persists `run_id` to improve correlation with `fetch_feedback(run_id)` diagnostics.
- Phase 7 CI cleanup: removed redundant workflows (`dummy-e2e`, `scheduled-remotive`, `telegram_webhook_set/get`) and added manual-only `offline_qa` + `wheelhouse` workflows.
- Phase 7 docs: added `docs/runbook_live.md`, refreshed E2E real runbook, and updated README/CI workflow inventory for Cloudflare-based live scheduling.

### Phase 7 live reliability hotfix (current)
**Status:** ✅ Done

**Shipped scope**
- Added explicit `run_mode` (`manual`/`scheduled`) and `force_send` controls to CLI runtime behavior.
- Introduced deterministic scheduled digest targeting **yesterday** in `Europe/Rome`.
- Implemented manual-mode observability: Telegram diagnostic send even with zero matches.
- Added persistent `out/run_summary.json` with notification reason codes, counters, window, timezone, and feedback diagnostics.
- Persisted live state metadata in `last_run*.json` (`last_successful_run_at`, `last_digest_date_local`, `last_seen_job_ids`) for stable next-day scheduled continuity.
- Added new workflow `.github/workflows/live-daily-telegram.yml` with:
  - dual UTC cron + Rome 08:00 gate,
  - manual dispatch inputs (`source`, `since_days`, `force_send`, `run_mode`),
  - always-on artifact upload for `out/`.
- Preserved feedback contracts: callback payload format/size checks and payload persistence (`out/telegram_payload.json`) for live diagnostics.
- Phase 7 live diagnostics hardening: persisted Telegram API forensic artifacts (`telegram_send_response.json`, `telegram_chat_check.json`), added thread/topic support via `TELEGRAM_MESSAGE_THREAD_ID`, and expanded `run_summary.json` with explicit send acceptance/error fields for production triage.
- Matcher tuning update: full-remote `Worldwide`/`Europe` locations are now accepted while UK and USA-only postings remain excluded, and role targeting now covers data governance/data quality/metadata/data management keywords to reduce false negatives from Remotive live runs.
- Sources expansion update: added public RSS/API multi-source support (`--sources` + `all`) while keeping `--source` compatibility, introduced We Work Remotely RSS connector with normalized fields, and added tests for WWR parsing plus `run_summary.source_counts` coverage.

- Phase 7 CV-driven targeting: enforced core keyword gate for TOP/DATA channels, hard-blocked marketing/brand titles, and added strong quant/trading soft penalties with rebalanced title/description-first scoring.
- Phase 7 feedback durability: callback schema migrated to `fb|run|vote|short_job_id`, KV feedback keys changed to `feedback:<run_id>:<user_id>:<job_id>`, and `/feedback` now validated to return all per-job events for a run.
- Added run summary counters (`gate_pass_count`, `hard_block_count`, `soft_penalty_count`) plus tests/docs updates for new targeting and feedback contracts.

### Search Quality — PR #1 (complete)
**Status:** ✅ Done

**Shipped scope (P1: dynamic thresholding + fallback top-K anti-zero)**
- Added pure digest selector `select_digest_items(...)` with configurable adaptive thresholding (`high_threshold` → `low_threshold`, fixed `step`).
- Added anti-zero fallback top-K behavior (`LOW_CONFIDENCE`) to prevent empty digests when `fetched_count > 0`.
- Added explicit digest mode labelling in Telegram (`TOP`, `ADAPTIVE`, `LOW_CONFIDENCE (anti-zero)`).
- Extended `out/run_summary.json` diagnostics with digest mode and threshold metadata.
- Annotated report output with digest mode + final threshold for quick triage.
- Added pytest coverage for adaptive and low-confidence selection, scheduled `fetched_count==0` invariants, and run summary fields.

### Search Quality — PR #1 FIX (anti-zero candidate-pool bug)
**Status:** ✅ Done

**Shipped scope (PR1-FIX)**
- Fixed the PR1 architectural bug where `candidates_count=0` prevented anti-zero from triggering even with `fetched_count>0`.
- Split flow explicitly into: hard filtering → candidate pool → selection (`TOP`/`ADAPTIVE`/`LOW_CONFIDENCE`).
- Candidate pool now reflects rows that survive hard filters (soft gate `title_not_targeted` no longer empties candidates in this phase).
- Dynamic thresholding now runs on candidate pool and can relax down to `low_threshold` before top-K fallback.
- Added explicit zero-result reasons in summary: `no_candidates_after_hard_filters`, `fetched_count_zero`.

### PR2 TEMP — pause `live-daily-telegram` cron (complete)
**Status:** ✅ Done

- Temporarily disabled automatic `on.schedule` triggers (`55 6 * * *`, `5 7 * * *`) in `.github/workflows/live-daily-telegram.yml`.
- Kept `workflow_dispatch` active so live checks can still run manually with existing inputs and artifacts.
- Updated README operational notes to document the temporary pause and rationale (avoid unattended sends until reactivation decision).

### Next: P4 Multi-source to increase volume
- RemoteOK (API)
- WeWorkRemotely (RSS)
- Arbeitnow (API)

Note: this is planned for a follow-up PR (not part of PR1-FIX implementation).

### PR2 — Schedule + 08:00 observability (complete)
**Status:** ✅ Done

- Enabled live GitHub Actions schedule on `.github/workflows/live-daily-telegram.yml` (`on.schedule`) with dual UTC cron (`55 6 * * *` + `5 7 * * *`) plus runtime time-gate on `Europe/Rome`.
- Added deterministic time-gate diagnostics: scheduled skip writes `out/run_summary.json` with `reason=time_gate_skip`, `now_utc`, `now_local`, timezone, and selected counters.
- Guaranteed artifact observability on every run (`out/run_summary.json` always present and uploaded).
- Updated scheduled behavior to avoid silent zero-result runs: scheduled no-match now sends diagnostic Telegram message and records `reason=no_matches`.
- Extended `run_summary` schema with `trigger_type`, `now_utc`, `now_local` for easier ops triage.
- Added unit tests for Rome 08:00 gate logic (CET/CEST) and scheduled no-match notification behavior.
- Updated README and troubleshooting docs with “08:00 no message” checks, DST rationale, and reason-code interpretation.

### PR2 FIX — schedule observability + run_mode isolation (complete)
**Status:** ✅ Done

- Removed global `JOB_SCOUT_RUN_MODE=scheduled` from workflow job-level environment to avoid contaminating manual dispatch behavior.
- Set `JOB_SCOUT_RUN_MODE=scheduled` only in the `Run scheduled mode` step; manual step now relies exclusively on workflow input `run_mode`.
- Added default-on Telegram ping for time-gate skips (`Scheduled run skipped (time gate)`) and persisted outcome in `out/run_summary.json`.
- Added scheduled post-run fallback ping for `reason=no_matches` when `telegram_attempted=false` to guarantee visible schedule observability.
- Kept artifact guarantees (`out/run_summary.json` and `out/` upload on `always()`) without introducing new secrets or secret logging.
- Added/kept test coverage for Rome 08:00 time gate and scheduled no-matches Telegram attempt semantics.
- Next step (P4): increase source volume to reduce `no_matches` days while preserving strict location/role/salary filters.

### PR3 — Wide recall + soft penalties + explainable CV scoring (complete)
**Status:** ✅ Done

- Switched manual matching from hard-gate rejects to soft penalties for `location_not_allowed`, `title_not_targeted`, and `salary_below_minimum` (scheduled keeps salary below min as hard reject).
- Kept hard rejects only for real blockers (`missing_url`, explicit excluded country/UK text, existing blacklist-like conditions).
- Reworked deterministic CV-driven scoring (title-weighted + description/platform signals, strong negative-domain and quant penalties, score clamp 0-100).
- Added explainability field `why[]` for selected jobs and surfaced `Why:` lines in Telegram digest/report outputs.
- Extended observability: `report.csv` now includes `penalties_applied` and `why`; `out/run_summary.json` now includes hard/soft counters, top penalties/hard rejects, score statistics.
- Added/updated pytest coverage for manual soft-penalty behavior, salary mode differences, report schema, run summary fields, and digest explainability.


### PR3.1 — Worker feedback observability + diagnostics (complete)
**Status:** ✅ Done

- Enabled Cloudflare Worker Observability persisted logs in `cloudflare/worker/wrangler.toml`.
- Added structured JSON feedback callback logs with `request_id`, `run_id`, `job_short_id`, `action`, `outcome`, `error_code`, `reason`, and `duration_ms`.
- Added deterministic `X-Request-Id` response header on every Worker response and response bodies including request correlation id.
- Hardened callback validation to support both `fb|run|action|short_id` and `fb|run|action|short_id|job_hash8`, with session/job resolution fallback by short_id then hash.
- Clarified feedback error taxonomy (`invalid_callback`, `session_missing`, `forbidden`) and updated Worker tests/docs/deploy workflow diagnostics.

### PR4 — Multi-source volume expansion (next)
- Increase daily candidate volume with additional public sources while preserving no-login/no-paywall policy.
- Keep PR3 wide-recall scoring pipeline unchanged; plug new sources into the same normalization/matching/ranking contracts.
- Goal: reduce low-volume days from Remotive-only fetches without sacrificing relevance.
- In progress:
  - added a source catalog surfaced via `job_scout sources --list --details` so the CLI can state exactly which sites/endpoints it searches
  - added `arbeitnow` public API support (`https://www.arbeitnow.com/api/job-board-api`) as a new no-auth source
  - added offline fixture/unit coverage and an opt-in live integration test for `arbeitnow`
  - queued next validation step: live multi-source fetch (`remotive`, `wwr`, `arbeitnow`) and ranking sanity-check against current EU/Italy/New York targeting rules
  - fixed `wwr` RSS parsing quality so HTML is stripped before reporting and `Headquarters:` values drive company/location extraction more reliably
  - tightened CV alignment in the matcher: generic manager/lead roles without core domain signals are now rejected in scheduled runs, and marketing/SEO/sales-family titles are hard-blocked
  - added Telegram command trigger scaffolding in the Cloudflare Worker: `mode=test` performs source probes and replies on Telegram; `mode=github` dispatches a workflow and replies with an acknowledgement
  - fixed staging Worker deploy by injecting `CLOUDFLARE_KV_NAMESPACE_ID` into `wrangler.toml` during GitHub Actions execution instead of relying on a checked-in KV id

### PR3.2 — Cloudflare observability schema alignment (complete)
**Status:** ✅ Done

- Updated `cloudflare/worker/wrangler.toml` observability blocks to match current Cloudflare dashboard schema.
- Added explicit `head_sampling_rate` and `persist` fields for logs, plus explicit traces settings.
- Kept observability enabled for logs and configured traces block explicitly for future rollout control.

### PR3.2 — Feedback callback diagnostics hardening (complete)
**Status:** ✅ Done

- Extended feedback window default for Worker vars to 24h (`FEEDBACK_WINDOW_MINUTES=1440`).
- Aligned session KV TTL with feedback window using a minimum 24h TTL for `session:<run_id>` records.
- Added structured `feedback_callback` logs for all `/telegram/feedback` exits, including non-callback updates.
- Normalized callback parse failure reasons (`bad_format`, `bad_action`, `missing_fields`) and session-missing reasons (`session_expired`, `no_session_for_run_id`).
- Kept request correlation deterministic with `X-Request-Id` and request-id text in error bodies.
- Added/updated tests for reason distinction, request-id presence, and structured callback diagnostics logs.
