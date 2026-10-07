"""공용 데이터 구조. 모든 시간 단위는 초(float)."""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple


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
    start: Optional[float] = None   # 원본 영상 기준
    end: Optional[float] = None


@dataclass
class EditPlan:
    """컷편집 결과: 원본에서 남길 구간들과, 편집본 타임라인 기준 자막."""
    keep: List[Tuple[float, float]]
    subtitles: List[Subtitle]                     # 편집본 타임라인 기준 시간
    dropped_words: List[Word] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return sum(e - s for s, e in self.keep)

    def to_dict(self) -> dict:
        return {
            "keep": [list(k) for k in self.keep],
            "duration": self.duration,
            "subtitles": [asdict(s) for s in self.subtitles],
            "dropped_words": [asdict(w) for w in self.dropped_words],
        }
