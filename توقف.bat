@echo off
chcp 1256 >nul
title «›—«ﬂ«·« -  Êﬁ›
echo ============================================
echo     Êﬁ› ”Ì” „ «›—«ﬂ«·«
echo ============================================
echo.

echo [1/2] „ Êﬁ› ﬂ—œ‰ ﬂ«‰ Ì‰—Â« (docker compose stop)...
docker compose stop
echo.

echo [2/2] »” ‰ ngrok...
taskkill /IM ngrok.exe /F >nul 2>&1
if errorlevel 1 (
  echo    ngrok œ— Õ«· «Ã—« ‰»Êœ.
) else (
  echo    ngrok »” Â ‘œ.
)
echo.

echo ”Ì” „ „ Êﬁ› ‘œ.
echo.
pause
