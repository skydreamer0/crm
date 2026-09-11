#!/bin/bash
# ==============================================================================
# CRM Automation System - macOS / Linux 終端機啟動腳本
# ==============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=================================================="
echo "      CRM Automation System"
echo "=================================================="
echo ""

# 1. 檢查 5050 連接埠佔用情況
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
if [ -d ".venv" ]; then
    echo "[CRM] 正在啟用虛擬環境 (.venv)..."
    source .venv/bin/activate
    PYTHON_EXEC="python"
elif [ -d "venv" ]; then
    echo "[CRM] 正在啟用虛擬環境 (venv)..."
    source venv/bin/activate
    PYTHON_EXEC="python"
elif command -v python3 >/dev/null 2>&1; then
    echo "[CRM] ⚠️ 未偵測到虛擬環境 (.venv / venv)，使用系統 python3..."
    PYTHON_EXEC="python3"
else
    PYTHON_EXEC="python"
fi

echo ""
echo "[CRM] 🚀 正在啟動 CRM 介面..."
echo "[CRM] 系統網址: http://127.0.0.1:5050"
echo "--------------------------------------------------"
echo ""

$PYTHON_EXEC src/app.py
