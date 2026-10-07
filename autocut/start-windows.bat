@echo off
chcp 65001 >nul
title AutoCut
cd /d "%~dp0"

echo ==========================================
echo   AutoCut - 자동 컷편집 / 자막 / CapCut
echo ==========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [필요] Python 이 설치되어 있지 않습니다.
  echo   https://www.python.org/downloads/ 에서 설치하세요.
  echo   설치 첫 화면에서 "Add python.exe to PATH" 를 꼭 체크하세요.
  echo.
  pause
  exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [필요] FFmpeg 가 설치되어 있지 않습니다.
  echo   명령 프롬프트에서 다음을 실행한 뒤, 이 창을 닫고 다시 실행하세요:
  echo     winget install --id Gyan.FFmpeg -e
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [준비] 처음 실행이라 필요한 프로그램을 설치합니다. 몇 분 걸릴 수 있어요...
  python -m venv .venv
  if errorlevel 1 goto :fail
)

rem requirements.txt 가 바뀌었으면(업데이트) 다시 설치
fc /b requirements.txt ".venv\installed-requirements.txt" >nul 2>nul
if errorlevel 1 (
  echo [준비] 필요한 프로그램을 설치/업데이트합니다. 처음엔 AI 모델 패키지 때문에 10분 이상 걸릴 수 있어요...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :fail
  copy /y requirements.txt ".venv\installed-requirements.txt" >nul
)

echo.
echo [실행] 잠시 후 브라우저가 열립니다. 이 창을 닫으면 프로그램이 종료됩니다.
echo.
".venv\Scripts\python.exe" -m autocut.server
pause
exit /b 0

:fail
echo.
echo [오류] 설치 중 문제가 생겼습니다. 위의 메시지를 캡처해서 알려 주세요.
pause
exit /b 1
