@echo off
REM Compatibility wrapper. The safe publisher lives in sync_and_publish.bat.
call "%~dp0sync_and_publish.bat" %*
exit /b %errorlevel%
