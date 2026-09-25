#!/bin/bash
# ==============================================================================
# CRM Automation System - macOS 啟動腳本 (.command)
# 支援 Finder 雙擊或終端機執行
# ==============================================================================

# 切換到腳本所在目錄
cd "$(dirname "$0")"

echo "=================================================="
echo "      CRM Automation System (macOS)"
echo "=================================================="
echo ""

# 1. 檢查 5050 連接埠佔用情況 (避免重覆啟動衝突)
EXISTING_PID=$(lsof -ti :5050 2>/dev/null)
if [ -n "$EXISTING_PID" ]; then
    echo "[CRM] ⚠️ 偵測到 5050 連接埠已被舊行程 (PID: $EXISTING_PID) 佔用。"
    echo "[CRM] 正在釋放連接埠以利啟動..."
    kill -9 $EXISTING_PID 2>/dev/null
    sleep 1
    echo "[CRM] ✅ 舊行程已清理完成"
    echo ""
fi

# 2. 虛擬環境檢查與啟動
VENV_ACTIVATED=0
if [ -d ".venv" ]; then
    echo "[CRM] 正在啟用虛擬環境 (.venv)..."
    source .venv/bin/activate
    PYTHON_EXEC="python"
    VENV_ACTIVATED=1
elif [ -d "venv" ]; then
    echo "[CRM] 正在啟用虛擬環境 (venv)..."
    source venv/bin/activate
    PYTHON_EXEC="python"
    VENV_ACTIVATED=1
fi

if [ $VENV_ACTIVATED -eq 0 ]; then
    if command -v python3 >/dev/null 2>&1; then
        echo "[CRM] ⚠️ 未偵測到虛擬環境 (.venv / venv)，使用系統 python3..."
        PYTHON_EXEC="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_EXEC="python"
    else
        echo "[ERROR] ❌ 找不到 Python 執行檔！請先安裝 Python 3.10 以上版本。"
        echo ""
        read -p "請按 Enter 鍵關閉視窗..."
        exit 1
    fi
fi

# 3. 檢查必要依賴
$PYTHON_EXEC -c "import flask, playwright" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "[CRM] ⚠️ 偵測到缺少必要套件，正在嘗試安裝依賴套件..."
    $PYTHON_EXEC -m pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "[ERROR] ❌ 套件安裝失敗，請檢查網路連線或 Python 環境。"
        echo ""
        read -p "請按 Enter 鍵關閉視窗..."
        exit 1
    fi
    echo "[CRM] 正在檢查 Playwright Chromium 瀏覽器..."
    $PYTHON_EXEC -m playwright install chromium
fi

echo ""
echo "[CRM] 🚀 正在啟動 CRM 介面..."
echo "[CRM] 系統網址: http://127.0.0.1:5050"
echo "[CRM] (伺服器就緒後將自動開啟預設瀏覽器，關閉此視窗即可停止系統)"
echo "--------------------------------------------------"
echo ""

# 4. 啟動 Flask 應用程式 (app.py 內建延遲自動開啟瀏覽器)
$PYTHON_EXEC src/app.py
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -ne 0 ]; then
    echo "[ERROR] ❌ 程式異常結束 (結束碼: $EXIT_CODE)。"
else
    echo "[CRM] 系統已正常停止。"
fi

echo ""
read -p "請按 Enter 鍵關閉視窗..."
