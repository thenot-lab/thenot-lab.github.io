@echo off
REM Eli OS Gateway launcher - Dominion home box (BRAYAI.bat convention).
REM Loads BrightValley\eli\.env, writes telemetry under brayai\logs,
REM serves the gateway on 127.0.0.1:8484 (health: GET /healthz).
setlocal

if "%BRIGHTVALLEY_ROOT%"=="" set "BRIGHTVALLEY_ROOT=C:\Users\Brayj\BrightValley"

if exist "%BRIGHTVALLEY_ROOT%\eli\.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%BRIGHTVALLEY_ROOT%\eli\.env") do set "%%A=%%B"
)

if "%ELI_TELEMETRY%"=="" (
  if not exist "%BRIGHTVALLEY_ROOT%\brayai\logs" mkdir "%BRIGHTVALLEY_ROOT%\brayai\logs"
  set "ELI_TELEMETRY=%BRIGHTVALLEY_ROOT%\brayai\logs\eli_os_telemetry.jsonl"
)

cd /d "%~dp0..\gateway"
python gateway.py serve --port 8484
