# Local Settings Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add per-user CRM settings to the Flask UI and automation runner.

**Architecture:** A new `settings_store` module owns persistence, validation, secret redaction, and environment fallback. Flask routes use that module and pass explicit settings into `run_automation`, keeping Playwright workflow code focused on browser automation.

**Tech Stack:** Python 3, Flask, pytest, Windows DPAPI via standard-library `ctypes`, JSON settings under `%APPDATA%`.

---

### Task 1: Settings Store

**Files:**
- Create: `src/settings_store.py`
- Test: `tests/test_settings_store.py`

**Steps:**
1. Write failing tests for saving required settings, redacting secrets, preserving existing secrets on blank update, and merging `.env` fallback.
2. Run `pytest tests/test_settings_store.py -q` and verify failures are due to the missing module.
3. Implement JSON persistence, config path override via `CRM_AUTOMATION_CONFIG_DIR`, Windows DPAPI secret protection, and public status helpers.
4. Run `pytest tests/test_settings_store.py -q`.

### Task 2: Flask API

**Files:**
- Modify: `src/app.py`
- Test: `tests/test_settings_api.py`

**Steps:**
1. Write failing Flask test-client tests for `GET /api/settings`, `POST /api/settings`, secret redaction, and `/api/execute` blocking when not configured.
2. Run `pytest tests/test_settings_api.py -q` and verify expected failures.
3. Add the settings routes and execution preflight check.
4. Run `pytest tests/test_settings_api.py -q`.

### Task 3: Automation Runtime Settings

**Files:**
- Modify: `src/create_appointments.py`
- Test: `tests/test_automation_settings.py`

**Steps:**
1. Write failing tests proving explicit runtime settings take priority over environment variables.
2. Add optional `settings` support to `run_automation()` and `send_line_notify()`.
3. Run `pytest tests/test_automation_settings.py -q`.

### Task 4: UI Settings Panel

**Files:**
- Modify: `src/templates/index.html`

**Steps:**
1. Add a settings section near the top of the app with CRM URL, account, password, LINE token, and headless controls.
2. Load `/api/settings` on page startup and show configured/missing state.
3. Save settings via `POST /api/settings`, leaving blank secret fields unchanged.
4. Disable/guard execution until settings are complete.

### Task 5: Verification

**Commands:**
- `pytest -q`
- `python -m py_compile src/app.py src/create_appointments.py src/settings_store.py`
- Launch `python src/app.py` and verify `GET /api/settings` returns JSON.
