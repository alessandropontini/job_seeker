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
**Status:** ✅ LIVE — Scheduled daily digest @ 08:00 Europe/Rome with Telegram
**Acceptance Criteria**
- Scheduled GitHub Actions workflow (workflow_dispatch + CET/CEST cron).
- Telegram notifications enabled by default with explicit logs for sent vs skipped.
- Missing/invalid secrets yield warnings without failing the run.
- Daily digest uses the last 24 hours of `posted_at` timestamps in UTC.
- State snapshot tracks notified job IDs and prevents duplicate alerts.

**Recent updates**
- Enabled daily scheduled runs at 08:00 Europe/Rome (CET/CEST-aware cron).
- Enforced daily-window digest logic (last 24h UTC) and always-on Telegram.
- Added snapshot de-duplication across days using notification timestamps.
- Documented live operations and daily digest behavior.

**Phase 6 refinement (current)**
- Added dual-channel outputs: TOP_MATCHES (strict) + DATA_ONLY_BEST_PICKS (wide).
- Implemented Telegram feedback buttons with a lightweight preference profile.
- Added stateful digest dedupe (`last_notified.json`) and cache persistence in Actions.
- Expanded documentation (README + runbook) and refreshed goldens/tests for no regressions.
