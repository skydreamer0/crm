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
    assert 'href="/settings/products"' in html

    index_html = client.get("/").get_data(as_text=True)
    assert "settingsBaseUrl" not in index_html  # 設定表單已移出主頁
    assert "/settings" in index_html  # 主頁保留設定頁連結


def test_product_rules_page_is_available_from_settings(client):
    response = client.get("/settings/products")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "醫院產品矩陣" in html
    # 頁面是 API 驅動：從 /api/product-config 讀公司產品、/api/settings 讀個人醫院規則
    assert "/api/product-config" in html
    assert "hospital_product_rules" in html
    assert "新增醫院" in html
    assert "settings_product_rules_prototype" not in html


def test_product_config_exposes_sku_catalog(client):
    response = client.get("/api/product-config")

    assert response.status_code == 200
    data = response.get_json()

    products = {p["code"]: p for p in data["products"]}
    assert products["eli_45"]["crm_product_id"] == "T5EL2"
    assert products["eli_22_5"]["crm_product_id"] == "T5EL1"
    assert products["eli_7_5"]["crm_product_id"] == "T5EL0"
    assert "eli" not in products  # 品牌層級的 eli 已拆成 SKU

    departments = {d["code"]: d for d in data["departments"]}
    assert departments["URO"]["default_products"] == ["uri", "eli_22_5", "oxb"]
    assert departments["PED"]["default_products"] == ["eli_45", "oxb"]


def test_parse_applies_locked_hospital_rules(client):
    save = client.post(
        "/api/settings",
        json={
            "hospital_product_rules": {
                "skh": {
                    "name": "新光醫院",
                    "aliases": ["新光"],
                    "departments": {
                        "URO": {"mode": "locked", "products": ["uri", "eli_45"], "note": ""}
                    },
                }
            }
        },
    )
    assert save.status_code == 200

    response = client.post("/api/parse", json={"text": "新光/URO/蔡醫師/A\n馬偕/URO/王小明/A"})

    assert response.status_code == 200
    entries = response.get_json()["entries"]

    locked = entries[0]
    assert locked["hospital_name"] == "新光"
    assert locked["products_locked"] is True
    assert [p["code"] for p in locked["selected_products"]] == ["uri", "eli_45"]

    fallback = entries[1]
    assert fallback["products_locked"] is False
    assert [p["code"] for p in fallback["selected_products"]] == ["uri", "eli_22_5"]


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
