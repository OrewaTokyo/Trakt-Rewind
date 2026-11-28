# Changelog

All notable changes to **Trakt-Rewind** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-27

### Added
- **PKCE OAuth Login:** Secure browser authentication without needing a Client Secret, with automatic local token caching and refresh.
- **Direct Trakt Global DB Search:** Exact + fuzzy show search displaying a structured status table (`Name`, `Title Status`, `My Watch Status / Lists`, `Rating`, `Started`, `Finished`) with live progress hydration.
- **Season & Episode-Wise Browser (`[l]`):** Season-by-season overview table (progress %, total runtime, aired date range, status) plus per-season, paginated `all`, and `u` (unwatched-only) episode tables.
- **3 Watch-History Editing Modes:**
  - **Manual Day-by-Day:** Prompts day-by-day with weekday/weekend schedule hints, optional manual start times, and mid-session `sync` or `auto` handoff.
  - **Automatic Spread:** Evenly distributes episodes from a Start Date to a Catch-up/Finish Date.
  - **Watched on Release Date (`[d]` or Mode 3):** Sets each episode to Trakt's native `"watched_at": "released"` air date while automatically skipping future/unaired episodes.
- **Runtime-Accurate Timestamp Engine:** Reads every episode's individual Trakt metadata length so consecutive episodes never overlap, with configurable spacing styles (`spread`, `gap`, `binge`), auto-detected local timezone, and optional weekday busy-hour schedules in `trakt_config.json`.
- **Flexible Range & Date Input:** Supports `1-3`, `S02E01-S02E05`, `2x1-2x5`, `season 2`, `all`, and `YYYY-MM-DD` / `DD-MM-YYYY` dates.
- **Show Ratings (`[r]`):** Add, update (`1–10`), or remove show ratings directly from the CLI.
- **Local Disk Cache (`trakt_cache.json`):** Fast startup using Trakt's `/sync/last_activities` delta check with smart partial refreshes and an interactive `cache` management menu.
- **3 Sync Speeds:** Choose between `Update Immediately`, `Quick 1-Confirm`, or `Safe Double-Confirm`.
- **Local Snapshot Backups (`trakt_backups/`):** Quick Account snapshots, Full History snapshots, single-show snapshots (`[k]`), automatic pre-edit backups, and safe show history restoration.
- **CI & Open-Source Polish:** Cross-platform GitHub Actions test matrix (Ubuntu, Windows, macOS), automated tagged releases, unit test suite, issue/PR templates, and `SECURITY.md`.
