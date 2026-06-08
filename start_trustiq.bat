@echo off
REM ====================================================================
REM  TrustIQ - Identity Trust Framework
REM  Starts the FastAPI backend + static frontend and opens Chrome.
REM  Uses the shared virtual environment at ..\venv
REM ====================================================================

setlocal
set ROOT=%~dp0
set VENV=%ROOT%venv\Scripts\python.exe

echo ========================================
echo   TrustIQ - Identity Trust Platform
echo ========================================
echo.

if not exist "%VENV%" (
  echo ERROR: virtual environment not found at:
  echo   %VENV%
  echo Create it first:  python -m venv venv  ^&^&  venv\Scripts\pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

REM --- Backend (port 8000) ---
echo [1/3] Starting backend API on http://localhost:8000 ...
start "TrustIQ Backend" cmd /k "cd /d "%ROOT%backend" && "%VENV%" -m uvicorn main:app --host 0.0.0.0 --port 8000"
timeout /t 5 >nul

REM --- Frontend (port 3000) ---
echo [2/4] Starting SOC dashboard on http://localhost:3000 ...
start "TrustIQ Frontend" cmd /k "cd /d "%ROOT%frontend" && "%VENV%" -m http.server 3000"
timeout /t 3 >nul

REM --- Bank of Baroda simulator (port 9100) ---
echo [3/4] Starting Bank of Baroda simulator on http://localhost:9100 ...
start "BoB Simulator" cmd /k "cd /d "%ROOT%bank_simulator" && "%VENV%" -m uvicorn server:app --host 0.0.0.0 --port 9100"
timeout /t 4 >nul

REM --- Open Chrome ---
echo [4/4] Opening TrustIQ in Chrome ...
start chrome "http://localhost:9100" "http://localhost:3000" "http://localhost:8000/docs"

echo.
echo TrustIQ is running.
echo   Bank simulator : http://localhost:9100   (act as 10 accounts)
echo   SOC dashboard  : http://localhost:3000   (watch fraud alerts)
echo   API docs       : http://localhost:8000/docs
echo.
echo Close the spawned terminal windows to stop the services.
pause
endlocal
