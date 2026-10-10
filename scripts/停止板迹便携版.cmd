@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0portable_stop.ps1"
if errorlevel 1 pause
