# Job Scout — Project Roadmap

## Where We Are Now (Post Phase 3)
- Runnable CLI pipeline that loads config, fetches sources, matches, and writes reports.
- Sources implemented today: `dummy` (offline) and `remotive` (public API).
- Location rules are enforced: EU + Italy + New York are allowed; UK is explicitly rejected.
- Role targeting is enforced: only manager/lead/head titles pass.
- Salary minimum is enforced at 52,000 EUR (with currency conversion when possible).
- Missing salary handling is enforced by strict/allow-missing-salary modes.
- Remote level is normalized and reported; **full-remote preference is recorded as a soft penalty**.
- Outputs are `out/report.csv` and `out/report.md` with Matches / Missing Salary / Rejected.
- Matching results include hard reject reasons, penalties, missing fields, and decision status.

## Target Vision (in one paragraph)
Job Scout evolves into a deterministic decision engine for job opportunities: it ingests multiple sources, applies explicit hard constraints and soft preferences, produces explainable decisions, and (later) ranks results using transparent scoring—without ML or opaque heuristics.

## Architecture at a Glance (ASCII diagram)
```
Sources (dummy, remotive) [today]
  -> Normalize [today]
  -> Match (hard constraints) [today]
  -> Explain (structured reasons) [Phase 3]
  -> Score (deterministic) [Phase 4]
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

## Phase 4 — Scoring & Ranking (PLANNED)
### Objective
Add a deterministic scoring function to rank matches while keeping decisions explainable and reproducible.

### Scope (what it changes conceptually)
Introduce scoring based on weighted preferences and deterministic tie-breaks, without ML.

### Definition of Done (5–8 checkboxes)
- [ ] Deterministic scoring function with documented inputs.
- [ ] Configurable weights for preference signals.
- [ ] Report ordering reflects score and tie-break rules.
- [ ] Scores are included in CSV/Markdown output.
- [ ] Unit tests cover scoring edge cases and tie-breaks.

### Risks addressed (3–5 bullets)
- Non-deterministic ordering across runs.
- Implicit scoring rules that are not documented.
- Overfitting to a single source.

### Non-goals (3–5 bullets)
- No machine learning or model-based ranking.
- No notification system changes.
- No new matching constraints beyond current config.

## Phase 5 — Reliability & Extensibility (PLANNED)
### Objective
Improve reliability through snapshot testing and make source integration more robust and maintainable.

### Scope (what it changes conceptually)
Add golden output tests and refine source abstractions without changing matching semantics.

### Definition of Done (5–8 checkboxes)
- [ ] Snapshot/golden tests for full pipeline outputs.
- [ ] Better source abstraction with consistent normalization rules.
- [ ] Externalized region/country mapping (not hard-coded lists).
- [ ] Error handling for network sources with clear failures.
- [ ] Documentation of source contract and normalization rules.

### Risks addressed (3–5 bullets)
- Undetected regressions in outputs.
- Fragile source parsing and normalization drift.
- Hard-coded geography rules becoming outdated.

### Non-goals (3–5 bullets)
- No new matching rules beyond current scope.
- No automated notifications yet.
- No changes to CLI flags.

## Phase 6 — Automation & Notifications (OPTIONAL / LATER)
### Objective
Automate scheduled runs and deliver notification digests when new high-quality matches appear.

### Scope (what it changes conceptually)
Add scheduling and notification delivery without changing matching or scoring rules.

### Definition of Done (5–8 checkboxes)
- [ ] Scheduled runs (e.g., GitHub Actions cron).
- [ ] Notification digest generation (Telegram optional).
- [ ] Notify only on new or high-scoring items.
- [ ] Opt-in configuration with explicit enablement.
- [ ] Tests or dry-run mode for notifications.

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
