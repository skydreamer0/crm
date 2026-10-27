@echo off
:: Scheduled run: create today's CRM appointments from the weekly plan Excel.
:: Arguments are passed to scripts\run_today.py, e.g.
::   run_today.bat --dry-run
::   run_today.bat --date 2026-10-27
cd /d "%~dp0"
set PYTHONUTF8=1

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python scripts\run_today.py %*
exit /b %ERRORLEVEL%
