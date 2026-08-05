@echo off
setlocal

REM Safe entrypoint for Stock Look Up publishing.
REM Default: build + validate + dry-run only.
REM Explicit live publish: sync_and_publish.bat --live

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM 1. Resolve Python executable safely (strip existing quotes if present)
if defined STOCK_LOOKUP_PYTHON (
  set "STOCK_LOOKUP_PYTHON=%STOCK_LOOKUP_PYTHON:"=%"
) else (
  set "STOCK_LOOKUP_PYTHON=python"
)

REM Verify Python executable is reachable
"%STOCK_LOOKUP_PYTHON%" --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python executable is invalid or unreachable: [%STOCK_LOOKUP_PYTHON%]
  echo [ERROR] Set STOCK_LOOKUP_PYTHON to a valid python.exe path.
  exit /b 1
)

REM 2. Resolve BACKEND_DIR (strip existing quotes if present)
if defined STOCK_LOOKUP_BACKEND_DIR (
  set "STOCK_LOOKUP_BACKEND_DIR=%STOCK_LOOKUP_BACKEND_DIR:"=%"
) else if defined STOCK_LOOKUP_RUNTIME_ROOT (
  set "STOCK_LOOKUP_BACKEND_DIR=%STOCK_LOOKUP_RUNTIME_ROOT:"=%"
) else if exist "%SCRIPT_DIR%\..\dashboard-runtime\screen_snapshot.csv" (
  set "STOCK_LOOKUP_BACKEND_DIR=%SCRIPT_DIR%\..\dashboard-runtime"
) else if exist "%SCRIPT_DIR%\..\..\dashboard-runtime\screen_snapshot.csv" (
  set "STOCK_LOOKUP_BACKEND_DIR=%SCRIPT_DIR%\..\..\dashboard-runtime"
) else (
  set "STOCK_LOOKUP_BACKEND_DIR=%SCRIPT_DIR%"
)

REM 3. Resolve WEB_DIR (strip existing quotes if present)
if defined STOCK_LOOKUP_WEB_DIR (
  set "STOCK_LOOKUP_WEB_DIR=%STOCK_LOOKUP_WEB_DIR:"=%"
) else (
  set "STOCK_LOOKUP_WEB_DIR=%SCRIPT_DIR%"
)

REM 4. Resolve PRODUCER_DIR (strip existing quotes if present)
if defined STOCK_LOOKUP_PRODUCER_DIR (
  set "STOCK_LOOKUP_PRODUCER_DIR=%STOCK_LOOKUP_PRODUCER_DIR:"=%"
) else if exist "%SCRIPT_DIR%\..\stock-core-private\tools\publish_release.py" (
  set "STOCK_LOOKUP_PRODUCER_DIR=%SCRIPT_DIR%\..\stock-core-private"
) else if exist "%SCRIPT_DIR%\..\..\stock-core-private\tools\publish_release.py" (
  set "STOCK_LOOKUP_PRODUCER_DIR=%SCRIPT_DIR%\..\..\stock-core-private"
) else (
  set "STOCK_LOOKUP_PRODUCER_DIR=%SCRIPT_DIR%"
)

REM Print resolved environment in safe brackets
echo ============================================================
echo STOCK LOOK UP - BUILD / SYNC / PUBLISH
echo Python   : [%STOCK_LOOKUP_PYTHON%]
echo Backend  : [%STOCK_LOOKUP_BACKEND_DIR%]
echo Web repo : [%STOCK_LOOKUP_WEB_DIR%]
echo Producer : [%STOCK_LOOKUP_PRODUCER_DIR%]
echo Mode     : [%*]
echo ============================================================

REM 5. Fail closed if Backend == Web
if /I "%STOCK_LOOKUP_BACKEND_DIR%"=="%STOCK_LOOKUP_WEB_DIR%" (
  echo [ERROR] STOCK_LOOKUP_BACKEND_DIR resolves to WEB_DIR ^([%STOCK_LOOKUP_WEB_DIR%]^). Cannot publish backend artifacts from web root to itself.
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

REM 6. Parse release groups (--whole-market, --trusted-ai, --all) and --live
set "DO_TRUSTED_AI=0"
set "DO_WHOLE_MARKET=0"
set "GROUP_SPECIFIED=0"
set "IS_LIVE=0"
set "PYTHON_ARGS="

for %%A in (%*) do (
  if /I "%%~A"=="--whole-market" (
    set "DO_WHOLE_MARKET=1"
    set "GROUP_SPECIFIED=1"
  ) else if /I "%%~A"=="--trusted-ai" (
    set "DO_TRUSTED_AI=1"
    set "GROUP_SPECIFIED=1"
  ) else if /I "%%~A"=="--all" (
    set "DO_WHOLE_MARKET=1"
    set "DO_TRUSTED_AI=1"
    set "GROUP_SPECIFIED=1"
  ) else if /I "%%~A"=="--live" (
    set "IS_LIVE=1"
    set "PYTHON_ARGS=!PYTHON_ARGS! --live"
  )
)

if "%GROUP_SPECIFIED%"=="0" (
  set "DO_WHOLE_MARKET=1"
  set "DO_TRUSTED_AI=1"
)

cd /d "%STOCK_LOOKUP_WEB_DIR%"

git rev-parse --show-toplevel >nul 2>&1
if errorlevel 1 exit /b 1

REM 7. Execute Trusted-AI Release (if requested)
if "%DO_TRUSTED_AI%"=="1" (
  if not exist "%STOCK_LOOKUP_PRODUCER_DIR%\tools\publish_release.py" (
    echo [ERROR] Missing trusted-subset release publisher: %STOCK_LOOKUP_PRODUCER_DIR%\tools\publish_release.py
    echo [ERROR] Set STOCK_LOOKUP_PRODUCER_DIR to the stock-core-private checkout.
    exit /b 1
  )
  echo ============================================================
  echo TRUSTED-SUBSET RELEASE (publish_release.py)
  echo ============================================================
  "%STOCK_LOOKUP_PYTHON%" "%STOCK_LOOKUP_PRODUCER_DIR%\tools\publish_release.py" --source "%STOCK_LOOKUP_BACKEND_DIR%" --destination "%STOCK_LOOKUP_WEB_DIR%"%PYTHON_ARGS%
  if errorlevel 1 (
    echo [ERROR] Trusted-subset release publisher failed. Aborting publish.
    exit /b 1
  )
)

REM 8. Execute Whole-Market Release (if requested)
if "%DO_WHOLE_MARKET%"=="1" (
  echo ============================================================
  echo FRONTEND BUILD (build_frontend.bat)
  echo ============================================================
  if "%IS_LIVE%"=="1" (
    call "%STOCK_LOOKUP_WEB_DIR%\build_frontend.bat" --live
  ) else (
    call "%STOCK_LOOKUP_WEB_DIR%\build_frontend.bat"
  )
  if errorlevel 1 (
    echo [ERROR] Frontend build failed with exit code %errorlevel%. Aborting publish.
    exit /b 1
  )

  echo ============================================================
  echo WHOLE-MARKET DASHBOARD RELEASE (publish_dashboard.py)
  echo ============================================================
  "%STOCK_LOOKUP_PYTHON%" "%STOCK_LOOKUP_WEB_DIR%\publish_dashboard.py"%PYTHON_ARGS%
  if errorlevel 1 (
    echo [ERROR] Whole-market publisher failed with exit code %errorlevel%.
    exit /b 1
  )
)

echo [OK] Publisher completed successfully. Without --live, no disk mutation or git stage/commit/push occurred.
exit /b 0
