# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for CRM Automation (Windows onedir build)
#
# 建置前必須設定 PLAYWRIGHT_BROWSERS_PATH=0 並執行 playwright install chromium，
# 讓 Chromium 安裝進 playwright 套件目錄，PyInstaller 的 playwright hook 才會
# 把瀏覽器一併收進 bundle（app.py 在 frozen 模式會設定同一個環境變數來找到它）。
# 詳見 docs/RELEASE.md 或直接執行 scripts/build_release.ps1。

a = Analysis(
    ['src/app.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        # _resource_path() 在 frozen 模式下以 sys._MEIPASS 為根目錄解析這些路徑
        ('src/templates', 'templates'),
        ('config', 'config'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CRM-Automation',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # 保留主控台視窗：使用者能看到執行 log，關閉視窗即停止伺服器
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='CRM-Automation',
)
