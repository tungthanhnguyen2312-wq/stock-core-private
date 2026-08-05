@echo off
setlocal

echo ============================================================
echo [DEPRECATED] sync_and_publish.bat is retired from production control plane.
echo Please use the authoritative Python release orchestrator:
echo   python tools\release_orchestrator.py whole-market [flags]
echo   python tools\release_orchestrator.py trusted-ai [flags]
echo   python tools\release_orchestrator.py all [flags]
echo ============================================================

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

if defined STOCK_LOOKUP_PYTHON (
  set "PYTHON_EXE=%STOCK_LOOKUP_PYTHON:"=%"
) else (
  set "PYTHON_EXE=python"
)

if exist "%SCRIPT_DIR%\tools\release_orchestrator.py" (
  set "ORCHESTRATOR=%SCRIPT_DIR%\tools\release_orchestrator.py"
) else if exist "%SCRIPT_DIR%\..\stock-core-private\tools\release_orchestrator.py" (
  set "ORCHESTRATOR=%SCRIPT_DIR%\..\stock-core-private\tools\release_orchestrator.py"
) else (
  echo [ERROR] Cannot locate release_orchestrator.py
  exit /b 1
)

"%PYTHON_EXE%" "%ORCHESTRATOR%" %*
exit /b %errorlevel%
