@echo off
setlocal

REM ============================================================
REM VNSTOCK - build_frontend.bat
REM Build Tailwind CSS offline with the Tailwind standalone CLI (no Node/npm,
REM no Vite/PostCSS project) - replaces the Tailwind Play CDN that used to run
REM JIT compilation in the browser at production.
REM
REM Pinned version: Tailwind CLI standalone v3.4.19 (NOT "latest" - Tailwind
REM   v4 removed "corePlugins" entirely, and this site depends on
REM   corePlugins:{preflight:false} so Tailwind does not clobber Bootstrap,
REM   which serves the actual data content. v3.4.19 is the last v3 release
REM   that shipped a standalone CLI binary - verified via GitHub releases,
REM   no v3.4.20 or v3.5.x exists).
REM
REM Manual download steps (only needed to set up a new machine):
REM   1. Download:
REM      https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.19/tailwindcss-windows-x64.exe
REM   2. Verify checksum against:
REM      https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.19/sha256sums.txt
REM      Expected SHA256: a15158c4c5e0e7a75f7229bfe4986fe7710d2edc468b6f96c8981f78ab211347
REM   3. Rename to tailwindcss.exe and place at tools\tailwind\tailwindcss.exe
REM      (tools\ is gitignored - the executable itself is never committed).
REM
REM Source of truth (committed):
REM   tailwind.config.js          - content globs + theme.extend + corePlugins,
REM                                  values unchanged from the old inline Play
REM                                  CDN config.
REM   assets/css/tailwind.src.css - the 3 @tailwind base/components/utilities
REM                                  directives.
REM Build output (committed, pre-built artifact):
REM   assets/css/tailwind.generated.css
REM
REM sync_and_publish.bat calls this script BEFORE publishing; if the build
REM fails, publishing must stop (non-zero exit) instead of shipping a
REM stale/broken CSS file.
REM ============================================================

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "TAILWIND_EXE=%SCRIPT_DIR%\tools\tailwind\tailwindcss.exe"
set "TAILWIND_CONFIG=%SCRIPT_DIR%\tailwind.config.js"
set "TAILWIND_INPUT=%SCRIPT_DIR%\assets\css\tailwind.src.css"
set "TAILWIND_OUTPUT=%SCRIPT_DIR%\assets\css\tailwind.generated.css"

echo ============================================================
echo BUILD FRONTEND - Tailwind CSS (standalone CLI v3.4.19)
echo ============================================================

if not exist "%TAILWIND_EXE%" (
  echo [ERROR] Tailwind CLI not found at: %TAILWIND_EXE%
  echo [ERROR] Download it first:
  echo   https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.19/tailwindcss-windows-x64.exe
  echo   Rename to tailwindcss.exe and place it under tools\tailwind\
  echo   Expected SHA256: a15158c4c5e0e7a75f7229bfe4986fe7710d2edc468b6f96c8981f78ab211347
  exit /b 1
)

if not exist "%TAILWIND_CONFIG%" (
  echo [ERROR] Missing %TAILWIND_CONFIG%
  exit /b 1
)

if not exist "%TAILWIND_INPUT%" (
  echo [ERROR] Missing %TAILWIND_INPUT%
  exit /b 1
)

echo Building: %TAILWIND_INPUT% -^> %TAILWIND_OUTPUT%
"%TAILWIND_EXE%" -i "%TAILWIND_INPUT%" -o "%TAILWIND_OUTPUT%" -c "%TAILWIND_CONFIG%" --minify
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo [ERROR] Tailwind build failed with exit code %RC%.
  exit /b %RC%
)

if not exist "%TAILWIND_OUTPUT%" (
  echo [ERROR] Build reported success but output file is missing.
  exit /b 1
)

echo [OK] Frontend build complete: %TAILWIND_OUTPUT%
exit /b 0
