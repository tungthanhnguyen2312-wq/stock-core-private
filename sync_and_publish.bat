@echo off
setlocal
REM Thin wrapper: Producer orchestrator + canonical web path only.
REM Launching a copy of this file from a legacy Dashboard clone must fail
REM because this wrapper pins both the orchestrator and the web checkout.

set "PRODUCER=%~dp0"
if "%PRODUCER:~-1%"=="\" set "PRODUCER=%PRODUCER:~0,-1%"
set "ORCHESTRATOR=%PRODUCER%\tools\release_orchestrator.py"
set "CANONICAL_WEB=C:\Projects\StockLookup\market-dashboard"

echo ============================================================
echo STOCK LOOKUP - thin wrapper to Producer release_orchestrator.py
echo Producer : %PRODUCER%
echo Web      : %CANONICAL_WEB%
echo ============================================================

if /I not "%PRODUCER%"=="C:\Projects\StockLookup\stock-core-private" (
  echo [ERROR] REFUSED: sync_and_publish.bat is not running from C:\Projects\StockLookup\stock-core-private
  echo Launching from a legacy Dashboard clone is forbidden.
  exit /b 1
)
if not exist "%ORCHESTRATOR%" (
  echo [ERROR] Cannot locate %ORCHESTRATOR%
  exit /b 1
)
if not exist "%CANONICAL_WEB%\.git" (
  echo [ERROR] Canonical Dashboard checkout missing: %CANONICAL_WEB%
  exit /b 1
)

if defined STOCK_LOOKUP_PYTHON (
  set "PYTHON_EXE=%STOCK_LOOKUP_PYTHON:"=%"
) else (
  set "PYTHON_EXE=python"
)

set "STOCK_LOOKUP_WEB_DIR=%CANONICAL_WEB%"
set "STOCK_LOOKUP_BACKEND_DIR=C:\Projects\StockLookup\dashboard-runtime"
"%PYTHON_EXE%" "%ORCHESTRATOR%" %*
exit /b %errorlevel%
