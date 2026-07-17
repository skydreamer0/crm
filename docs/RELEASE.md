# 打包與發佈指南 (RELEASE)

目前發布版本：`v1.1.1`

本專案是單機 Windows 工具，以 PyInstaller 打包成免安裝資料夾，並透過 GitHub Releases 分享給使用者。zip 內含 Python runtime 與 Playwright Chromium，使用者不需要另外安裝 Python 或瀏覽器。

## v1.1.0 更新重點

- 新增「醫院產品矩陣」設定頁：`/settings/products`
- 可依「醫院 + 科別」鎖定實際要建立的產品 SKU
- 新增 `/api/product-config`，提供產品 SKU 與科別預設產品給前端載入
- `hospital_product_rules` 會儲存在 `%APPDATA%\crm-automation\settings.json`
- 產品矩陣只更新產品規則，不會覆蓋既有 CRM 帳密設定
- Eligard 拆成 SKU：
  - `eli_7_5` -> `T5EL0`
  - `eli_22_5` -> `T5EL1`
  - `eli_45` -> `T5EL2`
- 名單預覽與實際執行會先套用醫院鎖定規則，沒有鎖定時才使用科別 fallback

## GitHub 自動發佈

推送一個 `v` 開頭的 tag，GitHub Actions 會在 Windows runner 上執行測試、打包，並建立 GitHub Release：

```bash
git tag v1.1.0
git push origin v1.1.0
```

幾分鐘後到 GitHub Releases 頁面下載：

```text
CRM-Automation-v1.1.0-windows.zip
```

相關 workflow：

- Release build: [.github/workflows/release.yml](../.github/workflows/release.yml)
- CI tests: [.github/workflows/ci.yml](../.github/workflows/ci.yml)

版本號建議使用語意化版本：

- bug fix：`v1.1.1`
- 新功能：`v1.2.0`
- 不相容改版：`v2.0.0`

## 本地手動打包

若不透過 GitHub Actions，可以在本機執行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1 -Version v1.1.0
```

產出：

```text
dist\CRM-Automation-v1.1.0-windows.zip
```

可加上 `-SkipTests` 跳過測試，但正式發佈前不建議略過。

## 打包注意事項

| 項目 | 說明 |
| --- | --- |
| 入口程式 | `src/app.py`，spec 定義在 [crm_automation.spec](../crm_automation.spec) |
| 模板與設定檔 | `src/templates` 與 `config/` 會一起 bundle，執行時透過 `_resource_path()` 支援 `sys._MEIPASS` |
| Chromium | 設定 `PLAYWRIGHT_BROWSERS_PATH=0` 並執行 `playwright install chromium`，讓 PyInstaller hook 能把瀏覽器一起打包 |
| 使用者設定 | 儲存在 `%APPDATA%\crm-automation\settings.json`，密碼以 Windows DPAPI 保護 |
| 產品規則 | `hospital_product_rules` 也是使用者設定，換新版 exe 後仍會沿用同一份 AppData 設定 |
| 執行紀錄 | 自動化歷史與截圖輸出到 `logs/` |

## 給使用者的更新說明

1. 到 GitHub Releases 下載 `CRM-Automation-v1.1.0-windows.zip`
2. 解壓縮到固定資料夾，例如 `D:\CRM-Automation`
3. 執行 `CRM-Automation.exe`
4. 第一次使用先到「設定」填 CRM 網址、帳號、密碼
5. 若要依醫院固定產品，進入「醫院產品矩陣」
6. 新增醫院名稱與別名，例如 `北醫, 北醫附醫, 台北醫學大學附設醫院`
7. 只有需要固定產品的「醫院 + 科別」才切成 `Locked`；其他維持 `Fallback`
8. 設定完記得按右上角「儲存」

## 發佈前檢查

```powershell
python -m pytest tests/ -q
```

確認測試通過後再推 tag。GitHub Release workflow 也會再跑一次完整測試與打包。
