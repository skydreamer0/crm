@echo off
title CRM Automation System
cd /d "%~dp0"

echo [CRM] Starting setup...

:: Check for virtual environment and activate
if exist "venv\Scripts\activate.bat" (
    echo [CRM] Activating venv...
    call venv\Scripts\activate.bat
)

:: Dependency check (optional)
:: python -m pip install -r requirements.txt

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to prepare environment.
    pause
    exit /b %ERRORLEVEL%
)

echo [CRM] Dependencies checked.
echo [CRM] Starting application...
echo [CRM] URL: http://127.0.0.1:5050

python src/app.py

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Application crashed.
    pause
)
pause
