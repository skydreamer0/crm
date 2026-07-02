import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("CRM_AUTOMATION_CONFIG_DIR", str(tmp_path))
    for name in (
        "CRM_BASE_URL",
        "CRM_USERNAME",
        "CRM_PASSWORD",
        "HEADLESS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_save_settings_redacts_secrets_and_reports_configured():
    from settings_store import get_effective_settings, get_public_settings, settings_path, save_settings

    public = save_settings(
        {
            "crm_base_url": "https://crm.example.test/SYNCRM/main.aspx",
            "crm_username": "alice",
            "crm_password": "super-secret",
            "headless": True,
        }
    )

    assert public["is_configured"] is True
    assert public["has_password"] is True
    assert public["crm_password"] == ""

    raw_file = settings_path().read_text(encoding="utf-8")
    assert "super-secret" not in raw_file

    effective = get_effective_settings()
    assert effective["crm_base_url"] == "https://crm.example.test/SYNCRM/main.aspx"
    assert effective["crm_username"] == "alice"
    assert effective["crm_password"] == "super-secret"
    assert effective["headless"] is True

    public_after_reload = get_public_settings()
    assert public_after_reload["crm_password"] == ""


def test_blank_secret_update_preserves_existing_saved_secret():
    from settings_store import get_effective_settings, save_settings

    save_settings(
        {
            "crm_base_url": "https://crm.example.test/old",
            "crm_username": "alice",
            "crm_password": "keep-me",
            "headless": False,
        }
    )

    public = save_settings(
        {
            "crm_base_url": "https://crm.example.test/new",
            "crm_username": "bob",
            "crm_password": "",
            "headless": True,
        }
    )

    effective = get_effective_settings()
    assert public["has_password"] is True
    assert effective["crm_base_url"] == "https://crm.example.test/new"
    assert effective["crm_username"] == "bob"
    assert effective["crm_password"] == "keep-me"
    assert effective["headless"] is True


def test_effective_settings_fall_back_to_environment(monkeypatch):
    from settings_store import get_effective_settings, save_settings

    monkeypatch.setenv("CRM_BASE_URL", "https://env.example.test")
    monkeypatch.setenv("CRM_USERNAME", "env-user")
    monkeypatch.setenv("CRM_PASSWORD", "env-pass")
    monkeypatch.setenv("HEADLESS", "true")

    save_settings(
        {
            "crm_base_url": "https://saved.example.test",
            "crm_username": "",
            "crm_password": "",
            "headless": False,
        }
    )

    effective = get_effective_settings()
    assert effective["crm_base_url"] == "https://saved.example.test"
    assert effective["crm_username"] == "env-user"
    assert effective["crm_password"] == "env-pass"
    assert effective["headless"] is False


def test_legacy_settings_file_with_line_token_still_loads(monkeypatch, tmp_path):
    # 舊版設定檔可能還留有 line_notify_token 欄位，讀取時應忽略而非壞掉
    from settings_store import get_effective_settings, save_settings, settings_path

    save_settings(
        {
            "crm_base_url": "https://crm.example.test",
            "crm_username": "alice",
            "crm_password": "secret",
            "headless": False,
        }
    )
    raw = json.loads(settings_path().read_text(encoding="utf-8"))
    raw["line_notify_token"] = {"encoding": "base64", "value": "bGVnYWN5"}
    settings_path().write_text(json.dumps(raw), encoding="utf-8")

    effective = get_effective_settings()
    assert effective["crm_username"] == "alice"
    assert "line_notify_token" not in effective


def test_settings_path_uses_appdata_style_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("CRM_AUTOMATION_CONFIG_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    from settings_store import settings_path

    expected = tmp_path / "crm-automation" / "settings.json"
    assert settings_path() == expected


def test_frozen_app_does_not_load_parent_dotenv(monkeypatch, tmp_path):
    from settings_store import get_effective_settings

    app_dir = tmp_path / "release" / "CRM-Automation"
    app_dir.mkdir(parents=True)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "CRM_USERNAME=packaged-env-user",
                "CRM_PASSWORD=packaged-env-password",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(app_dir)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    effective = get_effective_settings()

    assert effective["crm_username"] == ""
    assert effective["crm_password"] == ""
