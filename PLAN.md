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

### Phase 6 — Automation & Notifications (optional)
**Status:** 💤 Optional
**Acceptance Criteria**
- Scheduled runs are supported (e.g., cron or CI schedule).
- Notification digests are opt-in and deterministic.
- Notify only when new or high-scoring items appear.
- Notification tests use fixtures or dry-run mode.
