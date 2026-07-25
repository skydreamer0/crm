# 本地打包腳本 — 產出可分享的 Windows zip
# 用法: powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1 [-Version v1.2.1] [-SkipTests]
param(
    [string]$Version = "dev",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "[1/5] 安裝建置依賴..." -ForegroundColor Cyan
python -m pip install -r requirements.txt pyinstaller pytest

if (-not $SkipTests) {
    Write-Host "[2/5] 執行測試..." -ForegroundColor Cyan
    python -m pytest tests/ -q
} else {
    Write-Host "[2/5] 跳過測試 (-SkipTests)" -ForegroundColor Yellow
}

Write-Host "[3/5] PyInstaller 打包..." -ForegroundColor Cyan
python -m PyInstaller crm_automation.spec --noconfirm

# ── Chromium：優先用本機快取，已下載過就不重複下載 ──────────────────────────
Write-Host "[4/5] 準備 Chromium (優先用本機快取)..." -ForegroundColor Cyan
$cacheDir = if ($env:PLAYWRIGHT_BROWSERS_PATH_CACHE) {
    $env:PLAYWRIGHT_BROWSERS_PATH_CACHE
} else {
    Join-Path $env:LOCALAPPDATA "ms-playwright"
}

function Get-ChromiumDirs($root) {
    if (-not (Test-Path $root)) { return @() }
    Get-ChildItem $root -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^(chromium|chromium_headless_shell|ffmpeg)-' }
}

$browserDirs = Get-ChromiumDirs $cacheDir
if ($browserDirs.Count -eq 0) {
    Write-Host "    本機快取沒有 Chromium，下載一次到快取 ($cacheDir)..." -ForegroundColor Yellow
    Remove-Item Env:\PLAYWRIGHT_BROWSERS_PATH -ErrorAction SilentlyContinue
    python -m playwright install chromium
    $browserDirs = Get-ChromiumDirs $cacheDir
    if ($browserDirs.Count -eq 0) {
        throw "Chromium 下載失敗，且本機快取也沒有：$cacheDir"
    }
} else {
    Write-Host "    使用本機快取的 Chromium，略過下載：" -ForegroundColor Green
    $browserDirs | ForEach-Object { Write-Host "      - $($_.Name)" }
}

# 從快取複製到 dist（免安裝、離線可用）
$dest = "dist/CRM-Automation/browsers"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
foreach ($d in $browserDirs) {
    Copy-Item $d.FullName -Destination $dest -Recurse -Force
}
Write-Host "    Chromium 已放入 $dest" -ForegroundColor Green

Write-Host "[5/5] 壓縮..." -ForegroundColor Cyan
$zipPath = Join-Path (Resolve-Path "dist").Path "CRM-Automation-$Version-Windows.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
# 用 .NET 壓縮，避免 Compress-Archive 在部分環境載入失敗，也沒有大小上限問題
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    (Resolve-Path "dist/CRM-Automation").Path,
    $zipPath,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $true
)

Write-Host ""
Write-Host "完成: $zipPath" -ForegroundColor Green
Write-Host "分享方式: 上傳到 GitHub Release，或直接把 zip 傳給對方 (解壓後執行 CRM-Automation.exe)"
