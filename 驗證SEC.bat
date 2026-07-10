@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting SEC 10-K Viewer...
".venv\Scripts\python.exe" tools\sec_viewer.py
if errorlevel 1 (
  echo.
  echo Setup first if this failed:
  echo   .venv\Scripts\python -m pip install -e ".[dev,sec]"
  pause
)
