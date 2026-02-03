# Job Scout — Project Roadmap

## Where We Are Now (Phase 6 Validation)
- Phases 1–5 (rules, explainability, hard/soft separation, scoring, QA hardening) are complete.
- Runnable CLI pipeline that loads config, fetches sources, matches, and writes reports.
- Sources implemented today: `dummy` (offline) and `remotive` (public API).
- Location rules are enforced: EU + Italy + New York are allowed; UK is explicitly rejected.
- Role targeting is enforced: only manager/lead/head titles pass.
- Salary minimum is enforced at 52,000 EUR (with currency conversion when possible).
- Missing salary handling is enforced by strict/allow-missing-salary modes.
- Remote level is normalized and reported; **full-remote preference is recorded as a soft penalty**.
- Outputs are `out/report.csv` and `out/report.md` with Matches / Missing Salary / Rejected.
- Matching results include hard reject reasons, penalties, missing fields, and decision status.
- Scoring is deterministic, configurable, and applied to accepted postings for ranking.
- Offline tests are deterministic and run with `NO_NETWORK=1`; online integration tests are opt-in.
- Phase 6 is in validation: manual-only automation with Telegram notifications always enabled.
- Phase 5 QA notes confirm deterministic outputs, golden snapshot tests, and offline support.

## Target Vision (in one paragraph)
Job Scout evolves into a deterministic decision engine for job opportunities: it ingests multiple sources, applies explicit hard constraints and soft preferences, produces explainable decisions, and (later) ranks results using transparent scoring—without ML or opaque heuristics.

## Architecture at a Glance (ASCII diagram)
```
Sources (dummy, remotive) [today]
  -> Normalize [today]
  -> Match (hard constraints) [today]
  -> Explain (structured reasons) [Phase 3]
  -> Score (deterministic) [today]
  -> Report (csv/md) [today]
  -> Notify (future) [Phase 6]
```

## Phase 3 — Decision Engine (DONE)
### Objective
Formalize the decision layer by splitting hard constraints from soft preferences and producing structured, explainable outcomes without introducing scoring.

### Scope (what it changes conceptually)
Introduce a clear internal contract for decision reasons (accept, reject, preference), while preserving existing reports and CLI behavior.

### Definition of Done (5–8 checkboxes)
- [x] Explicit separation of hard constraints vs soft preferences in decision logic.
- [x] Structured rationale fields for accept/reject/preference outcomes.
- [x] Reports can surface structured reasons without changing report formats.
- [x] Deterministic ordering of reasons and output rows.
- [x] Unit tests validate rationale structure and determinism.
- [x] Documentation updated to reflect decision engine contract.

### Risks addressed (3–5 bullets)
- Ambiguous or inconsistent rejection reasons.
- Hidden preference logic that is not explainable.
- Difficulty validating decisions in tests.

### Non-goals (3–5 bullets)
- No scoring or ranking (reserved for Phase 4).
- No new sources or external integrations.
- No UI or dashboards.

## Phase 2 — Decision Transparency & Explainability (DONE)
### Objective
Make accept/reject decisions explainable with structured rationale fields and reports.

### Scope (what it changes conceptually)
Add explainability outputs without changing acceptance rules or adding scoring.

### Definition of Done (5–8 checkboxes)
- [x] Match results include decision status and rationale fields.
- [x] Reports include human-readable rationale and missing field visibility.
- [x] Backward compatibility for existing outputs preserved.
- [x] Tests validate decision transparency behavior.

### Non-goals (3–5 bullets)
- No scoring or ranking.
- No new rule enforcement beyond Phase 1.

## Phase 1 — Rule Definition & Enforcement (DONE)
### Objective
Define and enforce deterministic hard rules for location, role, salary, and required fields.

### Scope (what it changes conceptually)
Introduce strict vs non-strict matching with explicit hard reject reasons.

### Definition of Done (5–8 checkboxes)
- [x] Hard constraints enforce location, role, and salary rules deterministically.
- [x] Missing required fields produce explicit reject reasons.
- [x] Strict vs non-strict modes are supported and tested.
- [x] Rule enforcement covered by unit tests.

### Non-goals (3–5 bullets)
- No scoring or ranking.
- No notification automation.

## Phase 4 — Scoring & Ranking (DONE)
### Objective
Add a deterministic scoring function to rank matches while keeping decisions explainable and reproducible.

### Scope (what it changes conceptually)
Introduce scoring based on weighted preferences and deterministic tie-breaks, without ML.

### Definition of Done (5–8 checkboxes)
- [x] Deterministic scoring function with documented inputs.
- [x] Configurable weights for preference signals.
- [x] Report ordering reflects score and tie-break rules.
- [x] Scores are included in CSV/Markdown output.
- [x] Unit tests cover scoring edge cases and tie-breaks.

### Risks addressed (3–5 bullets)
- Non-deterministic ordering across runs.
- Implicit scoring rules that are not documented.
- Overfitting to a single source.

### Non-goals (3–5 bullets)
- No machine learning or model-based ranking.
- No notification system changes.
- No new matching constraints beyond current config.

## Phase 5 — Reliability & Extensibility (DONE)
### Objective
Improve reliability through snapshot testing and make source integration more robust and maintainable.

### Scope (what it changes conceptually)
Add golden output tests and refine source abstractions without changing matching semantics.

### Definition of Done (5–8 checkboxes)
- [x] Snapshot/golden tests for full pipeline outputs.
- [x] Better source abstraction with consistent normalization rules.
- [x] Externalized region/country mapping (not hard-coded lists).
- [x] Error handling for network sources with clear failures and no-network guardrails.
- [x] Documentation of source contract and normalization rules.
- [x] Offline CI run with network disabled; integration tests are opt-in.
- [x] Deterministic pipeline outputs validated with offline execution support.
- [x] External dependency failures (HTTP 403/429, `NO_NETWORK`) documented as environment limitations.

### Risks addressed (3–5 bullets)
- Undetected regressions in outputs.
- Fragile source parsing and normalization drift.
- Hard-coded geography rules becoming outdated.

### Non-goals (3–5 bullets)
- No new matching rules beyond current scope.
- No automated notifications yet.
- No changes to CLI flags.

## Phase 6 — Automation & Notifications (IN VALIDATION — Telegram always enabled, manual trigger only)
### Objective
Enable manual runs that deliver notification digests when new high-quality matches appear.

### Scope (what it changes conceptually)
Add manual-only automation and notification delivery without changing matching or scoring rules.

### Definition of Done (5–8 checkboxes)
- [x] Manual-only runs (GitHub Actions workflow_dispatch only).
- [x] Notification digest generation (Telegram enabled by default).
- [x] Notify only on new or improved/high-scoring items.
- [x] Clear logs when notifications are sent or skipped (with reasons).
- [x] Unit tests for diff logic + notification formatting (no network).

### Risks addressed (3–5 bullets)
- Spamming notifications without relevance.
- Non-deterministic digests.
- Hidden network calls in tests.

### Non-goals (3–5 bullets)
- No additional UI or dashboards.
- No ML-based recommendations.
- No scraping behind logins.

## “Good Enough” Stopping Point
The project is “done enough” when multiple sources are supported, the decision engine is deterministic and explainable, scoring is deterministic with documented weights, and outputs are stable across runs. Automated digests are optional but desirable once scoring is in place.
