@echo off
chcp 1256 >nul
title ÇÝÑÇßÇáÇ - ÔÊíÈÇäíÑí
echo ============================================
echo    ÔÊíÈÇäíÑí ÇÒ ÇíÇå ÏÇÏå
echo ============================================
echo.

if not exist "%~dp0backups" mkdir "%~dp0backups"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%I"
set "OUTFILE=%~dp0backups\whatsapp_sender_%STAMP%.sql"

echo ÝÇíá ÎÑæÌí:
echo    %OUTFILE%
echo.

echo ÏÑ ÍÇá Êåíå ÔÊíÈÇä (docker exec pg_dump)...
docker exec claudegreenapi-db-1 pg_dump -U afrakala whatsapp_sender > "%OUTFILE%"
if errorlevel 1 (
  echo    [ÎØÇ] ÔÊíÈÇäíÑí äÇãæÝÞ ÈæÏ.
  echo    ãØãÆä ÔæíÏ ßÇäÊíäÑ ÇíÇå ÏÇÏå ÏÑ ÍÇá ÇÌÑÇÓÊ.
) else (
  echo    ÔÊíÈÇä ÈÇ ãæÝÞíÊ ÐÎíÑå ÔÏ.
)
echo.
pause
