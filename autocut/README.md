# autocut — 자동 컷편집 + 자동 자막 → CapCut 드래프트

영상과 자막 스크립트만 넣으면

1. **버벅임/말 반복/재촬영 테이크/군말("음", "어")** 을 찾아 잘라내고
2. **너무 긴 멈춤·말 없는 긴 동작** 을 짧게 줄이고
3. **스크립트 문장을 실제 말하는 타이밍에 맞춰 자막** 으로 깔아서
4. [pyCapCut](https://github.com/GuanYixuan/pyCapCut) 으로 **CapCut 드래프트(프로젝트)** 를 만들어 줍니다.

CapCut 을 열면 편집된 프로젝트가 목록에 나타나고, 컷/자막을 그대로 이어서 수정할 수 있습니다.

## 동작 원리

```
영상 ──► Whisper 음성인식(단어별 시간) ──┐
                                        ├─► 글자 단위 정렬 ─► 스크립트에 없는 말 = 버벅임 → 제거
스크립트 ───────────────────────────────┘                  └► 문장별 시작/끝 시간 = 자막 타이밍
                                         ▼
                 남길 구간 계산 (긴 공백은 pause-keep 만 남김)
                                         ▼
               pyCapCut: 영상 조각 이어붙이기 + 자막 트랙 → CapCut 드래프트
```

- 음성인식 결과와 스크립트를 글자 단위로 정렬(affine-gap 전역 정렬)합니다. 스크립트에 대응되지 않는 말은
  버벅임·반복·군말로 보고 잘라냅니다.
- 같은 문장을 여러 번 말했다면(재촬영) **마지막 테이크**를 남깁니다.
- 인식 오타가 조금 있어도 정렬이 흡수하므로 괜찮습니다.

## 설치

필요한 것: Python 3.9+, [FFmpeg](https://ffmpeg.org/download.html) (`ffmpeg`, `ffprobe` 가 PATH 에 있어야 함), CapCut 데스크톱

```bash
cd autocut
pip install -r requirements.txt
```

처음 실행할 때 Whisper 모델이 자동으로 다운로드됩니다 (`small` 약 500MB).

## 웹 화면으로 쓰기 (추천)

### 처음 한 번 준비

1. **Python** 설치: https://www.python.org/downloads/
   (Windows 는 설치 첫 화면에서 **"Add python.exe to PATH"** 체크)
2. **FFmpeg** 설치
   - Windows: 명령 프롬프트에서 `winget install --id Gyan.FFmpeg -e`
   - Mac: 터미널에서 `brew install ffmpeg`
3. 이 저장소를 내려받기: GitHub 에서 **Code → Download ZIP** 후 압축 풀기

### 실행

`autocut` 폴더 안의 파일을 **더블클릭**하세요.

- Windows: `start-windows.bat`
- Mac: `start-mac.command` (처음에 "확인되지 않은 개발자" 경고가 뜨면 **우클릭 → 열기**)

처음 실행할 때는 필요한 프로그램을 자동으로 설치하느라 몇 분 걸립니다.
그다음부터는 바로 브라우저에 화면(http://127.0.0.1:8765)이 열립니다. 검은 창을 닫으면 종료됩니다.

> 개발자용: `pip install -r requirements.txt && python -m autocut.server` 로도 실행됩니다.
> 화면 코드를 수정했다면 `cd frontend && npm install && npm run build` 로 다시 빌드하세요.

화면에서 할 수 있는 것:

- 영상 끌어다 놓기 → 스크립트 붙여넣기(또는 .txt/.srt 불러오기) → **분석 시작**
- **편집본 미리보기**: 잘린 구간을 건너뛰며 재생하고, 자막도 겹쳐서 보여 줍니다 (렌더링 없이 바로)
- **타임라인**: 남긴 구간 / 잘린 구간 / 제거된 말(버벅임) 위치 표시, 클릭으로 이동
- **자막 편집**: 문구·시간 수정, 합치기, 삭제
- **자막 스타일**: 크기·위치·색·테두리·굵기 (미리보기 반영)
- 컷 기준을 바꿔 **다시 분석** (음성 인식 결과는 저장돼서 빠름)
- **CapCut 드래프트 만들기**, SRT 받기

업로드한 영상은 `~/AutoCut/projects/` 에 보관됩니다 (환경변수 `AUTOCUT_HOME` 으로 변경 가능).
CapCut 드래프트가 이 파일을 참조하므로 **CapCut 작업이 끝날 때까지 지우지 마세요.**

> 화면 코드를 고치면서 개발할 때는 `python -m autocut.server --no-browser` 를 켜 둔 채
> `cd frontend && npm run dev` 로 http://localhost:5173 에 접속하면 됩니다 (/api 는 자동 프록시).

## 명령행으로 쓰기

스크립트는 `.txt`(한 줄 = 자막 하나) 또는 `.srt`(텍스트만 사용, 시간은 다시 계산) 입니다.

```text
안녕하세요 여러분
오늘은 제품을 소개해 드릴게요
이 제품은 정말 가볍고 튼튼합니다
감사합니다
```

```bash
python -m autocut 영상.mp4 스크립트.txt --name "제품소개_자동편집"
```

```
[1/4] 영상 정보: 1080x1920, 30.00fps, 74.2초
      스크립트: 자막 18개
[2/4] 음성 인식 중 (Whisper small)...
[3/4] 컷 편집: 74.2초 → 51.8초 (22.4초 제거, 구간 23개)
      제거된 말(버벅임/반복/스크립트 외): 음 오늘은 제 어 아 잠깐만 ...
      자막 18개 → 제품소개_자동편집.srt
[4/4] CapCut 드래프트 생성 완료: .../com.lveditor.draft/제품소개_자동편집
```

CapCut 을 열면 홈 화면에 `제품소개_자동편집` 프로젝트가 생깁니다 (안 보이면 CapCut 을 껐다 켜세요).

### CapCut 드래프트 폴더

기본 위치를 자동으로 찾습니다. 못 찾으면 `--drafts-dir` 로 지정하세요
(CapCut → 설정 → 드래프트 위치 에서 확인).

| OS | 기본 위치 |
|---|---|
| Windows | `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft` |
| macOS | `~/Movies/CapCut/User Data/Projects/com.lveditor.draft` |

> 드래프트는 원본 영상을 **절대 경로로 참조**합니다. CapCut 이 설치된 컴퓨터에서 실행하고,
> 실행 후 원본 영상을 옮기지 마세요.

### 주요 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--max-pause` | 0.6 | 이보다 긴 멈춤/말 없는 동작은 잘라냄 (초). 동작을 더 살리고 싶으면 크게 (예: 2) |
| `--pause-keep` | 0.3 | 잘라낸 자리에 남길 여유 (초) |
| `--max-chars` | 18 | 자막 한 개 최대 글자 수, 넘으면 문장부호/띄어쓰기 기준 자동 분할 (0=분할 안 함) |
| `--model` | small | Whisper 모델. 정확도가 중요하면 `medium` / `large-v3` (GPU 권장) |
| `--transcript` | | 저장된 음성인식 결과 재사용 (옵션만 바꿔 다시 돌릴 때 빠름) |
| `--no-asr` | | 음성인식 없이 무음 감지만 사용 (버벅임 제거 불가, 자막은 글자 수 비율 배치) |
| `--font-size` / `--color` / `--border-color` / `--no-border` / `--bold` | 7 / #FFFFFF / #000000 | 자막 스타일 |
| `--position` | 가로 -0.8, 세로 -0.55 | 자막 세로 위치 (-1 맨 아래 ~ 1 맨 위) |
| `--preview out.mp4` | | 컷 결과를 ffmpeg 로 바로 렌더링해서 확인 (자막 미포함) |
| `--dry-run` | | 드래프트 없이 분석 결과(SRT/JSON)만 출력 |
| `--replace` | | 같은 이름의 드래프트 덮어쓰기 |

음성인식 결과는 `영상이름.transcript.json` 으로 저장되므로, 컷 강도만 바꿔 보고 싶을 때는:

```bash
python -m autocut 영상.mp4 스크립트.txt --transcript 영상.transcript.json --max-pause 1.5 --replace
```

### 출력 파일

- CapCut 드래프트 (`<드래프트 폴더>/<이름>/`)
- `<이름>.srt` — 편집본 기준 자막
- `<이름>.plan.json` — 남긴 구간, 자막 시간, 제거된 단어 목록 (디버깅용)

## 팁 / 한계

- 스크립트와 실제 말이 많이 다르면(애드리브) 스크립트에 없는 말은 잘립니다. 살리고 싶은 애드리브는 스크립트에 추가하세요.
- 숫자(“3개” ↔ “세 개”)처럼 표기가 다른 부분은 정렬이 약간 흔들릴 수 있지만 주변 글자로 보정됩니다.
- 자막 폰트는 CapCut 기본 폰트를 씁니다. 한글 폰트 변경은 CapCut 에서 자막 트랙 전체 선택 후 한 번에 바꾸는 것이 가장 편합니다.
- 최신 CapCut 버전 호환성은 pyCapCut 지원 범위를 따릅니다.

## 테스트

```bash
pip install pytest
python -m pytest
```
