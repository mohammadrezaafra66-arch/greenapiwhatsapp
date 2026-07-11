@echo off
chcp 65001 >nul
rem Prefer Windows Terminal (proper Persian font fallback); fall back to powershell.
where wt.exe >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dpn0.ps1"
) else (
  wt.exe powershell -NoProfile -ExecutionPolicy Bypass -File "%~dpn0.ps1"
)
