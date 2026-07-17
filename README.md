# CRM Report Automation Crawler

![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)
![Playwright](https://img.shields.io/badge/Playwright-Automation-green.svg)
![Flask](https://img.shields.io/badge/Flask-Web_GUI-black.svg)

## 專案簡介

本專案旨在自動化登入 CRM 系統並完成報表填寫工作。透過 Playwright 瀏覽器自動化，將重複性的行政工作（新增日報、建立約會記錄、填寫產品資料）全部自動化，協助業務與管理人員節省時間，大幅提升工作效率。

## ✨ 主要功能 (Features)

- **自動化登入與導航**：自動登入 CRM 系統並跳轉至報表填寫頁面。
- **智慧解析待訪名單**：自動解析包含客戶名稱、醫院、產品的文字名單。
- **自動建立約會與日報**：根據解析出的名單，自動在系統內建立對應的約會記錄與日報。
- **自動產品匹配與填寫**：根據 `product_catalog.yaml` 的設定，自動選取對應產品並填寫相關描述。
- **直覺的 Web 介面**：提供 Flask 打造的 Web GUI，使用者只需貼上文字名單即可一鍵啟動自動化。

---

## 🚀 一般使用者指南 (免安裝版)

如果您是不熟悉程式的終端使用者，請依照以下步驟直接使用：

1. 到 GitHub **Releases** 頁面下載最新的 `CRM-Automation-vX.X.X-windows.zip`。
2. 解壓縮下載的檔案。
3. 執行資料夾中的 `CRM-Automation.exe` 或是 `start_crm.bat`，即可開啟網頁介面。（**無需安裝 Python 或任何瀏覽器**）
4. 在網頁介面中貼入待訪名單文字，點擊「開始執行」即可。

> **註：** 詳細說明與打包/發佈流程可參考 [docs/RELEASE.md](docs/RELEASE.md)。

---

## 💻 開發者快速開始

如果您是開發者，希望能修改原始碼或於本地端開發：

### 技術棧
- **語言**: Python 3.10+
- **自動化框架**: Playwright
- **Web 介面**: Flask
- **資料處理**: Pandas / PyYAML
- **配置管理**: `.env` 環境變數 + YAML 設定檔

### 環境建置與啟動

1. **建立虛擬環境**: 
   ```bash
   python -m venv venv
   ```
2. **啟用虛擬環境**: 
   - Windows: `venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`
3. **安裝依賴套件**: 
   ```bash
   pip install -r requirements.txt
   ```
4. **安裝 Playwright 瀏覽器**: 
   ```bash
   playwright install chromium
   ```
5. **設定環境變數**: 
   建立並設定 `.env` 檔案，補上您的 CRM 憑證等所需環境變數。
6. **啟動 Web 介面**: 
   ```bash
   python src/app.py
   ```
7. 開啟瀏覽器進入 http://127.0.0.1:5050 即可使用。

---

## 📂 專案結構

```text
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
│   └── dev_tools/          # 開發階段的探索/測試腳本
│
├── tests/                  # 測試腳本
├── docs/                   # 文件與設定說明
└── logs/                   # 執行日誌與截圖 (不進版控)
```

## 🛠 核心檔案說明

| 檔案 | 角色描述 |
|---|---|
| `src/app.py` | Flask 伺服器，提供 Web GUI 與 API（解析名單、觸發自動化、查詢進度）|
| `src/create_appointments.py` | 自動化引擎，驅動 Playwright 完成登入、日報、約會記錄、產品填寫 |
| `src/visit_list_parser.py` | 名單解析器，將文字格式名單轉為結構化資料並進行產品匹配 |

---

## 🧠 開發與 AI 協助規範

- 程式碼遵循 `snake_case` 命名規範。
- 敏感資訊（如帳號密碼）必須透過環境變數 (`.env`) 管理，**絕不可 Hardcode** 在程式碼中。
- 所有新的系統規則、頁面流程邏輯，應詳細記錄於 `docs/` 資料夾中的相關文件內。
