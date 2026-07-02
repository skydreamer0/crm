import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def test_resolve_runtime_settings_prefers_explicit_settings(monkeypatch):
    from create_appointments import resolve_runtime_settings

    monkeypatch.setenv("CRM_BASE_URL", "https://env.example.test")
    monkeypatch.setenv("CRM_USERNAME", "env-user")
    monkeypatch.setenv("CRM_PASSWORD", "env-pass")
    monkeypatch.setenv("LINE_NOTIFY_TOKEN", "env-line")
    monkeypatch.setenv("HEADLESS", "false")

    settings = resolve_runtime_settings(
        {
            "crm_base_url": "https://saved.example.test",
            "crm_username": "saved-user",
            "crm_password": "saved-pass",
            "line_notify_token": "saved-line",
            "headless": True,
        }
    )

    assert settings["base_url"] == "https://saved.example.test"
    assert settings["username"] == "saved-user"
    assert settings["password"] == "saved-pass"
    assert settings["line_notify_token"] == "saved-line"
    assert settings["headless"] is True


def test_resolve_runtime_settings_keeps_environment_fallback(monkeypatch):
    from create_appointments import resolve_runtime_settings

    monkeypatch.setenv("CRM_BASE_URL", "https://env.example.test")
    monkeypatch.setenv("CRM_USERNAME", "env-user")
    monkeypatch.setenv("CRM_PASSWORD", "env-pass")
    monkeypatch.setenv("LINE_NOTIFY_TOKEN", "env-line")
    monkeypatch.setenv("HEADLESS", "true")

    settings = resolve_runtime_settings()

    assert settings["base_url"] == "https://env.example.test"
    assert settings["username"] == "env-user"
    assert settings["password"] == "env-pass"
    assert settings["line_notify_token"] == "env-line"
    assert settings["headless"] is True


def test_frozen_runtime_settings_do_not_load_parent_dotenv(monkeypatch, tmp_path):
    from create_appointments import resolve_runtime_settings

    app_dir = tmp_path / "release" / "CRM-Automation"
    app_dir.mkdir(parents=True)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "CRM_USERNAME=packaged-env-user",
                "CRM_PASSWORD=packaged-env-password",
                "LINE_NOTIFY_TOKEN=packaged-env-token",
            ]
        ),
        encoding="utf-8",
    )

    for name in (
        "CRM_USERNAME",
        "CRM_PASSWORD",
        "LINE_NOTIFY_TOKEN",
        "HEADLESS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(app_dir)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    settings = resolve_runtime_settings()

    assert settings["username"] is None
    assert settings["password"] is None
    assert settings["line_notify_token"] is None
