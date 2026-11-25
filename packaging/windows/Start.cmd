@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist "config.yaml" copy "config.example.yaml" "config.yaml" >nul
call start.bat --config config.yaml %*
set "RESULT=%errorlevel%"
popd
exit /b %RESULT%
