"""웹 UI 용 로컬 API 서버.

실행:  python -m autocut.server   →  http://127.0.0.1:8765
CapCut 드래프트가 원본 영상을 절대 경로로 참조하므로, 업로드한 영상은 작업 폴더(AUTOCUT_HOME)에 보관된다.
"""
import json
import os
import re
import shutil
import threading
import time
import traceback
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

import pycapcut as cc
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import media
from .draft import SubtitleStyle, build_draft, default_drafts_dir, hex_to_rgb, srt_text
from .models import EditPlan, Subtitle
from .pipeline import AnalyzeOptions, analyze
from .script_parser import parse_script_text
from .transitions import TransitionSettings, catalog as transition_catalog, resolve as resolve_transitions

HOME = Path(os.environ.get("AUTOCUT_HOME", Path.home() / "AutoCut")).expanduser()
PROJECTS = HOME / "projects"
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app = FastAPI(title="AutoCut")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

_lock = threading.Lock()            # 무거운 분석은 한 번에 하나씩
_status: dict = {}                  # project_id -> {"state", "step", "error"}


# --------------------------------------------------------------------------- #
# 프로젝트 저장소
# --------------------------------------------------------------------------- #
def _dir(pid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{12}", pid):
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다")
    d = PROJECTS / pid
    if not (d / "project.json").exists():
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다")
    return d


def _load(pid: str) -> dict:
    return json.loads((_dir(pid) / "project.json").read_text(encoding="utf-8"))


def _save(pid: str, data: dict) -> None:
    path = PROJECTS / pid / "project.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _public(pid: str, data: dict) -> dict:
    status = _status.get(pid) or {"state": "done" if data.get("plan") else "idle", "step": "", "error": None}
    return {**{k: v for k, v in data.items() if k != "video_path"}, "id": pid, "status": status}


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.get("/api/transitions")
def transitions_catalog():
    return transition_catalog()


@app.get("/api/config")
def config():
    return {
        "drafts_dir": default_drafts_dir() or "",
        "workspace": str(HOME),
        "models": ["tiny", "base", "small", "medium", "large-v3"],
        "fonts": sorted(cc.FontType.__members__.keys()),
    }


@app.get("/api/projects")
def list_projects():
    out = []
    if PROJECTS.exists():
        for d in sorted(PROJECTS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            f = d / "project.json"
            if f.exists():
                data = json.loads(f.read_text(encoding="utf-8"))
                out.append({"id": d.name, "video_name": data["video_name"],
                            "created": data.get("created"), "has_plan": bool(data.get("plan"))})
    return out


@app.post("/api/projects")
async def create_project(video: UploadFile = File(...)):
    pid = uuid.uuid4().hex[:12]
    d = PROJECTS / pid
    d.mkdir(parents=True)
    name = Path(video.filename or "video.mp4").name
    safe = re.sub(r'[\\/:*?"<>|]', "_", name)
    dest = d / safe
    with dest.open("wb") as f:
        while chunk := await video.read(8 * 1024 * 1024):
            f.write(chunk)
    try:
        info = media.probe(str(dest))
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(400, f"영상 파일을 읽을 수 없습니다: {e}")
    data = {"video_name": name, "video_path": str(dest), "info": asdict(info),
            "created": time.time(), "script_text": "", "plan": None, "draft": None}
    _save(pid, data)
    return _public(pid, data)


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    return _public(pid, _load(pid))


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    shutil.rmtree(_dir(pid))
    _status.pop(pid, None)
    return {"ok": True}


@app.get("/api/projects/{pid}/video")
def get_video(pid: str):
    return FileResponse(_load(pid)["video_path"])


class AnalyzeRequest(BaseModel):
    script_text: str
    max_chars: int = 18
    max_pause: float = Field(0.6, ge=0.1, le=30)
    pause_keep: float = Field(0.3, ge=0, le=5)
    keep_threshold: float = Field(0.5, ge=0.1, le=1)
    no_asr: bool = False
    model: str = "small"
    language: str = "ko"
    retranscribe: bool = False


@app.post("/api/projects/{pid}/analyze")
def start_analyze(pid: str, req: AnalyzeRequest):
    data = _load(pid)
    if _status.get(pid, {}).get("state") == "running":
        raise HTTPException(409, "이미 분석 중입니다")
    try:
        script = parse_script_text(req.script_text, req.max_chars)
    except ValueError as e:
        raise HTTPException(400, str(e))

    transcript = PROJECTS / pid / "transcript.json"
    if req.retranscribe or data.get("asr_model") not in (None, req.model):
        transcript.unlink(missing_ok=True)

    data["script_text"] = req.script_text
    data["options"] = req.model_dump()
    _save(pid, data)
    _status[pid] = {"state": "running", "step": "대기 중", "error": None}

    def run():
        def progress(msg: str):
            _status[pid]["step"] = msg
        try:
            with _lock:
                opt = AnalyzeOptions(max_pause=req.max_pause, pause_keep=req.pause_keep,
                                     keep_threshold=req.keep_threshold, no_asr=req.no_asr,
                                     model=req.model, language=req.language)
                info = media.VideoInfo(**data["info"])
                plan = analyze(data["video_path"], script, opt, transcript_path=str(transcript),
                               info=info, progress=progress)
            fresh = _load(pid)
            fresh["plan"] = plan.to_dict()
            if not req.no_asr:
                fresh["asr_model"] = req.model
            _save(pid, fresh)
            _status[pid] = {"state": "done", "step": "완료", "error": None}
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            _status[pid] = {"state": "error", "step": "", "error": str(e)}

    threading.Thread(target=run, daemon=True).start()
    return _public(pid, _load(pid))


class SubtitleIn(BaseModel):
    text: str
    start: float
    end: float


class StyleIn(BaseModel):
    size: float = 7.0
    color: str = "#FFFFFF"
    border: bool = True
    border_color: str = "#000000"
    bold: bool = False
    position: Optional[float] = None
    font: Optional[str] = None


class TransitionIn(BaseModel):
    enabled: bool = False
    type: str = "叠化"
    duration: float = Field(0.5, ge=0.1, le=3)
    apply: str = Field("long_cuts", pattern="^(all|long_cuts)$")
    min_cut: float = Field(2.0, ge=0, le=60)
    overrides: Dict[int, str] = {}


class DraftRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    drafts_dir: str
    replace: bool = False
    subtitles: List[SubtitleIn]
    style: StyleIn = StyleIn()
    transition: TransitionIn = TransitionIn()


def _plan_with(data: dict, subtitles: List[SubtitleIn]) -> EditPlan:
    if not data.get("plan"):
        raise HTTPException(400, "먼저 분석을 실행하세요")
    keep = [tuple(k) for k in data["plan"]["keep"]]
    subs = [Subtitle(s.text.strip(), s.start, s.end) for s in subtitles if s.text.strip()]
    return EditPlan(keep=keep, subtitles=subs)


@app.post("/api/projects/{pid}/draft")
def make_draft(pid: str, req: DraftRequest):
    data = _load(pid)
    plan = _plan_with(data, req.subtitles)
    if re.search(r'[\\/:*?"<>|]', req.name):
        raise HTTPException(400, '드래프트 이름에 \\ / : * ? " < > | 는 쓸 수 없습니다')
    if not req.drafts_dir or not os.path.isdir(req.drafts_dir):
        raise HTTPException(400, f"CapCut 드래프트 폴더가 없습니다: {req.drafts_dir}")
    if req.style.font and req.style.font not in cc.FontType.__members__:
        raise HTTPException(400, f"알 수 없는 폰트: {req.style.font}")

    info = media.VideoInfo(**data["info"])
    vertical = info.height > info.width
    st = req.style
    style = SubtitleStyle(
        size=st.size, color=hex_to_rgb(st.color), bold=st.bold, border=st.border,
        border_color=hex_to_rgb(st.border_color),
        transform_y=st.position if st.position is not None else (-0.55 if vertical else -0.8),
        max_line_width=0.9 if vertical else 0.82, font=st.font or None)
    tr = req.transition
    for name in [tr.type, *tr.overrides.values()]:
        if name != "none" and name not in cc.TransitionType.__members__:
            raise HTTPException(400, f"알 수 없는 전환 효과: {name}")
    transitions = resolve_transitions(plan.keep, TransitionSettings(**tr.model_dump()))
    try:
        path = build_draft(data["video_path"], plan, drafts_dir=req.drafts_dir, draft_name=req.name,
                           width=info.width, height=info.height, fps=info.fps,
                           style=style, transitions=transitions, allow_replace=req.replace)
    except FileExistsError:
        raise HTTPException(409, f"'{req.name}' 드래프트가 이미 있습니다. 덮어쓰기를 켜거나 이름을 바꾸세요")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        raise HTTPException(500, f"드래프트 생성 실패: {e}")

    data["draft"] = {"name": req.name, "path": path, "transitions": sum(1 for t in transitions if t)}
    data["transition"] = tr.model_dump()
    data["plan"]["subtitles"] = [asdict(s) for s in plan.subtitles]
    _save(pid, data)
    return {"path": path}


@app.post("/api/projects/{pid}/srt", response_class=PlainTextResponse)
def export_srt(pid: str, subtitles: List[SubtitleIn]):
    plan = _plan_with(_load(pid), subtitles)
    return srt_text(plan.subtitles)


if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


def main() -> None:
    import argparse
    import webbrowser

    import uvicorn

    p = argparse.ArgumentParser(description="AutoCut 웹 UI 서버")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()
    PROJECTS.mkdir(parents=True, exist_ok=True)
    url = f"http://{args.host}:{args.port}"
    print(f"AutoCut 웹 UI: {url}  (작업 폴더: {HOME})")
    if not FRONTEND_DIST.is_dir():
        print("※ frontend/dist 가 없습니다. `cd frontend && npm install && npm run build` 를 먼저 실행하세요.")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
