@echo off
setlocal

REM ============================================================
REM  Build single-file YTMini.exe
REM  - Run this on a PC that has Python installed.
REM  - Output: dist\YTMini.exe  (standalone, no console window)
REM  - Target PC only needs the WebView2 runtime
REM    (preinstalled on most Windows 10/11 systems).
REM  - Uses "python -m ..." so it also works with Microsoft
REM    Store Python, whose Scripts dir is not on PATH.
REM ============================================================

python -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller
    if errorlevel 1 goto fail
)

python -m pip show pywebview >nul 2>nul
if errorlevel 1 (
    echo Installing pywebview...
    python -m pip install pywebview
    if errorlevel 1 goto fail
)

set ICON_OPTS=
if exist icon.ico (
    set ICON_OPTS=--icon icon.ico --add-data "icon.ico;."
) else (
    echo NOTE: icon.ico not found - building with default icon.
    echo       Copy icon.ico next to this file to use the custom icon.
)

echo.
echo Building YTMini.exe ...
python -m PyInstaller --onefile --noconsole --clean --name YTMini %ICON_OPTS% --hidden-import webview.platforms.winforms --hidden-import webview.platforms.edgechromium --collect-all webview youtube_mini.py
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
