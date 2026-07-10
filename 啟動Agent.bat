@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting AI Browser Agent chat window...
echo (a browser window will open; type tasks in the chat window)
".venv\Scripts\python.exe" tools\agent_chat.py
if errorlevel 1 (
  echo.
  echo Something went wrong. Make sure setup is done:
  echo   python -m venv .venv
  echo   .venv\Scripts\python -m pip install -e ".[dev,browser]"
  echo   .venv\Scripts\python -m playwright install chromium
  echo   npm i -g @openai/codex  ^&^&  codex login
  pause
)
