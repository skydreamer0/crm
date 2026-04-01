# CRM 提報防呆驗證機制實作計畫

這個計畫旨在提升機器的穩定度，透過在填表後加入「確認／驗證」機制，確保 CRM 確實正確地接收了輸入值。如果驗證失敗，則拋出異常讓該筆記錄進行跳過（Skip）處理，避免資料殘缺或是卡死流程。

## User Review Required

> [!IMPORTANT]
> 請確認以下關於產品驗證的「兩個思考方向」是否符合您的預期。若確認無誤，請回覆批准，我將立即開始進行程式碼修改。

## Proposed Changes

### 1. 醫師姓名輸入驗證 (Customer Name Verification)

**實作邏輯：**
在 `fill_appointment` 函數中，輸入並點擊 Enter 讓 CRM 載入下拉選單後，增加一小段 DOM 驗證機制。
1. 利用 Playwright 抓取 `div#new_abc` (客戶欄位) 內的 `text_content()`。
2. 正常情況下，CRM 的 Lookup 欄位若是正確選擇到對象，該 UI 區塊內會顯示被選中的「關聯名稱」（也就是醫生姓名）。
3. 如果讀取出來的內文**不包含**我們預期輸入的 `customer_name`，代表 CRM 端吃字或查無此人，此時強制讓這個 `attempt` 重試。
4. 若 3 次 attempt 結束後，仍然沒有驗證成功，則主動 `raise Exception(f"醫師姓名 '{customer_name}' 無法正確載入與驗證")`。外層的 `create_single_appointment` 捕捉到這個錯誤後，就會直接報錯並接續處理下一筆，標示「❌ [error] 跳過此筆」。

### 2. 產品兩筆驗證 (Product Addition Verification)

我們將透過兩個層次（兩個思考方向）來確保至少有 2 個產品被輸入成功：

**思考方向一：記憶體中的成功次數計數（流程驗證）**
在 `add_products_to_appointment` 中，我們會利用一個迴圈去新增產品（依據 `products_to_add` 的數量，目前預設為 2）。
1. 每一圈只要順利走到「產品 Popup 儲存並關閉」並且沒拋出錯誤，就將內部變數 `success_count += 1`。
2. 在迴圈徹底結束後，進行斷言：判斷 `success_count == len(products_to_add)`。如果不相等，代表其中一項產品在新增時遭遇不可恢復的錯誤，此時拋出警告，標示約會產品不完整。

**思考方向二：依據 CRM 主畫面的 Subgrid 渲染結果驗證（UI 視覺驗證）**
除了確定點過兩次成功的儲存，我們也讓程式去巡視父層「約會 Popup」的產品明細表格（Subgrid）是否真的長出了兩筆資料。
1. 在產品新增完畢後，等待約會表單的 Subgrid 重整完畢。
2. 使用 Playwright 掃描 iframe 內的產品列表（通常 class 包含 `.ms-crm-List-Row` 或特定列結構）。
3. 計算產品資料列的數量是否 `>= 2`。如果不夠，則發出警示（因為 CRM 可能介面顯示有時間差，或是儲存真的被後端吃掉）。

## 實作檔案 

#### [MODIFY] [create_appointments.py](file:///c:/Users/User/Documents/%E6%96%B0%E5%A2%9E%E8%B3%87%E6%96%99%E5%A4%BE/crm/src/create_appointments.py)
我們將直接增修其中的 `fill_appointment` 和 `add_products_to_appointment` 這兩個主要函數的實作邏輯。

## Open Questions

- 目前如果產品少於指定的兩項（例如只存活 1 個），您希望這整筆約會被標記為「錯誤（Error）並跳過」，還是「完成（Done）但把缺少產品的狀況輸出在終端機警告中」？
- 上述兩個思考方向的結合（流程次數確認 + UI 實際清單確認），是否就是您希望用來核對產品輸入的模式？

## Verification Plan

### Manual Verification
透過自動化腳本運行一次（Headless=False 模式），並刻意在中途干擾或把某個醫師名字改錯：
1. 目視它是否能夠主動報錯並安全跳到下一筆。
2. 目視終端機 log 是否會秀出「醫師驗證失敗：預期 xxx...」與「產品數量驗證：成功 X 項...」的除錯訊息。
