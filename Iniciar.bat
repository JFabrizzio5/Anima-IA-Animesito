@echo off
rem Starts ComfyUI and Ollama if they are down, then Animesito, and opens http://127.0.0.1:7799
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\animesito.ps1" start %*
if errorlevel 1 pause
