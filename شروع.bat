@echo off
chcp 1256 >nul
title «›—«ﬂ«·« - —«Â«‰œ«“Ì
echo ============================================
echo    —«Â«‰œ«“Ì ”Ì” „ «›—«ﬂ«·«
echo ============================================
echo.

echo [1/4] »——”Ì «Ã—«Ì Docker...
docker info >nul 2>&1
if errorlevel 1 (
  echo    [Œÿ«] Docker Desktop œ— Õ«· «Ã—« ‰Ì” .
  echo    ·ÿ›« «» œ« Docker Desktop —« »«“ ﬂ‰Ìœ Ê ”Å” œÊ»«—Â  ·«‘ ﬂ‰Ìœ.
  echo.
  pause
  exit /b 1
)
echo    Docker ›⁄«· «” .
echo.

echo [2/4] —«Â«‰œ«“Ì ﬂ«‰ Ì‰—Â« (docker compose up -d)...
docker compose up -d
echo.

echo [3/4] —«Â«‰œ«“Ì ngrok —ÊÌ œ«„‰Â À«» ...
start "ngrok - «›—«ﬂ«·«" ngrok.cmd http --url=https://multidisciplinary-jeri-physiognomically.ngrok-free.dev 8002
echo    ngrok œ— Ìﬂ Å‰Ã—Â ÃœÌœ «Ã—« ‘œ.
echo.

echo [4/4] ç‰œ ·ÕŸÂ ’»— ﬂ‰Ìœ  « ”—ÊÌ”Â« ¬„«œÂ ‘Ê‰œ...
timeout /t 8 /nobreak >nul
echo.

echo »«“ ﬂ—œ‰ Å‰· „œÌ—Ì  œ— „—Ê—ê—...
start "" http://localhost:3002
echo.

set "LANIP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /r /c:"IPv4.*192\.168\." /c:"IPv4.*10\."') do if not defined LANIP set "LANIP=%%a"
set "LANIP=%LANIP: =%"
if not defined LANIP set "LANIP=localhost"

echo ============================================
echo    ”Ì” „ ¬„«œÂ «” !
echo.
echo    ¬œ—” —ÊÌ «Ì‰ ﬂ«„ÅÌÊ —:  http://localhost:3002
echo    ¬œ—” »—«Ì ‘»ﬂÂ/Ê«Ì›«Ì:  http://%LANIP%:3002
echo ============================================
echo.
pause
