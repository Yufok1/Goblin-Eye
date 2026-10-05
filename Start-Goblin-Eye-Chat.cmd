@echo off
setlocal
cd /d "%~dp0wow-ai"
where node >nul 2>nul
if errorlevel 1 (
  echo Install Node.js 22.2 or newer for optional in-game chat.
  pause
  exit /b 1
)
if not exist "bridge\config.json" (
  echo Run Setup-WoWAI.cmd from the Goblin Eye folder first.
  pause
  exit /b 1
)
echo Goblin Eye optional in-game chat bridge. Keep this window open.
node bridge\supervisor.js --project "%~dp0Goblin-Eye-Chat"
if errorlevel 1 pause
