# CRM Report Automation Crawler

## 專案簡介
本專案旨在自動化登入 CRM 系統並完成報表填寫工作。透過 Playwright 瀏覽器自動化，將重複性的行政工作（新增日報、建立約會記錄、填寫產品資料）全部自動化，提升效率。

## 技術棧
- **語言**: Python 3.10+
- **自動化框架**: Playwright
- **Web 介面**: Flask
- **資料處理**: Pandas / PyYAML
- **配置管理**: `.env` 環境變數 + YAML 設定檔

## 下載使用（一般使用者，免安裝）
到 GitHub **Releases** 頁面下載最新的 `CRM-Automation-vX.X.X-windows.zip`，解壓後執行 `CRM-Automation.exe` 即可，不需要安裝 Python 或瀏覽器。詳細說明與打包/發佈流程見 [docs/RELEASE.md](docs/RELEASE.md)。

## 快速開始（開發者）
1. 建立虛擬環境: `python -m venv venv`
2. 啟用虛擬環境: `source venv/bin/activate`
3. 安裝依賴: `pip install -r requirements.txt`
4. 安裝瀏覽器: `playwright install chromium`
5. 設定 `.env` 檔案中的 CRM 憑證
6. 啟動 Web 介面: `python src/app.py`
7. 開啟 http://127.0.0.1:5050 貼入待訪名單即可使用

## 專案結構

```
crm/
├── .env                    # CRM 帳密與設定 (不進版控)
├── requirements.txt        # Python 套件清單
├── README.md               # 本文件
├── ROADMAP.md              # 開發藍圖
│
├── config/                 # 外部設定檔
│   ├── selectors.yaml      # CRM 頁面的 DOM 選擇器對照表
│   ├── department_mapping.yaml  # 科別代碼對應表
│   └── product_catalog.yaml     # 產品目錄與描述
│
├── src/                    # 核心程式碼
│   ├── app.py              # Flask Web 介面 (主入口)
│   ├── create_appointments.py  # Playwright 自動化引擎
│   ├── visit_list_parser.py    # 待訪名單解析 & 產品匹配
│   ├── templates/
│   │   └── index.html      # Web UI 前端頁面
│   └── dev_tools/          # 開發階段的探索/測試腳本 (不影響運行)
│       └── README.md       # 各腳本說明
│
├── tests/                  # 測試
│   ├── test_visit_list_parser.py
│   └── verify_fixes.py
│
├── docs/                   # 文件與 HTML 匯出
└── logs/                   # 執行日誌與截圖 (不進版控)
```

## 核心檔案說明

| 檔案 | 角色 |
|---|---|
| `src/app.py` | Flask 伺服器，提供 Web GUI 與 API（解析名單、觸發自動化、查詢進度）|
| `src/create_appointments.py` | 自動化引擎，驅動 Playwright 完成登入、日報、約會記錄、產品填寫 |
| `src/visit_list_parser.py` | 名單解析器，將文字格式名單轉為結構化資料並匹配產品 |

## 使用規則 (AI 規範)
- 遵循 `snake_case` 命名規範。
- 敏感資訊（帳號密碼）必須透過環境變數管理，不可 hardcode。
- 所有的系統規則與邏輯應詳細記錄於 `docs/` 資料夾中。
