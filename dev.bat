@echo off
REM ============================================
REM SC GR Management -- Dev Mode Launcher
REM Uses local database for offline development
REM ============================================
set SC_GR_DEV=1
set SC_GR_DATA_DIR=%~dp0

echo.
echo ========================================
echo  SC GR Management -- DEV MODE
echo  Database: %~dp0data\sc_gr.sqlite3
echo ========================================
echo.

cd /d "%~dp0"
start "Vite Dev Server" cmd /c "cd frontend && npm run dev"
timeout /t 3 /nobreak >nul
uv run python -m sc_gr_app.main
