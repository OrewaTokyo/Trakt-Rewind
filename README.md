# Trakt-Rewind

[![CI](https://github.com/tokyo720022-create/Trakt-Rewind/actions/workflows/ci.yml/badge.svg)](https://github.com/tokyo720022-create/Trakt-Rewind/actions/workflows/ci.yml)
![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)
![Zero Dependencies](https://img.shields.io/badge/dependencies-zero%20(stdlib%20only)-brightgreen.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Trakt-Rewind** is a fast, zero-dependency Python CLI for searching Trakt, cleaning up messy bulk-sync watch history spikes, backdating episodes realistically using Trakt's actual episode runtimes, managing ratings, and creating offline snapshot backups—without breaking your watch streak.

---

## Features

- **Direct Trakt Global DB Search:** Searches Trakt's full database (exact + fuzzy) and renders a clean status table with **Title Status**, **My Watch Status / Lists**, **My Rating**, **Started Date**, and **Finished Date**.
- **Season & Episode-Wise Browser (`[l]`):** View a Season-by-Season overview (progress %, total runtime, aired range, status) and drill into individual seasons, paginated `all` views, or `u` (unwatched-only) lists.
- **3 Flexible Editing Modes:**
  1. **Manual Day-by-Day:** Walk through dates with weekday/weekend hints, custom start times, and `sync` / `auto` shortcuts.
  2. **Automatic Spread:** Distribute a range of episodes smoothly between a Start Date and Catch-up/Finish Date.
  3. **Watched on Release Date (`[d]` or Mode 3):** Automatically saves each episode's exact original Trakt release date & time while skipping future/unaired episodes.
- **Runtime-Accurate Timestamp Spreading:** Uses every episode's individual Trakt metadata runtime (e.g., `24m`, `42m`, `43m`) as a strict floor so episodes never overlap, with configurable spacing styles (`spread`, `gap`, `binge`) and optional weekday busy-hour windows.
- **Fast Range & Date Input:** Enter `1-3`, `S02E01-S02E05`, `2x1-2x5`, `season 2`, or `all` in one prompt; dates accept `YYYY-MM-DD`, `YYYY/MM/DD`, or `DD-MM-YYYY`.
- **Show Ratings (`[r]`):** Add, update (`1–10`), or remove show ratings directly from the terminal.
- **Local Disk Cache (`trakt_cache.json`):** Near-instant startup using Trakt's `/sync/last_activities` delta check.
- **3 Sync Speeds:** Choose **Update Immediately**, **Quick 1-Confirm**, or **Safe Double-Confirm** (`yes` + `YES`).
- **Offline Snapshot Backups & Restore (`trakt_backups/`):** Quick Account snapshots, Full History snapshots, single-show snapshots (`[k]`), automatic pre-edit backups, and full show restore.

---

## Quick Start

### 1. Create a Free Trakt PKCE App
1. Go to **[https://developer.trakt.tv/apps](https://developer.trakt.tv/apps)** and click **New Application**.
2. Give it a name (e.g., `Trakt-Rewind`).
3. Under **Redirect URI**, add this exact URL:
   ```text
   http://localhost:8765/callback
   ```
4. Save the app and copy your **Client ID** (PKCE apps do not need a Client Secret).

### 2. Clone & Run (Zero `pip install` Needed)
Requires **Python 3.8+** only.

```bash
git clone https://github.com/tokyo720022-create/Trakt-Rewind.git
cd Trakt-Rewind
python trakt_rewind.py
```

On first launch:
1. Paste your **Trakt Client ID** (saved locally to `trakt_config.json`; you can also set the `TRAKT_CLIENT_ID` environment variable).
2. Approve the Trakt PKCE authorization prompt in your browser (saved locally to `trakt_token.json`).

---

## Commands Cheat Sheet

### Main Prompt
| Command | Action |
| :--- | :--- |
| `<show name>` | Search Trakt global DB (e.g., `One Piece`, `The Vampire Diaries`) |
| `backup` | Open Local Snapshot Backup Manager (Quick / Full / List / Restore / Auto-Backup) |
| `cache` | Open Cache & Preferences menu (Cache ON/OFF, Default Sync Speed, Timestamp Spacing) |
| `refresh` | Force a full account library refresh from Trakt |
| `exit` | Quit Trakt-Rewind |

### Show Card Actions
| Key | Action |
| :---: | :--- |
| `e` | Edit or log episode history (Manual Day-by-Day, Automatic Spread, or Release Date) |
| `d` | Quick Release Date — move all watched (or aired) episodes to original air dates |
| `l` | Open Season & Episode-wise browser (`1`, `2`, `0`, `all`, `u`) |
| `r` | Rate show (`1–10`) or remove rating (`0`) |
| `k` | Save an immediate offline backup snapshot of this show's watch history |
| `f` | Force refresh this show's guide & history live from Trakt |
| `b` | Back to search |

---

## Customizing Timezone & Weekday Schedule

`trakt_rewind.py` automatically detects your system's local timezone. To override your timezone or enable custom weekday busy hours (for example, school/college/work hours prior to a specific date), copy `trakt_config.example.json` to `trakt_config.json` (or edit the generated file):

```json
{
  "timezone_offset_minutes": 330,
  "timezone_label": "IST",
  "schedule": {
    "default_window": ["07:00", "22:00"],
    "weekday_busy_cutoff_date": "2025-04-30",
    "weekday_windows_before_cutoff": [["06:00", "07:00"], ["14:00", "22:00"]]
  }
}
```

Leave `"timezone_offset_minutes": null` to auto-detect your system timezone, and `"weekday_busy_cutoff_date": null` to use `default_window` on all days.

---

## Running Tests

```bash
python -m unittest discover -s tests -v
```

## Security & Privacy

Never commit `trakt_token.json`, `trakt_config.json`, `trakt_cache.json`, `trakt_edit_log.json`, or `trakt_backups/`. See [SECURITY.md](SECURITY.md) for full details.

## License

Licensed under the [MIT License](LICENSE).
