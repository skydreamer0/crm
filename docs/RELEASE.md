# 打包與發佈指南 (RELEASE)

本專案是單機 Windows 工具，以 PyInstaller 打包成免安裝的資料夾，透過 **GitHub Releases** 分享給其他使用者。zip 內含 Python runtime 與 Chromium 瀏覽器，**收到的人不需要安裝任何東西**。

---

## 方式一：GitHub 自動發佈（建議）

推送一個 `v` 開頭的 tag，GitHub Actions 會自動在 Windows runner 上跑測試、打包、建立 Release：

```bash
git tag v1.0.0
git push origin v1.0.0
```

幾分鐘後到 GitHub 的 **Releases** 頁面就會出現 `CRM-Automation-v1.0.0-windows.zip`，把 Release 頁面連結傳給要使用的人即可。

- Workflow 定義：[.github/workflows/release.yml](../.github/workflows/release.yml)
- 版本號建議用 [語意化版本](https://semver.org/lang/zh-TW/)：修 bug 進版 `v1.0.1`、加功能進版 `v1.1.0`

另外每次 push 到 `main` 或開 PR 時，[ci.yml](../.github/workflows/ci.yml) 會自動跑測試。

## 方式二：本地打包

不想經過 GitHub 時（例如快速給同事測試版）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1 -Version v1.0.0
```

產出 `dist\CRM-Automation-v1.0.0-windows.zip`，直接傳給對方。加 `-SkipTests` 可跳過測試。

> **注意**：腳本會以 `PLAYWRIGHT_BROWSERS_PATH=0` 把 Chromium（約 300MB）安裝到目前 Python 環境的 playwright 套件目錄內，這是讓 PyInstaller 能把瀏覽器收進 bundle 的必要步驟，只需第一次會下載。

## 打包原理（維護時需要知道的事）

| 元件 | 機制 |
|------|------|
| 進入點 | `src/app.py`，spec 檔為 [crm_automation.spec](../crm_automation.spec)（onedir 模式） |
| 模板與設定 | `src/templates` 和 `config/` 以 datas 收進 bundle，程式內以 `_resource_path()`（`sys._MEIPASS`）解析 |
| Chromium | 建置時 `PLAYWRIGHT_BROWSERS_PATH=0` + `playwright install chromium` 裝進套件目錄 → PyInstaller hook 自動收集；執行時 `app.py` 偵測 frozen 模式設定同一變數，playwright 便從 bundle 內找瀏覽器 |
| 主控台視窗 | 刻意保留（`console=True`），使用者可看 log，關閉視窗即停止伺服器 |
| 使用者設定 | 存於 `%APPDATA%\crm-automation\settings.json`，密碼以 Windows DPAPI 加密，與 exe 位置無關（更新版本不會遺失設定） |
| 執行紀錄 | 寫到 exe 所在資料夾的 `logs/`（history JSON 與截圖） |

---

## 給使用者的安裝說明（可直接複製傳給對方）

> 1. 打開我傳給你的 GitHub Release 連結，下載 `CRM-Automation-vX.X.X-windows.zip`
> 2. 解壓縮到任意資料夾（例如 `D:\CRM-Automation`）
> 3. 進入資料夾，雙擊 `CRM-Automation.exe`——會出現一個黑色視窗（請不要關閉，它是伺服器），瀏覽器會自動開啟操作介面
> 4. 第一次使用：點右上角「⚙️ 設定」，填入 CRM 網址、帳號、密碼後儲存
> 5. 回主頁貼入待訪名單 → 解析名單 → 執行自動化；跑完看「填寫檢核」報告，有缺漏會列出要補的名單
> 6. 用完關掉黑色視窗即可
>
> 註：Windows 可能跳出「Windows 已保護您的電腦」，點「其他資訊」→「仍要執行」（因為程式沒有數位簽章）。更新新版本時直接解壓覆蓋即可，設定不會遺失。
