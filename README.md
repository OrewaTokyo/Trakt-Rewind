# ⏪ Trakt-Rewind

> Fix messy Trakt watch history spikes without breaking your streak. A fast, zero-dependency Python CLI featuring Trakt DB search, PKCE OAuth login, runtime-accurate timestamp spreading, release-date syncing, local disk caching, and offline snapshot backups.

[![CI](https://github.com/OrewaTokyo/Trakt-Rewind/actions/workflows/ci.yml/badge.svg)](https://github.com/OrewaTokyo/Trakt-Rewind/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![Dependencies](https://img.shields.io/badge/Dependencies-Zero%20(Stdlib%20Only)-brightgreen)
![Auth](https://img.shields.io/badge/Trakt%20API-v2%20%7C%20PKCE%20OAuth-red)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## ✨ Why Trakt-Rewind?

If you have ever imported watch history from another tracker, bulk-synced a long-running anime, or accidentally marked hundreds of episodes watched on a single day, your Trakt calendar and stats end up with massive artificial spikes.

**Trakt-Rewind** lets you search Trakt's global database directly from your terminal and clean up, backfill, or restore your watch history accurately — while preserving your daily watch streak and episode runtimes.

---

## 🚀 Features

* **Zero External Dependencies:** 100% Python standard library (`urllib`, `json`, `http.server`) — no `pip install` needed.
* **Direct Trakt DB Search (Exact + Fuzzy):** Search any show on Trakt (even with typos) and view a structured table showing **Title Status**, **My Watch Status / Lists**, **Rating**, **Started Date**, and **Finished Date**.
* **Three Editing Modes:**
  1. **Manual Day-by-Day:** Prompts day-by-day with weekday/weekend context, episode counts, and optional custom start times.
  2. **Automatic Spread:** Evenly distributes a range of episodes across your chosen Start Date and Catch-up/Finish Date.
  3. **Watched on Release Date:** Uses Trakt's native `watched_at: "released"` per episode so each episode gets its original air date and time (automatically skips unaired/future episodes).
* **Runtime-Accurate Timestamp Spacing:** Reads each episode's actual Trakt metadata length (`24m`, `42m`, `43m`, etc.) as a strict floor so consecutive episodes never overlap, while spreading watches organically across your active hours.
* **Season & Episode-Wise Browser (`[l]`):** View a season-by-season overview table (completion %, total runtime, aired range) and drill into individual seasons, paginated `all`, or `u` unwatched views.
* **Quick Range & Date Shortcuts:** Enter ranges in one step (`1-3`, `S02E01-S02E05`, `2x1-2x5`, `season 2`, `all`) and dates in `YYYY-MM-DD`, `YYYY/MM/DD`, or `DD-MM-YYYY`.
* **Show Ratings (`[r]`):** Add, update (`1–10`), or remove show ratings directly from the CLI, with optional custom rating dates.
* **Configurable Sync Speeds:** Choose **Update Immediately**, **Quick 1-Confirm**, or **Safe Double-Confirm** (`yes` + `YES`).
* **Smart Local Disk Cache (`trakt_cache.json`):** Uses a single `/sync/last_activities` delta check on startup to load your library and episode guides in under a second when nothing changed.
* **Offline Snapshot Backups & Restore (`trakt_backups/`):** Save Quick Account Snapshots, Full History Snapshots, or Single-Show Snapshots (`[k]`), with automatic pre-edit backups enabled by default and double-confirmed Show Restore.

---

## 📋 Prerequisites

* **Python 3.8 or higher** ([python.org/downloads](https://www.python.org/downloads/))
* A **Trakt account** ([trakt.tv](https://trakt.tv))

---

## 🔑 Step 1: Create a Trakt API App (PKCE)

1. Go to **[https://developer.trakt.tv/apps](https://developer.trakt.tv/apps)** and sign in with your Trakt account.
2. Click **Create New App** (or open an existing PKCE app).
3. Configure the app:
   * **Name:** `Trakt-Rewind` (or any name you prefer)
   * **Redirect URI:**
     ```text
     http://localhost:8765/callback
     ```
   * **Sign-in Flow:** **PKCE** *(no Client Secret is needed)*
4. Save your settings, open the **Credentials** tab, and copy your **Client ID**.

> **Important:** Make sure `http://localhost:8765/callback` is saved under **Settings → Redirect URIs** before running the script, or Trakt will reject the browser login callback.

---

## 💻 Step 2: Install & Run

1. Clone this repository:
   ```bash
   git clone https://github.com/OrewaTokyo/Trakt-Rewind.git
   cd Trakt-Rewind
   ```

2. Run **Trakt-Rewind**:
   ```bash
   python trakt_rewind.py
   ```

3. **First-Time Setup:**
   * Paste your **Trakt Client ID** when prompted (or set the `TRAKT_CLIENT_ID` environment variable).
   * Your browser will open Trakt's authorization screen — click **Yes / Allow**.
   * Your OAuth session is stored locally in `trakt_token.json` and auto-refreshes automatically.

---

## 🛠️ Usage Guide

### Main Menu Commands

| Command | Action |
| :--- | :--- |
| `<Show Name>` | Search Trakt DB (exact + fuzzy) and display your status table |
| `backup` | Open the Local Snapshot Backup Manager (Quick, Full, List, Restore) |
| `cache` | Toggle disk cache ON/OFF, clear cache, set default sync speed & timestamp spacing |
| `refresh` | Force a full live refresh of your Trakt library |
| `exit` / `q` | Quit Trakt-Rewind |

### Show Card Shortcuts

| Key | Action |
| :--- | :--- |
| `e` | **Edit / Log History** (Manual Day-by-Day, Automatic Spread, or Release Date) |
| `d` | **Quick Release Date** (Move watched or aired episodes straight to original air dates) |
| `l` | **Seasons / Episodes Browser** (Season overview, episode lists, unwatched filter) |
| `r` | **Rate Show** (`1–10` or `0` to remove rating) |
| `k` | **Backup Show** (Save an instant offline JSON snapshot of this show's history) |
| `f` | **Refresh** (Force live reload of this show's guide and history from Trakt) |
| `b` | **Back** to Search |

### Episode Range Shortcuts
When prompted for **Start or Range**, you can enter:
* `1-5` or `1 to 5` — Episodes 1 through 5
* `S02E01-S02E10` or `2x1-2x10` — Specific season/episode range
* `season 2` — Entire Season 2
* `all` — All loaded episodes
* `s2` or `list` — Browse Season 2 (or first 30 episodes) before choosing

---

## ⚙️ Customizing Timezone & Schedule (`trakt_config.json`)

By default, **Trakt-Rewind** automatically detects your system timezone and spreads watches between `07:00` and `22:00`. You can customize your timezone and optional split weekday hours (e.g. school/college/work) in `trakt_config.json` (see `trakt_config.example.json`):

```json
{
  "client_id": "YOUR_TRAKT_PKCE_CLIENT_ID",
  "cache_enabled": true,
  "default_sync_mode": "ask",
  "timestamp_style": "spread",
  "auto_backup_before_edit": true,
  "timezone_offset_minutes": 330,
  "timezone_label": "IST",
  "schedule": {
    "default_window": ["07:00", "22:00"],
    "weekday_busy_cutoff_date": "2025-04-30",
    "weekday_windows_before_cutoff": [
      ["06:00", "07:00"],
      ["14:00", "22:00"]
    ]
  }
}
```

---

## 🧪 Running Tests

Run the built-in zero-dependency unit test suite:

```bash
python -m unittest discover -s tests -v
```

---

## 🤝 Contributing & Security

* See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on submitting pull requests or reporting issues.
* See [SECURITY.md](SECURITY.md) for token safety practices and vulnerability reporting.

## 📄 License

Released under the [MIT License](LICENSE).