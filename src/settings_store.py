"""Per-user settings storage for the CRM automation app."""

from __future__ import annotations

import base64
import ctypes
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


APP_DIR_NAME = "crm-automation"
SETTINGS_FILE_NAME = "settings.json"
DEFAULT_CRM_BASE_URL = "https://crm.synmosa.com.tw/SYNCRM/main.aspx#187829805/"

REQUIRED_FIELDS = ("crm_base_url", "crm_username", "crm_password")
SECRET_FIELDS = ("crm_password", "line_notify_token")


def settings_path() -> Path:
    """Return the per-user settings path."""
    override = os.getenv("CRM_AUTOMATION_CONFIG_DIR")
    if override:
        return Path(override) / SETTINGS_FILE_NAME

    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / APP_DIR_NAME / SETTINGS_FILE_NAME

    return Path.home() / f".{APP_DIR_NAME}" / SETTINGS_FILE_NAME


def load_saved_settings() -> dict[str, Any]:
    """Load saved settings with secrets decrypted when possible."""
    path = settings_path()
    if not path.exists():
        return _empty_settings()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_settings()

    return {
        "crm_base_url": _as_text(data.get("crm_base_url")),
        "crm_username": _as_text(data.get("crm_username")),
        "crm_password": _decode_secret(data.get("crm_password")),
        "line_notify_token": _decode_secret(data.get("line_notify_token")),
        "headless": _as_bool(data.get("headless"), default=False),
    }


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist settings and return the public, secret-redacted status."""
    existing_raw = _load_raw_settings()

    raw = {
        "crm_base_url": _as_text(payload.get("crm_base_url")),
        "crm_username": _as_text(payload.get("crm_username")),
        "headless": _as_bool(payload.get("headless"), default=False),
    }

    for field in SECRET_FIELDS:
        value = _as_text(payload.get(field))
        if value:
            raw[field] = _encode_secret(value)
        elif existing_raw.get(field):
            raw[field] = existing_raw[field]
        else:
            raw[field] = None

    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return get_public_settings()


def get_effective_settings() -> dict[str, Any]:
    """Merge saved settings over .env/environment fallback values."""
    load_dotenv()
    saved = load_saved_settings()

    return {
        "crm_base_url": saved["crm_base_url"] or os.getenv("CRM_BASE_URL", DEFAULT_CRM_BASE_URL),
        "crm_username": saved["crm_username"] or os.getenv("CRM_USERNAME", ""),
        "crm_password": saved["crm_password"] or os.getenv("CRM_PASSWORD", ""),
        "line_notify_token": saved["line_notify_token"] or os.getenv("LINE_NOTIFY_TOKEN", ""),
        "headless": saved["headless"] if "headless" in saved else _env_headless(),
    }


def get_public_settings() -> dict[str, Any]:
    """Return settings status suitable for API responses."""
    saved = load_saved_settings()
    effective = get_effective_settings()
    missing = [field for field in REQUIRED_FIELDS if not _as_text(effective.get(field))]

    return {
        "crm_base_url": saved["crm_base_url"] or _as_text(os.getenv("CRM_BASE_URL", DEFAULT_CRM_BASE_URL)),
        "crm_username": saved["crm_username"] or _as_text(os.getenv("CRM_USERNAME")),
        "crm_password": "",
        "line_notify_token": "",
        "headless": effective["headless"],
        "has_password": bool(effective["crm_password"]),
        "has_line_notify_token": bool(effective["line_notify_token"]),
        "is_configured": not missing,
        "missing_fields": missing,
        "settings_path": str(settings_path()),
    }


def validate_effective_settings(settings: dict[str, Any] | None = None) -> list[str]:
    """Return missing required setting names."""
    effective = settings or get_effective_settings()
    return [field for field in REQUIRED_FIELDS if not _as_text(effective.get(field))]


def _empty_settings() -> dict[str, Any]:
    return {
        "crm_base_url": "",
        "crm_username": "",
        "crm_password": "",
        "line_notify_token": "",
        "headless": False,
    }


def _load_raw_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _env_headless() -> bool:
    return os.getenv("HEADLESS", "false").strip().lower() == "true"


def _encode_secret(value: str) -> dict[str, str]:
    raw = value.encode("utf-8")
    protected = _protect_windows(raw)
    if protected is not None:
        return {"encoding": "win32-dpapi", "value": base64.b64encode(protected).decode("ascii")}
    return {"encoding": "base64", "value": base64.b64encode(raw).decode("ascii")}


def _decode_secret(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""

    encoding = value.get("encoding")
    encoded = value.get("value")
    if not encoded:
        return ""

    try:
        raw = base64.b64decode(encoded)
    except (TypeError, ValueError):
        return ""

    if encoding == "win32-dpapi":
        unprotected = _unprotect_windows(raw)
        if unprotected is None:
            return ""
        return unprotected.decode("utf-8")
    if encoding == "base64":
        return raw.decode("utf-8")
    return ""


def _protect_windows(data: bytes) -> bytes | None:
    if os.name != "nt":
        return None
    try:
        return _crypt_protect_data(data)
    except Exception:
        return None


def _unprotect_windows(data: bytes) -> bytes | None:
    if os.name != "nt":
        return None
    try:
        return _crypt_unprotect_data(data)
    except Exception:
        return None


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_ulong),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _bytes_to_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _crypt_protect_data(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    blob_in, _buffer = _bytes_to_blob(data)
    blob_out = _DataBlob()

    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise ctypes.WinError()

    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _crypt_unprotect_data(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    blob_in, _buffer = _bytes_to_blob(data)
    blob_out = _DataBlob()

    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise ctypes.WinError()

    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
