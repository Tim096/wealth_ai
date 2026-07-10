@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting AI Reliability Platform console...
echo Opening http://127.0.0.1:8800 in your browser.
".venv\Scripts\python.exe" tools\webapp.py
if errorlevel 1 (
  echo.
  echo Setup first if this failed:
  echo   .venv\Scripts\python -m pip install -e ".[dev,sec,browser]"
  echo   .venv\Scripts\python -m playwright install chromium
  pause
)
