@echo off
chcp 1256 >nul
title «›—«ﬂ«·« - Ê÷⁄Ì 
echo ============================================
echo    Ê÷⁄Ì  ”Ì” „ «›—«ﬂ«·«
echo ============================================
echo.

echo Ê÷⁄Ì  ﬂ«‰ Ì‰—Â«:
echo --------------------------------------------
docker compose ps
echo.

echo »——”Ì ”·«„  ”—ÊÌ” (Backend):
echo --------------------------------------------
curl -s http://localhost:8002/health/detailed
echo.
echo.
pause
