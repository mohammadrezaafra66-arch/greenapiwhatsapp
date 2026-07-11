@echo off
chcp 1256 >nul
title «›—«ﬂ«·« - —Ì«” «— 
echo ============================================
echo    —Ì«” «—  ”—ÊÌ”Â«Ì «›—«ﬂ«·«
echo ============================================
echo.

echo œ— Õ«· —Ì«” «—  ”—ÊÌ”Â«...
docker compose restart backend worker-general worker-webhooks beat frontend
echo.

echo —Ì«” «—  ﬂ«„· ‘œ.
echo.
pause
