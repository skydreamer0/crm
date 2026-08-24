#!/bin/bash
cd "$(dirname "$0")"

echo "[CRM] Starting setup..."

if [ -d ".venv" ]; then
    echo "[CRM] Activating .venv..."
    source .venv/bin/activate
elif [ -d "venv" ]; then
    echo "[CRM] Activating venv..."
    source venv/bin/activate
fi

echo "[CRM] Starting application..."
echo "[CRM] URL: http://127.0.0.1:5050"

# Open default browser on macOS
open "http://127.0.0.1:5050" 2>/dev/null &

python src/app.py
