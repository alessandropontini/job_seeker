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

### 2) Data source integration (future)
**Acceptance Criteria**
- Source connectors listed in config are implemented.
- Each connector respects access restrictions (no scraping behind logins).
- Source runs produce normalized job records.

### Sprint 2: Real sources + matching rules (complete)
**Status:** ✅ Done

**Shipped scope**
- Added Remotive public API connector with fixtures and parser tests.
- Implemented matcher engine for location, role, salary, and remote annotations.
- Expanded pipeline filtering and reporting (CSV columns + Markdown sections).
- Extended CLI flags for strict mode, missing-salary override, and source selection.
- Added matcher, pipeline filtering, and connector tests.

### 3) Matching rules engine (future)
**Acceptance Criteria**
- Location filters enforce EU/Italy/New York and exclude UK.
- Role targeting enforces manager/lead titles.
- Salary filter enforces 52,000 EUR minimum, with missing salary flagged.
- Remote preference applied without excluding non-remote roles by default.

### 4) Notification pipeline (future)
**Acceptance Criteria**
- Notifications can be sent through configured channels (e.g., Telegram).
- Notifications include match rationale and any missing-salary flags.

### 5) Scheduling & observability (future)
**Acceptance Criteria**
- Scheduled daily run with logs for source fetch, match, and notify.
- Failures reported with actionable error summaries.
