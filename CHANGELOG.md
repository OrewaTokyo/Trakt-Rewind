# Changelog

All notable changes to **Trakt-Rewind** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-28

### Added
- **Zero-Dependency CLI (`trakt_rewind.py`):** Runs on Python 3.8+ standard library with no external packages.
- **PKCE OAuth 2.0 Authentication:** Browser-based sign-in with local `http://localhost:8765/callback` receiver, automatic token refresh, and `TRAKT_CLIENT_ID` environment variable support.
- **Direct Trakt DB Search & Live Hydration:** Exact + fuzzy show search with structured status table (`Title Status`, `My Watch Status / Lists`, `Rating`, `Started`, `Finished`) hydrated via `/shows/{id}/progress/watched`.
- **Three Watch History Editing Modes:**
  - Manual Day-by-Day with weekday/weekend window prompts and optional manual start times.
  - Automatic Spread across Start Date and Catch-up/Finish Date.
  - Watched on Release Date (`[d]` shortcut or Mode 3) using Trakt's native `watched_at: "released"` with unaired episode protection.
- **Runtime-Accurate Timestamp Spreading:** Strictly enforces each episode's Trakt metadata runtime so consecutive episodes never overlap, with configurable spacing styles (`spread`, `gap`, `binge`) and overflow notices.
- **Season & Episode-Wise Browser (`[l]`):** Season overview table with completion %, total runtime, and aired date range, plus season drilldown, paginated `all`, and `u` unwatched views.
- **Show Ratings (`[r]`):** Add, update (`1–10`), or remove show ratings with optional custom dates.
- **Configurable Sync Speeds:** Choose between `IMMEDIATE`, `QUICK` (1-confirm), and `DOUBLE` (`yes` + `YES`) confirmation modes.
- **Smart Local Disk Cache (`trakt_cache.json`):** Delta verification via `/sync/last_activities` for sub-second startup and cached episode guides.
- **Local Snapshot Backup & Restore (`trakt_backups/`):** Quick Account Snapshots, Full History Snapshots, Single-Show Snapshots (`[k]`), automatic pre-edit snapshots, and double-confirmed Show Restore.
- **Configurable Timezone & Schedules:** Auto-detects system local timezone with optional UTC offset and split weekday schedule overrides in `trakt_config.json`.
- **Automated Testing & CI/CD:** Unit test suite (`tests/test_trakt_rewind.py`), cross-platform GitHub Actions CI + secret-leak guard, and automated tag-based Releases.