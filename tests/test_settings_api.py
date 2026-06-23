import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CRM_AUTOMATION_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CRM_BASE_URL", "")
    monkeypatch.setenv("CRM_USERNAME", "")
    monkeypatch.setenv("CRM_PASSWORD", "")
    monkeypatch.setenv("LINE_NOTIFY_TOKEN", "")
    monkeypatch.setenv("HEADLESS", "false")

    import app as app_module

    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_get_settings_returns_public_status_without_secrets(client):
    response = client.get("/api/settings")

    assert response.status_code == 200
    data = response.get_json()
    assert data["is_configured"] is False
    assert data["has_password"] is False
    assert data["crm_password"] == ""
    assert data["line_notify_token"] == ""


def test_post_settings_saves_and_redacts_secret_fields(client):
    response = client.post(
        "/api/settings",
        json={
            "crm_base_url": "https://crm.example.test/SYNCRM/main.aspx",
            "crm_username": "alice",
            "crm_password": "super-secret",
            "line_notify_token": "line-secret",
            "headless": True,
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["is_configured"] is True
    assert data["has_password"] is True
    assert data["has_line_notify_token"] is True
    assert "super-secret" not in response.get_data(as_text=True)
    assert "line-secret" not in response.get_data(as_text=True)


def test_execute_requires_configured_credentials(client):
    response = client.post(
        "/api/execute",
        json={"text": "王小明/URO/台大醫院/A", "date": "2026-06-23"},
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"
    assert "設定" in data["message"]
