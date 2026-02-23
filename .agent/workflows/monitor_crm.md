---
description: 監控 CRM 自動化 (開啟有 UI 的瀏覽器供觀察)
---

# 啟動並監控 CRM 自動化腳本

執行此 Workflow 將會啟動 Playwright 腳本 (`src/create_appointments.py`)。腳本預設採用 `headless=False`，所以會彈出真實的瀏覽器視窗，你可以直接在畫面上監控機器人自動操作 CRM 的整個過程：包含登入、建立日報、以及自動新增約會記錄。

## 執行指令

// turbo
```powershell
python src/create_appointments.py
```
