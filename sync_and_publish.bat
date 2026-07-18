@echo off
setlocal

REM Safe entrypoint for Stock Look Up publishing.
REM Default: build + validate + dry-run only.
REM Explicit live publish: sync_and_publish.bat --live

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
if not defined STOCK_LOOKUP_BACKEND_DIR set "STOCK_LOOKUP_BACKEND_DIR=%SCRIPT_DIR%"
if not defined STOCK_LOOKUP_WEB_DIR set "STOCK_LOOKUP_WEB_DIR=%SCRIPT_DIR%"
if not defined STOCK_LOOKUP_PYTHON set "STOCK_LOOKUP_PYTHON=python"

echo ============================================================
echo STOCK LOOK UP - BUILD / SYNC / PUBLISH
echo Backend : %STOCK_LOOKUP_BACKEND_DIR%
echo Web repo: %STOCK_LOOKUP_WEB_DIR%
echo Mode    : %*
echo ============================================================

if not exist "%STOCK_LOOKUP_BACKEND_DIR%\screen_snapshot.csv" (
  echo [ERROR] Missing backend artifact: screen_snapshot.csv
  exit /b 1
)
if not exist "%STOCK_LOOKUP_WEB_DIR%\publish_dashboard.py" (
  echo [ERROR] Missing publisher in web repo: publish_dashboard.py
  exit /b 1
)
if not exist "%STOCK_LOOKUP_WEB_DIR%\build_frontend.bat" (
  echo [ERROR] Missing frontend build script: build_frontend.bat
  exit /b 1
)

cd /d "%STOCK_LOOKUP_WEB_DIR%"

call "%STOCK_LOOKUP_WEB_DIR%\build_frontend.bat"
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo [ERROR] Frontend build failed with exit code %RC%. Aborting publish.
  exit /b %RC%
)
git rev-parse --show-toplevel
if errorlevel 1 exit /b 1
git branch --show-current
if errorlevel 1 exit /b 1
git remote -v
if errorlevel 1 exit /b 1
git rev-parse HEAD
if errorlevel 1 exit /b 1

"%STOCK_LOOKUP_PYTHON%" "%STOCK_LOOKUP_WEB_DIR%\publish_dashboard.py" %*
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo [ERROR] Publisher failed with exit code %RC%.
  exit /b %RC%
)

echo [OK] Publisher completed. Without --live, no stage/commit/push occurred.
exit /b 0
