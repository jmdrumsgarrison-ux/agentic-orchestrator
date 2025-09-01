@echo off
setlocal enabledelayedexpansion

REM ====== Paths ======
set ROOT=G:\HuggingFace\HF_Agent_Package
set LOGS=%ROOT%\Logs
set VENV=%ROOT%\env

if not exist "%LOGS%" mkdir "%LOGS%"
set LOGFILE=%LOGS%\deploy_%DATE:~10,4%-%DATE:~4,2%-%DATE:~7,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%.log
set LOGFILE=%LOGFILE: =0%

echo [DEPLOY] Starting > "%LOGFILE%"
call "%VENV%\Scripts\activate.bat"
cd /d "%ROOT%\app"

REM Run the app on port 7860
python app.py >> "%LOGFILE%" 2>&1
echo [DEPLOY] App exited with code %ERRORLEVEL% >> "%LOGFILE%"
echo Deploy complete. See log: "%LOGFILE%"
exit /b 0
