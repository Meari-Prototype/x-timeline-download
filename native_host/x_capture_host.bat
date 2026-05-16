@echo off
setlocal

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%~dp0x_capture_host.py"
) else (
  python "%~dp0x_capture_host.py"
)
