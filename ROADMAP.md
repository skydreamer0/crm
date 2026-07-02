# CRM 報表填寫自動化 - 發展藍圖 (ROADMAP)

> **產品定位（2026-07 確定）**：單機 Windows 工具，以 PyInstaller 打包分享給其他使用者在本機執行。
> 不做伺服器部署、不做多使用者、不換 Web 框架——以「把現有功能修穩」為原則。

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
- [x] ~~異常偵測與自動警示 (Line Notify 支援)~~ **已廢除**：LINE Notify 服務已於 2025/3 終止，通知功能不再使用，相關程式碼待移除

## 第四．五階段：本地設定與打包 (Done)
- [x] `settings_store.py`：per-user 設定持久化（%APPDATA%、DPAPI 密碼加密、密文遮蔽）
- [x] `/api/settings` GET/POST + 執行前設定完整性檢查
- [x] Web UI 設定面板（CRM URL / 帳密 / headless）
- [x] 設定移至獨立頁面 `/settings`，主頁只保留狀態徽章與連結 (2026-07-02)
- [x] PyInstaller 打包支援（bundled app path 處理、frozen 模式 debug=False）
- [x] 測試基礎建立（settings store / API / parser / bundle path 等 6 個測試檔）

---

## 已知問題清單

> 依嚴重程度列出，狀態隨程式碼演進更新（最後核對：2026-07-02）。

#### 高優先 (High)

| # | 問題 | 影響 | 狀態 |
|---|------|------|------|
| H1 | `TIMING` dict 硬編碼毫秒數，主流程仍有多處 `wait_for_timeout`，CRM 回應變慢即失敗 | 自動化中斷率高 | 部分完成 (2026-07-02)：產品視窗就緒改為條件等待（等輸入欄可見，上限 20 秒）；鍵盤節奏類短等待無可觀察 DOM 條件，屬刻意保留 |
| H2 | `_automation_state` 是無鎖全域 dict，progress list 無界限增長 | Thread safety、記憶體增長 | **已完成 (2026-07-02)** |
| H3 | 無取消 / 逾時機制，瀏覽器崩潰後無法中斷執行 | 程序卡死、資源無法釋放 | **已完成 (2026-07-02)**：`/api/cancel` 協作式取消（逐筆檢查） |
| H4 | **產品填寫部分成功無法察覺**：單一產品失敗只 log warning 就繼續，`add_products_to_appointment` 無回傳值，檢核報告只有約會層級兩態，「2 個產品只存進 1 個」仍顯示成功，需手動回 CRM 逐筆巡查 | 資料不完整且不可見 | **已完成 (2026-07-02)**：per-product 結果回傳 + subgrid 實際列數驗證 + 三態檢核報告 + Web UI 補填名單 + 部分完成自動截圖 |

#### 中優先 (Medium)

| # | 問題 | 影響 | 狀態 |
|---|------|------|------|
| M1 | `create_appointments.py` 達 911 行，瀏覽器、表單、商業邏輯混在一起 | 難以維護與測試 | 未動工 |
| M2 | `app.py` 在 thread 內建立 asyncio event loop，混用 threading + async | 難以 debug，例外清理不完整 | **已完成 (2026-07-02)**：改用 `asyncio.run()`，維持 Flask |
| M3 | `create_appointments.py` 直接 import `visit_list_parser`，緊耦合 | 無法獨立單元測試 | 未動工 |
| M4 | Flask routes 無 schema 驗證，直接 `data.get()` 取值 | 錯誤輸入造成非預期行為 | **已完成 (2026-07-02)**：text 型別/長度 + date 格式驗證 |
| M5 | `selectors.yaml` 使用多層 fallback CSS selector，CRM UI 一改即斷 | 維護成本高 | 未動工 |
| M6 | 單筆失敗跳過但未驗證表單是否已部份提交，可能留下孤立記錄 | CRM 資料不一致 | **已完成 (2026-07-02)**：追蹤約會儲存時點，失敗筆標示孤立記錄風險並顯示於報告與 UI |
| M7 | 使用基本 logging，無 run_id、無結構化輸出 | 難以追蹤問題 | 未動工 |

#### 低優先 (Low)

| # | 問題 | 狀態 |
|---|------|------|
| L1 | 無資料庫持久化，執行紀錄只存 JSON 檔 | 單機工具下優先度低，可選 SQLite |
| L4 | 正式環境 debug mode | 已處理（打包後 `debug=False`，開發模式保留 debug 屬刻意行為） |
| L5 | 無 pre-commit hooks（linting / formatting 未自動化） | 未動工 |
| L6 | 部份函式缺少 return type hint | 未動工 |

> 原 L2（多使用者隔離）、L3（稽核軌跡）因確定走單機路線，已移除。

---

## 第五階段：填寫可靠性 (Phase 5 — Fill Reliability) ← 目前重點

> 目標：解決「填了但不完整、不完整卻看不見」的核心痛點。

- [x] **H4-1** `add_products_to_appointment` 回傳 per-product 結果（成功/失敗+原因），往上傳遞至 `run_automation`
- [x] **H4-2** 關閉約會 Popup 前讀取產品明細 subgrid 實際列數（`span#core_ItemsTotal` + 資料列 fallback），與預計新增數比對（以 CRM 實際狀態為準，不信任儲存流程）
- [x] **H4-3** 檢核報告改三態：✅ 完整 / 🟡 部分完成（列出缺哪個產品）/ ❌ 失敗，寫入 `logs/history` JSON
- [x] **H4-4** Web UI 執行結束顯示「填寫檢核」區塊（統計卡 + 需補填名單表格，含缺漏產品明細）
- [x] **H4-5** 部分完成時自動截圖該筆約會表單，存 `logs/screenshots/partial_*.png`
- [x] **H1**（產品段落）產品視窗就緒改為條件等待（等 `new_product` 輸入欄可見，上限 20 秒，取代固定 3 秒）；鍵盤節奏類短等待因無可觀察 DOM 條件刻意保留，其餘長等待視實際失敗案例逐步替換
- [x] **M6** 追蹤約會儲存時點（`state["appointment_saved"]`），失敗筆若約會已存入 CRM 則標示「孤立記錄風險」，寫入 history JSON 並顯示於 UI 失敗名單備註欄

## 第六階段：穩定化 (Phase 6 — Stabilization) — Done (2026-07-02)

> 目標：消除執行中斷與狀態管理問題，不改變外部行為。

- [x] **H2** 為 `_automation_state` 加上 `threading.Lock`（含 busy 檢查的原子化），progress 改為有界限的 `collections.deque(maxlen=500)`
- [x] **H3** 取消機制：`POST /api/cancel` 設定 cancel event，目前這筆處理完後停止，未執行筆數列入失敗名單（原因: 使用者取消）；UI 進度區塊加「⏹ 取消」按鈕
- [x] **M2** 收斂 thread + asyncio 混用：改用 `asyncio.run()` 統一處理 event loop 建立/例外清理/關閉，維持 Flask
- [x] **M4** `text` 欄位型別與長度驗證（上限 20000 字元）、`date` 欄位 ISO 格式驗證，套用於 `/api/parse` 與 `/api/execute`
- [x] 移除 Line Notify 相關程式碼（send_line_notify、settings/env token 欄位、requests 依賴；舊設定檔含 token 欄位仍可正常讀取）

## 第七階段：可維護性與分享 (Phase 7 — Maintainability & Distribution)

> 目標：程式碼好維護、打包好分享。視實際痛點決定是否執行，不強求。

- [ ] **M1** 拆分 `create_appointments.py`（瀏覽器管理 / 表單填寫 / 流程協調）
- [ ] **M3** 建構子注入 `VisitListParser`，解除緊耦合
- [ ] **M5** 精簡 selectors fallback 層級，補上 selector 失效時的明確錯誤訊息
- [ ] **M7** 日誌加入 `run_id` 便於對照 history / screenshots
- [x] 打包發佈流程 (2026-07-02)：`crm_automation.spec`（含 Chromium bundle）、`scripts/build_release.ps1` 本地打包、GitHub Actions（`ci.yml` 測試 + `release.yml` tag 觸發自動建置發佈）、`docs/RELEASE.md` 含給使用者的安裝說明
- [ ] Web UI 歷史查詢頁（讀 `logs/history`，看過去執行結果與補填名單）
- [ ] **L5/L6** pre-commit hooks 與 type hints（順手做）
