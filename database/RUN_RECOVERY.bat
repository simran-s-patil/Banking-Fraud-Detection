@echo off
title Banking Fraud DB Recovery
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy_real_db.ps1" -Port 3306
echo.
pause
