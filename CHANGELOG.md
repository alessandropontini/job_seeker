# Changelog

All notable changes to this project will be documented in this file.

## Unreleased
### Added
- Dual-channel reporting: TOP_MATCHES (strict) and DATA_ONLY_BEST_PICKS (wide).
- Telegram feedback buttons with a lightweight preference profile stored locally.
- Stateful daily digest dedupe via `out/last_notified.json`.

### Changed
- Telegram digest now includes dual-channel sections and feedback buttons.
- GitHub Actions caches notification state and preference profiles between runs.

### Fixed
- Prevented duplicate daily digests from sending on the same UTC date.

### Breaking changes
- None.
