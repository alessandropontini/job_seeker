# Job Scout — Architecture & Contracts

## System Overview
Job Scout is a deterministic batch pipeline that fetches job postings, applies rule-based matching, and writes CSV/Markdown reports. Core modules:
- `job_scout.__main__`: CLI entry points and argument parsing.
- `job_scout.config`: config loader and defaults.
- `job_scout.sources`: source registry (`dummy`, `remotive`).
- `job_scout.pipeline`: orchestration (fetch, match, group, write).
- `job_scout.matcher`: matching rules + match metadata.
- `job_scout.writers`: CSV/Markdown report writers.
- `job_scout.models`: `JobPosting` data model.

## Pipeline Flow
1. CLI reads config (`job_scout.config.load_config`) and resolves sources (`job_scout.pipeline.run_pipeline`).
2. Each source fetcher returns `JobPosting` items (`job_scout.sources`).
3. `job_scout.matcher.match_posting` evaluates rules and annotates match metadata.
4. `job_scout.pipeline.run_pipeline` groups rows into Matches / Missing Salary / Rejected.
5. `job_scout.writers.write_reports` writes `out/report.csv` and `out/report.md`.

## Key Decision Points (Current)
- Config loading & merge (`job_scout.config.load_config`).
- Source selection & registry lookup (`job_scout.sources.AVAILABLE_SOURCES`).
- `match_posting` evaluation and reject reasons (`job_scout.matcher.match_posting`).
- Grouping into matches/missing/rejected (`job_scout.pipeline.run_pipeline`).
- Report writing (`job_scout.writers.write_reports`).

## Contracts
### Source Contract
A source must provide a callable with signature:
- `fetch_source(since_days: int) -> list[JobPosting]`

Required `JobPosting` fields:
- `id`, `source`, `company`, `title`, `location_text`, `location_country`,
  `remote_type`, `url`, `posted_at`, `salary_text`, `currency`, `tags`.

Normalization expectations:
- `posted_at` must be timezone-aware (`datetime` with tzinfo).
- `location_country` should be a normalized country label when possible.
- `remote_type` should be a raw string; normalization happens in matcher.

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
- `notifications.telegram` — **PLANNED / NOT ENFORCED YET** (disabled by default).

**USED TODAY**: all keys above except `notifications.telegram`.

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

### Scoring Contract (Phase 4 planned)
- Deterministic score function based on configured weights.
- Stable tie-break rules (e.g., newest `posted_at`).
- Scores included in reports and applied consistently.

## Testing Strategy (Current + Planned)
Current tests cover matcher rules, pipeline grouping, and Remotive fixture parsing. Planned in Phase 5: snapshot/golden tests to validate full pipeline outputs across sources and config permutations.
