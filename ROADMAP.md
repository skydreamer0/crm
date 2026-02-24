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

