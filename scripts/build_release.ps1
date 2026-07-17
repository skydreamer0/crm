# 本地打包腳本 — 產出可分享的 Windows zip
# 用法: powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1 [-Version v1.1.0] [-SkipTests]
param(
    [string]$Version = "dev",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "[1/5] 安裝建置依賴..." -ForegroundColor Cyan
python -m pip install -r requirements.txt pyinstaller pytest

# 確保 Playwright 下載到一般快取中供測試使用
Write-Host "[2/5] 下載 Chromium..." -ForegroundColor Cyan
python -m playwright install chromium

if (-not $SkipTests) {
    Write-Host "[3/5] 執行測試..." -ForegroundColor Cyan
    python -m pytest tests/ -q
} else {
    Write-Host "[3/5] 跳過測試 (-SkipTests)" -ForegroundColor Yellow
}

Write-Host "[4/5] PyInstaller 打包..." -ForegroundColor Cyan
python -m PyInstaller crm_automation.spec --noconfirm

Write-Host "[5/5] 下載 Chromium (裝進 dist 供發布)..." -ForegroundColor Cyan
$env:PLAYWRIGHT_BROWSERS_PATH = "dist/CRM-Automation/browsers"
python -m playwright install chromium

Write-Host "[6/6] 壓縮..." -ForegroundColor Cyan
$zipPath = "dist/CRM-Automation-$Version-Windows.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path "dist/CRM-Automation" -DestinationPath $zipPath

Write-Host ""
Write-Host "完成: $zipPath" -ForegroundColor Green
Write-Host "分享方式: 上傳到 GitHub Release，或直接把 zip 傳給對方 (解壓後執行 CRM-Automation.exe)"
