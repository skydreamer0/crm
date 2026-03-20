# 開發工具腳本 (Dev Tools)

此資料夾存放的是**開發階段**使用的探索與測試腳本。  
這些腳本在正式的自動化流程中**不會被調用**，但保留作為參考與未來除錯使用。

## 檔案說明

| 檔案 | 用途 |
|---|---|
| `main.py` | 早期 CLI 版本的自動化腳本（功能已整合至 `create_appointments.py`）|
| `explore_appointment.py` | 探索約會紀錄表單的 HTML 結構與欄位 ID |
| `explore_product_fields.py` | 探索產品介紹明細 Popup 的結構 |
| `test_name_input.py` | 單獨測試「拜訪對象」姓名自動填入流程 |
| `find_activity_button.py` | 開啟 DevTools 手動定位「+ 新增約會紀錄」按鈕 |
| `find_fields_by_tab.py` | 按 Tab 鍵逐一偵測表單欄位順序 |
| `capture_form_screenshot.py` | 截取日報表單畫面 |
| `check_screenshot.py` | 確認截圖檔案是否存在 |
| `dump_saved_report.py` | 匯出已儲存日報的 HTML（含所有 iframe）|
| `extract_html.py` | 抓取 CRM 首頁 HTML |
| `extract_daily_html.py` | 抓取日報清單頁 HTML |
| `extract_daily_form_html.py` | 抓取新增日報表單 HTML |
| `parse_form.py` | 用 BeautifulSoup 解析表單欄位（需安裝 bs4）|

## 使用方式

這些腳本都是獨立執行的，例如：

```bash
source venv/bin/activate
python src/dev_tools/explore_appointment.py
```
