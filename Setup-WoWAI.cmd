@echo off
setlocal
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Install Node.js 22.2 or newer for optional in-game chat.
  pause
  exit /b 1
)
node "%~dp0Setup-WoWAI.js" %*
if errorlevel 1 (
  pause
  exit /b 1
)
if "%~1"=="" pause
