@echo off
chcp 1256 >nul
title «›—«ﬂ«·« - ¬œ—” «‘ —«ﬂ
echo ============================================
echo    ¬œ—” «‘ —«ﬂ ê–«—Ì œ— ‘»ﬂÂ „Õ·Ì
echo ============================================
echo.

echo œ— Õ«· Ì«› ‰ ¬œ—” ¬ÌÅÌ «Ì‰ œ” ê«Â...
set "LANIP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /r /c:"IPv4.*192\.168\." /c:"IPv4.*10\."') do if not defined LANIP set "LANIP=%%a"
set "LANIP=%LANIP: =%"
if not defined LANIP set "LANIP=localhost"
echo.

echo ============================================
echo    «Ì‰ ¬œ—” —« »—«Ì «›—«œ œÌê— »›—” Ìœ:
echo.
echo         http://%LANIP%:3002
echo.
echo    (»«Ìœ »Â Â„«‰ ‘»ﬂÂ/Ê«Ì›«Ì „ ’· »«‘‰œ)
echo ============================================
echo.
pause
