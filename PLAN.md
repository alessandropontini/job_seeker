# Daily Job-Matching System Plan

## Milestones & Acceptance Criteria

### 1) Repository scaffolding
**Acceptance Criteria**
- Required documentation files exist: `AGENTS.md`, `PLAN.md`.
- Configuration scaffold exists at `config/config.yaml` with placeholders.
- `.gitignore` includes `out/` and `data/` entries.

### 2) Data source integration (future)
**Acceptance Criteria**
- Source connectors listed in config are implemented.
- Each connector respects access restrictions (no scraping behind logins).
- Source runs produce normalized job records.

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
