@echo off
rem Sets up Animesito inside WSL: Python, frontend, .env files, database, model report.
rem Safe to run again. Optional: Instalar.bat -ComfyDir "D:\ComfyUI"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\animesito.ps1" install %*
pause
