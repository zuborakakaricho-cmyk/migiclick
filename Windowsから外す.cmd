@echo off
rem migiclick: uninstall (double-click)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\install.ps1" -Remove
pause
