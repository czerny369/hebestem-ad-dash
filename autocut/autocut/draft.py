"""pyCapCut 으로 CapCut 드래프트 생성."""
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import pycapcut as cc

from .models import EditPlan, Subtitle
from .transitions import get_type

SEC = 1_000_000  # pyCapCut 내부 시간 단위: 마이크로초


def default_drafts_dir() -> Optional[str]:
    """OS 별 CapCut 기본 드래프트 폴더를 찾는다 (없으면 None)."""
    home = Path.home()
    candidates = []
    if platform.system() == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        candidates.append(local / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft")
    elif platform.system() == "Darwin":
        candidates.append(home / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft")
        candidates.append(home / "Library" / "Containers" / "com.lemon.lvoverseas" / "Data" / "Movies"
                          / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft")
    for c in candidates:
        if c.is_dir():
            return str(c)
    return None


@dataclass
class SubtitleStyle:
    size: float = 7.0
    color: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    border: bool = True
    border_color: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    border_width: float = 40.0
    bold: bool = False
    transform_y: float = -0.75
    """세로 위치. -1 이 화면 아래 끝, 0 이 가운데."""
    max_line_width: float = 0.82
    font: Optional[str] = None
    """pycapcut.FontType 멤버 이름 (예: 'Freehand'). 없으면 CapCut 기본 폰트."""


def hex_to_rgb(value: str) -> Tuple[float, float, float]:
    v = value.lstrip("#")
    if len(v) != 6:
        raise ValueError(f"색상은 #RRGGBB 형식이어야 합니다: {value}")
    return tuple(int(v[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _to_frames(seconds: float, fps: float) -> int:
    """초 → 프레임 경계에 맞춘 마이크로초."""
    frame_us = SEC / fps
    return int(round(round(seconds * fps) * frame_us))


def build_draft(video_path: str, plan: EditPlan, *, drafts_dir: str, draft_name: str,
                width: int, height: int, fps: float,
                style: SubtitleStyle = SubtitleStyle(),
                transitions: Optional[Sequence[Optional[Tuple[str, float]]]] = None,
                allow_replace: bool = False) -> str:
    """편집 계획대로 CapCut 드래프트를 만들고 드래프트 폴더 경로를 반환한다.

    `transitions[i]` 는 i 번째와 i+1 번째 조각 사이의 (전환 효과 이름, 길이초) 또는 None.
    """
    transitions = list(transitions or [])
    transition_types = [get_type(t[0]) if t else None for t in transitions]  # 이름 오류는 폴더 생성 전에
    # 드래프트 폴더를 만들기 전에 소재부터 읽어서, 실패해도 빈 드래프트가 남지 않게 한다.
    try:
        material = cc.VideoMaterial(os.path.abspath(video_path))
    except Exception as e:  # pymediainfo 가 길이를 못 읽는 컨테이너(webm 등)
        raise ValueError(f"CapCut 소재로 읽을 수 없는 영상입니다 ({e}). MP4 또는 MOV 로 변환 후 다시 시도하세요.") from e

    folder = cc.DraftFolder(drafts_dir)
    script = folder.create_draft(draft_name, width, height, fps=int(round(fps)),
                                 allow_replace=allow_replace)
    script.add_track(cc.TrackType.video).add_track(cc.TrackType.text, "자막")

    # ---- 영상: 남길 구간을 순서대로 이어붙임 ----
    cursor = 0
    speeds = plan.speed_list()
    for i, (s, e) in enumerate(plan.keep):
        src_start = _to_frames(s, fps)
        src_end = min(_to_frames(e, fps), material.duration)
        dur = src_end - src_start
        if dur <= 0:
            continue
        speed = speeds[i]
        seg = cc.VideoSegment(material, cc.trange(cursor, int(round(dur / speed))),
                              source_timerange=cc.trange(src_start, dur),
                              speed=None if abs(speed - 1.0) < 1e-6 else speed)
        # 전환은 '앞' 조각에 붙인다
        if i < len(transition_types) and transition_types[i] is not None and i + 1 < len(plan.keep):
            seg.add_transition(transition_types[i], duration=int(transitions[i][1] * SEC))
        script.add_segment(seg)
        cursor += seg.target_timerange.duration
    total = cursor

    # ---- 자막 ----
    text_style = cc.TextStyle(size=style.size, color=style.color, bold=style.bold, align=1,
                              auto_wrapping=True, max_line_width=style.max_line_width)
    border = cc.TextBorder(color=style.border_color, width=style.border_width) if style.border else None
    font = getattr(cc.FontType, style.font) if style.font else None
    clip = cc.ClipSettings(transform_y=style.transform_y)

    last_end = 0
    for sub in plan.subtitles:
        start = max(_to_frames(sub.start, fps), last_end)
        end = min(_to_frames(sub.end, fps), total)
        if end - start < SEC // 10:
            continue
        seg = cc.TextSegment(sub.text, cc.trange(start, end - start), font=font,
                             style=text_style, clip_settings=clip, border=border)
        script.add_segment(seg, "자막")
        last_end = end

    script.save()
    return os.path.join(drafts_dir, draft_name)


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt_text(subs: List[Subtitle]) -> str:
    lines = []
    for k, s in enumerate(subs, 1):
        lines += [str(k), f"{_srt_time(s.start)} --> {_srt_time(s.end)}", s.text, ""]
    return "\n".join(lines)


def write_srt(subs: List[Subtitle], path: str) -> None:
    Path(path).write_text(srt_text(subs), encoding="utf-8")
