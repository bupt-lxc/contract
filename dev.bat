@echo off
REM ============================================
REM PO Management Platform -- Dev Mode Launcher
REM Uses local database for offline development
REM ============================================
set SC_GR_DEV=1
set SC_GR_DATA_DIR=%~dp0

echo.
echo ========================================
echo  PO Management Platform -- DEV MODE
echo  Database: %~dp0data\sc_gr.sqlite3
echo ========================================
echo.

cd /d "%~dp0"
start "Vite Dev Server" cmd /c "cd frontend && npm run dev"
timeout /t 3 /nobreak >nul
start "Email Notification (Draft)" cmd /c "uv run python -m sc_gr_app.notification --draft --poll-interval 60"
uv run python -m sc_gr_app.main
