@echo off
setlocal

REM Safe entrypoint for Stock Look Up publishing.
REM Default: build + validate + dry-run only.
REM Explicit live publish: sync_and_publish.bat --live

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

if not defined STOCK_LOOKUP_BACKEND_DIR (
  if defined STOCK_LOOKUP_RUNTIME_ROOT (
    set "STOCK_LOOKUP_BACKEND_DIR=%STOCK_LOOKUP_RUNTIME_ROOT%"
  ) else if exist "%SCRIPT_DIR%\..\dashboard-runtime\screen_snapshot.csv" (
    set "STOCK_LOOKUP_BACKEND_DIR=%SCRIPT_DIR%\..\dashboard-runtime"
  ) else if exist "%SCRIPT_DIR%\..\..\dashboard-runtime\screen_snapshot.csv" (
    set "STOCK_LOOKUP_BACKEND_DIR=%SCRIPT_DIR%\..\..\dashboard-runtime"
  ) else (
    set "STOCK_LOOKUP_BACKEND_DIR=%SCRIPT_DIR%"
  )
)
if not defined STOCK_LOOKUP_WEB_DIR set "STOCK_LOOKUP_WEB_DIR=%SCRIPT_DIR%"
if not defined STOCK_LOOKUP_PYTHON set "STOCK_LOOKUP_PYTHON=python"
REM STOCK_LOOKUP_PRODUCER_DIR: the stock-core-private checkout holding tools\publish_release.py.
REM Not user-configured -> try both known layouts (direct sibling, e.g. WEB_DIR=dashboard-runtime;
REM one level deeper, e.g. WEB_DIR=worktrees\market-dashboard-main) before giving up and letting
REM the explicit existence check below fail closed with guidance.
if not defined STOCK_LOOKUP_PRODUCER_DIR (
  if exist "%SCRIPT_DIR%\..\stock-core-private\tools\publish_release.py" (
    set "STOCK_LOOKUP_PRODUCER_DIR=%SCRIPT_DIR%\..\stock-core-private"
  ) else if exist "%SCRIPT_DIR%\..\..\stock-core-private\tools\publish_release.py" (
    set "STOCK_LOOKUP_PRODUCER_DIR=%SCRIPT_DIR%\..\..\stock-core-private"
  )
)

echo ============================================================
echo STOCK LOOK UP - BUILD / SYNC / PUBLISH
echo Backend : %STOCK_LOOKUP_BACKEND_DIR%
echo Web repo: %STOCK_LOOKUP_WEB_DIR%
echo Mode    : %*
echo ============================================================

if /I "%STOCK_LOOKUP_BACKEND_DIR%"=="%STOCK_LOOKUP_WEB_DIR%" (
  echo [ERROR] STOCK_LOOKUP_BACKEND_DIR resolves to WEB_DIR ^(%STOCK_LOOKUP_WEB_DIR%^). Cannot publish backend artifacts from web root to itself.
  echo [ERROR] Set STOCK_LOOKUP_BACKEND_DIR to point to dashboard-runtime ^(e.g. C:\Projects\StockLookup\dashboard-runtime^).
  exit /b 1
)

if not exist "%STOCK_LOOKUP_BACKEND_DIR%\screen_snapshot.csv" (
  echo [ERROR] Missing backend artifact: %STOCK_LOOKUP_BACKEND_DIR%\screen_snapshot.csv
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
if errorlevel 1 (
  echo [ERROR] Frontend build failed with exit code %errorlevel%. Aborting publish.
  exit /b 1
)
git rev-parse --show-toplevel
if errorlevel 1 exit /b 1
git branch --show-current
if errorlevel 1 exit /b 1
git remote -v
if errorlevel 1 exit /b 1
git rev-parse HEAD
if errorlevel 1 exit /b 1

REM Trusted-subset release (analysis_bundle.json + bundle_manifest.json + focus_extract.json
REM + statement_taxonomy_sidecar.json) must land as one hash-verified unit BEFORE
REM publish_dashboard.py ever touches screen_snapshot data.
if not exist "%STOCK_LOOKUP_PRODUCER_DIR%\tools\publish_release.py" (
  echo [ERROR] Missing trusted-subset release publisher: %STOCK_LOOKUP_PRODUCER_DIR%\tools\publish_release.py
  echo [ERROR] Set STOCK_LOOKUP_PRODUCER_DIR to the stock-core-private checkout.
  exit /b 1
)
echo ============================================================
echo TRUSTED-SUBSET RELEASE ^(publish_release.py^) - must land before dashboard data publish
echo ============================================================
"%STOCK_LOOKUP_PYTHON%" "%STOCK_LOOKUP_PRODUCER_DIR%\tools\publish_release.py" --source "%STOCK_LOOKUP_BACKEND_DIR%" --destination "%STOCK_LOOKUP_WEB_DIR%" %*
if errorlevel 1 (
  echo [ERROR] Trusted-subset release publisher failed. Aborting publish.
  exit /b 1
)

"%STOCK_LOOKUP_PYTHON%" "%STOCK_LOOKUP_WEB_DIR%\publish_dashboard.py" %*
if errorlevel 1 (
  echo [ERROR] Publisher failed with exit code %errorlevel%.
  exit /b 1
)

echo [OK] Publisher completed. Without --live, no stage/commit/push occurred.
exit /b 0
