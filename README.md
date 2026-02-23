# CRM Report Automation Crawler

## 專案簡介
本專案旨在自動化登入 CRM 系統並完成報表填寫工作。透過爬蟲技術（爬蟲/自動化工具如 Selenium 或 Playwright），將重複性的行政工作自動化，提升效率。

## 技術棧 (預計)
- **語言**: Python
- **自動化框架**: Playwright / Selenium
- **資料處理**: Pandas
- **配置管理**: YAML / Environment Variables

## 快速開始
1. 安裝 Python 3.10+
2. 建立虛擬環境: `python -m venv venv`
3. 安裝依賴: `pip install -r requirements.txt`
4. 設定 `.env` 檔案中的憑證資訊
5. 執行主程式: `python src/main.py`

## 使用規則 (AI 規範)
- 遵循 `snake_case` 命名規範。
- 敏感資訊（帳號密碼）必須透過環境變數管理，不可 hardcode。
- 所有的系統規則與邏輯應詳細記錄於 `docs/` 資料夾中。
