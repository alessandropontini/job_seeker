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

### Sprint 2: Real sources + matching rules (next)
**Planned scope**
- Add first real source connector (non-authenticated, no paywall).
- Implement location/role/salary filtering based on config rules.
- Expand reporting with match rationale and missing salary flags.
- Add source-specific unit tests and regression fixtures.

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
