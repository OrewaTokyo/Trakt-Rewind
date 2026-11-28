# Security Policy

## Supported Versions

Only the latest release on the `main` branch of **Trakt-Rewind** receives active security updates.

| Version | Supported |
| :--- | :---: |
| `1.x` (`main`) | Yes |
| `< 1.0` | No |

## Credential & Data Privacy Model

**Trakt-Rewind** runs 100% locally on your machine and communicates exclusively with the official Trakt API (`https://api.trakt.tv` and `https://trakt.tv/oauth/authorize`). No third-party servers or analytics are used.

- **PKCE OAuth Flow:** Uses OAuth 2.0 with PKCE (`S256`), so no Client Secret is required or stored.
- **Local Files Generated at Runtime:**
  - `trakt_token.json` — Contains your personal OAuth access token and refresh token. **Treat this like a password and never share or commit it.**
  - `trakt_config.json` — Contains your Trakt app Client ID and local preferences.
  - `trakt_cache.json`, `trakt_edit_log.json`, `trakt_backups/` — Contain your personal Trakt watch history and ratings.
- All runtime files are excluded by `.gitignore` and verified by CI to prevent accidental commits.

## If You Accidentally Exposed a Token
1. Go to [https://trakt.tv/oauth/authorized_applications](https://trakt.tv/oauth/authorized_applications) and **Revoke** the app immediately.
2. Delete your local `trakt_token.json` file.
3. Re-run `python trakt_rewind.py` to generate a fresh PKCE token.

## Reporting a Vulnerability

If you discover a security vulnerability (such as token leakage, unsafe file handling, or OAuth callback issues):
1. **Do not** open a public GitHub Issue.
2. Report it privately via GitHub's **Security → Advisories → Report a vulnerability** tab on this repository (or contact the maintainer directly).
3. Include steps to reproduce and the affected Python version/OS. You can expect an initial response within 7 days.
