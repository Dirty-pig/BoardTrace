@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0portable_launch.ps1"
if errorlevel 1 pause
