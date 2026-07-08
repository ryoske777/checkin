@echo off
chcp 65001 >nul
REM ============================================================
REM  YT Mini 단일 exe 빌드 스크립트
REM  - 파이썬이 설치된 PC 에서 이 파일을 더블클릭하면
REM    dist\YTMini.exe 가 생성된다.
REM  - 생성된 YTMini.exe 는 파이썬이 없는 PC 에서도 단독 실행되며
REM    콘솔(cmd) 창 없이 프로그램 창만 뜬다.
REM  - 실행 대상 PC 에는 WebView2 런타임만 있으면 됨
REM    (Windows 10/11 은 대부분 기본 탑재)
REM ============================================================

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo PyInstaller 설치 중...
    pip install pyinstaller || goto :fail
)

pip show pywebview >nul 2>nul
if errorlevel 1 (
    echo pywebview 설치 중...
    pip install pywebview || goto :fail
)

echo.
echo YTMini.exe 빌드 시작...
pyinstaller --onefile --noconsole --clean --name YTMini ^
  --hidden-import webview.platforms.winforms ^
  --hidden-import webview.platforms.edgechromium ^
  --collect-all webview ^
  youtube_mini.py
if errorlevel 1 goto :fail

echo.
echo ============================================
echo  빌드 완료!  실행 파일: dist\YTMini.exe
echo  이 파일 하나만 복사해서 아무 PC 에서나 실행하면 됩니다.
echo ============================================
pause
exit /b 0

:fail
echo.
echo 빌드에 실패했습니다. 위 오류 메시지를 확인하세요.
pause
exit /b 1
