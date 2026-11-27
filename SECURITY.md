# Security Policy

## Supported Versions

Security fixes and Trakt API compatibility updates are provided for the latest release on the default branch.

| Version | Supported |
| :--- | :---: |
| Latest (`main`) | ✅ |
| Older snapshots | ❌ |

---

## Reporting a Vulnerability

If you discover a security issue (such as credential leakage, OAuth handling flaws, unsafe file writes, or injection risks):

1. **Please do not open a public GitHub issue** with sensitive exploit details or exposed tokens.
2. Report the issue privately using **GitHub Private Vulnerability Reporting** under the repository's **Security → Advisories** tab (recommended).
3. If Private Vulnerability Reporting is not enabled on this repository, open a minimal issue asking the maintainer for a private contact channel without disclosing sensitive details.

### What to Include in Your Report
* A clear description of the vulnerability and its potential impact.
* Steps to reproduce the issue (sanitized of any personal OAuth tokens or Client IDs).
* Your Python version and operating system.
* Any suggested fix or mitigation, if available.

You can expect an initial acknowledgment within **7 days**, followed by status updates as a fix is prepared.

---

## User Security & Privacy Best Practices

Because this CLI interacts directly with your personal Trakt account, please follow these precautions:

### 1. Keep OAuth Tokens & Personal Files Local
This tool uses Trakt's **PKCE OAuth 2.0** flow (which requires no Client Secret) and stores sensitive session and personal history data locally in the script directory:
* `trakt_token.json` — Contains your active OAuth `access_token` and `refresh_token`. **Treat this file like a password.**
* `trakt_config.json` — Contains your Trakt app `client_id` and local preferences.
* `trakt_cache.json`, `trakt_edit_log.json`, and `trakt_backups/` — Contain your personal watch history, ratings, and lists.

Never upload, share, or commit these files to version control. Ensure all of them remain listed in `.gitignore`.

### 2. Localhost OAuth Callback Scope
During initial login, the script starts a temporary Python `HTTPServer` bound strictly to `localhost:8765` (`http://localhost:8765/callback`) solely to receive the PKCE authorization code, and shuts it down immediately once the code is received.

### 3. Revoking Access if a Token Is Compromised
If your `trakt_token.json` file is ever accidentally exposed or committed:
1. Immediately revoke the app in your Trakt account at **[https://trakt.tv/oauth/authorized_applications](https://trakt.tv/oauth/authorized_applications)**.
2. Delete the exposed `trakt_token.json` file (and purge it from Git history if committed).
3. Re-authenticate cleanly on the next run.

### 4. Protecting Against Accidental History Loss
* Keep **Auto-Backup Before Show Edits** enabled (`backup` → Option `5`) — especially when using `UPDATE IMMEDIATELY` sync mode.
* Create a **Full History Snapshot** (`backup` → Option `2`) before performing large multi-show cleanups.