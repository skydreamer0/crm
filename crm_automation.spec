# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for CRM Automation (Windows onedir build)
#
# 建置時不設定 PLAYWRIGHT_BROWSERS_PATH，讓 PyInstaller 略過打包瀏覽器，
# 藉此避開 macOS 上的 codesign 錯誤。
# 瀏覽器會在 PyInstaller 執行完畢後，由 GitHub Actions 另外下載並放入 dist/CRM-Automation/browsers/
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
