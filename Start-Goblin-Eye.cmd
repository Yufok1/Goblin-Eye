@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-Goblin-Eye.ps1"
if errorlevel 1 (
    echo.
    echo Goblin Eye could not start. Read the error above and START-HERE.md.
    pause
)
