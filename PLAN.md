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

### Phase 3 — Decision Engine (next)
**Status:** ⏳ Planned
**Acceptance Criteria**
- Hard constraints and soft preferences are separated in decision logic.
- Structured decision reasons are produced for accept/reject/preference.
- Deterministic ordering for decision reasons and report rows.
- Reports remain compatible with existing CSV/Markdown formats.
- Unit tests cover decision rationale structure and determinism.
- Documentation updated to reflect the decision engine contract.

### Phase 4 — Scoring & Ranking
**Status:** ⏳ Planned
**Acceptance Criteria**
- Deterministic scoring function with documented inputs.
- Configurable weights for preference signals (no ML).
- Report ordering reflects score plus deterministic tie-breaks.
- Scores are included in CSV/Markdown outputs.
- Unit tests cover scoring edge cases and tie-break rules.

### Phase 5 — Reliability & Extensibility
**Status:** ⏳ Planned
**Acceptance Criteria**
- Snapshot/golden tests validate end-to-end pipeline outputs.
- Source normalization contract is documented and enforced.
- Region/country mapping is externalized from hard-coded lists.
- Network source errors are handled with clear error messages.
- Docs updated with source contract and failure modes.

### Phase 6 — Automation & Notifications (optional)
**Status:** 💤 Optional
**Acceptance Criteria**
- Scheduled runs are supported (e.g., cron or CI schedule).
- Notification digests are opt-in and deterministic.
- Notify only when new or high-scoring items appear.
- Notification tests use fixtures or dry-run mode.
