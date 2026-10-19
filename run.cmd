@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 verify_package.py
  if errorlevel 1 goto FAILED
  py -3 qa_main.py --app "%~dp0app" --cases all
) else (
  where python >nul 2>nul
  if errorlevel 1 goto PYTHON_MISSING
  python verify_package.py
  if errorlevel 1 goto FAILED
  python qa_main.py --app "%~dp0app" --cases all
)
set "RC=%ERRORLEVEL%"
echo.
echo [NOX] Exit code: %RC%
echo [NOX] Check reports folder for REPORT_打开我.md and report.json.
pause
exit /b %RC%
:PYTHON_MISSING
echo [NOX] Python 3 is required; nothing was changed.
goto FAILED
:FAILED
echo [NOX] Preflight blocked. No QA browser tasks started.
pause
exit /b 2
