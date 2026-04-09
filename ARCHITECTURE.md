# Job Scout — Architecture & Contracts

## System Overview
Job Scout is a deterministic job-scouting system composed of:
- a Python batch pipeline for fetch, normalization, matching, ranking, reporting, and Telegram payload generation
- a Cloudflare Worker for Telegram webhook handling, feedback persistence, live scheduling, source-probe commands, and GitHub workflow dispatch
- GitHub Actions for controlled manual/live runs and Worker deployment

Core Python modules:
- `job_scout.__main__`: CLI entry points and argument parsing.
- `job_scout.config`: config loader and defaults.
- `job_scout.sources`: source registry and source catalog (`dummy`, `remotive`, `wwr`, `arbeitnow`).
- `job_scout.normalize`: source contract models + normalization helpers.
- `job_scout.regions`: region/country mapping loader and validation.
- `job_scout.pipeline`: orchestration (fetch, match, group, write).
- `job_scout.matcher`: matching rules + match metadata.
- `job_scout.scoring`: deterministic scoring and ranking metadata.
- `job_scout.state`: snapshot + diff helpers for notifications.
- `job_scout.notifications`: notification orchestration (state diff + digest).
- `job_scout.notifier.telegram`: Telegram delivery backend.
- `job_scout.writers`: CSV/Markdown report writers.
- `job_scout.models`: `JobPosting` data model.

Supporting runtime components:
- `cloudflare/worker/worker.js`: Telegram webhook, feedback/session APIs, cron/live runner, `/jobscout` command handling, GitHub workflow dispatch.
- `.github/workflows/live-daily-telegram.yml`: manual or triggered job-scout execution workflow.
- `.github/workflows/deploy_worker.yml`: Cloudflare Worker deployment workflow.

## Pipeline Flow
1. CLI reads config (`job_scout.config.load_config`) and resolves sources (`job_scout.pipeline.run_pipeline`).
2. Region metadata loads from `config/regions.json` (`job_scout.regions.load_region_data`).
3. Each source fetcher returns `SourceJob` items (`job_scout.sources`).
4. `job_scout.normalize.normalize_source_job` enforces the normalization contract.
5. `job_scout.matcher.match_posting` evaluates rules and annotates match metadata.
6. `job_scout.scoring.apply_scoring` computes scores for accepted postings.
7. `job_scout.pipeline.run_pipeline` groups rows into Matches / Missing Salary / Rejected.
8. `job_scout.writers.write_reports` writes `out/report.csv` and `out/report.md`.
9. `job_scout.notifications.maybe_notify` persists `out/last_run.json` and sends a
   digest if configured.

## Runtime Flows
### Local / CLI batch flow
1. Operator runs `python -m job_scout run ...` or `python -m job_scout sources ...`.
2. The pipeline fetches configured public sources, normalizes them, applies CV-driven matching rules, and scores surviving rows.
3. Reports are written to `out/` (`report.csv`, `report.md`, `digest.md`, `run_summary.json`, and Telegram payload artifacts in fake mode).

### Telegram test trigger flow
1. Telegram sends a webhook update to `POST /telegram/feedback` on the Cloudflare Worker.
2. The Worker accepts a bot message command such as `/jobscout` or `/jobscout mode=test sources=remotive,wwr,arbeitnow since_days=7`.
3. In `mode=test`, the Worker probes the configured public sources directly.
4. The Worker replies on Telegram with source counts and the exact public endpoints being used.

### Telegram GitHub dispatch flow
1. Telegram sends `/jobscout mode=github ...` to the same webhook.
2. The Worker validates the allowed Telegram user and GitHub runtime config.
3. The Worker dispatches the configured GitHub Actions workflow through the GitHub REST API (`workflow_dispatch`).
4. The Worker replies on Telegram with an acknowledgement of the dispatch result.

### Live scheduling flow
1. Cloudflare cron triggers the Worker in UTC.
2. The Worker applies a Europe/Rome local-hour guard and only executes at local 08:00.
3. The Worker runs the same live notification flow with dedupe and feedback-window persistence in KV.

## Key Decision Points (Current)
- Config loading & merge (`job_scout.config.load_config`).
- Source selection & registry lookup (`job_scout.sources.AVAILABLE_SOURCES`).
- Source catalog exposure for operator visibility (`job_scout.sources.SOURCE_CATALOG` via `python -m job_scout sources --list --details`).
- `match_posting` evaluation and reject reasons (`job_scout.matcher.match_posting`).
- Grouping into matches/missing/rejected (`job_scout.pipeline.run_pipeline`).
- Report writing (`job_scout.writers.write_reports`).
- Telegram command routing and auth (`cloudflare/worker/worker.js`).
- GitHub dispatch gating (`cloudflare/worker/worker.js`, `workflow_dispatch` target workflow).

## Contracts
### Source Contract
A source must provide a callable with signature:
- `fetch_source(since_days: int) -> list[SourceJob]`

Required `SourceJob` fields:
- `id`, `source`, `company`, `title`, `location_text`, `location_country`,
  `location_city`, `remote_type`, `url`, `posted_at`, `salary_text`, `currency`, `tags`.

Normalized contract (`NormalizedJob`):
- `id`, `source`, `company`, `title`
- `location_text`, `location_country`, `location_city`
- `posted_at` normalized to UTC
- `remote_level` (canonical)
- `salary_text`, `salary_min`, `salary_max`, `currency`

Normalization expectations:
- `posted_at` must be timezone-aware (`datetime` with tzinfo).
- `location_country` should use alias-normalized country labels.
- `remote_level` is centralized in `job_scout.normalize`.
- Salary parsing and currency conversion use `job_scout.normalize`.
- Network access is explicitly disabled when `NO_NETWORK=1`; sources should fail fast
  with clear errors or use fixtures.

Allowed / forbidden:
- Allowed: public APIs and offline fixtures.
- Forbidden: scraping content behind logins/paywalls (e.g., LinkedIn/Indeed).

Current public sources:
- `remotive`: public API
- `wwr`: We Work Remotely RSS feed
- `arbeitnow`: public API
- `dummy`: deterministic dev/test source

Operator visibility contract:
- `python -m job_scout sources --list --details` must print the source catalog, including site URL, access URL, and access mode.
- `python -m job_scout sources --test <source>` must probe a source and report whether it is reachable.

### Config Contract
Config keys and semantics:
- `sources.enabled` — list of source names to run.
- `location_rules.include_regions` — region allowlist (e.g., `EU`).
- `location_rules.include_countries` — country allowlist (e.g., `Italy`).
- `location_rules.include_cities` — city allowlist (e.g., `New York`).
- `location_rules.exclude_countries` — country denylist (must include `UK`).
- `location_rules.prefer_full_remote` — soft preference (penalty when not full-remote).
- `role_targeting.include_titles` — required title keywords.
- `salary_rules.minimum_eur` — minimum salary threshold (EUR).
- `salary_rules.allow_missing_salary` — keep missing salary postings.
- `salary_rules.currency_rates` — conversion map.
- `regions_path` — path to region/country mapping data.
- `scoring.base_score` — starting score for accepted postings.
- `scoring.penalty_weights` — per-penalty deductions.
- `scoring.bonus_weights` — per-bonus additions.
- `notifications.telegram.enabled` — enable Telegram notifications.
- `notifications.telegram.dry_run` — write Telegram payload locally without network calls.
- `notifications.telegram.top_n` — max jobs included in a digest.
- `notifications.telegram.min_score` — minimum score to notify.
- `notifications.telegram.min_score_improvement` — minimum score delta to notify.
- `feedback.*` — Cloudflare Worker integration for session registration and feedback retrieval.

**USED TODAY**: all keys above.

### Decision Engine Contract (Phase 3 implemented)
- Hard constraints: failing any hard constraint rejects the posting.
- Soft preferences: recorded as penalties without rejecting.
- Structured rationale fields per posting:
  - `decision` (`accepted` or `rejected`)
  - `hard_reject_reasons` (list)
  - `penalties` (list)
  - `missing_fields` (list)
- `matches_all` is derived from `decision == "accepted"` for compatibility.
- Deterministic evaluation order and outputs.

### Scoring Contract (Phase 4 implemented)
- Deterministic score function based on configured weights.
- Only soft-preference signals influence score; hard rejections are unchanged.
- Stable tie-break rules: score (desc), `posted_at` (desc), then `id`.
- Scores and applied adjustments are included in reports.

Current targeting shape:
- hard location boundary: EU, Italy, New York only
- explicit UK exclusion
- full-remote is a preference, not a blanket hard requirement
- manager/lead/governance-oriented roles are prioritized
- marketing / SEO / sales-family roles are hard-blocked
- generic leadership roles without data-governance domain signals are rejected in scheduled runs

### Telegram Worker Contract
Worker endpoints:
- `POST /telegram/feedback`: Telegram webhook for callback queries and bot commands
- `POST /window/open`: signed feedback session registration
- `POST /feedback`: signed feedback fetch by `run_id`
- `POST /run_daily`: protected manual live trigger
- `GET /healthz`: liveness

Supported bot commands today:
- `/jobscout`
- `/jobscout mode=test sources=remotive,wwr,arbeitnow since_days=7`
- `/jobscout mode=github sources=remotive,wwr,arbeitnow since_days=7`

Worker runtime requirements:
- Cloudflare KV binding: `JOB_SCOUT_KV`
- Telegram secrets: `TELEGRAM_BOT_TOKEN`, `JOB_SCOUT_WEBHOOK_SECRET`, `ALLOWED_TELEGRAM_USER_ID`
- GitHub dispatch runtime: `GITHUB_OWNER`, `GITHUB_REPO`, `GITHUB_REF`, Worker secret `GITHUB_TOKEN`

Dispatch semantics:
- `mode=test` stays inside Cloudflare and returns source probe results to Telegram
- `mode=github` calls GitHub `workflow_dispatch` and returns an acknowledgement to Telegram
- final GitHub-run result callback back into Telegram is not yet part of the closed loop

### Deployment Contract
- Cloudflare Worker deploys through `.github/workflows/deploy_worker.yml`.
- The workflow injects `CLOUDFLARE_KV_NAMESPACE_ID` into `wrangler.toml` at deploy time.
- The workflow uploads repository secret `WORKER_GH_TOKEN` to Cloudflare as Worker secret `GITHUB_TOKEN`.
- Staging defaults for this repo are:
  - `GITHUB_OWNER=alessandropontini`
  - `GITHUB_REPO=job_seeker`
  - `GITHUB_REF=main`

## Testing Strategy (Current + Planned)
Current tests cover matcher rules, pipeline grouping, source parsing (`remotive`, `wwr`, `arbeitnow`), CLI behavior, and Worker webhook smoke paths. Phase 5 added golden snapshot tests for full pipeline outputs, unit tests for normalization and region loading, and optional online integration tests. Offline runs set `NO_NETWORK=1` to enforce deterministic, no-network behavior; online integration tests are opt-in via `JOB_SCOUT_RUN_INTEGRATION=1` and `-m integration`. External dependency failures (HTTP 403/429, `NO_NETWORK`) are treated as environment limitations, not project defects. Dev-only dependencies are installed via `tools/install_dev_deps.sh`, which attempts PyPI and falls back to a wheelhouse archive specified by `JOB_SCOUT_WHEELHOUSE_URL` for air-gapped environments.

## Region Mapping Design
- Region data lives in `config/regions.json`.
- `job_scout.regions.load_region_data` validates the file at runtime and fails fast if missing or malformed.
- Country aliases are applied consistently in normalization and matching.

## Source Failure Propagation
- Source fetch errors raise explicit exceptions and are surfaced in `out/report.md`.
- The pipeline continues running remaining sources and records a **Source Status** section summarizing counts or errors.
- Live integration tests are opt-in via `JOB_SCOUT_RUN_INTEGRATION=1` and marked with `integration`.
