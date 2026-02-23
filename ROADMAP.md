# CRM 報表填寫自動化 - 發展藍圖 (ROADMAP)

## 第一階段：基礎建設 (Current)
- [x] 初始化專案結構
- [x] 建立 README 與 ROADMAP
- [ ] 撰寫技術規格說明書
- [ ] 環境變數與配置系統設計

## 第二階段：爬蟲核心開發
- [ ] CRM 系統登入自動化同步 (包含處理驗證碼/雙重驗證)
- [ ] 報表填寫頁面解析 (Selectors mapping)
- [ ] 基礎自動填表邏輯與錯誤重試機制
 
## 第二．五階段：待訪名單解析與產品匹配
- [x] 待訪名單解析器 (visit_list_parser.py)
- [x] 科別對應表 (department_mapping.yaml)
- [x] 產品目錄 (product_catalog.yaml)
- [x] 整合至約會記錄自動化流程
- [ ] 產品描述規則與自動帶入

## 第三階段：資料對接與驗證
- [ ] 支援從 Excel/CSV 讀取待填寫資料
- [ ] 填寫完成後的截圖驗證與 Log 記錄
- [ ] 異常偵測與自動警示 (Line/Email)

## 第四階段：優化與穩定
- [ ] 多執行緒/非同步處理加速
- [ ] 支援背景執行 (Headless mode)
- [ ] 定時任務整合 (GitHub Actions / Local Task Scheduler)
