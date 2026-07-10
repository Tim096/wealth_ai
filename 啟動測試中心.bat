@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting Reliability Test Center at http://127.0.0.1:8765 ...
".venv\Scripts\python.exe" tools\test_center.py
if errorlevel 1 (
  echo.
  echo Setup first if this failed:
  echo   python -m venv .venv
  echo   .venv\Scripts\python -m pip install -e ".[dev,sec,browser]"
  echo   .venv\Scripts\python -m playwright install chromium
  echo   npm i -g @openai/codex  ^&^&  codex login   (Agent Mode 用 Codex)
  pause
)
