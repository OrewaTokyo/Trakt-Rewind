#!/usr/bin/env python3
"""
Trakt-Rewind (v1.0.0)
Zero-dependency Python CLI for fixing, backdating, rating, and backing up
Trakt watch history.

Features:
- PKCE OAuth login (no Client Secret required) with local token refresh
- Direct Trakt global DB search (exact + fuzzy) with live-hydrated progress
- Season & Episode-wise interactive browser ([l]) with progress %, runtimes & air dates
- 3 Editing Modes:
    1) Manual Day-by-Day (custom or auto-spread timestamps)
    2) Automatic Spread (Start Date -> Catch-up/Finish Date)
    3) Watched on Release Date (Trakt native original air dates, skips unaired)
- Runtime-accurate timestamp engine: honors every episode's Trakt metadata length
- Configurable timezone & optional weekday busy-hour windows via trakt_config.json
- Local disk cache (trakt_cache.json) with /sync/last_activities delta check
- 3 Sync Speeds: Update Immediately, Quick 1-Confirm, or Safe Double-Confirm
- Local Snapshot Backup & Restore system (trakt_backups/) with auto-backup before edits
- Zero external dependencies (Python 3.8+ standard library only)
"""
import os
import re
import sys
import json
import time
import base64
import hashlib
import secrets
import random
import webbrowser
import urllib.parse
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, date, timedelta, timezone

# Prevent Windows console Unicode crashes on titles like "Pokémon" or "Shippūden"
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ================= CONFIGURATION =================
__version__ = "1.0.0"

DEFAULT_CLIENT_ID = ""  # Never hardcode personal credentials; set via setup prompt or TRAKT_CLIENT_ID env var
REDIRECT_URI = "http://localhost:8765/callback"
API_BASE = "https://api.trakt.tv"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "trakt_config.json")
TOKEN_FILE = os.path.join(SCRIPT_DIR, "trakt_token.json")
CACHE_FILE = os.path.join(SCRIPT_DIR, "trakt_cache.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "trakt_edit_log.json")
BACKUP_DIR = os.path.join(SCRIPT_DIR, "trakt_backups")

DEFAULT_BATCH_SIZE = 15
DEFAULT_RELEASE_BATCH_SIZE = 100
PAGE_LIMIT = 250  # Trakt 2026 max pagination limit

# Cache TTLs (seconds)
SHOW_GUIDE_TTL_RETURNING = 7 * 24 * 3600   # 7 days for ongoing/returning shows
SHOW_GUIDE_TTL_ENDED = 30 * 24 * 3600      # 30 days for ended/canceled shows
SHOW_HISTORY_TTL = 24 * 3600               # 24 hours (also auto-invalidated on sync/last_activities)
# =================================================

CLIENT_ID = os.environ.get("TRAKT_CLIENT_ID", DEFAULT_CLIENT_ID).strip()
APP_CONFIG = {
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "cache_enabled": True,
    "default_sync_mode": "ask",       # "ask", "immediate", "quick", "double"
    "timestamp_style": "spread",      # "spread" (day-wide w/ gaps), "gap" (15-45m), "binge" (1-5m)
    "auto_backup_before_edit": True,  # Automatically snapshot show history before modifying it
    "timezone_offset_minutes": None,  # null = auto-detect system local timezone (e.g. 330 for IST +05:30)
    "timezone_label": "",             # Optional short label (e.g. "IST", "EST", "UTC")
    "schedule": {
        "default_window": ["07:00", "22:00"],
        "weekday_busy_cutoff_date": None,  # Optional YYYY-MM-DD (e.g. "2025-04-30") for weekday school/work schedule
        "weekday_windows_before_cutoff": [["06:00", "07:00"], ["14:00", "22:00"]],
    },
}


def get_local_tz():
    """Returns configured timezone offset or auto-detected local system timezone."""
    offset_min = APP_CONFIG.get("timezone_offset_minutes")
    if isinstance(offset_min, (int, float)):
        return timezone(timedelta(minutes=int(offset_min)))
    local_tz = datetime.now().astimezone().tzinfo
    return local_tz if local_tz is not None else timezone.utc


def get_tz_label():
    """Returns a short readable timezone label for terminal output."""
    custom = (APP_CONFIG.get("timezone_label") or "").strip()
    if custom:
        return custom
    tz = get_local_tz()
    name = datetime.now(tz).tzname() or "LOCAL"
    return name if len(name) <= 6 else "LOCAL"


IST = get_local_tz()  # Dynamic alias refreshed after config load


# ----------------- CONFIG MANAGEMENT -------------
def save_app_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(APP_CONFIG, f, indent=2)


def load_or_setup_config():
    global CLIENT_ID, IST
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if isinstance(cfg.get("schedule"), dict):
                merged_sched = dict(APP_CONFIG["schedule"])
                merged_sched.update(cfg["schedule"])
                cfg["schedule"] = merged_sched
            APP_CONFIG.update(cfg)
            IST = get_local_tz()
            env_cid = os.environ.get("TRAKT_CLIENT_ID", "").strip()
            if env_cid:
                CLIENT_ID = env_cid
                return APP_CONFIG
            if APP_CONFIG.get("client_id"):
                CLIENT_ID = APP_CONFIG["client_id"].strip()
                return APP_CONFIG
        except Exception:
            pass

    env_cid = os.environ.get("TRAKT_CLIENT_ID", "").strip()
    if env_cid:
        CLIENT_ID = env_cid
        APP_CONFIG["client_id"] = CLIENT_ID
        IST = get_local_tz()
        save_app_config()
        return APP_CONFIG

    print("=== TRAKT-REWIND FIRST-TIME SETUP ===")
    print("1. Create a free PKCE app at: https://developer.trakt.tv/apps")
    print(f"2. Add Redirect URI:          {REDIRECT_URI}")
    print("3. Copy your Client ID and paste it below.\n")
    while True:
        entered = input("Paste your Trakt Client ID: ").strip()
        if entered:
            CLIENT_ID = entered
            break
        print("  Client ID cannot be empty. Visit https://developer.trakt.tv/apps to create one.")

    APP_CONFIG["client_id"] = CLIENT_ID
    APP_CONFIG["redirect_uri"] = REDIRECT_URI
    APP_CONFIG.setdefault("cache_enabled", True)
    APP_CONFIG.setdefault("default_sync_mode", "ask")
    APP_CONFIG.setdefault("timestamp_style", "spread")
    APP_CONFIG.setdefault("auto_backup_before_edit", True)
    IST = get_local_tz()
    save_app_config()
    print(f"Saved config to {os.path.basename(CONFIG_FILE)}.\n")
    return APP_CONFIG


# ----------------- API & AUTH --------------------
def api_request(method, endpoint, payload=None, access_token=None, return_headers=False):
    url = f"{API_BASE}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": CLIENT_ID,
        "User-Agent": "Trakt-Rewind/1.0.0",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    data = json.dumps(payload).encode("utf-8") if payload is not None else None

    retries = 0
    while True:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                parsed = json.loads(raw) if raw.strip() else {}
                norm_headers = {k.lower(): v for k, v in resp.headers.items()}
                if return_headers:
                    return resp.status, parsed, norm_headers
                return resp.status, parsed
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            norm_headers = {k.lower(): v for k, v in e.headers.items()}
            if e.code == 429:
                wait = int(norm_headers.get("retry-after", 5))
                print(f"  [Rate Limit 429] Waiting {wait + 1}s...")
                time.sleep(wait + 1)
                continue
            if e.code in (500, 502, 503, 504) and retries < 3:
                retries += 1
                print(f"  [Server {e.code}] Retrying ({retries}/3)...")
                time.sleep(2 * retries)
                continue
            if return_headers:
                return e.code, body, norm_headers
            return e.code, body
        except urllib.error.URLError as e:
            if retries < 3:
                retries += 1
                print(f"  [Network Error] {e.reason} — Retrying ({retries}/3)...")
                time.sleep(2 * retries)
                continue
            raise


def fetch_all_pages(base_endpoint, token, limit=PAGE_LIMIT):
    """Fetches every page of a paginated Trakt endpoint safely."""
    all_items = []
    page = 1
    sep = "&" if "?" in base_endpoint else "?"
    while True:
        url = f"{base_endpoint}{sep}page={page}&limit={limit}"
        s, data, headers = api_request("GET", url, access_token=token, return_headers=True)
        if s != 200:
            raise RuntimeError(f"GET {url} failed ({s}): {data}")
        if not isinstance(data, list) or not data:
            break
        all_items.extend(data)
        page_count_str = headers.get("x-pagination-page-count")
        if page_count_str is not None:
            if page >= int(page_count_str):
                break
        else:
            break
        page += 1
        time.sleep(0.15)
    return all_items


def load_or_authenticate():
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                tok = json.load(f)
            saved_cid = tok.get("client_id")
            if saved_cid and saved_cid != CLIENT_ID:
                print("Client ID changed — starting fresh Trakt login...")
            else:
                expires_at = tok.get("created_at", 0) + tok.get("expires_in", 0) - 300
                if tok.get("access_token") and time.time() < expires_at:
                    s, _ = api_request("GET", "/users/settings", access_token=tok["access_token"])
                    if s == 200:
                        return tok["access_token"]
                if tok.get("refresh_token"):
                    print("Refreshing Trakt access token...")
                    s, res = api_request("POST", "/oauth/token", {
                        "refresh_token": tok["refresh_token"],
                        "client_id": CLIENT_ID,
                        "redirect_uri": REDIRECT_URI,
                        "grant_type": "refresh_token",
                    })
                    if s == 200 and "access_token" in res:
                        res["created_at"] = int(time.time())
                        res["client_id"] = CLIENT_ID
                        with open(TOKEN_FILE, "w", encoding="utf-8") as out:
                            json.dump(res, out, indent=2)
                        return res["access_token"]
        except Exception:
            pass

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")

    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    auth_url = f"https://trakt.tv/oauth/authorize?{params}"
    auth_code = {"value": None}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in query:
                auth_code["value"] = query["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h2>Trakt authorized! You can close this tab and return to the terminal.</h2>")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Authorization failed or cancelled.")

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("localhost", 8765), CallbackHandler)
    print("\n=== TRAKT PKCE AUTHORIZATION ===")
    print("Opening browser... If it does not open, paste this URL into your browser:\n")
    print(auth_url + "\n")
    webbrowser.open(auth_url)

    while auth_code["value"] is None:
        server.handle_request()
    server.server_close()

    status, res = api_request("POST", "/oauth/token", {
        "code": auth_code["value"],
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    })
    if status != 200:
        raise RuntimeError(f"Token exchange failed ({status}): {res}")

    res["created_at"] = int(time.time())
    res["client_id"] = CLIENT_ID
    with open(TOKEN_FILE, "w", encoding="utf-8") as out:
        json.dump(res, out, indent=2)
    print("Authenticated and saved token locally!\n")
    return res["access_token"]


# ----------------- TIME & FORMAT HELPERS ---------
def to_ist(iso_str):
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(get_local_tz())


def short_date_ist(iso_str):
    if not iso_str:
        return "-"
    try:
        return to_ist(iso_str).strftime("%Y-%m-%d")
    except Exception:
        return "-"


def is_future_airdate(iso_str):
    if not iso_str:
        return False
    try:
        dt_utc = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt_utc > datetime.now(timezone.utc)
    except Exception:
        return False


def truncate(text, width):
    text = str(text or "")
    return text if len(text) <= width else text[: width - 1] + "…"


def ep_code(ep):
    return f"S{ep['season']:02d}E{ep['number']:02d}"


def ep_label(ep, max_title=36):
    title = (ep.get("title") or "").strip() or "Untitled"
    return f"{ep_code(ep)} — {truncate(title, max_title)}"


def format_age(epoch_sec):
    if not epoch_sec:
        return "unknown"
    delta = max(0, int(time.time() - epoch_sec))
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h {(delta % 3600) // 60}m ago"
    return f"{delta // 86400}d ago"


def format_duration(total_minutes):
    total_minutes = int(round(total_minutes or 0))
    if total_minutes <= 0:
        return "0m"
    h, m = divmod(total_minutes, 60)
    if h and m:
        return f"{h}h {m:02d}m"
    if h:
        return f"{h}h 00m"
    return f"{m}m"


# ----------------- LOCAL DISK CACHE --------------
def empty_cache():
    return {
        "version": 6,
        "saved_at": 0,
        "last_activities": {},
        "watched": {},        # int tid -> dict
        "ratings": {},        # int tid -> dict
        "watchlist": set(),   # set of int tid
        "favorites": set(),   # set of int tid
        "custom_lists": {},   # int tid -> [list_names]
        "show_guides": {},    # int tid -> {"fetched_at": ts, "status": str, "seasons": [...]}
        "show_histories": {}, # int tid -> {"fetched_at": ts, "items": [...]}
        "search_mem": {},     # in-memory only (not saved to disk)
    }


def save_cache_to_disk(cache):
    if not APP_CONFIG.get("cache_enabled", True):
        return
    try:
        payload = {
            "version": 6,
            "saved_at": int(time.time()),
            "last_activities": cache.get("last_activities", {}),
            "watched": {str(k): v for k, v in cache.get("watched", {}).items()},
            "ratings": {str(k): v for k, v in cache.get("ratings", {}).items()},
            "watchlist": sorted(cache.get("watchlist", set())),
            "favorites": sorted(cache.get("favorites", set())),
            "custom_lists": {str(k): v for k, v in cache.get("custom_lists", {}).items()},
            "show_guides": {str(k): v for k, v in cache.get("show_guides", {}).items()},
            "show_histories": {str(k): v for k, v in cache.get("show_histories", {}).items()},
        }
        tmp_path = CACHE_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp_path, CACHE_FILE)
        cache["saved_at"] = payload["saved_at"]
    except Exception as e:
        print(f"  [Cache Save Warning] {e}")


def load_cache_from_disk():
    if not APP_CONFIG.get("cache_enabled", True) or not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if raw.get("version") != 6:
            return None
        cache = empty_cache()
        cache["saved_at"] = raw.get("saved_at", 0)
        cache["last_activities"] = raw.get("last_activities", {})
        cache["watched"] = {int(k): v for k, v in raw.get("watched", {}).items()}
        cache["ratings"] = {int(k): v for k, v in raw.get("ratings", {}).items()}
        cache["watchlist"] = {int(x) for x in raw.get("watchlist", [])}
        cache["favorites"] = {int(x) for x in raw.get("favorites", [])}
        cache["custom_lists"] = {int(k): v for k, v in raw.get("custom_lists", {}).items()}
        cache["show_guides"] = {int(k): v for k, v in raw.get("show_guides", {}).items()}
        cache["show_histories"] = {int(k): v for k, v in raw.get("show_histories", {}).items()}
        return cache
    except Exception:
        return None


def fetch_last_activities(token):
    s, data = api_request("GET", "/sync/last_activities", access_token=token)
    if s == 200 and isinstance(data, dict):
        return data
    return {}


def activities_signature(act):
    """Extracts the timestamps relevant to shows, episodes, ratings, watchlist, lists, and favorites."""
    if not isinstance(act, dict):
        return {}
    return {
        "ep_watched": act.get("episodes", {}).get("watched_at"),
        "ep_rated": act.get("episodes", {}).get("rated_at"),
        "show_rated": act.get("shows", {}).get("rated_at"),
        "show_watchlist": act.get("shows", {}).get("watchlist_at"),
        "show_fav": act.get("shows", {}).get("favorited_at"),
        "lists_updated": act.get("lists", {}).get("updated_at"),
        "lists_liked": act.get("lists", {}).get("liked_at"),
    }


def load_user_account_cache(token, force_refresh=False):
    """
    Fast startup:
    - If cache_enabled and trakt_cache.json exists (and not force_refresh):
      checks /sync/last_activities (1 tiny API call).
      * If Trakt timestamps match cached timestamps -> loads instantly!
      * If only watched OR ratings OR lists changed -> refreshes only what changed!
    - Otherwise fetches full account library and saves to disk.
    """
    existing = None if force_refresh else load_cache_from_disk()
    remote_act = fetch_last_activities(token)
    remote_sig = activities_signature(remote_act)

    if existing and APP_CONFIG.get("cache_enabled", True):
        cached_sig = activities_signature(existing.get("last_activities", {}))
        if cached_sig and cached_sig == remote_sig:
            print(
                f"[Cache HIT] Loaded {len(existing['watched'])} watched shows | "
                f"{len(existing['ratings'])} ratings | {len(existing['watchlist'])} watchlist | "
                f"{len(existing['show_guides'])} cached show guides ({format_age(existing['saved_at'])}).\n"
            )
            return existing

        # Partial smart refresh if only some sections changed
        print("[Cache] Account changed since last run — syncing updated sections...")
        cache = existing
        need_watched = cached_sig.get("ep_watched") != remote_sig.get("ep_watched")
        need_ratings = cached_sig.get("show_rated") != remote_sig.get("show_rated")
        need_watchlist = cached_sig.get("show_watchlist") != remote_sig.get("show_watchlist")
        need_fav = cached_sig.get("show_fav") != remote_sig.get("show_fav")
        need_lists = cached_sig.get("lists_updated") != remote_sig.get("lists_updated")
        if need_watched:
            # Invalidate per-show cached histories when external watches happened
            cache["show_histories"] = {}
    else:
        print("Syncing your Trakt library (watched, ratings, watchlist, lists)...")
        cache = existing if existing else empty_cache()
        if force_refresh:
            cache["show_histories"] = {}
        need_watched = need_ratings = need_watchlist = need_fav = need_lists = True

    if need_watched:
        old_watched = cache.get("watched", {})
        watched_raw = fetch_all_pages("/sync/watched/shows?extended=progress", token)
        watched_map = {}
        for entry in watched_raw:
            show = entry.get("show", {})
            tid = show.get("ids", {}).get("trakt")
            if not tid:
                continue

            ep_dates = []
            unique_regular_eps = set()
            seasons = entry.get("seasons") or []
            for season in seasons:
                s_num = season.get("number", 0)
                for ep in season.get("episodes", []):
                    if s_num > 0:
                        unique_regular_eps.add((s_num, ep.get("number")))
                    lwa = ep.get("last_watched_at")
                    if lwa:
                        ep_dates.append(lwa)

            plays = entry.get("plays", 0) or 0
            aired = show.get("aired_episodes")
            last_watched_at = entry.get("last_watched_at")
            has_season_data = len(seasons) > 0 and len(unique_regular_eps) > 0

            # Preserve exact_hydrated fields if this show's plays & last_watched_at didn't change
            prev = old_watched.get(tid)
            if (
                prev
                and prev.get("exact_hydrated")
                and prev.get("plays") == plays
                and prev.get("last_watched_at") == last_watched_at
                and not force_refresh
            ):
                watched_map[tid] = prev
                continue

            if has_season_data:
                watched_eps = len(unique_regular_eps)
                ep_dates.sort()
                started_at = ep_dates[0] if ep_dates else last_watched_at
                finished_at = ep_dates[-1] if ep_dates else last_watched_at
            else:
                watched_eps = min(plays, aired) if (aired and plays) else plays
                started_at = None
                finished_at = last_watched_at

            watched_map[tid] = {
                "plays": plays,
                "watched_eps": watched_eps,
                "started_at": started_at,
                "finished_at": finished_at,
                "last_watched_at": last_watched_at,
                "aired_episodes": aired,
                "title": show.get("title", ""),
                "exact_hydrated": False,
            }
        cache["watched"] = watched_map

    if need_ratings:
        ratings_raw = fetch_all_pages("/users/me/ratings/shows", token)
        cache["ratings"] = {
            r["show"]["ids"]["trakt"]: {"rating": r.get("rating"), "rated_at": r.get("rated_at")}
            for r in ratings_raw
            if r.get("show", {}).get("ids", {}).get("trakt")
        }

    if need_watchlist:
        watchlist_raw = fetch_all_pages("/users/me/watchlist/shows", token)
        cache["watchlist"] = {
            item["show"]["ids"]["trakt"]
            for item in watchlist_raw
            if item.get("show", {}).get("ids", {}).get("trakt")
        }

    if need_fav:
        try:
            fav_raw = fetch_all_pages("/users/me/favorites/shows", token)
            cache["favorites"] = {
                item["show"]["ids"]["trakt"]
                for item in fav_raw
                if item.get("show", {}).get("ids", {}).get("trakt")
            }
        except Exception:
            pass

    if need_lists:
        custom_lists_map = {}
        try:
            s, lists_meta = api_request("GET", "/users/me/lists", access_token=token)
            if s == 200 and isinstance(lists_meta, list):
                for lst in lists_meta:
                    list_id = lst.get("ids", {}).get("trakt")
                    list_name = lst.get("name", "Custom List")
                    if not list_id:
                        continue
                    items = fetch_all_pages(f"/users/me/lists/{list_id}/items/shows", token)
                    for it in items:
                        tid = it.get("show", {}).get("ids", {}).get("trakt")
                        if tid:
                            custom_lists_map.setdefault(tid, []).append(list_name)
        except Exception:
            pass
        cache["custom_lists"] = custom_lists_map

    cache["last_activities"] = remote_act
    save_cache_to_disk(cache)
    print(
        f"Loaded {len(cache['watched'])} watched shows | {len(cache['ratings'])} ratings | "
        f"{len(cache['watchlist'])} watchlist | {len(cache['favorites'])} favorites.\n"
    )
    return cache


def manage_cache_menu(cache, token):
    while True:
        enabled = APP_CONFIG.get("cache_enabled", True)
        size_kb = os.path.getsize(CACHE_FILE) / 1024.0 if os.path.exists(CACHE_FILE) else 0.0
        sync_pref = APP_CONFIG.get("default_sync_mode", "ask")
        ts_style = APP_CONFIG.get("timestamp_style", "spread")

        print("\n" + "=" * 68)
        print("CACHE & PREFERENCES")
        print("=" * 68)
        print(f"  Disk Cache Status:   {'ON' if enabled else 'OFF'}  ({size_kb:.1f} KB on disk)")
        print(f"  Last Synced:         {format_age(cache.get('saved_at', 0))}")
        print(f"  Cached Library:      {len(cache['watched'])} watched | {len(cache['ratings'])} ratings | {len(cache['watchlist'])} watchlist")
        print(f"  Cached Show Guides:  {len(cache['show_guides'])} shows | {len(cache['show_histories'])} show histories")
        print(f"  Default Sync Speed:  {sync_pref.upper()}")
        print(f"  Timestamp Spacing:   {ts_style.upper()}")
        print("-" * 68)
        print("  1) Toggle Disk Cache ON / OFF")
        print("  2) Force Full Refresh from Trakt now")
        print("  3) Clear Disk Cache file (trakt_cache.json)")
        print("  4) Set Default Sync Speed (Immediate / Quick 1-Confirm / Safe Double / Ask)")
        print("  5) Set Timestamp Spacing (Spread across day / Fixed Gap 15-45m / Binge)")
        print("  b) Back to Search")
        choice = input("Choose option: ").strip().lower()

        if choice == "1":
            APP_CONFIG["cache_enabled"] = not enabled
            save_app_config()
            if APP_CONFIG["cache_enabled"]:
                save_cache_to_disk(cache)
                print("  -> Disk Cache turned ON and saved.")
            else:
                print("  -> Disk Cache turned OFF (all requests will fetch live from Trakt).")
        elif choice == "2":
            new_cache = load_user_account_cache(token, force_refresh=True)
            cache.clear()
            cache.update(new_cache)
            print("  -> Full refresh complete!")
        elif choice == "3":
            if os.path.exists(CACHE_FILE):
                os.remove(CACHE_FILE)
            cache["show_guides"].clear()
            cache["show_histories"].clear()
            cache["search_mem"].clear()
            print("  -> Cleared disk & show caches.")
        elif choice == "4":
            print("\nChoose default sync speed when editing:")
            print("  1) immediate  -> Update Immediately (syncs right away, zero extra prompts)")
            print("  2) quick      -> Quick 1-Confirm (preview + press Enter to upload)")
            print("  3) double     -> Safe Double-Confirm (preview + type yes + YES)")
            print("  4) ask        -> Ask me every time")
            sp = input("Enter 1-4: ").strip()
            mapping = {"1": "immediate", "2": "quick", "3": "double", "4": "ask"}
            if sp in mapping:
                APP_CONFIG["default_sync_mode"] = mapping[sp]
                save_app_config()
                print(f"  -> Default Sync Speed set to: {mapping[sp].upper()}")
        elif choice == "5":
            print("\nChoose Timestamp Spacing Style:")
            print("  1) spread -> Spread episodes across the day's time window with natural gaps [DEFAULT]")
            print("  2) gap    -> Session with 15-45 min break between each episode")
            print("  3) binge  -> Back-to-back (1-5 min between episodes)")
            ts_pick = input("Enter 1-3: ").strip()
            ts_map = {"1": "spread", "2": "gap", "3": "binge"}
            if ts_pick in ts_map:
                APP_CONFIG["timestamp_style"] = ts_map[ts_pick]
                save_app_config()
                print(f"  -> Timestamp Spacing set to: {ts_map[ts_pick].upper()}")
        else:
            break


# ----------------- LOCAL SNAPSHOT BACKUPS --------
def ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


def slugify_name(name):
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", (name or "show").strip().lower()).strip("_")
    return slug[:40] or "show"


def save_show_snapshot(show, history, cache, reason="manual"):
    """Saves a lightweight offline JSON snapshot of a single show's exact Trakt history."""
    ensure_backup_dir()
    tid = show["ids"]["trakt"]
    title = show.get("title", "Unknown")
    now_ist = datetime.now(get_local_tz())
    ts_tag = now_ist.strftime("%Y-%m-%d_%H-%M-%S")
    fname = f"show_{slugify_name(title)}_{ts_tag}.json"
    fpath = os.path.join(BACKUP_DIR, fname)

    payload = {
        "snapshot_type": "show",
        "version": 8,
        "reason": reason,
        "created_at_ist": now_ist.isoformat(),
        "show": {
            "title": title,
            "year": show.get("year"),
            "ids": show.get("ids", {}),
            "status": show.get("status"),
            "aired_episodes": show.get("aired_episodes"),
            "runtime": show.get("runtime"),
        },
        "rating": cache.get("ratings", {}).get(tid),
        "history_count": len(history),
        "history": history,
    }
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return fpath


def create_quick_account_snapshot(cache, token):
    """Fast offline snapshot of watched shows, all ratings, watchlist, favorites, custom lists & cached histories."""
    ensure_backup_dir()
    print("\nCreating Quick Account Snapshot from Trakt...")

    watched_shows = fetch_all_pages("/sync/watched/shows?extended=progress", token)
    ratings_shows = fetch_all_pages("/users/me/ratings/shows", token)
    ratings_seasons = []
    ratings_episodes = []
    ratings_movies = []
    try:
        ratings_seasons = fetch_all_pages("/users/me/ratings/seasons", token)
    except Exception:
        pass
    try:
        ratings_episodes = fetch_all_pages("/users/me/ratings/episodes", token)
    except Exception:
        pass
    try:
        ratings_movies = fetch_all_pages("/users/me/ratings/movies", token)
    except Exception:
        pass

    watchlist_shows = fetch_all_pages("/users/me/watchlist/shows", token)
    favorites_shows = []
    try:
        favorites_shows = fetch_all_pages("/users/me/favorites/shows", token)
    except Exception:
        pass

    custom_lists = []
    try:
        s, lists_meta = api_request("GET", "/users/me/lists", access_token=token)
        if s == 200 and isinstance(lists_meta, list):
            for lst in lists_meta:
                lid = lst.get("ids", {}).get("trakt")
                if not lid:
                    continue
                items = fetch_all_pages(f"/users/me/lists/{lid}/items", token)
                custom_lists.append({"list": lst, "items": items})
    except Exception:
        pass

    last_act = fetch_last_activities(token)
    now_ist = datetime.now(get_local_tz())
    fname = f"snapshot_quick_{now_ist.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    fpath = os.path.join(BACKUP_DIR, fname)

    payload = {
        "snapshot_type": "quick_account",
        "version": 8,
        "created_at_ist": now_ist.isoformat(),
        "last_activities": last_act,
        "summary": {
            "watched_shows": len(watched_shows),
            "ratings_shows": len(ratings_shows),
            "ratings_seasons": len(ratings_seasons),
            "ratings_episodes": len(ratings_episodes),
            "ratings_movies": len(ratings_movies),
            "watchlist_shows": len(watchlist_shows),
            "favorites_shows": len(favorites_shows),
            "custom_lists": len(custom_lists),
            "cached_show_histories": len(cache.get("show_histories", {})),
        },
        "watched_shows": watched_shows,
        "ratings": {
            "shows": ratings_shows,
            "seasons": ratings_seasons,
            "episodes": ratings_episodes,
            "movies": ratings_movies,
        },
        "watchlist_shows": watchlist_shows,
        "favorites_shows": favorites_shows,
        "custom_lists": custom_lists,
        "cached_show_histories": {str(k): v for k, v in cache.get("show_histories", {}).items()},
    }
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    size_kb = os.path.getsize(fpath) / 1024.0
    print(f"[SUCCESS] Saved Quick Account Snapshot -> trakt_backups/{fname} ({size_kb:.1f} KB)")
    print(
        f"  Captured: {len(watched_shows)} watched shows | {len(ratings_shows)} show ratings | "
        f"{len(ratings_episodes)} ep ratings | {len(watchlist_shows)} watchlist | {len(custom_lists)} lists."
    )
    return fpath


def create_full_history_snapshot(token):
    """Complete offline snapshot of EVERY episode & movie play timestamp, ratings, watchlist, and lists."""
    ensure_backup_dir()
    print("\nCreating Full History Snapshot (this fetches your complete Trakt watch history)...")
    print("  1/5 Fetching all episode history entries...")
    ep_history = fetch_all_pages("/users/me/history/episodes", token)
    print(f"      -> {len(ep_history)} episode plays fetched.")

    print("  2/5 Fetching all movie history entries...")
    mov_history = fetch_all_pages("/users/me/history/movies", token)
    print(f"      -> {len(mov_history)} movie plays fetched.")

    print("  3/5 Fetching all ratings (shows, seasons, episodes, movies)...")
    ratings_shows = fetch_all_pages("/users/me/ratings/shows", token)
    ratings_seasons = []
    ratings_episodes = []
    ratings_movies = []
    try:
        ratings_seasons = fetch_all_pages("/users/me/ratings/seasons", token)
    except Exception:
        pass
    try:
        ratings_episodes = fetch_all_pages("/users/me/ratings/episodes", token)
    except Exception:
        pass
    try:
        ratings_movies = fetch_all_pages("/users/me/ratings/movies", token)
    except Exception:
        pass

    print("  4/5 Fetching watchlist, favorites, and personal lists...")
    watchlist = fetch_all_pages("/users/me/watchlist", token)
    favorites = []
    try:
        favorites = fetch_all_pages("/users/me/favorites", token)
    except Exception:
        pass

    custom_lists = []
    try:
        s, lists_meta = api_request("GET", "/users/me/lists", access_token=token)
        if s == 200 and isinstance(lists_meta, list):
            for lst in lists_meta:
                lid = lst.get("ids", {}).get("trakt")
                if not lid:
                    continue
                items = fetch_all_pages(f"/users/me/lists/{lid}/items", token)
                custom_lists.append({"list": lst, "items": items})
    except Exception:
        pass

    print("  5/5 Writing snapshot file to disk...")
    last_act = fetch_last_activities(token)
    now_ist = datetime.now(get_local_tz())
    fname = f"snapshot_full_{now_ist.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    fpath = os.path.join(BACKUP_DIR, fname)

    payload = {
        "snapshot_type": "full_history",
        "version": 8,
        "created_at_ist": now_ist.isoformat(),
        "last_activities": last_act,
        "summary": {
            "episode_plays": len(ep_history),
            "movie_plays": len(mov_history),
            "ratings_shows": len(ratings_shows),
            "ratings_seasons": len(ratings_seasons),
            "ratings_episodes": len(ratings_episodes),
            "ratings_movies": len(ratings_movies),
            "watchlist_items": len(watchlist),
            "favorites_items": len(favorites),
            "custom_lists": len(custom_lists),
        },
        "history_episodes": ep_history,
        "history_movies": mov_history,
        "ratings": {
            "shows": ratings_shows,
            "seasons": ratings_seasons,
            "episodes": ratings_episodes,
            "movies": ratings_movies,
        },
        "watchlist": watchlist,
        "favorites": favorites,
        "custom_lists": custom_lists,
    }
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    size_mb = os.path.getsize(fpath) / (1024.0 * 1024.0)
    print(f"[SUCCESS] Saved Full History Snapshot -> trakt_backups/{fname} ({size_mb:.2f} MB)")
    print(f"  Captured: {len(ep_history)} episode plays | {len(mov_history)} movie plays | {len(ratings_shows)} show ratings.")
    return fpath


def list_local_snapshots():
    ensure_backup_dir()
    files = sorted(
        (f for f in os.listdir(BACKUP_DIR) if f.endswith(".json")),
        reverse=True,
    )
    metas = []
    for fname in files:
        fpath = os.path.join(BACKUP_DIR, fname)
        size_kb = os.path.getsize(fpath) / 1024.0
        snap_type = "unknown"
        created = "-"
        info = ""
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            snap_type = data.get("snapshot_type", "unknown")
            created = (data.get("created_at_ist") or "-")[:19].replace("T", " ")
            if snap_type == "show":
                sh = data.get("show", {})
                info = f"{sh.get('title', '?')} ({data.get('history_count', 0)} plays, {data.get('reason', 'manual')})"
            elif snap_type == "full_history":
                sm = data.get("summary", {})
                info = f"{sm.get('episode_plays', 0)} ep plays, {sm.get('movie_plays', 0)} mov plays"
            elif snap_type == "quick_account":
                sm = data.get("summary", {})
                info = f"{sm.get('watched_shows', 0)} shows, {sm.get('ratings_shows', 0)} ratings"
        except Exception:
            info = "(corrupted or unreadable)"
        metas.append({
            "fname": fname,
            "fpath": fpath,
            "size_kb": size_kb,
            "type": snap_type,
            "created": created,
            "info": info,
        })
    return metas


def print_snapshots_table(metas):
    if not metas:
        print("\nNo local snapshots found in trakt_backups/ yet.")
        return
    print("\n" + "=" * 116)
    print(f"{'#':>2} | {'Type':<13} | {'Created (IST)':<19} | {'Size':>8} | {'Summary':<34} | {'Filename'}")
    print("-" * 116)
    for idx, m in enumerate(metas, 1):
        size_s = f"{m['size_kb']/1024.0:.2f} MB" if m["size_kb"] >= 1024 else f"{m['size_kb']:.1f} KB"
        print(
            f"{idx:>2} | {m['type']:<13} | {m['created']:<19} | {size_s:>8} | "
            f"{truncate(m['info'], 34):<34} | {truncate(m['fname'], 32)}"
        )
    print("=" * 116)


def restore_show_from_snapshot(cache, token):
    metas = [m for m in list_local_snapshots() if m["type"] in ("show", "full_history")]
    if not metas:
        print("\nNo restorable snapshots found. Create a Show Snapshot ([k]) or Full History Snapshot first.")
        return

    print_snapshots_table(metas)
    pick = input("Select snapshot # to restore a show from (or Enter to cancel): ").strip()
    if not pick.isdigit() or not (1 <= int(pick) <= len(metas)):
        return

    snap_meta = metas[int(pick) - 1]
    with open(snap_meta["fpath"], "r", encoding="utf-8") as f:
        snap = json.load(f)

    if snap.get("snapshot_type") == "show":
        show_obj = snap.get("show", {})
        tid = show_obj.get("ids", {}).get("trakt")
        title = show_obj.get("title", "Unknown")
        backup_items = snap.get("history", [])
    else:
        q = input("Enter show name inside this Full Snapshot to restore: ").strip().lower()
        if not q:
            return
        by_show = {}
        for it in snap.get("history_episodes", []):
            sh = it.get("show", {})
            stitle = sh.get("title", "")
            stid = sh.get("ids", {}).get("trakt")
            if stid and q in stitle.lower():
                by_show.setdefault(stid, {"show": sh, "items": []})["items"].append(it)
        if not by_show:
            print(f"No show matching '{q}' found in that snapshot.")
            return
        candidates = sorted(by_show.values(), key=lambda x: x["show"].get("title", ""))
        for idx, c in enumerate(candidates, 1):
            print(f"  {idx}) {c['show'].get('title')} ({c['show'].get('year')}) — {len(c['items'])} plays in backup")
        spick = input("Select show #: ").strip()
        if not spick.isdigit() or not (1 <= int(spick) <= len(candidates)):
            return
        chosen = candidates[int(spick) - 1]
        show_obj = chosen["show"]
        tid = show_obj["ids"]["trakt"]
        title = show_obj["title"]
        backup_items = chosen["items"]

    if not tid:
        print("Snapshot is missing Trakt show ID.")
        return

    print(f"\nChecking live Trakt history for '{title}'...")
    live_history = fetch_show_history(tid, token, cache=cache, use_cache=False)

    b_dates = sorted(it["watched_at"] for it in backup_items if it.get("watched_at"))
    l_dates = sorted(it["watched_at"] for it in live_history if it.get("watched_at"))

    print("\n" + "=" * 78)
    print(f"RESTORE PREVIEW: {title}")
    print("=" * 78)
    print(f"  Current on Trakt: {len(live_history)} play(s)  "
          f"({short_date_ist(l_dates[0]) if l_dates else '-'} -> {short_date_ist(l_dates[-1]) if l_dates else '-'})")
    print(f"  In Snapshot:      {len(backup_items)} play(s)  "
          f"({short_date_ist(b_dates[0]) if b_dates else '-'} -> {short_date_ist(b_dates[-1]) if b_dates else '-'})")
    print("=" * 78)

    c1 = input(f"\n[Confirm 1/2] Replace live Trakt history for '{title}' with this snapshot? (yes/no): ").strip().lower()
    if c1 not in ("y", "yes"):
        print("Restore cancelled.")
        return
    c2 = input("[Confirm 2/2] Type RESTORE to proceed: ").strip()
    if c2 != "RESTORE":
        print("Restore cancelled on 2nd confirmation.")
        return

    live_ids = [it["id"] for it in live_history if "id" in it]
    if live_ids:
        print(f"  Removing {len(live_ids)} current history record(s)...")
        for i in range(0, len(live_ids), 100):
            s, res = api_request("POST", "/sync/history/remove", {"ids": live_ids[i : i + 100]}, access_token=token)
            if s != 200:
                print(f"  [ERROR] Remove failed ({s}): {res}")
                return
            time.sleep(1.05)

    restore_payload = []
    for it in backup_items:
        ep_tid = it.get("episode", {}).get("ids", {}).get("trakt")
        wa = it.get("watched_at")
        if ep_tid and wa:
            restore_payload.append({"ids": {"trakt": ep_tid}, "watched_at": wa})

    if restore_payload:
        print(f"  Restoring {len(restore_payload)} episode play(s) from snapshot...")
        total_added = 0
        for i in range(0, len(restore_payload), 100):
            s, res = api_request("POST", "/sync/history", {"episodes": restore_payload[i : i + 100]}, access_token=token)
            if s in (200, 201):
                total_added += res.get("added", {}).get("episodes", 0)
            else:
                print(f"  [ERROR] Restore upload failed ({s}): {res}")
                return
            if i + 100 < len(restore_payload):
                time.sleep(1.05)
        print(f"  [SUCCESS] Restored {total_added} episode play(s) for '{title}'!")
    else:
        print(f"  [SUCCESS] Cleared live history for '{title}' (snapshot had 0 plays).")

    refresh_show_in_cache(show_obj, cache, token)


def manage_backup_menu(cache, token):
    while True:
        metas = list_local_snapshots()
        total_kb = sum(m["size_kb"] for m in metas)
        size_s = f"{total_kb/1024.0:.2f} MB" if total_kb >= 1024 else f"{total_kb:.1f} KB"
        auto_bk = APP_CONFIG.get("auto_backup_before_edit", True)

        print("\n" + "=" * 72)
        print("LOCAL SNAPSHOT BACKUP MANAGER  (folder: trakt_backups/)")
        print("=" * 72)
        print(f"  Saved Snapshots:          {len(metas)} file(s) ({size_s} total)")
        print(f"  Auto-Backup Before Edit:  {'ON' if auto_bk else 'OFF'}")
        print("-" * 72)
        print("  1) Create Quick Account Snapshot  (Fast: shows, ratings, watchlist, lists)")
        print("  2) Create Full History Snapshot   (Complete: EVERY ep & movie timestamp)")
        print("  3) List Local Snapshots")
        print("  4) Restore a Show's History from a Snapshot")
        print("  5) Toggle Auto-Backup Before Show Edits (ON / OFF)")
        print("  b) Back to Search")
        choice = input("Choose option: ").strip().lower()

        if choice == "1":
            create_quick_account_snapshot(cache, token)
        elif choice == "2":
            create_full_history_snapshot(token)
        elif choice == "3":
            print_snapshots_table(list_local_snapshots())
        elif choice == "4":
            restore_show_from_snapshot(cache, token)
        elif choice == "5":
            APP_CONFIG["auto_backup_before_edit"] = not auto_bk
            save_app_config()
            print(f"  -> Auto-Backup Before Show Edits turned {'ON' if APP_CONFIG['auto_backup_before_edit'] else 'OFF'}.")
        else:
            break


def hydrate_watched_show_exact(show, cache, token):
    tid = show.get("ids", {}).get("trakt")
    if not tid or tid not in cache["watched"]:
        return

    entry = cache["watched"][tid]
    if entry.get("exact_hydrated"):
        return

    try:
        s, prog = api_request(
            "GET",
            f"/shows/{tid}/progress/watched?hidden=false&specials=false&count_specials=false",
            access_token=token,
        )
        if s == 200 and isinstance(prog, dict):
            completed = prog.get("completed")
            aired = prog.get("aired")
            if isinstance(completed, int):
                entry["watched_eps"] = completed
            if isinstance(aired, int) and aired > 0:
                entry["aired_episodes"] = aired

            ep_dates = []
            for season in prog.get("seasons", []):
                for ep in season.get("episodes", []):
                    if ep.get("completed") and ep.get("last_watched_at"):
                        ep_dates.append(ep["last_watched_at"])
            if ep_dates:
                ep_dates.sort()
                entry["started_at"] = ep_dates[0]
                entry["finished_at"] = ep_dates[-1]

        if not entry.get("started_at") or not entry.get("finished_at"):
            hist = fetch_show_history(tid, token, cache, use_cache=True)
            dates = sorted(it["watched_at"] for it in hist if it.get("watched_at"))
            if dates:
                entry["started_at"] = dates[0]
                entry["finished_at"] = dates[-1]
                entry["plays"] = len(hist)

        entry["exact_hydrated"] = True
        save_cache_to_disk(cache)
    except Exception:
        pass


# ----------------- TRAKT DB SEARCH ---------------
def search_trakt_db_shows(query, token, cache, max_results=12):
    q_key = query.strip().lower()
    if APP_CONFIG.get("cache_enabled", True) and q_key in cache.get("search_mem", {}):
        return cache["search_mem"][q_key]

    q_enc = urllib.parse.quote(query)
    combined = []
    seen_ids = set()

    for endpoint in (
        f"/search/show/exact?query={q_enc}&extended=full&page=1&limit=5",
        f"/search/show?query={q_enc}&extended=full&page=1&limit={max_results}",
    ):
        s, res = api_request("GET", endpoint, access_token=token)
        if s == 200 and isinstance(res, list):
            for item in res:
                show = item.get("show")
                if not show:
                    continue
                tid = show.get("ids", {}).get("trakt")
                if tid and tid not in seen_ids:
                    seen_ids.add(tid)
                    combined.append(show)
        if len(combined) >= max_results:
            break

    result = combined[:max_results]
    cache.setdefault("search_mem", {})[q_key] = result
    return result


def summarize_user_status(show, cache):
    tid = show.get("ids", {}).get("trakt")
    w = cache["watched"].get(tid)
    aired = (w.get("aired_episodes") if w and w.get("aired_episodes") else None) or show.get("aired_episodes") or 0
    r = cache["ratings"].get(tid)
    in_wl = tid in cache["watchlist"]
    in_fav = tid in cache["favorites"]
    lists = list(cache["custom_lists"].get(tid, []))

    tags = []
    if in_wl:
        tags.append("Watchlist")
    if in_fav:
        tags.append("Fav")
    tags.extend(lists)

    if w:
        weps = w["watched_eps"]
        if aired and weps >= aired:
            watch_status = f"Completed ({weps}/{aired})"
        elif aired:
            watch_status = f"Watching ({weps}/{aired})"
        else:
            watch_status = f"Watched ({weps} eps)"
        started = short_date_ist(w.get("started_at"))
        finished = short_date_ist(w.get("finished_at"))
    else:
        watch_status = "In List" if tags else "Not Watched"
        started = "-"
        finished = "-"

    if tags:
        watch_status += f" [{', '.join(tags)}]"

    rating_str = f"{r['rating']}/10" if r and r.get("rating") is not None else "-"
    return watch_status, rating_str, started, finished


def print_search_results_table(shows, cache, token=None):
    if token:
        for show in shows:
            tid = show.get("ids", {}).get("trakt")
            if tid in cache["watched"] and not cache["watched"][tid].get("exact_hydrated"):
                hydrate_watched_show_exact(show, cache, token)

    print("\n" + "=" * 124)
    header = (
        f"{'#':>2} | {'Name (Year)':<32} | {'Title Status':<16} | "
        f"{'My Watch Status / Lists':<30} | {'Rating':<6} | {'Started':<10} | {'Finished':<10}"
    )
    print(header)
    print("-" * 124)

    for idx, show in enumerate(shows, 1):
        title = show.get("title", "Unknown")
        year = show.get("year")
        name_yr = f"{title} ({year})" if year else title
        t_status = (show.get("status") or "unknown").title()
        w_status, rating_str, started, finished = summarize_user_status(show, cache)

        print(
            f"{idx:>2} | {truncate(name_yr, 32):<32} | {truncate(t_status, 16):<16} | "
            f"{truncate(w_status, 30):<30} | {rating_str:<6} | {started:<10} | {finished:<10}"
        )
    print("=" * 124)


# ----------------- SHOW DATA (CACHED) ------------
def fetch_show_seasons_episodes(trakt_id, token, cache, show_status="", force=False):
    if not force and APP_CONFIG.get("cache_enabled", True):
        cached = cache.get("show_guides", {}).get(trakt_id)
        if cached:
            ttl = SHOW_GUIDE_TTL_ENDED if (show_status or "").lower() in ("ended", "canceled") else SHOW_GUIDE_TTL_RETURNING
            if (time.time() - cached.get("fetched_at", 0)) < ttl:
                return cached.get("seasons", []), True

    s, data = api_request("GET", f"/shows/{trakt_id}/seasons?extended=episodes,full", access_token=token)
    if s != 200 or not isinstance(data, list):
        return [], False

    if APP_CONFIG.get("cache_enabled", True):
        cache.setdefault("show_guides", {})[trakt_id] = {
            "fetched_at": int(time.time()),
            "status": show_status,
            "seasons": data,
        }
        save_cache_to_disk(cache)
    return data, False


def fetch_show_history(trakt_id, token, cache=None, use_cache=True):
    if use_cache and cache is not None and APP_CONFIG.get("cache_enabled", True):
        cached = cache.get("show_histories", {}).get(trakt_id)
        if cached and (time.time() - cached.get("fetched_at", 0)) < SHOW_HISTORY_TTL:
            return cached.get("items", [])

    items = fetch_all_pages(f"/users/me/history/shows/{trakt_id}", token)
    if cache is not None and APP_CONFIG.get("cache_enabled", True):
        cache.setdefault("show_histories", {})[trakt_id] = {
            "fetched_at": int(time.time()),
            "items": items,
        }
        save_cache_to_disk(cache)
    return items


# ----------------- RATINGS -----------------------
def rate_show_interactive(show, cache, token):
    tid = show["ids"]["trakt"]
    title = show["title"]
    cur = cache["ratings"].get(tid, {}).get("rating")
    print(f"\n=== RATE SHOW: {title} ===")
    print(f"Current Rating: {cur}/10" if cur else "Current Rating: Not rated yet")
    print("Enter a rating from 1 to 10, '0' to REMOVE your rating, or Enter to cancel.")

    ans = input("New rating (1-10 / 0=remove): ").strip()
    if not ans:
        print("Cancelled.")
        return

    if not ans.isdigit() or not (0 <= int(ans) <= 10):
        print("Invalid input. Must be a whole number from 0 to 10.")
        return

    val = int(ans)
    if val == 0:
        confirm = input(f"Remove your rating for '{title}' on Trakt? (yes/no): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Cancelled.")
            return
        s, res = api_request("POST", "/sync/ratings/remove", {"shows": [{"ids": {"trakt": tid}}]}, access_token=token)
        if s == 200:
            cache["ratings"].pop(tid, None)
            cache["last_activities"] = fetch_last_activities(token)
            save_cache_to_disk(cache)
            print(f"[SUCCESS] Rating removed for '{title}'.")
        else:
            print(f"[ERROR] Failed to remove rating ({s}): {res}")
        return

    date_raw = input("Rating date YYYY-MM-DD (or press Enter for right now): ").strip()
    rated_at_iso = None
    if date_raw:
        try:
            d = parse_flexible_date(date_raw)
            dt_ist = datetime(d.year, d.month, d.day, 20, 0, 0, tzinfo=get_local_tz())
            rated_at_iso = dt_ist.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        except ValueError:
            print("Invalid date format; using current time instead.")

    show_payload = {"ids": {"trakt": tid}, "rating": val}
    if rated_at_iso:
        show_payload["rated_at"] = rated_at_iso

    confirm = input(f"Save rating {val}/10 for '{title}' to Trakt? (Enter/y=yes, n=no): ").strip().lower()
    if confirm in ("n", "no"):
        print("Cancelled.")
        return

    s, res = api_request("POST", "/sync/ratings", {"shows": [show_payload]}, access_token=token)
    if s in (200, 201):
        cache["ratings"][tid] = {
            "rating": val,
            "rated_at": rated_at_iso or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        cache["last_activities"] = fetch_last_activities(token)
        save_cache_to_disk(cache)
        print(f"[SUCCESS] Rated '{title}' {val}/10 on Trakt!")
    else:
        print(f"[ERROR] Failed to save rating ({s}): {res}")


# ----------------- SCHEDULE RULES ----------------
def get_schedule_windows(d: date):
    sched = APP_CONFIG.get("schedule") or {}
    def_win = sched.get("default_window") or ["07:00", "22:00"]
    dw_s, dw_e = parse_hhmm(def_win[0]), parse_hhmm(def_win[1])
    def_label = f"{def_win[0]}-{def_win[1]}"

    cutoff_raw = sched.get("weekday_busy_cutoff_date")
    cutoff_d = None
    if cutoff_raw:
        try:
            cutoff_d = date.fromisoformat(str(cutoff_raw))
        except ValueError:
            cutoff_d = None

    is_weekend = d.weekday() >= 5
    if cutoff_d and d <= cutoff_d:
        if is_weekend:
            return [(dw_s, dw_e)], f"Weekend ({def_label})"
        raw_wk = sched.get("weekday_windows_before_cutoff") or [["06:00", "07:00"], ["14:00", "22:00"]]
        wins = [(parse_hhmm(w[0]), parse_hhmm(w[1])) for w in raw_wk]
        lbl = " & ".join(f"{w[0]}-{w[1]}" for w in raw_wk)
        return wins, f"Weekday Schedule ({lbl})"

    day_type = "Weekend" if is_weekend else "Standard"
    return [(dw_s, dw_e)], f"{day_type} ({def_label})"


def parse_hhmm(time_str):
    parts = time_str.strip().split(":")
    if len(parts) != 2:
        raise ValueError("Use HH:MM (24-hour format, e.g. 06:15 or 14:30)")
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("Invalid hour or minute.")
    return h * 60 + m


def _spread_minutes_in_window(ws: int, we: int, runtimes, pin_first_at_start: bool = False, style: str = "spread"):
    """
    Places len(runtimes) episodes strictly chronologically inside [ws, we) in minutes from midnight.
    STRICT TRAKT RUNTIME RULE:
      - Every episode i+1 ALWAYS starts at >= start[i] + runtimes[i] + min_break.
      - Every episode finishes at <= we whenever window capacity permits.
      - NEVER compresses spacing below an episode's actual Trakt runtime!
    Returns (minute_points, overflowed_minutes).
    """
    n = len(runtimes)
    if n == 0:
        return [], 0.0

    win_len = max(1, we - ws)
    total_runtime = sum(runtimes)
    last_rt = runtimes[-1]

    # Single episode in this window: MUST finish at or before `we` if runtime fits!
    if n == 1:
        if pin_first_at_start:
            overflow = max(0.0, (ws + last_rt) - we)
            return [float(ws)], overflow
        if last_rt <= win_len:
            latest = we - last_rt
            earliest = ws
            if (latest - earliest) > 40:
                earliest = ws + min(20, (latest - ws) // 6)
            return [float(random.randint(int(earliest), int(latest)))], 0.0
        else:
            return [float(ws)], float(last_rt - win_len)

    # Multi-episode case: reserve full runtime for every episode (including final episode finishing <= we)
    min_gap_floor = 1.0
    min_total_needed = total_runtime + (n - 1) * min_gap_floor
    slack = win_len - min_total_needed

    if slack >= 0:
        if style in ("gap", "binge"):
            min_g, max_g = (15, 45) if style == "gap" else (1, 5)
            extra_gaps = [max(0.0, random.randint(min_g, max_g) - min_gap_floor) for _ in range(n - 1)]
            total_extra = sum(extra_gaps)
            if total_extra > slack:
                scale = slack / max(1e-6, total_extra)
                extra_gaps = [g * scale for g in extra_gaps]
                total_extra = sum(extra_gaps)

            leftover = max(0.0, slack - total_extra)
            start_pos = float(ws) if pin_first_at_start else float(ws + random.uniform(0.0, leftover))
            pts = [start_pos]
            cur = start_pos
            for i in range(n - 1):
                cur += runtimes[i] + min_gap_floor + extra_gaps[i]
                pts.append(cur)
            return pts, 0.0

        # Default "spread" style: spread naturally across the full window with varied breaks
        lead_w = 0.0 if pin_first_at_start else random.uniform(0.25, 0.65)
        tail_w = random.uniform(0.20, 0.60)
        gap_weights = [random.uniform(0.65, 1.45) for _ in range(n - 1)]

        extra_min_gap = min(14.0, (slack * 0.40) / (n - 1)) if slack >= (n - 1) * 4 else 0.0
        distributable = max(0.0, slack - extra_min_gap * (n - 1))
        total_w = lead_w + tail_w + sum(gap_weights)

        lead = distributable * (lead_w / total_w) if total_w > 0 else 0.0
        gaps = [min_gap_floor + extra_min_gap + (distributable * (w / total_w) if total_w > 0 else 0.0) for w in gap_weights]

        cur = ws + lead
        pts = [cur]
        for i in range(n - 1):
            cur += runtimes[i] + gaps[i]
            pts.append(cur)
        return pts, 0.0

    # Window shorter than total actual episode runtimes: still honor 100% of each episode's runtime + 1-2m gap
    cur = float(ws)
    pts = [cur]
    for i in range(n - 1):
        cur += runtimes[i] + random.uniform(1.0, 2.0)
        pts.append(cur)
    end_time = pts[-1] + last_rt
    return pts, max(0.0, end_time - we)


def generate_day_timestamps(d: date, count: int, runtime_min: int = 24, start_time_str: str = "", ep_runtimes=None, warnings_out=None):
    """
    Generates `count` chronological IST datetimes on date `d`, strictly respecting
    Trakt episode lengths (runtimes) and college-era / post-college schedule windows.
    - Guarantees next_start >= prev_start + prev_runtime (never overlaps unfinished eps).
    - If total runtime exceeds the standard window (e.g. 15 x 42m = 10h 30m on a 9h college day),
      expands the day's evening/morning window cleanly up to 23:55 and logs a notice in warnings_out.
    """
    if count <= 0:
        return []

    windows, _ = get_schedule_windows(d)
    style = APP_CONFIG.get("timestamp_style", "spread")
    runtimes = [
        max(5, min((ep_runtimes[i] if ep_runtimes and i < len(ep_runtimes) and ep_runtimes[i] else runtime_min), 180))
        for i in range(count)
    ]
    total_rt = sum(runtimes)
    min_needed_day = total_rt + max(0, count - 1) * 1

    minute_points = []
    notes = []

    if start_time_str.strip():
        cur_min = parse_hhmm(start_time_str)
        if len(windows) == 2 and cur_min < 7 * 60:
            m_count = 0
            m_end = cur_min
            for rt in runtimes:
                gap = 0 if m_count == 0 else 2
                if m_end + gap + rt <= 7 * 60:
                    m_end += gap + rt
                    m_count += 1
                else:
                    break
            if m_count == 0:
                m_count = 1
            pts_m, _ = _spread_minutes_in_window(cur_min, 7 * 60, runtimes[:m_count], pin_first_at_start=True, style=style)
            minute_points.extend(pts_m)
            if m_count < count:
                rem_rts = runtimes[m_count:]
                rem_needed = sum(rem_rts) + max(0, len(rem_rts) - 1)
                eve_end = 22 * 60
                if rem_needed > (eve_end - 14 * 60):
                    eve_end = min(23 * 60 + 55, 14 * 60 + rem_needed + 10)
                    notes.append(
                        f"{d.strftime('%a %Y-%m-%d')}: {count} eps need {format_duration(total_rt)} (Trakt episode lengths); "
                        f"extended evening cutoff past 22:00 to avoid episode overlap."
                    )
                pts_e, _ = _spread_minutes_in_window(14 * 60, eve_end, rem_rts, pin_first_at_start=False, style=style)
                minute_points.extend(pts_e)
        else:
            end_min = 22 * 60 if cur_min < 21 * 60 else 23 * 60 + 55
            if cur_min + min_needed_day > end_min:
                end_min = min(23 * 60 + 55, cur_min + min_needed_day + 5)
                if cur_min + min_needed_day > 22 * 60:
                    notes.append(
                        f"{d.strftime('%a %Y-%m-%d')}: {count} eps ({format_duration(total_rt)}) starting at {start_time_str} "
                        f"extended past 22:00 to preserve full episode runtimes."
                    )
            pts, _ = _spread_minutes_in_window(cur_min, end_min, runtimes, pin_first_at_start=True, style=style)
            minute_points.extend(pts)
    else:
        if len(windows) == 2:
            # College weekday: 06:00-07:00 (60m) + 14:00-22:00 (480m) = 540m standard
            max_morning = 0
            m_acc = 0
            for rt in runtimes:
                needed = rt if max_morning == 0 else (rt + 5)
                if m_acc + needed <= 60:
                    m_acc += needed
                    max_morning += 1
                else:
                    break

            if max_morning == 0:
                m_count = 0
            elif count == 1:
                m_count = 1 if random.random() < 0.20 else 0
            elif count <= 3:
                m_count = 1 if random.random() < 0.40 else 0
            else:
                aft_needed_all = total_rt + max(0, count - 1)
                if aft_needed_all > 480:
                    m_count = max_morning
                else:
                    m_count = min(max_morning, 1 if count <= 10 else 2)

            m_rts = runtimes[:m_count]
            e_rts = runtimes[m_count:]
            e_needed = sum(e_rts) + max(0, len(e_rts) - 1)

            if e_needed <= 480:
                if m_count > 0:
                    pts_m, _ = _spread_minutes_in_window(6 * 60, 7 * 60, m_rts, style=style)
                    minute_points.extend(pts_m)
                if e_rts:
                    pts_e, _ = _spread_minutes_in_window(14 * 60, 22 * 60, e_rts, style=style)
                    minute_points.extend(pts_e)
            elif e_needed <= (23 * 60 + 55 - 14 * 60):
                if m_count > 0:
                    pts_m, _ = _spread_minutes_in_window(6 * 60, 7 * 60, m_rts, style=style)
                    minute_points.extend(pts_m)
                eve_end = min(23 * 60 + 55, 14 * 60 + e_needed + 15)
                pts_e, _ = _spread_minutes_in_window(14 * 60, eve_end, e_rts, style=style)
                minute_points.extend(pts_e)
                notes.append(
                    f"{d.strftime('%a %Y-%m-%d')}: {count} eps need {format_duration(total_rt)} (Trakt lengths), "
                    f"exceeding 9h college window -> extended evening to ~{eve_end//60:02d}:{eve_end%60:02d} IST (kept 07:00-14:00 clear)."
                )
            else:
                day_start = max(10, (23 * 60 + 55) - min_needed_day - 30)
                if min_needed_day <= (23 * 60 + 45):
                    pts_all, _ = _spread_minutes_in_window(day_start, 23 * 60 + 55, runtimes, style=style)
                    minute_points.extend(pts_all)
                    notes.append(
                        f"{d.strftime('%a %Y-%m-%d')}: {count} eps need {format_duration(total_rt)} (Trakt lengths), exceeding college afternoon capacity; "
                        f"used extended day window ({day_start//60:02d}:{day_start%60:02d}-23:55 IST) so episodes never overlap."
                    )
                else:
                    step = (23 * 60 + 40) / max(1, count - 1)
                    minute_points = [10.0 + i * step for i in range(count)]
                    notes.append(
                        f"{d.strftime('%a %Y-%m-%d')}: WARNING — {count} eps total {format_duration(total_rt)} (>24h in 1 day!). "
                        f"Consider spreading across more days."
                    )
        else:
            ws, we = windows[0]
            if min_needed_day <= (we - ws):
                pts, _ = _spread_minutes_in_window(ws, we, runtimes, style=style)
                minute_points.extend(pts)
            elif min_needed_day <= (23 * 60 + 55 - 6 * 60):
                ext_start = max(6 * 60, ws - max(0, (min_needed_day - (23 * 60 + 55 - ws))))
                ext_end = min(23 * 60 + 55, ext_start + min_needed_day + 20)
                pts, _ = _spread_minutes_in_window(ext_start, ext_end, runtimes, style=style)
                minute_points.extend(pts)
                notes.append(
                    f"{d.strftime('%a %Y-%m-%d')}: {count} eps need {format_duration(total_rt)} (Trakt lengths) > 15h; "
                    f"extended window to {ext_start//60:02d}:{ext_start%60:02d}-{ext_end//60:02d}:{ext_end%60:02d} IST."
                )
            elif min_needed_day <= (23 * 60 + 45):
                pts, _ = _spread_minutes_in_window(10, 23 * 60 + 55, runtimes, style=style)
                minute_points.extend(pts)
                notes.append(
                    f"{d.strftime('%a %Y-%m-%d')}: {count} eps need {format_duration(total_rt)}; used full 24h day to prevent overlap."
                )
            else:
                step = (23 * 60 + 40) / max(1, count - 1)
                minute_points = [10.0 + i * step for i in range(count)]
                notes.append(
                    f"{d.strftime('%a %Y-%m-%d')}: WARNING — {count} eps total {format_duration(total_rt)} (>24h in 1 day!). "
                    f"Consider spreading across more days."
                )

    if warnings_out is not None and notes:
        warnings_out.extend(notes)

    timestamps = []
    prev_total_sec = -1
    for m_val in minute_points:
        clamped_m = max(0.0, min(m_val, 23 * 60 + 58))
        base_sec = int(clamped_m) * 60 + random.randint(0, 59)
        if base_sec <= prev_total_sec:
            base_sec = min(23 * 3600 + 59 * 60 + 59, prev_total_sec + 60)
        prev_total_sec = base_sec
        hh = base_sec // 3600
        mm = (base_sec % 3600) // 60
        ss = base_sec % 60
        timestamps.append(datetime(d.year, d.month, d.day, hh, mm, ss, tzinfo=get_local_tz()))

    return timestamps


# ----------------- SYNC & CONFIRMATION -----------
def format_record_new_ts(r):
    if r.get("use_released"):
        fa = r.get("first_aired")
        if fa:
            try:
                fa_ist = to_ist(fa)
                return f"RELEASED ({fa_ist.strftime('%a %Y-%m-%d %H:%M')} {get_tz_label()})"
            except Exception:
                return f"RELEASED ({fa})"
        return "RELEASED (Trakt original air date)"
    dt = r["new_dt"]
    return f"{dt.strftime('%a %Y-%m-%d %H:%M:%S')} {get_tz_label()}"


def build_watched_at_value(r):
    if r.get("use_released"):
        return "released"
    return r["new_dt"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def append_local_log(show_title, batch_records):
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    logs.append({
        "logged_at_ist": datetime.now(get_local_tz()).isoformat(),
        "show": show_title,
        "count": len(batch_records),
        "episodes": [
            {
                "code": ep_code(r),
                "title": r.get("title") or "Untitled",
                "new_watched_at": format_record_new_ts(r),
                "removed_history_ids": r["old_history_ids"],
            }
            for r in batch_records
        ],
    })
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)


def print_batch_preview_lines(batch_records):
    def fmt_line(r):
        old_str = r["old_dates"][0] if r["old_dates"] else "unwatched"
        rt = r.get("runtime")
        rt_tag = f"[{rt}m]" if rt else ""
        lbl = ep_label(r, max_title=25)
        return f"  {lbl:<35} {rt_tag:>5} | {format_record_new_ts(r):<34} (was: {old_str})"

    if len(batch_records) <= 25:
        for r in batch_records:
            print(fmt_line(r))
    else:
        for r in batch_records[:10]:
            print(fmt_line(r))
        print(f"  ... ({len(batch_records) - 15} more episodes in this batch) ...")
        for r in batch_records[-5:]:
            print(fmt_line(r))


def choose_sync_mode():
    pref = APP_CONFIG.get("default_sync_mode", "ask")
    if pref in ("immediate", "quick", "double"):
        print(f"\nSync Speed: {pref.upper()} (change anytime via 'cache' menu)")
        return pref

    print("\nChoose Sync Speed:")
    print("  1) UPDATE IMMEDIATELY  (Syncs right away after each day/batch — no extra prompts)")
    print("  2) QUICK 1-CONFIRM     (Shows preview, press Enter to upload immediately)")
    print("  3) SAFE DOUBLE-CONFIRM (Shows preview, asks twice: yes + YES)")
    pick = input("Enter 1, 2, or 3 [default: 1]: ").strip() or "1"
    return {"1": "immediate", "2": "quick", "3": "double"}.get(pick, "immediate")


def sync_batch_to_trakt(show_title, batch_records, token, sync_mode="double"):
    """
    sync_mode:
      - "immediate": prints preview and uploads immediately without extra prompts
      - "quick":     prints preview and uploads on Enter / y (type 'n' to skip)
      - "double":    prints preview and requires yes + YES confirmation
    """
    if not batch_records:
        return True

    print("\n" + "=" * 102)
    mode_tag = {"immediate": "IMMEDIATE SYNC", "quick": "QUICK SYNC", "double": "SAFE BATCH"}[sync_mode]
    print(f"[{mode_tag}] {show_title} ({len(batch_records)} episode(s))")
    print("=" * 102)
    print_batch_preview_lines(batch_records)
    print("=" * 102)

    if sync_mode == "quick":
        c = input(f"\nUpload these {len(batch_records)} episode(s) to Trakt now? (Enter/y=yes, n=skip): ").strip().lower()
        if c in ("n", "no"):
            print("  -> Skipped. Nothing changed on Trakt.")
            return False
    elif sync_mode == "double":
        c1 = input(f"\n[Confirm 1/2] Save & upload these {len(batch_records)} episode(s) to Trakt? (yes/no): ").strip().lower()
        if c1 not in ("y", "yes"):
            print("  -> Batch skipped / cancelled. Nothing changed on Trakt.")
            return False

        c2 = input(f"[Confirm 2/2] FINAL CHECK — Update Trakt for these {len(batch_records)} episode(s)? Type YES to upload: ").strip()
        if c2 != "YES":
            print("  -> Cancelled on 2nd confirmation. Nothing changed on Trakt.")
            return False
    else:
        print("\nUpdating Trakt immediately...")

    old_ids = []
    for r in batch_records:
        old_ids.extend(r["old_history_ids"])

    if old_ids:
        print(f"  Removing {len(old_ids)} old history record(s)...")
        for i in range(0, len(old_ids), 100):
            chunk = old_ids[i : i + 100]
            s, res = api_request("POST", "/sync/history/remove", {"ids": chunk}, access_token=token)
            if s != 200:
                print(f"  [ERROR] Remove failed ({s}): {res}")
                return False
            time.sleep(1.05)

    episodes_payload = [
        {
            "ids": {"trakt": r["ep_trakt_id"]},
            "watched_at": build_watched_at_value(r),
        }
        for r in batch_records
    ]

    print(f"  Uploading {len(episodes_payload)} episode timestamp(s)...")
    total_added = 0
    for i in range(0, len(episodes_payload), 100):
        chunk = episodes_payload[i : i + 100]
        s, res = api_request("POST", "/sync/history", {"episodes": chunk}, access_token=token)
        if s in (200, 201):
            total_added += res.get("added", {}).get("episodes", 0)
        else:
            print(f"  [ERROR] Upload failed ({s}): {res}")
            return False
        if i + 100 < len(episodes_payload):
            time.sleep(1.05)

    append_local_log(show_title, batch_records)
    print(f"  [SUCCESS] Synced {total_added} episode(s) to Trakt! (Logged to trakt_edit_log.json)\n")
    return True


# ----------------- PARSERS & EPISODE BROWSER -----
def print_episode_guide(episodes_ordered, season_filter=None, show_all=False, page=1, page_size=25):
    filtered = [
        (idx, ep)
        for idx, ep in enumerate(episodes_ordered, 1)
        if season_filter is None or ep["season"] == season_filter
    ]
    total = len(filtered)
    if total == 0:
        print("\n  No episodes found" + (f" for Season {season_filter}." if season_filter is not None else "."))
        return 1

    if season_filter is not None:
        slice_items = filtered
        total_pages = 1
        title_bar = f"SEASON {season_filter:02d} EPISODES ({total} eps)" if season_filter > 0 else f"SPECIALS — SEASON 00 ({total} eps)"
    elif show_all:
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        slice_items = filtered[start : start + page_size]
        title_bar = f"ALL EPISODES — Page {page}/{total_pages} ({total} total)"
    else:
        slice_items = filtered[:30]
        total_pages = 1
        title_bar = f"EPISODE GUIDE (showing {len(slice_items)} of {total})"

    print("\n" + "=" * 106)
    print(f"  {title_bar}")
    print("-" * 106)
    print(f"{'#':>4} | {'Code':<7} | {'Episode Name':<38} | {'Len':>4} | {'Aired':<10} | {'My Status'}")
    print("-" * 106)
    for idx, ep in slice_items:
        aired_s = short_date_ist(ep.get("first_aired"))
        rt = ep.get("runtime")
        rt_s = f"{rt}m" if rt else "-"
        status_s = f"Watched ({ep['old_dates'][0]})" if ep["old_dates"] else "Unwatched"
        print(
            f"{idx:>4} | {ep_code(ep):<7} | {truncate(ep.get('title') or 'Untitled', 38):<38} | "
            f"{rt_s:>4} | {aired_s:<10} | {status_s}"
        )
    if not show_all and season_filter is None and total > 30:
        print(f"... showing first 30 of {total}. Type 's1', 's2', etc. to view a specific season.")
    print("=" * 106)
    return total_pages


def print_seasons_overview(show_title, seasons_db, db_regular_aired, db_specials):
    """Renders a clean Season-by-Season summary table with progress %, total runtime & aired range."""
    season_titles = {}
    for s in seasons_db:
        s_num = s.get("number")
        if s_num is not None:
            season_titles[s_num] = s.get("title") or ("Specials" if s_num == 0 else f"Season {s_num}")

    by_season = {}
    for ep in db_regular_aired:
        by_season.setdefault(ep["season"], []).append(ep)
    if db_specials:
        by_season[0] = list(db_specials)

    season_nums = sorted(k for k in by_season if k > 0)
    if 0 in by_season:
        season_nums.append(0)

    print("\n" + "=" * 108)
    print(f"  SEASON & EPISODE OVERVIEW: {show_title}")
    print("-" * 108)
    print(f"{'Season':<7} | {'Season Name':<22} | {'Progress':<18} | {'Total Len':>9} | {'Aired Range':<24} | {'Status'}")
    print("-" * 108)

    for s_num in season_nums:
        eps = by_season[s_num]
        total_cnt = len(eps)
        watched_cnt = sum(1 for e in eps if e["old_dates"])
        pct = (watched_cnt / total_cnt * 100.0) if total_cnt else 0.0
        total_min = sum((e.get("runtime") or 0) for e in eps)

        aired_dates = sorted(short_date_ist(e.get("first_aired")) for e in eps if e.get("first_aired"))
        aired_dates = [d for d in aired_dates if d != "-"]
        if aired_dates:
            aired_range = f"{aired_dates[0]} -> {aired_dates[-1]}" if len(aired_dates) > 1 else aired_dates[0]
        else:
            aired_range = "-"

        if watched_cnt == total_cnt and total_cnt > 0:
            st = "Completed"
        elif watched_cnt > 0:
            st = f"Watching ({total_cnt - watched_cnt} left)"
        else:
            st = "Unwatched"

        s_code = f"S{s_num:02d}"
        s_title = truncate(season_titles.get(s_num, f"Season {s_num}"), 22)
        prog_s = f"{watched_cnt}/{total_cnt} ({pct:5.1f}%)"
        print(f"{s_code:<7} | {s_title:<22} | {prog_s:<18} | {format_duration(total_min):>9} | {aired_range:<24} | {st}")

    print("=" * 108)
    return season_nums


def browse_seasons_and_episodes(show_title, seasons_db, db_regular_aired, db_specials):
    """Interactive Season & Episode-wise browser."""
    while True:
        season_nums = print_seasons_overview(show_title, seasons_db, db_regular_aired, db_specials)
        cmd = input(
            "Enter Season # to list episodes (e.g. 1, 2, 0=Specials) | 'all' paginated | 'u' unwatched | Enter=back: "
        ).strip().lower()

        if not cmd or cmd in ("b", "back", "q"):
            break

        if cmd == "u":
            unwatched = [e for e in db_regular_aired if not e["old_dates"]]
            if not unwatched:
                print("\n  All aired regular episodes are watched!")
                continue
            page = 1
            while True:
                tp = print_episode_guide(unwatched, show_all=True, page=page, page_size=25)
                if tp <= 1:
                    input("Press Enter to return to Seasons overview...")
                    break
                nav = input(f"Unwatched Page {page}/{tp} — [n] Next | [p] Prev | [b] Back: ").strip().lower()
                if nav == "n" and page < tp:
                    page += 1
                elif nav == "p" and page > 1:
                    page -= 1
                else:
                    break
            continue

        if cmd == "all":
            page = 1
            while True:
                tp = print_episode_guide(db_regular_aired, show_all=True, page=page, page_size=25)
                if tp <= 1:
                    input("Press Enter to return to Seasons overview...")
                    break
                nav = input(f"All Episodes Page {page}/{tp} — [n] Next | [p] Prev | [s<N>] Jump Season | [b] Back: ").strip().lower()
                if nav == "n" and page < tp:
                    page += 1
                elif nav == "p" and page > 1:
                    page -= 1
                elif re.match(r"^s(\d+)$", nav):
                    s_target = int(nav[1:])
                    pool_v = db_specials if s_target == 0 else db_regular_aired
                    print_episode_guide(pool_v, season_filter=s_target)
                    input("Press Enter to continue...")
                else:
                    break
            continue

        m_s = re.match(r"^s?(\d+)$", cmd)
        if m_s:
            s_num = int(m_s.group(1))
            if s_num not in season_nums:
                print(f"  Season {s_num} not found for this show.")
                continue
            pool_view = db_specials if s_num == 0 else db_regular_aired
            print_episode_guide(pool_view, season_filter=s_num)
            input("Press Enter to return to Seasons overview...")
            continue

        print("  Enter a season number (e.g. 1, 2, 0), 'all', 'u', or press Enter to go back.")


def resolve_single_token(tok, episodes_ordered):
    """Resolves a single position token ('23', 'S02E01', '2x1') to 1-based index or (None, err_msg)."""
    tok = tok.strip()
    total = len(episodes_ordered)
    if tok.isdigit():
        pos = int(tok)
        if 1 <= pos <= total:
            return pos, None
        return None, (
            f"[Out of range] #{pos} is outside loaded episodes "
            f"(#1 {ep_code(episodes_ordered[0])} to #{total} {ep_code(episodes_ordered[-1])})."
        )

    m = re.match(r"^[sS]?(\d+)[eExX](\d+)$", tok)
    if m:
        s_target, e_target = int(m.group(1)), int(m.group(2))
        for idx, ep in enumerate(episodes_ordered, 1):
            if ep["season"] == s_target and ep["number"] == e_target:
                return idx, None
        return None, f"[Not found] S{s_target:02d}E{e_target:02d} is not in the loaded list. Type 's{s_target}' to view."

    return None, None


def parse_range_expression(raw, episodes_ordered):
    """
    Parses range expressions like:
      - '1-3' or '1 - 3' or '1 to 3'
      - 'S02E01-S02E05' or '2x1-2x5'
      - 'all' -> (1, total)
      - 'season 2' or 'all s2' -> full season 2 range
    Returns (start_pos, end_pos, err_msg) or (None, None, None) if not a range.
    """
    text = raw.strip()
    low = text.lower()
    total = len(episodes_ordered)

    if low == "all":
        return 1, total, None

    m_all_s = re.match(r"^(?:all\s+s|season\s*)(\d+)$", low)
    if m_all_s:
        s_num = int(m_all_s.group(1))
        idxs = [i for i, ep in enumerate(episodes_ordered, 1) if ep["season"] == s_num]
        if idxs:
            return idxs[0], idxs[-1], None
        return None, None, f"[Not found] No loaded episodes for Season {s_num}."

    # Split on '-' or 'to'
    m_rng = re.match(r"^([^\s\-]+)\s*(?:-|to)\s*([^\s\-]+)$", text, re.IGNORECASE)
    if m_rng:
        left_tok, right_tok = m_rng.group(1), m_rng.group(2)
        p1, err1 = resolve_single_token(left_tok, episodes_ordered)
        if err1:
            return None, None, err1
        p2, err2 = resolve_single_token(right_tok, episodes_ordered)
        if err2:
            return None, None, err2
        if p1 is not None and p2 is not None:
            return (p1, p2, None) if p1 <= p2 else (p2, p1, None)
        return None, None, "Could not parse range. Examples: 1-3, S02E01-S02E05, or 2x1-2x5."

    return None, None, None


def prompt_episode_range(episodes_ordered, default_start):
    """
    Prompts for Start (or full range like '1-3' / 'S02E01-S02E05' / 'season 2').
    If a range is entered on the first prompt, skips asking for Stop!
    """
    total = len(episodes_ordered)
    def_start_ep = episodes_ordered[default_start - 1]
    def_end_ep = episodes_ordered[-1]

    while True:
        raw = input(
            f"Start or Range (e.g. 1-3, S02E01-S02E05, 'season 2', 's2'/'list' to browse) "
            f"[default: #{default_start} {ep_code(def_start_ep)}]: "
        ).strip()

        if not raw:
            start_pos = default_start
            break

        low = raw.lower()
        if low == "list":
            print_episode_guide(episodes_ordered)
            continue
        m_browse = re.match(r"^s(\d+)$", low)
        if m_browse:
            print_episode_guide(episodes_ordered, season_filter=int(m_browse.group(1)))
            continue

        r_start, r_end, r_err = parse_range_expression(raw, episodes_ordered)
        if r_err:
            print(f"  {r_err}")
            continue
        if r_start is not None:
            return r_start, r_end

        pos, err = resolve_single_token(raw, episodes_ordered)
        if err:
            print(f"  {err}")
            continue
        if pos is not None:
            start_pos = pos
            break

        print("  Invalid input. Examples: 1, 1-3, S02E01, S02E01-S02E05, 'season 2', or 's2' to browse.")

    # Ask for Stop position
    while True:
        raw_end = input(
            f"Stop at (1-{total}, S##E##, 's2'/'list' to browse) [default: #{total} {ep_code(def_end_ep)}]: "
        ).strip()
        if not raw_end:
            end_pos = total
            break

        low = raw_end.lower()
        if low == "list":
            print_episode_guide(episodes_ordered)
            continue
        m_browse = re.match(r"^s(\d+)$", low)
        if m_browse:
            print_episode_guide(episodes_ordered, season_filter=int(m_browse.group(1)))
            continue

        pos, err = resolve_single_token(raw_end, episodes_ordered)
        if err:
            print(f"  {err}")
            continue
        if pos is not None:
            end_pos = pos
            break

        print("  Invalid input. Enter an episode # (e.g. 5) or code (e.g. S02E05).")

    return (start_pos, end_pos) if start_pos <= end_pos else (end_pos, start_pos)


def parse_flexible_date(raw):
    text = raw.strip().replace("/", "-")
    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", text):
        y, m, d = (int(x) for x in text.split("-"))
        return date(y, m, d)
    # DD-MM-YYYY
    if re.match(r"^\d{1,2}-\d{1,2}-\d{4}$", text):
        d, m, y = (int(x) for x in text.split("-"))
        return date(y, m, d)
    raise ValueError("Use YYYY-MM-DD (e.g. 2022-11-30) or DD-MM-YYYY (e.g. 30-11-2022).")


def prompt_date(label, default_date=None):
    hint = f" [default: {default_date.isoformat()}]" if default_date else ""
    while True:
        raw = input(f"{label} (YYYY-MM-DD or DD-MM-YYYY){hint}: ").strip()
        if not raw and default_date:
            return default_date
        try:
            return parse_flexible_date(raw)
        except ValueError as e:
            print(f"  Invalid date: {e}")


# ----------------- EDITING MODES -----------------
def build_auto_schedule(episodes_slice, start_d: date, end_d: date, runtime_min: int, warnings_out=None):
    total_eps = len(episodes_slice)
    if total_eps == 0:
        return []
    total_days = max(1, (end_d - start_d).days + 1)

    base_per_day = total_eps // total_days
    remainder = total_eps % total_days
    day_counts = [base_per_day + (1 if i < remainder else 0) for i in range(total_days)]

    if total_eps < total_days:
        day_counts = [0] * total_days
        for i in range(total_eps):
            idx = round(i * (total_days - 1) / max(1, total_eps - 1)) if total_eps > 1 else 0
            day_counts[idx] += 1

    scheduled = []
    ep_idx = 0
    for day_offset, cnt in enumerate(day_counts):
        if cnt <= 0:
            continue
        cur_d = start_d + timedelta(days=day_offset)
        day_eps = episodes_slice[ep_idx : ep_idx + cnt]
        day_runtimes = [e.get("runtime") for e in day_eps]
        ts_list = generate_day_timestamps(
            cur_d, cnt, runtime_min=runtime_min, ep_runtimes=day_runtimes, warnings_out=warnings_out
        )
        for ts, ep in zip(ts_list, day_eps):
            rec = dict(ep)
            rec["new_dt"] = ts
            rec["use_released"] = False
            scheduled.append(rec)
        ep_idx += cnt
    return scheduled


def sync_release_date_mode(show_title, target_eps, token):
    aired_eps = [ep for ep in target_eps if not is_future_airdate(ep.get("first_aired"))]
    skipped = len(target_eps) - len(aired_eps)
    if skipped > 0:
        print(f"  [Info] Skipped {skipped} future/unaired episode(s) so you don't log unreleased content.")
    if not aired_eps:
        print("No aired episodes to sync.")
        return False

    sync_mode = choose_sync_mode()
    if sync_mode == "immediate":
        batch_size = len(aired_eps)  # Push all selected in 100-ep API chunks immediately
    else:
        batch_raw = input(
            f"Sync batch size for Release Date mode [default: {DEFAULT_RELEASE_BATCH_SIZE}, or enter 15]: "
        ).strip()
        batch_size = max(1, int(batch_raw)) if batch_raw.isdigit() else DEFAULT_RELEASE_BATCH_SIZE

    scheduled = []
    for ep in aired_eps:
        rec = dict(ep)
        rec["use_released"] = True
        rec["new_dt"] = None
        scheduled.append(rec)

    print(f"\nPrepared {len(scheduled)} episode(s) to save with their exact Release Date & Time.")
    synced_any = False
    for i in range(0, len(scheduled), batch_size):
        batch = scheduled[i : i + batch_size]
        ok = sync_batch_to_trakt(show_title, batch, token, sync_mode=sync_mode)
        if ok:
            synced_any = True
        else:
            cont = input("Continue to next batch or stop editing? (c=continue / s=stop): ").strip().lower()
            if cont != "c":
                break
    return synced_any


def run_editor_for_show(show_title, episodes_ordered, runtime_min, token):
    total_eps = len(episodes_ordered)

    last_watched_idx = None
    first_unwatched_idx = None
    for idx, ep in enumerate(episodes_ordered, 1):
        if ep["old_dates"]:
            last_watched_idx = idx
        elif first_unwatched_idx is None:
            first_unwatched_idx = idx

    print(f"\nTotal episodes loaded: {total_eps}")
    first_tag = " [Unwatched]" if not episodes_ordered[0]["old_dates"] else f" [{episodes_ordered[0]['old_dates'][0]}]"
    print(f"  First:          #1   = {ep_label(episodes_ordered[0])}{first_tag}")
    if last_watched_idx is not None and last_watched_idx != 1:
        lw = episodes_ordered[last_watched_idx - 1]
        print(f"  Last Watched:   #{last_watched_idx:<3} = {ep_label(lw)} [{lw['old_dates'][0]}]")
    if first_unwatched_idx is not None and first_unwatched_idx != 1:
        fu = episodes_ordered[first_unwatched_idx - 1]
        print(f"  Next Unwatched: #{first_unwatched_idx:<3} = {ep_label(fu)} [Unwatched]")
    if total_eps > 1:
        print(f"  Last:           #{total_eps:<3} = {ep_label(episodes_ordered[-1])}")

    default_start = first_unwatched_idx if (last_watched_idx and first_unwatched_idx) else 1
    print()
    start_pos, end_pos = prompt_episode_range(episodes_ordered, default_start)

    target_eps = episodes_ordered[start_pos - 1 : end_pos]
    if not target_eps:
        print("No episodes in selected range.")
        return False

    sel_total_min = sum((e.get("runtime") or runtime_min) for e in target_eps)
    print(
        f"\nSelected {len(target_eps)} episode(s) (~{format_duration(sel_total_min)} total Trakt runtime): "
        f"{ep_label(target_eps[0], 28)}  -->  {ep_label(target_eps[-1], 28)}"
    )

    print("\nChoose Editing Mode:")
    print("  1) MANUAL DAY-BY-DAY       (Shows weekday/weekend, asks episodes & optional start time per day)")
    print("  2) AUTOMATIC SPREAD        (Auto-distributes selected episodes from Start Date to Catch-up Date)")
    print("  3) WATCHED ON RELEASE DATE (Auto-saves each episode's exact air/release date & time on Trakt)")
    mode = input("Enter 1, 2, or 3: ").strip()

    if mode == "3":
        return sync_release_date_mode(show_title, target_eps, token)

    if mode not in ("1", "2"):
        print("Invalid mode selection. Cancelled.")
        return False

    start_d = prompt_date("Enter Start Date")
    if mode == "2":
        catchup_d = prompt_date("Enter Catch-up / Finish Date", default_date=start_d)
    else:
        catchup_d = prompt_date("Enter Catch-up / Finish Date (Enter if same/open)", default_date=start_d)

    if catchup_d < start_d:
        print("Catch-up date cannot be before Start Date. Swapping them.")
        start_d, catchup_d = catchup_d, start_d

    sync_mode = choose_sync_mode()
    if sync_mode == "immediate":
        batch_size = 1 if mode == "1" else len(target_eps)
    else:
        batch_raw = input(f"Sync batch size (ask to update Trakt every N episodes) [default: {DEFAULT_BATCH_SIZE}]: ").strip()
        batch_size = max(1, int(batch_raw)) if batch_raw.isdigit() else DEFAULT_BATCH_SIZE

    synced_any = False

    if mode == "2":
        rt_warnings = []
        scheduled = build_auto_schedule(target_eps, start_d, catchup_d, runtime_min, warnings_out=rt_warnings)
        print(f"\nGenerated {len(scheduled)} timestamp(s) from {start_d} to {catchup_d} (Trakt episode lengths enforced).")
        for w in rt_warnings[:8]:
            print(f"  [Runtime Check] {w}")
        if len(rt_warnings) > 8:
            print(f"  [Runtime Check] ... and {len(rt_warnings) - 8} more day(s) extended to prevent overlap.")
        for i in range(0, len(scheduled), batch_size):
            batch = scheduled[i : i + batch_size]
            ok = sync_batch_to_trakt(show_title, batch, token, sync_mode=sync_mode)
            if ok:
                synced_any = True
            else:
                cont = input("Continue to next batch or stop editing? (c=continue / s=stop): ").strip().lower()
                if cont != "c":
                    break
        return synced_any

    # Mode 1: Manual Day-by-Day
    print("\n--- MANUAL DAY-BY-DAY MODE ---")
    if sync_mode == "immediate":
        print("Immediate Mode ON: Each day's episodes upload to Trakt right away!")
    print("Tips: Enter a number (e.g. 5), 0 to skip a day, 'sync' to upload queued now, 'auto' for rest, or 'q' to stop.\n")

    cur_d = start_d
    ep_cursor = 0
    pending_batch = []

    while ep_cursor < len(target_eps):
        remaining = len(target_eps) - ep_cursor
        next_ep = target_eps[ep_cursor]
        _, rule_label = get_schedule_windows(cur_d)
        day_header = f"{cur_d.strftime('%a, %b %d, %Y')}  [{rule_label}]"
        queue_info = "IMMEDIATE" if sync_mode == "immediate" else f"Queued: {len(pending_batch)}/{batch_size}"
        print(f"\nDate: {day_header}")
        print(f"  Next episode: {ep_label(next_ep, 40)} | Remaining: {remaining} | {queue_info}")

        ans = input("  How many episodes watched this day? (number / 0 / sync / auto / q): ").strip().lower()
        if ans == "q":
            break

        if ans in ("sync", "now"):
            if pending_batch:
                if sync_batch_to_trakt(show_title, pending_batch, token, sync_mode=sync_mode):
                    synced_any = True
                pending_batch = []
            else:
                print("  Nothing queued yet.")
            continue

        if ans == "auto":
            end_for_auto = max(cur_d, catchup_d)
            if end_for_auto == cur_d and remaining > 10:
                end_for_auto = prompt_date("  Auto-fill through which Finish Date?", default_date=cur_d)
            auto_rest = build_auto_schedule(target_eps[ep_cursor:], cur_d, end_for_auto, runtime_min)
            pending_batch.extend(auto_rest)
            ep_cursor = len(target_eps)
            chunk_sz = len(pending_batch) if sync_mode == "immediate" else batch_size
            for i in range(0, len(pending_batch), chunk_sz):
                chunk = pending_batch[i : i + chunk_sz]
                if sync_batch_to_trakt(show_title, chunk, token, sync_mode=sync_mode):
                    synced_any = True
                else:
                    break
            pending_batch = []
            break

        if not ans.isdigit():
            print("  Please enter a valid number, 0, 'sync', 'auto', or 'q'.")
            continue

        cnt = int(ans)
        if cnt == 0:
            cur_d += timedelta(days=1)
            continue

        if cnt > remaining:
            print(f"  Only {remaining} episode(s) remaining; capping to {remaining}.")
            cnt = remaining

        day_eps = target_eps[ep_cursor : ep_cursor + cnt]
        day_preview = ", ".join(ep_label(e, 22) for e in day_eps[:3])
        if len(day_eps) > 3:
            day_preview += f", ... (+{len(day_eps) - 3} more)"
        print(f"  Logging: {day_preview}")

        start_time_str = input("  Start time in 24h HH:MM (or press Enter for auto smart time): ").strip()
        try:
            day_runtimes = [e.get("runtime") for e in day_eps]
            day_warns = []
            ts_list = generate_day_timestamps(
                cur_d, cnt, runtime_min=runtime_min, start_time_str=start_time_str,
                ep_runtimes=day_runtimes, warnings_out=day_warns
            )
            for w in day_warns:
                print(f"  [Runtime Check] {w}")
        except ValueError as e:
            print(f"  Time error: {e}. Try this day again.")
            continue

        day_records = []
        for ts, ep in zip(ts_list, day_eps):
            rec = dict(ep)
            rec["new_dt"] = ts
            rec["use_released"] = False
            day_records.append(rec)
        ep_cursor += cnt

        if sync_mode == "immediate":
            # Upload this day's episodes straight to Trakt right now
            if sync_batch_to_trakt(show_title, day_records, token, sync_mode="immediate"):
                synced_any = True
        else:
            pending_batch.extend(day_records)
            while len(pending_batch) >= batch_size:
                chunk = pending_batch[:batch_size]
                pending_batch = pending_batch[batch_size:]
                if sync_batch_to_trakt(show_title, chunk, token, sync_mode=sync_mode):
                    synced_any = True

        cur_d += timedelta(days=1)

    if pending_batch:
        print(f"\nYou have {len(pending_batch)} remaining queued episode(s).")
        if sync_batch_to_trakt(show_title, pending_batch, token, sync_mode=sync_mode):
            synced_any = True

    return synced_any


# ----------------- SHOW INSPECTOR ----------------
def refresh_show_in_cache(show, cache, token):
    tid = show["ids"]["trakt"]
    title = show["title"]
    new_hist = fetch_show_history(tid, token, cache=cache, use_cache=False)
    dates = sorted(it["watched_at"] for it in new_hist if it.get("watched_at"))
    reg_eps = {
        (it["episode"]["season"], it["episode"]["number"])
        for it in new_hist
        if it.get("episode", {}).get("season", 0) > 0
    }
    if dates:
        cache["watched"][tid] = {
            "plays": len(new_hist),
            "watched_eps": len(reg_eps),
            "started_at": dates[0],
            "finished_at": dates[-1],
            "last_watched_at": dates[-1],
            "aired_episodes": show.get("aired_episodes"),
            "title": title,
            "exact_hydrated": True,
        }
    cache["last_activities"] = fetch_last_activities(token)
    save_cache_to_disk(cache)
    return new_hist


def build_show_state(show, history, seasons_db, cache, runtime):
    tid = show["ids"]["trakt"]
    title = show["title"]

    db_meta_by_ep = {}
    for s in seasons_db:
        s_num = s.get("number")
        for ep in s.get("episodes", []):
            db_meta_by_ep[(s_num, ep.get("number"))] = {
                "title": ep.get("title") or "Untitled",
                "first_aired": ep.get("first_aired"),
                "runtime": ep.get("runtime") or runtime,
            }

    hist_by_ep = {}
    ts_counter = {}
    all_ist_dates = []
    reg_watched_keys = set()
    for item in history:
        ep = item.get("episode", {})
        s_num, e_num = ep.get("season"), ep.get("number")
        wa = item.get("watched_at")
        hid = item.get("id")
        if s_num is None or e_num is None or not wa:
            continue
        if s_num > 0:
            reg_watched_keys.add((s_num, e_num))
        dt_ist = to_ist(wa)
        all_ist_dates.append(dt_ist)
        ts_key = dt_ist.strftime("%Y-%m-%d %H:%M:%S")
        ts_counter[ts_key] = ts_counter.get(ts_key, 0) + 1
        meta_ep = db_meta_by_ep.get((s_num, e_num), {})
        rec = hist_by_ep.setdefault((s_num, e_num), {
            "season": s_num,
            "number": e_num,
            "title": meta_ep.get("title") or ep.get("title") or "Untitled",
            "ep_trakt_id": ep.get("ids", {}).get("trakt"),
            "first_aired": meta_ep.get("first_aired"),
            "runtime": meta_ep.get("runtime") or runtime,
            "old_history_ids": [],
            "old_dates": [],
        })
        rec["old_history_ids"].append(hid)
        rec["old_dates"].append(dt_ist.strftime("%Y-%m-%d %H:%M"))

    if all_ist_dates:
        all_ist_dates.sort()
        raw_dates = sorted(it["watched_at"] for it in history if it.get("watched_at"))
        cache["watched"][tid] = {
            "plays": len(history),
            "watched_eps": len(reg_watched_keys),
            "started_at": raw_dates[0],
            "finished_at": raw_dates[-1],
            "last_watched_at": raw_dates[-1],
            "aired_episodes": show.get("aired_episodes"),
            "title": title,
            "exact_hydrated": True,
        }
        started_str = all_ist_dates[0].strftime("%a, %Y-%m-%d %H:%M IST")
        finished_str = all_ist_dates[-1].strftime("%a, %Y-%m-%d %H:%M IST")
        top_ts, top_cnt = max(ts_counter.items(), key=lambda x: x[1])
        catchup_note = f"{top_ts} IST ({top_cnt} eps logged at once)" if top_cnt >= 5 else "No single bulk spike detected"
    else:
        started_str = "-"
        finished_str = "-"
        catchup_note = "Not watched yet"

    db_regular_aired = []
    db_specials = []
    for s in seasons_db:
        s_num = s.get("number")
        for ep in s.get("episodes", []):
            e_num = ep.get("number")
            ep_tid = ep.get("ids", {}).get("trakt")
            if not ep_tid:
                continue
            existing = hist_by_ep.get((s_num, e_num))
            rec = {
                "season": s_num,
                "number": e_num,
                "title": ep.get("title") or "Untitled",
                "ep_trakt_id": ep_tid,
                "first_aired": ep.get("first_aired"),
                "runtime": ep.get("runtime") or runtime,
                "old_history_ids": list(existing["old_history_ids"]) if existing else [],
                "old_dates": list(existing["old_dates"]) if existing else [],
            }
            if s_num == 0:
                db_specials.append(rec)
            elif not is_future_airdate(rec["first_aired"]) or rec["old_dates"]:
                db_regular_aired.append(rec)

    db_regular_aired.sort(key=lambda x: (x["season"], x["number"]))
    db_specials.sort(key=lambda x: (x["season"], x["number"]))
    watched_regular = [e for e in db_regular_aired if e["old_dates"]]
    unwatched_regular = [e for e in db_regular_aired if not e["old_dates"]]

    return {
        "started_str": started_str,
        "finished_str": finished_str,
        "catchup_note": catchup_note,
        "db_regular_aired": db_regular_aired,
        "db_specials": db_specials,
        "watched_regular": watched_regular,
        "unwatched_regular": unwatched_regular,
    }


def inspect_and_manage_show(show, cache, token):
    tid = show["ids"]["trakt"]
    title = show["title"]
    year = show.get("year", "?")
    status_raw = show.get("status") or "unknown"
    status = status_raw.title()
    runtime = show.get("runtime") or 24
    aired_eps = show.get("aired_episodes") or "?"

    # Load episode guide & watch history ONCE (using disk cache when fresh)
    seasons_db, from_guide_cache = fetch_show_seasons_episodes(tid, token, cache, show_status=status_raw, force=False)
    history = fetch_show_history(tid, token, cache=cache, use_cache=True)
    source_tag = "cached" if from_guide_cache else "live"
    state = build_show_state(show, history, seasons_db, cache, runtime)

    while True:
        db_regular_aired = state["db_regular_aired"]
        db_specials = state["db_specials"]
        watched_regular = state["watched_regular"]
        unwatched_regular = state["unwatched_regular"]

        next_up_str = ep_label(unwatched_regular[0], 45) if unwatched_regular else "All aired episodes watched!"
        w_status, rating_str, _, _ = summarize_user_status(show, cache)

        print("\n" + "=" * 84)
        print(f"NAME:          {title} ({year})   [Trakt ID: {tid} | Guide: {source_tag}]")
        print(f"TITLE STATUS:  {status}  |  Runtime: ~{runtime} min/ep  |  Aired: {aired_eps} eps")
        print(f"MY STATUS:     {w_status}")
        print(f"NEXT UP:       {next_up_str}")
        print(f"MY RATING:     {rating_str}")
        print(f"STARTED DATE:  {state['started_str']}")
        print(f"FINISHED DATE: {state['finished_str']}")
        print(f"CATCH-UP / SPIKE: {state['catchup_note']}")
        print("=" * 84)

        action = input(
            "\nOptions: [e] Edit/Log  |  [d] Release Date  |  [l] Seasons/Eps  |  [r] Rate  |  [k] Backup Show  |  [f] Refresh  |  [b] Back  |  [q] Quit : "
        ).strip().lower()

        if action == "q":
            return "quit"
        if action == "b":
            return "back"

        if action == "f":
            print(f"Force refreshing '{title}' from Trakt...")
            seasons_db, _ = fetch_show_seasons_episodes(tid, token, cache, show_status=status_raw, force=True)
            history = refresh_show_in_cache(show, cache, token)
            source_tag = "live"
            state = build_show_state(show, history, seasons_db, cache, runtime)
            continue

        if action == "r":
            rate_show_interactive(show, cache, token)
            continue

        if action == "l":
            browse_seasons_and_episodes(title, seasons_db, db_regular_aired, db_specials)
            continue

        if action == "k":
            fpath = save_show_snapshot(show, history, cache, reason="manual")
            print(f"  [SUCCESS] Show snapshot saved -> trakt_backups/{os.path.basename(fpath)} ({len(history)} plays)")
            continue

        if action == "d":
            if watched_regular:
                pool = list(watched_regular)
                print(f"\nQuick Release Date -> targeting your {len(pool)} watched regular episode(s).")
            else:
                pool = list(db_regular_aired)
                print(f"\nShow not watched yet -> targeting all {len(pool)} aired regular episode(s) from Trakt DB.")

            if db_specials:
                sp = input(f"Include Season 0 Specials ({len(db_specials)} eps)? (y/n) [default: n]: ").strip().lower()
                if sp in ("y", "yes"):
                    pool = sorted(pool + db_specials, key=lambda x: (x["season"], x["number"]))

            if not pool:
                print("No episodes available.")
                continue

            if APP_CONFIG.get("auto_backup_before_edit", True) and history:
                bk_path = save_show_snapshot(show, history, cache, reason="auto_before_release_edit")
                print(f"  [Auto-Backup] Saved pre-edit snapshot -> trakt_backups/{os.path.basename(bk_path)}")
            if sync_release_date_mode(title, pool, token):
                history = refresh_show_in_cache(show, cache, token)
                state = build_show_state(show, history, seasons_db, cache, runtime)
            continue

        if action == "e":
            print("\nWhich episodes do you want to work with?")
            print(f"  1) All aired episodes from Trakt DB ({len(db_regular_aired)} eps: {len(watched_regular)} watched, {len(unwatched_regular)} unwatched) [DEFAULT]")
            if unwatched_regular:
                print(f"  2) Unwatched episodes only ({len(unwatched_regular)} eps — starts at {ep_label(unwatched_regular[0], 30)})")
            if watched_regular:
                print(f"  3) Watched episodes only ({len(watched_regular)} eps — {ep_code(watched_regular[0])} to {ep_code(watched_regular[-1])})")

            scope = input("Enter 1, 2, or 3 [default: 1]: ").strip() or "1"

            if scope == "2" and unwatched_regular:
                pool = list(unwatched_regular)
            elif scope == "3" and watched_regular:
                pool = list(watched_regular)
            else:
                pool = list(db_regular_aired)

            if db_specials:
                sp = input(f"Include Season 0 Specials ({len(db_specials)} eps)? (y/n) [default: n]: ").strip().lower()
                if sp in ("y", "yes"):
                    pool = sorted(pool + db_specials, key=lambda x: (x["season"], x["number"]))

            if not pool:
                print("No episodes available to edit.")
                continue

            if APP_CONFIG.get("auto_backup_before_edit", True) and history:
                bk_path = save_show_snapshot(show, history, cache, reason="auto_before_edit")
                print(f"  [Auto-Backup] Saved pre-edit snapshot -> trakt_backups/{os.path.basename(bk_path)}")
            if run_editor_for_show(title, pool, runtime, token):
                history = refresh_show_in_cache(show, cache, token)
                state = build_show_state(show, history, seasons_db, cache, runtime)


# ----------------- MAIN LOOP ---------------------
def main():
    load_or_setup_config()
    token = load_or_authenticate()
    cache = load_user_account_cache(token)

    while True:
        cache_badge = "ON" if APP_CONFIG.get("cache_enabled", True) else "OFF"
        query = input(f"\nSearch Trakt DB by Show Name (commands: 'backup' | 'cache' [{cache_badge}] | 'refresh' | 'exit'): ").strip()
        if not query or query.lower() in ("exit", "quit", "q"):
            print("Goodbye!")
            break
        if query.lower() == "refresh":
            cache = load_user_account_cache(token, force_refresh=True)
            continue
        if query.lower() == "cache":
            manage_cache_menu(cache, token)
            continue
        if query.lower() == "backup":
            manage_backup_menu(cache, token)
            continue

        print(f"Searching Trakt DB for '{query}'...")
        results = search_trakt_db_shows(query, token, cache, max_results=12)
        if not results:
            print(f"No shows found on Trakt DB for '{query}'.")
            continue

        print_search_results_table(results, cache, token=token)
        pick = input("Select show # to inspect/edit/rate (or press Enter to search again): ").strip()
        if not pick:
            continue
        if not pick.isdigit() or not (1 <= int(pick) <= len(results)):
            print("Invalid selection.")
            continue

        res = inspect_and_manage_show(results[int(pick) - 1], cache, token)
        if res == "quit":
            print("Goodbye!")
            break


if __name__ == "__main__":
    main()
