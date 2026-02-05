# Changelog

All notable changes to this project will be documented in this file.

## Unreleased
### Added
- Dual-channel reporting: TOP_MATCHES (strict) and DATA_ONLY_BEST_PICKS (wide).
- Telegram feedback buttons with a lightweight preference profile stored locally.
- Stateful daily digest dedupe via `out/last_notified.json`.
- Dry-run Telegram payload output (`out/telegram_payload.json`, `out/digest.md`) for dummy E2E runs.

### Changed
- Telegram digest now includes dual-channel sections and feedback buttons.
- GitHub Actions caches notification state and preference profiles between runs.
- Daily workflow split into real (remotive) and dummy E2E workflows.

### Fixed
- Prevented duplicate daily digests from sending on the same UTC date.
- Fixed empty Telegram digests by persisting the full digest payload in `out/last_run.json`
  and using the daily window digest for notifications.
- Stabilized `last_run.json` digest schema (channel lists + counts aliases) and added a
  fallback digest scope when the 24h window is empty to keep dummy E2E artifacts consistent.

### Breaking changes
- None.
