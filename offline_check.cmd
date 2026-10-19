@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 verify_package.py
  if errorlevel 1 goto FAILED
  py -3 qa_main.py --app "%~dp0app" --offline-only
) else (
  where python >nul 2>nul
  if errorlevel 1 goto FAILED
  python verify_package.py
  if errorlevel 1 goto FAILED
  python qa_main.py --app "%~dp0app" --offline-only
)
echo.
pause
exit /b %ERRORLEVEL%
:FAILED
echo [NOX] Preflight blocked.
pause
exit /b 2
