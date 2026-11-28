# Security Policy

## Supported Versions

Security fixes and Trakt API compatibility updates are provided for the latest release on the `main` branch.

| Version | Supported |
| :--- | :---: |
| `1.x` (Latest) | ✅ |
| Older snapshots | ❌ |

---

## Reporting a Vulnerability

If you discover a security vulnerability (such as credential leakage, OAuth callback issues, unsafe file writes, or injection risks):

1. **Do not open a public GitHub issue** containing exploit details or exposed tokens.
2. Report the issue privately using **GitHub Private Vulnerability Reporting** under the repository's **Security → Advisories** tab.
3. If Private Vulnerability Reporting is unavailable, open a minimal issue asking the maintainer for a private contact channel without sharing sensitive details.

### What to Include
* A clear description of the vulnerability and potential impact.
* Steps to reproduce (sanitized of personal Client IDs or tokens).
* Your Python version and operating system.
* Any suggested fix or mitigation.

You can expect an initial acknowledgment within **7 days**.

---

## User Security & Privacy Best Practices

### 1. Keep OAuth Tokens & Personal Data Local
**Trakt-Rewind** uses Trakt's **PKCE OAuth 2.0** flow (requiring no Client Secret) and writes session and history files locally:
* `trakt_token.json` — Active OAuth `access_token` and `refresh_token`. **Treat this file like a password.**
* `trakt_config.json` — Your Trakt `client_id` and local schedule preferences.
* `trakt_cache.json`, `trakt_edit_log.json`, and `trakt_backups/` — Your personal watch history, ratings, and offline snapshots.

Never commit or share these files. All of them are listed in `.gitignore` and enforced by CI secret-guard checks.

### 2. Localhost OAuth Callback Scope
During initial sign-in, the CLI starts a temporary Python `HTTPServer` bound strictly to `localhost:8765` (`http://localhost:8765/callback`) solely to capture the PKCE authorization code, then shuts it down immediately.

### 3. Revoking Access if a Token Is Compromised
If your `trakt_token.json` is ever accidentally exposed:
1. Revoke the app immediately at **[https://trakt.tv/oauth/authorized_applications](https://trakt.tv/oauth/authorized_applications)**.
2. Delete the local `trakt_token.json` file (and purge it from Git history if committed).
3. Re-authenticate on your next run.

### 4. Guarding Against Accidental History Changes
* Keep **Auto-Backup Before Show Edits** enabled (`backup` → Option `5`), especially when using `IMMEDIATE` sync mode.
* Take a **Full History Snapshot** (`backup` → Option `2`) before large multi-show cleanups.