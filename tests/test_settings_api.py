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


def test_post_settings_saves_and_redacts_secret_fields(client):
    response = client.post(
        "/api/settings",
        json={
            "crm_base_url": "https://crm.example.test/SYNCRM/main.aspx",
            "crm_username": "alice",
            "crm_password": "super-secret",
            "headless": True,
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["is_configured"] is True
    assert data["has_password"] is True
    assert "super-secret" not in response.get_data(as_text=True)


def test_settings_page_is_served_separately_from_index(client):
    response = client.get("/settings")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "settingsBaseUrl" in html
    assert "返回主頁" in html

    index_html = client.get("/").get_data(as_text=True)
    assert "settingsBaseUrl" not in index_html  # 設定表單已移出主頁
    assert "/settings" in index_html  # 主頁保留設定頁連結


def test_execute_requires_configured_credentials(client):
    response = client.post(
        "/api/execute",
        json={"text": "王小明/URO/台大醫院/A", "date": "2026-06-23"},
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"
    assert "設定" in data["message"]


def test_execute_rejects_overlong_text(client):
    import app as app_module

    response = client.post(
        "/api/execute",
        json={"text": "a" * (app_module.MAX_TEXT_LENGTH + 1)},
    )

    assert response.status_code == 400
    assert "過長" in response.get_json()["message"]


def test_execute_rejects_non_string_text(client):
    response = client.post("/api/execute", json={"text": ["not", "a", "string"]})

    assert response.status_code == 400
    assert "文字" in response.get_json()["message"]


def test_execute_rejects_invalid_date(client):
    # 先完成設定，讓請求走到日期驗證之後仍會被日期擋下 (日期驗證在設定檢查之前)
    response = client.post(
        "/api/execute",
        json={"text": "王小明/URO/台大醫院/A", "date": "2026/06/23"},
    )

    assert response.status_code == 400
    assert "日期格式" in response.get_json()["message"]


def test_parse_rejects_overlong_text(client):
    import app as app_module

    response = client.post(
        "/api/parse",
        json={"text": "a" * (app_module.MAX_TEXT_LENGTH + 1)},
    )

    assert response.status_code == 400
    assert "過長" in response.get_json()["error"]


def test_cancel_returns_conflict_when_idle(client):
    response = client.post("/api/cancel")

    assert response.status_code == 409
    assert response.get_json()["status"] == "idle"


def test_status_returns_serializable_snapshot(client):
    response = client.get("/api/status")

    assert response.status_code == 200
    data = response.get_json()
    assert data["running"] is False
    assert isinstance(data["progress"], list)
    assert data["summary"] is None
