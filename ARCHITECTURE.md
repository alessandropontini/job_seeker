# Job Scout — Architecture & Contracts

## System Overview
Job Scout is a deterministic batch pipeline that fetches job postings, applies rule-based matching, and writes CSV/Markdown reports. Core modules:
- `job_scout.__main__`: CLI entry points and argument parsing.
- `job_scout.config`: config loader and defaults.
- `job_scout.sources`: source registry (`dummy`, `remotive`).
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

## Key Decision Points (Current)
- Config loading & merge (`job_scout.config.load_config`).
- Source selection & registry lookup (`job_scout.sources.AVAILABLE_SOURCES`).
- `match_posting` evaluation and reject reasons (`job_scout.matcher.match_posting`).
- Grouping into matches/missing/rejected (`job_scout.pipeline.run_pipeline`).
- Report writing (`job_scout.writers.write_reports`).

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
- `notifications.telegram.top_n` — max jobs included in a digest.
- `notifications.telegram.min_score` — minimum score to notify.
- `notifications.telegram.min_score_improvement` — minimum score delta to notify.

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

## Testing Strategy (Current + Planned)
Current tests cover matcher rules, pipeline grouping, and Remotive fixture parsing. Phase 5 added golden snapshot tests for full pipeline outputs, unit tests for normalization and region loading, and optional online integration tests. Offline runs set `NO_NETWORK=1` to enforce deterministic, no-network behavior; online integration tests are opt-in via `JOB_SCOUT_RUN_INTEGRATION=1` and `-m integration`. External dependency failures (HTTP 403/429, `NO_NETWORK`) are treated as environment limitations, not project defects. Dev-only dependencies are installed via `tools/install_dev_deps.sh`, which attempts PyPI and falls back to a wheelhouse archive specified by `JOB_SCOUT_WHEELHOUSE_URL` for air-gapped environments.

## Region Mapping Design
- Region data lives in `config/regions.json`.
- `job_scout.regions.load_region_data` validates the file at runtime and fails fast if missing or malformed.
- Country aliases are applied consistently in normalization and matching.

## Source Failure Propagation
- Source fetch errors raise explicit exceptions and are surfaced in `out/report.md`.
- The pipeline continues running remaining sources and records a **Source Status** section summarizing counts or errors.
- Live integration tests are opt-in via `JOB_SCOUT_RUN_INTEGRATION=1` and marked with `integration`.
