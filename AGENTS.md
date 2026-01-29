# Agent Instructions

## Job-Matching Requirements
- Target locations: **EU**, **Italy**, and **New York** only.
- Explicitly **exclude the UK** from all location matching.
- Prefer **full-remote** roles whenever available.
- Focus on **manager** and **lead** roles only.
- Minimum salary: **52,000 EUR**.
  - If salary is missing, keep the job but **flag it as missing salary**.
- **Do not** scrape or access **LinkedIn** or **Indeed** content that is behind logins or paywalls.

## Documentation Rules
- Every code change MUST include documentation updates.
- At minimum, update one or more of:
  - README.md (usage, setup, examples)
  - PLAN.md (progress, completed sprint, next steps)
  - Inline docstrings for public modules and functions
- No sprint is considered complete unless PLAN.md is updated.
- If new commands, config options, outputs, or behaviors are introduced, README.md MUST be updated accordingly.
- Codex should treat documentation as part of the deliverable, not optional.
