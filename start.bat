@echo off
REM Start FinanceTracker on Windows: create venv if needed, install deps, run app.
REM Run from project root: start.bat

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
  set PY=py
) else (
  set PY=python
)

if not exist "venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY% -m venv venv
)
if not exist "venv\Scripts\python.exe" (
  echo Failed to create venv. Install Python from https://www.python.org/downloads/
  exit /b 1
)

echo Installing/updating dependencies...
venv\Scripts\python.exe -m pip install -q -r requirements.txt

echo.
echo Starting FinanceTracker...
echo   Flask + Dash: http://127.0.0.1:5000
echo   Streamlit backtest: http://127.0.0.1:8501
echo   Streamlit filings: http://127.0.0.1:8502
echo.
venv\Scripts\python.exe main.py
pause
