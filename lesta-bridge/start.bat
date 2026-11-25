@echo off
setlocal
pushd "%~dp0" || exit /b 1
set "BRIDGE_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "BRIDGE_PYTHON=.venv\Scripts\python.exe"
if exist "python_env\python.exe" set "BRIDGE_PYTHON=python_env\python.exe"
"%BRIDGE_PYTHON%" launcher.py %*
set "BRIDGE_STATUS=%errorlevel%"
popd
if not "%BRIDGE_STATUS%"=="0" pause
exit /b %BRIDGE_STATUS%
