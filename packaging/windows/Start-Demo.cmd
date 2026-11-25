@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist "config.offline.yaml" copy "config.example.yaml" "config.offline.yaml" >nul
call start.bat --dry-run --config config.offline.yaml %*
set "RESULT=%errorlevel%"
popd
exit /b %RESULT%
