@echo off
cd /d "%~dp0"
python scripts\setup_supabase_env.py
echo.
pause
