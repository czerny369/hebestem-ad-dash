"""공용 데이터 구조. 모든 시간 단위는 초(float)."""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Sequence, Tuple


@dataclass
class Word:
    """음성 인식 결과의 단어 하나 (원본 영상 기준 시간)."""
    text: str
    start: float
    end: float


@dataclass
class Subtitle:
    """자막 한 줄."""
    text: str
    start: Optional[float] = None
    end: Optional[float] = None
    action: Optional[str] = None
    """스크립트에서 이 자막 아래 적힌 [동작 설명] (화면 기준 편집에서 장면 매칭에 사용)"""


@dataclass
class Piece:
    """원본 영상을 빈틈없이 나눈 조각 하나. 사용자가 UI 에서 남김/잘림을 바꿀 수 있다."""
    start: float
    end: float
    keep: bool
    speed: float = 1.0
    reason: str = ""
    """잘린 이유 또는 조각 설명: silence / stutter / ng / long / idle / action ..."""
    label: str = ""


def keep_from_pieces(pieces: Sequence[Piece]) -> Tuple[List[Tuple[float, float]], List[float]]:
    """남길 조각들을 (구간, 속도) 목록으로. 붙어 있고 속도가 같은 조각은 하나로 합친다."""
    keep: List[Tuple[float, float]] = []
    speeds: List[float] = []
    for p in sorted(pieces, key=lambda p: p.start):
        if not p.keep or p.end - p.start <= 1e-6:
            continue
        if keep and abs(keep[-1][1] - p.start) < 1e-6 and abs(speeds[-1] - p.speed) < 1e-6:
            keep[-1] = (keep[-1][0], p.end)
        else:
            keep.append((p.start, p.end))
            speeds.append(p.speed)
    return keep, speeds


def pieces_from_keep(keep: Sequence[Tuple[float, float]], duration: float,
                     cut_reason=lambda s, e: "cut") -> List[Piece]:
    """남길 구간 목록 → 원본 전체를 덮는 조각 목록 (속도 1)."""
    pieces: List[Piece] = []
    cursor = 0.0
    for s, e in keep:
        if s - cursor > 1e-3:
            pieces.append(Piece(cursor, s, False, reason=cut_reason(cursor, s)))
        pieces.append(Piece(s, e, True))
        cursor = e
    if duration - cursor > 1e-3:
        pieces.append(Piece(cursor, duration, False, reason=cut_reason(cursor, duration)))
    return pieces


@dataclass
class EditPlan:
    """컷편집 결과: 원본에서 남길 구간(+속도)들과, 편집본 타임라인 기준 자막."""
    keep: List[Tuple[float, float]]
    subtitles: List[Subtitle]                     # 편집본 타임라인 기준 시간
    dropped_words: List[Word] = field(default_factory=list)
    speeds: List[float] = field(default_factory=list)
    """keep 과 같은 길이 (비어 있으면 모두 1.0)"""
    pieces: List[Piece] = field(default_factory=list)
    mode: str = "voice"
    """voice = 음성 기준, visual = 화면 기준, silence = 무음 감지"""
    notes: List[str] = field(default_factory=list)

    def speed_list(self) -> List[float]:
        return self.speeds if len(self.speeds) == len(self.keep) else [1.0] * len(self.keep)

    @property
    def duration(self) -> float:
        return sum((e - s) / sp for (s, e), sp in zip(self.keep, self.speed_list()))

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "keep": [list(k) for k in self.keep],
            "speeds": self.speed_list(),
            "duration": self.duration,
            "pieces": [asdict(p) for p in self.pieces],
            "subtitles": [asdict(s) for s in self.subtitles],
            "dropped_words": [asdict(w) for w in self.dropped_words],
            "notes": self.notes,
        }
