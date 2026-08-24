#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

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

python src/app.py
