@echo off
REM ============================================
REM SC GR Management — Dev Mode Launcher
REM Uses local database for offline development
REM ============================================
set SC_GR_DEV=1

echo.
echo ========================================
echo  SC GR Management — DEV MODE
echo  Database: %%APPDATA%%\sc-gr-management-dev
echo ========================================
echo.

cd /d "%~dp0"
start "Vite Dev Server" cmd /c "cd frontend && npm run dev"
timeout /t 3 /nobreak >nul
uv run python -m sc_gr_app.main
