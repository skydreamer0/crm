# CRM 報表填寫自動化 - 發展藍圖 (ROADMAP)

## 第一階段：基礎建設 (Done)
- [x] 初始化專案結構
- [x] 建立 README 與 ROADMAP
- [x] 環境變數與配置系統設計 (.env & venv)

## 第二階段：爬蟲核心與產品驗證 (Done)
- [x] CRM 產品欄位探索 (探索 Popup HTML/ID 結構)
- [x] 產品選取邏輯 (ID 搜尋 + 動態規則 for ELI)
- [x] 拜訪內容 / 拜訪目的隨機填寫邏輯
- [x] 選擇器外部化 → `config/selectors.yaml`

## 第二．五階段：待訪名單解析與產品匹配 (Done)
- [x] 待訪名單解析器 (visit_list_parser.py)
- [x] 科別對應表 (department_mapping.yaml)
- [x] 產品目錄 (product_catalog.yaml)
- [x] 整合至約會記錄自動化流程 (姓名自動填入)
- [x] 產品描述隨機選取邏輯

## 第三階段：操作介面與串接 (Done)
- [x] Flask 本地 server (app.py)
- [x] Web GUI 頁面 (貼入名單 → 即時預覽解析結果)
- [x] **一鍵執行 CRM 自動化 (API 串接)**
    - [x] `/api/execute` 接收名單文字 → 背景執行 Playwright
    - [x] `/api/status` 進度回報 (Polling)
    - [x] `HEADLESS` 環境變數控制

## 第四階段：穩定性與優化 (Done)
- [x] 前端進度條即時顯示與執行 Log (Web UI)
- [x] 填寫完成後的截圖驗證 (logs/screenshots) 與日誌記錄 (logs/history)
- [x] 背景執行例外處理 (單筆失敗跳過機制)
- [x] 異常偵測與自動警示 (Line Notify 支援)

---

## 架構審查發現的問題與改善計畫

> 以下為對現有程式碼進行架構審查後，依嚴重程度列出的問題與對應改善方向。

### 已知問題清單

#### 高優先 (High)

| # | 問題 | 影響 |
|---|------|------|
| H1 | `TIMING` dict 硬編碼毫秒數 (200~2000ms)，CRM 若回應變慢即失敗 | 自動化中斷率高 |
| H2 | `_automation_state` 是無鎖全域 dict，progress list 無界限增長 | Thread safety 問題、記憶體洩漏 |
| H3 | 無取消 / 逾時機制，瀏覽器崩潰後無法中斷執行 | 程序卡死、資源無法釋放 |

#### 中優先 (Medium)

| # | 問題 | 影響 |
|---|------|------|
| M1 | `create_appointments.py` 達 972 行，瀏覽器、表單、商業邏輯混在一起 | 難以維護與測試 |
| M2 | `app.py` 在 thread 內建立 asyncio event loop，混用 threading + async | 難以 debug，例外清理不完整 |
| M3 | `create_appointments.py` 直接 import `visit_list_parser`，緊耦合 | 無法獨立單元測試 |
| M4 | Flask routes 無 schema 驗證，直接 `data.get()` 取值 | 錯誤輸入可能造成非預期行為 |
| M5 | `selectors.yaml` 使用多層 fallback CSS selector，CRM UI 一改即斷 | 維護成本高 |
| M6 | 單筆失敗跳過但未驗證表單是否已部份提交，可能留下孤立記錄 | CRM 資料不一致 |
| M7 | 使用基本 logging，無 request ID、無 JSON 結構化輸出 | 難以追蹤生產問題 |

#### 低優先 / 缺失功能 (Low / Missing)

| # | 問題 |
|---|------|
| L1 | 無資料庫持久化，執行紀錄只存 JSON 檔 |
| L2 | 單一全域 state，多使用者同時操作會互相干擾 |
| L3 | 無稽核軌跡（誰、何時、執行什麼） |
| L4 | 確認正式環境 `debug=False`（Flask debug mode） |
| L5 | 無 pre-commit hooks（linting / formatting 未自動化） |
| L6 | 部份函式缺少 return type hint |

---

## 第五階段：架構穩定化 (Phase 5 — Stabilization)

> 目標：消除最容易造成自動化中斷的問題，不改變外部行為。

- [ ] **H1** 將所有 `wait_for_timeout(n)` 替換為 `wait_for_selector` / `wait_for_load_state`，移除 `TIMING` dict
- [ ] **H2** 為 `_automation_state` 加上 `threading.Lock`，並將 progress list 改為有界限的 `collections.deque`
- [ ] **H3** 實作 `CancelToken`，支援從 `/api/cancel` 中止執行中的自動化
- [ ] **M4** Flask routes 加上 Marshmallow 或 Pydantic schema 驗證（長度上限、型別檢查）
- [ ] **L5** 加入 pre-commit hooks（`ruff` linting + `black` formatting）
- [ ] **L6** 補齊所有公開函式的 type hints

## 第六階段：架構強健化 (Phase 6 — Robustness)

> 目標：提升可測試性、可維護性，並建立完整的錯誤恢復機制。

- [ ] **M1** 拆分 `create_appointments.py` 為三個模組：
    - `browser_manager.py` — 瀏覽器生命週期管理
    - `crm_form_filler.py` — DOM 操作與表單填寫
    - `appointment_service.py` — 商業邏輯與流程協調
- [ ] **M2** 將 Flask 改為 FastAPI，移除 thread + asyncio 混用
- [ ] **M3** 透過建構子注入 `VisitListParser`，解除 `create_appointments` 與 parser 的直接依賴
- [ ] **M6** 實作 per-appointment 驗證：提交後確認記錄存在，失敗時記錄孤立記錄清單
- [ ] **M7** 導入 `structlog`，輸出 JSON 結構化日誌，加入 `run_id` 追蹤
- [ ] **L1** 加入 SQLite 儲存執行歷史，支援查詢過去執行紀錄

## 第七階段：生產就緒 (Phase 7 — Production Ready)

> 目標：支援多使用者、可部署、可監控。

- [ ] **L2** 以 `run_id` 隔離每次執行的 state，支援多使用者同時操作
- [ ] **L3** 加入稽核日誌（執行者、時間、輸入名單、結果摘要）
- [ ] Docker 容器化（`Dockerfile` + `docker-compose.yml`）
- [ ] 使用 Gunicorn 作為 WSGI server（取代 Flask dev server）
- [ ] 加入使用者認證（Basic Auth 或 OAuth2）
- [ ] 建立 OpenAPI 文件（`/docs` 端點）
- [ ] 監控儀表板：成功率、平均執行時間、失敗原因分類

