@echo off
setlocal

REM ============================================================
REM  Build single-file YTMini.exe
REM  - Run this on a PC that has Python installed.
REM  - Output: dist\YTMini.exe  (standalone, no console window)
REM  - Target PC only needs the WebView2 runtime
REM    (preinstalled on most Windows 10/11 systems).
REM ============================================================

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
    if errorlevel 1 goto fail
)

pip show pywebview >nul 2>nul
if errorlevel 1 (
    echo Installing pywebview...
    pip install pywebview
    if errorlevel 1 goto fail
)

echo.
echo Building YTMini.exe ...
pyinstaller --onefile --noconsole --clean --name YTMini --hidden-import webview.platforms.winforms --hidden-import webview.platforms.edgechromium --collect-all webview youtube_mini.py
if errorlevel 1 goto fail

echo.
echo ============================================
echo  Done!  Output: dist\YTMini.exe
echo  Copy this single file to any PC and run it.
echo ============================================
pause
exit /b 0

:fail
echo.
echo Build FAILED. Check the error messages above.
pause
exit /b 1
