@echo off
rem Sets up Animesito inside WSL: Python, frontend, .env files, database and models.
rem Safe to run again; interrupted downloads resume. Options:
rem   Instalar.bat -Models base,anime        (or all / none; default: asks)
rem   Instalar.bat -ComfyDir "D:\ComfyUI"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\animesito.ps1" install %*
pause
