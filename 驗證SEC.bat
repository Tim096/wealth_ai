@echo off
cd /d "%~dp0"
echo Starting tools/sec_viewer.py ...
".venv\Scripts\python.exe" tools\sec_viewer.py
if errorlevel 1 (
  echo.
  echo Setup first if this failed:
  echo   python -m venv .venv
  echo   .venv\Scripts\python -m pip install -e ".[dev,sec,browser]"
  echo   .venv\Scripts\python -m playwright install chromium
  echo   npm i -g @openai/codex   then   codex login
  pause
)
