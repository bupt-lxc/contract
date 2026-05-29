@echo off
set SC_GR_DEV=1
cd /d F:\桌面\audi\contract
.venv\Scripts\python.exe -c "from sc_gr_app.db.migrations import migrate; from sc_gr_app.config import default_config; migrate(default_config()); print('Migration done')"
pause
