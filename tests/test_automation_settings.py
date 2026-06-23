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
