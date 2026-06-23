# Local Settings Design

## Goal

Let each Windows user configure CRM credentials from the Flask UI without editing `.env` or sharing credentials from the repository.

## Recommended Approach

Add a small settings boundary around the existing Flask app and automation runner.

1. Store user settings outside the repo at `%APPDATA%\crm-automation\settings.json`.
2. Keep `.env` as a development fallback only.
3. Never return plaintext secrets from `/api/settings`.
4. Encrypt the password and optional LINE token with Windows DPAPI when available.
5. Block `/api/execute` with a clear message when the required CRM URL, username, or password are missing.

## Components

- `src/settings_store.py` owns the config path, validation, JSON persistence, secret protection, and `.env` fallback merge.
- `src/app.py` exposes `GET /api/settings` and `POST /api/settings`, checks settings before starting automation, and passes effective settings into the runner.
- `src/create_appointments.py` accepts optional runtime settings while preserving CLI `.env` behavior.
- `src/templates/index.html` adds an inline settings section and prevents accidental execution before setup.

## Data Flow

The browser loads `/api/settings` on startup. The response contains public fields, booleans such as `has_password`, and `is_configured`; it never includes plaintext secrets. Saving settings posts the fields to `/api/settings`. Blank secret fields preserve existing saved secrets so users can update the URL or headless mode without retyping the password.

When executing automation, Flask loads the effective settings. Saved local settings win over `.env`; missing saved values fall back to `.env` for development. If required values are still missing, Flask returns HTTP 400.

## Testing

Use pytest with `CRM_AUTOMATION_CONFIG_DIR` to isolate local settings from the real Windows profile. Cover secret redaction, secret preservation on partial update, `.env` fallback merge, API validation, and `run_automation()` accepting explicit settings.
