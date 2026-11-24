@echo off
cd /d "%~dp0"
if exist "python_env\python.exe" (
    "python_env\python.exe" launcher.py %*
) else (
    python launcher.py %*
)
if errorlevel 1 pause
