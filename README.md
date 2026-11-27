# 🎬 Trakt-Chrono

> A fast, zero-dependency Python CLI for fixing, backdating, and managing Trakt watch history — featuring PKCE OAuth login, runtime-aware timestamp spreading, release-date syncing, local disk caching, and offline snapshot backups.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![Dependencies](https://img.shields.io/badge/Dependencies-Zero%20(Stdlib%20Only)-brightgreen)
![Auth](https://img.shields.io/badge/Trakt%20API-v2%20%7C%20PKCE%20OAuth-red)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

---

## ✨ Why Use Trakt-Chrono?

If you have ever imported watch history from another tracker, synced a long-running anime in bulk, or accidentally logged hundreds of episodes on a single day, your Trakt calendar and stats end up with massive artificial spikes.

**Trakt-Chrono** lets you search the Trakt database directly from your terminal and clean up or backfill your watch history accurately — without breaking your daily watch streak or losing completion progress.

---

## 🚀 Features

* **Zero External Dependencies:** Built 100% with Python's standard library (`urllib`, `json`, `http.server`) — no `pip install` required.
* **Direct Trakt DB Search (Exact + Fuzzy):** Search any show on Trakt (even with typos) and view a structured status table showing **Title Status**, **My Watch Status / Lists**, **Rating**, **Started Date**, and **Finished Date**.
* **Three Flexible Editing Modes:**
  1. **Manual Day-by-Day:** Prompts day-by-day with weekday/weekend schedule context, episode counts, and optional custom start times.
  2. **Automatic Spread:** Evenly distributes an episode range across your chosen Start Date and Catch-up/Finish Date.
  3. **Watched on Release Date:** Uses Trakt's native `watched_at: "released"` per episode so each episode gets its original air date and time (automatically skips unaired/future episodes).
* **Runtime-Accurate Timestamp Spacing:** Reads each episode's actual Trakt metadata length (`24m`, `42m`, `43m`, etc.) as a strict floor so consecutive episodes never overlap, while naturally spreading watches across your active hours.
* **Season & Episode-Wise Browser (`[l]`):** View a season-by-season progress table (completion %, total runtime, aired date range) and drill into individual seasons, paginated episode lists, or unwatched-only views.
* **Quick Range & Date Shortcuts:** Enter ranges in one step (`1-3`, `S02E01-S02E05`, `2x1-2x5`, `season 2`, `all`) and dates in `YYYY-MM-DD` or `DD-MM-YYYY`.
* **Show Ratings (`[r]`):** Add, update (`1–10`), or remove show ratings directly from the CLI, with optional custom rating dates.
* **Configurable Sync Speeds:** Choose between **Update Immediately**, **Quick 1-Confirm**, or **Safe Double-Confirm** (`yes` + `YES`).
* **Smart Local Disk Cache (`trakt_cache.json`):** Uses a single `/sync/last_activities` delta check on startup to load your library and episode guides in under a second when nothing has changed.
* **Local Snapshot Backups & Restore (`trakt_backups/`):** Save offline Quick Account Snapshots, Full History Snapshots, or Single-Show Snapshots (`[k]`), with automatic pre-edit backups enabled by default and double-confirmed Show Restore.

---

## 📋 Prerequisites

* **Python 3.8 or higher** ([python.org/downloads](https://www.python.org/downloads/))
* A **Trakt account** ([trakt.tv](https://trakt.tv))

---

## 🔑 Step 1: Create a Trakt API App (PKCE)

1. Go to **[https://developer.trakt.tv/apps](https://developer.trakt.tv/apps)** and sign in with your Trakt account.
2. Click **Create New App** (or open an existing PKCE app).
3. Fill in the app details:
   * **Name:** `Trakt-Chrono` (or any name you like)
   * **Redirect URI:**
     ```text
     http://localhost:8765/callback
     ```
   * **Authentication / Sign-in Flow:** **PKCE** *(no Client Secret is needed)*
4. Save the app, then open the **Credentials** tab and copy your **Client ID**.

> **Note:** Make sure `http://localhost:8765/callback` is saved under your app's **Settings → Redirect URIs** before running the script, otherwise Trakt will reject the browser login callback.

---

## 💻 Step 2: Install & Run

1. Clone this repository (or download the Python script):
   ```bash
   git clone https://github.com/<your-username>/Trakt-Chrono.git
   cd Trakt-Chrono
   ```

2. Run the script:
   ```bash
   python trakt_history_editor.py
   ```

3. **First-Time Setup:**
   * Paste your **Trakt Client ID** when prompted (saved locally to `trakt_config.json`).
   * Your browser will open Trakt's authorization screen — click **Yes / Allow**.
   * Your OAuth token is saved locally to `trakt_token.json` and auto-refreshes on future runs.

---

## 🛠️ Usage Guide

### Main Menu Commands
At the main search prompt, type any **Show Name** to search Trakt DB, or use these commands:

| Command | Action |
| :--- | :--- |
| `<Show Name>` | Search Trakt DB (exact + fuzzy) and display your status table |
| `backup` | Open the Local Snapshot Backup Manager (Quick, Full, List, Restore) |
| `cache` | Toggle disk cache ON/OFF, clear cache, set default sync speed & timestamp spacing |
| `refresh` | Force a full live refresh of your Trakt library |
| `exit` / `q` | Quit the application |

### Show Card Shortcuts
After selecting a show from the search table:

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
When prompted for **Start or Range**, you can type:
* `1-5` or `1 to 5` — Episodes 1 through 5
* `S02E01-S02E10` or `2x1-2x10` — Specific season/episode range
* `season 2` — Entire Season 2
* `all` — All loaded episodes
* `s2` or `list` — Preview Season 2 (or first 30 episodes) right before choosing

---

## ⚙️ Customizing Schedule & Timezone

By default, the script formats timestamps in **IST (`UTC+5:30`)** and uses two customizable daily schedule profiles inside the configuration header at the top of the script:
* `IST = timezone(timedelta(hours=5, minutes=30))` — Change to your local UTC offset.
* `COLLEGE_CUTOFF = date(2025, 4, 30)` — Optional cutoff date for split weekday schedules vs. all-day schedules.
* **Spacing Style (`cache` → Option `5`):** Switch anytime between `SPREAD` (full-day natural gaps, default), `GAP` (`15–45m` breaks), or `BINGE` (`1–5m` breaks).

---

## 📂 Local Files & `.gitignore`

The script creates local files in its working directory to store your preferences, OAuth session, cache, logs, and offline backups. **Do not commit these files to a public repository:**

```gitignore
trakt_config.json
trakt_token.json
trakt_cache.json
trakt_cache.json.tmp
trakt_edit_log.json
trakt_backups/
__pycache__/
*.pyc
```

---

## 🤝 Contributing

Issues, bug reports, and pull requests are welcome! If you find an issue with Trakt API pagination, timestamp calculation, or restore handling, please open an issue with steps to reproduce.

## 📄 License

This project is open-source and available under the **MIT License**.