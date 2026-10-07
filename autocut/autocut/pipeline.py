"""CLI 와 웹 서버가 공유하는 편집 파이프라인."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from . import media
from .models import EditPlan, Subtitle  # noqa: F401
from .planner import CutOptions, plan_from_silence, plan_from_words

Progress = Callable[[str], None]


@dataclass
class AnalyzeOptions:
    max_pause: float = 0.6
    pause_keep: float = 0.3
    keep_threshold: float = 0.5
    silence_db: float = -35.0
    no_asr: bool = False
    model: str = "small"
    language: str = "ko"
    device: str = "auto"
    mode: str = "auto"
    """auto = 소리가 있으면 음성 기준, 없으면 화면 기준 / voice / visual"""
    max_action: float = 6.0
    long_mode: str = "speed"
    remove_ng: bool = True
    extra: dict = field(default_factory=dict)

    def cut_options(self) -> CutOptions:
        return CutOptions(max_pause=self.max_pause, pause_keep=self.pause_keep,
                          keep_threshold=self.keep_threshold)


def analyze(video: str, script: List[Subtitle], opt: AnalyzeOptions, *,
            transcript_path: Optional[str] = None, info: Optional[media.VideoInfo] = None,
            progress: Progress = lambda _msg: None) -> EditPlan:
    """영상을 분석해 편집 계획을 만든다.

    `transcript_path` 가 존재하면 음성인식 결과를 재사용하고, 없으면 인식 후 그 경로에 저장한다.
    """
    info = info or media.probe(video)
    cut = opt.cut_options()

    mode = opt.mode
    if mode == "auto":
        progress("오디오 확인 중")
        mode = "voice" if media.has_meaningful_audio(video) else "visual"
    if mode == "visual":
        from .visual import VisualOptions, plan_from_visual
        vopt = VisualOptions(max_action=opt.max_action, long_mode=opt.long_mode, remove_ng=opt.remove_ng)
        plan = plan_from_visual(video, script, info.duration, vopt, cut, progress=progress)
        if opt.mode == "auto":
            plan.notes.insert(0, "영상에 음성이 없어 화면 기준으로 편집했습니다")
        return plan

    def by_silence() -> EditPlan:
        progress("무음 구간 감지 중")
        silences = media.detect_silences(video, noise_db=opt.silence_db,
                                         min_silence=min(0.3, opt.max_pause), duration=info.duration)
        return plan_from_silence(silences, script, info.duration, cut)

    if opt.no_asr:
        return by_silence()

    from .transcribe import load_words, save_words, transcribe
    if transcript_path and os.path.exists(transcript_path):
        progress("저장된 음성인식 결과 사용")
        words = load_words(transcript_path)
    else:
        progress(f"음성 인식 중 (Whisper {opt.model})")
        prompt = " ".join(s.text for s in script)[:200]
        words = transcribe(video, model_size=opt.model, language=opt.language,
                           device=opt.device, initial_prompt=prompt)
        if transcript_path:
            Path(transcript_path).parent.mkdir(parents=True, exist_ok=True)
            save_words(words, transcript_path)

    if not words:
        progress("음성이 인식되지 않아 무음 감지 모드로 전환")
        return by_silence()
    progress("스크립트와 음성 정렬 중")
    return plan_from_words(words, script, info.duration, cut)
