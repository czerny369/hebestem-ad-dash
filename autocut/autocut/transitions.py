"""컷과 컷 사이 전환 효과 (pyCapCut TransitionType) 선택/적용 규칙."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import pycapcut as cc

# 자주 쓰는 무료 전환 효과 (TransitionType 멤버 이름, 한글 이름, 분류)
PRESETS: List[Tuple[str, str, str]] = [
    ("叠化", "디졸브 (겹쳐 사라짐)", "기본"),
    ("闪白", "화이트 플래시", "기본"),
    ("闪黑", "블랙 플래시", "기본"),
    ("泛白", "하얗게 번짐", "기본"),
    ("转场_模糊", "블러", "기본"),
    ("色彩溶解", "컬러 디졸브", "기본"),
    ("推近", "줌 인", "움직임"),
    ("拉远", "줌 아웃", "움직임"),
    ("向左", "왼쪽으로 밀기", "움직임"),
    ("向右", "오른쪽으로 밀기", "움직임"),
    ("向上", "위로 밀기", "움직임"),
    ("向下", "아래로 밀기", "움직임"),
    ("旋焦", "회전 포커스", "움직임"),
    ("震动", "흔들림", "움직임"),
    ("向左擦除", "왼쪽 와이프", "와이프"),
    ("向右擦除", "오른쪽 와이프", "와이프"),
    ("渐变擦除", "그라데이션 와이프", "와이프"),
    ("横向拉幕", "가로 커튼", "와이프"),
    ("竖向拉幕", "세로 커튼", "와이프"),
    ("百叶窗", "블라인드", "와이프"),
    ("圆形遮罩", "원형 마스크", "와이프"),
    ("快门", "셔터", "개성"),
    ("眨眼", "눈 깜빡임", "개성"),
    ("故障", "글리치", "개성"),
    ("频闪", "스트로브", "개성"),
    ("光束", "빛줄기", "개성"),
    ("炫光", "렌즈 플레어", "개성"),
    ("翻页", "페이지 넘김", "개성"),
    ("撕纸", "종이 찢기", "개성"),
    ("白色烟雾", "흰 연기", "개성"),
    ("水墨", "수묵", "개성"),
    ("马赛克", "모자이크", "개성"),
]
PRESET_LABELS: Dict[str, str] = {k: label for k, label, _ in PRESETS}

MIN_DURATION = 0.1


def get_type(name: str) -> cc.TransitionType:
    try:
        return cc.TransitionType[name]
    except KeyError:
        raise ValueError(f"알 수 없는 전환 효과: {name}")


def catalog() -> dict:
    """UI 용 전환 효과 목록."""
    presets = []
    for key, label, group in PRESETS:
        meta = get_type(key).value
        presets.append({"id": key, "label": label, "group": group,
                        "duration": meta.default_duration / 1e6, "vip": meta.is_vip})
    all_items = [{"id": t.name, "name": t.value.name.strip(), "vip": t.value.is_vip,
                  "duration": t.value.default_duration / 1e6, "label": PRESET_LABELS.get(t.name)}
                 for t in cc.TransitionType]
    all_items.sort(key=lambda x: (x["vip"], x["label"] is None, x["name"]))
    return {"presets": presets, "all": all_items}


@dataclass
class TransitionSettings:
    enabled: bool = False
    type: str = "叠化"
    duration: float = 0.5
    """초"""
    apply: str = "long_cuts"
    """'all' = 모든 컷, 'long_cuts' = `min_cut` 초 이상 잘린 곳만"""
    min_cut: float = 2.0
    overrides: Dict[int, str] = field(default_factory=dict)
    """컷 번호(0부터, keep[i] 와 keep[i+1] 사이) → 효과 이름 또는 'none'"""


def resolve(keep: Sequence[Tuple[float, float]],
            settings: TransitionSettings) -> List[Optional[Tuple[str, float]]]:
    """각 컷 경계(len(keep)-1 개)에 넣을 (효과, 길이초) 또는 None.

    전환 길이는 앞뒤 조각 중 짧은 쪽의 절반을 넘지 않게 줄인다 (CapCut 은 조각보다 긴 전환을 허용하지 않음).
    """
    out: List[Optional[Tuple[str, float]]] = []
    for i in range(len(keep) - 1):
        override = settings.overrides.get(i)
        if override == "none":
            out.append(None)
            continue
        if override:
            kind = override
        elif not settings.enabled:
            out.append(None)
            continue
        else:
            removed = keep[i + 1][0] - keep[i][1]
            if settings.apply == "long_cuts" and removed < settings.min_cut:
                out.append(None)
                continue
            kind = settings.type
        limit = min(keep[i][1] - keep[i][0], keep[i + 1][1] - keep[i + 1][0]) / 2
        duration = min(settings.duration, limit)
        out.append((kind, duration) if duration >= MIN_DURATION else None)
    return out
