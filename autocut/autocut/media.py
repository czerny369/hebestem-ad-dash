"""ffprobe/ffmpeg 를 이용한 영상 정보 조회 및 무음 감지."""
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class VideoInfo:
    duration: float
    width: int
    height: int
    fps: float


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise RuntimeError(f"{tool} 을(를) 찾을 수 없습니다. FFmpeg 를 설치하고 PATH 에 추가하세요.")
    return path


def probe(video_path: str) -> VideoInfo:
    out = subprocess.run(
        [_require("ffprobe"), "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", video_path],
        capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    vstream = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    if vstream is None:
        raise ValueError(f"영상 스트림이 없습니다: {video_path}")
    w, h = int(vstream["width"]), int(vstream["height"])

    rotation = 0
    for sd in vstream.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    rotation = int(vstream.get("tags", {}).get("rotate", rotation))
    if abs(rotation) % 180 == 90:
        w, h = h, w

    num, _, den = vstream.get("avg_frame_rate", "30/1").partition("/")
    try:
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        fps = 30.0
    if not 1 <= fps <= 240:
        fps = 30.0
    duration = float(data["format"].get("duration") or vstream.get("duration"))
    return VideoInfo(duration=duration, width=w, height=h, fps=fps)


_SIL_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SIL_END = re.compile(r"silence_end:\s*([\d.]+)")


def detect_silences(video_path: str, noise_db: float = -35.0, min_silence: float = 0.3,
                    duration: float = 0.0) -> List[Tuple[float, float]]:
    """ffmpeg silencedetect 로 무음 구간 목록을 얻는다."""
    proc = subprocess.run(
        [_require("ffmpeg"), "-hide_banner", "-nostats", "-i", video_path, "-vn",
         "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True)
    silences, start = [], None
    for line in proc.stderr.splitlines():
        m = _SIL_START.search(line)
        if m:
            start = max(0.0, float(m.group(1)))
            continue
        m = _SIL_END.search(line)
        if m and start is not None:
            silences.append((start, float(m.group(1))))
            start = None
    if start is not None and duration:
        silences.append((start, duration))
    return silences
