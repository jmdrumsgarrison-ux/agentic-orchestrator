@echo off
setlocal enabledelayedexpansion

REM ====== Paths ======
set ROOT=G:\HuggingFace\HF_Agent_Package
set LOGS=%ROOT%\Logs
set VENV=%ROOT%\env

if not exist "%LOGS%" mkdir "%LOGS%"
set LOGFILE=%LOGS%\setup_%DATE:~10,4%-%DATE:~4,2%-%DATE:~7,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%.log
set LOGFILE=%LOGFILE: =0%

echo [SETUP] Starting > "%LOGFILE%"

REM ====== Ensure ROOT exists and copy package ======
if not exist "%ROOT%" mkdir "%ROOT%"
xcopy /E /I /Y ".\app" "%ROOT%\app" >> "%LOGFILE%" 2>&1
copy /Y ".\requirements.txt" "%ROOT%\requirements.txt" >> "%LOGFILE%" 2>&1

REM ====== Create venv and install deps ======
if not exist "%VENV%" (
  echo [SETUP] Creating virtual environment... >> "%LOGFILE%"
  py -3 -m venv "%VENV%" >> "%LOGFILE%" 2>&1
)

call "%VENV%\Scripts\activate.bat"
python -m pip install --upgrade pip >> "%LOGFILE%" 2>&1
pip install -r "%ROOT%\requirements.txt" >> "%LOGFILE%" 2>&1

echo [SETUP] Done. >> "%LOGFILE%"
echo Setup complete. See log: "%LOGFILE%"
exit /b 0
