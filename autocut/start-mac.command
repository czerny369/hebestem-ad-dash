#!/bin/bash
# AutoCut 실행 (macOS) — Finder 에서 더블클릭
cd "$(dirname "$0")" || exit 1

echo "=========================================="
echo "  AutoCut - 자동 컷편집 / 자막 / CapCut"
echo "=========================================="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "[필요] Python 이 없습니다. https://www.python.org/downloads/ 에서 설치 후 다시 실행하세요."
  read -r -p "엔터를 누르면 닫힙니다"; exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[필요] FFmpeg 가 없습니다. 터미널에서 'brew install ffmpeg' 실행 후 다시 실행하세요."
  echo "       (Homebrew 가 없다면 https://brew.sh 먼저 설치)"
  read -r -p "엔터를 누르면 닫힙니다"; exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "[준비] 처음 실행이라 필요한 프로그램을 설치합니다. 몇 분 걸릴 수 있어요..."
  python3 -m venv .venv || { read -r -p "설치 실패. 엔터를 누르면 닫힙니다"; exit 1; }
fi
if [ ! -f .venv/installed.txt ]; then
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r requirements.txt || { read -r -p "설치 실패. 엔터를 누르면 닫힙니다"; exit 1; }
  echo ok > .venv/installed.txt
fi

echo
echo "[실행] 잠시 후 브라우저가 열립니다. 이 창을 닫으면 프로그램이 종료됩니다."
echo
.venv/bin/python -m autocut.server
