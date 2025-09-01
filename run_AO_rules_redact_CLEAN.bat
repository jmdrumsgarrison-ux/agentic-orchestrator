@echo off
setlocal ENABLEDELAYEDEXPANSION
if not exist "Logs" mkdir "Logs"
for /f "tokens=1-5 delims=/:. " %%a in ("%date% %time%") do set TS=%%a%%b%%c-%%d%%e
set "LOG=Logs\run-RULES-REDACT-CLEAN-SAFE-!TS!.txt"

echo ===== AO Versioner (Rules + Redaction + CLEAN) [PREFILLED + DROPS + SAFE CLEAN] ===== > "%LOG%"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File ".\build_AO_rules_redact.ps1" -CleanRemote 1 1>>"%LOG%" 2>&1
echo ExitCode: !ERRORLEVEL! >> "%LOG%"
echo Finished. Log: %LOG%
pause
