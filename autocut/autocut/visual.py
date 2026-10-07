"""음성이 없는 영상용: 화면 움직임/내용을 분석해 컷편집하고 [동작 설명]에 맞춰 자막을 배치한다.

1. 저해상도 흑백 프레임으로 움직임 곡선을 구해 장면 전환/정지 구간을 기준으로 '동작 조각'으로 나눈다.
2. (선택) 다국어 CLIP 으로 각 조각의 화면과 스크립트의 [동작 설명]을 비교해, 설명 순서를 지키며
   가장 잘 맞는 조각을 고른다. 같은 동작을 여러 번 찍었으면 마지막 것을 남기고 앞의 것은 NG 로 자른다.
3. 너무 긴 조각은 빨리감기(speed) 또는 중간 자르기(trim) 한다.
"""
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from .models import EditPlan, Piece, Subtitle, keep_from_pieces
from .planner import CutOptions, TimelineMap, _redistribute_missing, distribute_evenly, finalize_subtitles

Progress = Callable[[str], None]


@dataclass
class VisualOptions:
    max_action: float = 6.0
    """이보다 긴 장면은 줄인다 (초)"""
    long_mode: str = "speed"
    """speed = 빨리감기, trim = 중간을 잘라 앞뒤만 남김"""
    max_speed: float = 4.0
    remove_ng: bool = True
    """같은 동작을 다시 찍은 앞부분(NG)을 자른다 (AI 모델 필요)"""
    ng_margin: float = 0.6
    """NG 판단 여유 (클수록 더 많이 NG 로 판단)"""
    sample_fps: float = 5.0
    min_still: float = 0.6
    """이 이상 화면이 거의 안 움직이면 정지 구간으로 본다 (초)"""
    min_segment: float = 0.5


@dataclass
class Segment:
    start: float
    end: float
    kind: str  # action | idle

    @property
    def duration(self) -> float:
        return self.end - self.start


# --------------------------------------------------------------------------- #
# 프레임 읽기
# --------------------------------------------------------------------------- #
def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg 를 찾을 수 없습니다")
    return path


def read_frames(video: str, fps: float, width: int, height: int, gray: bool):
    """ffmpeg 로 프레임을 일정 간격으로 읽어 (index, ndarray) 를 차례로 돌려준다."""
    pix = "gray" if gray else "rgb24"
    ch = 1 if gray else 3
    vf = (f"fps={fps},scale={width}:{height}" if gray else
          f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}")
    proc = subprocess.Popen([_ffmpeg(), "-v", "error", "-i", video, "-an", "-vf", vf,
                             "-f", "rawvideo", "-pix_fmt", pix, "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size = width * height * ch
    i = 0
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            arr = np.frombuffer(buf, dtype=np.uint8)
            yield i, (arr.reshape(height, width) if gray else arr.reshape(height, width, 3))
            i += 1
    finally:
        proc.stdout.close()
        proc.wait()


def motion_curve(video: str, fps: float) -> np.ndarray:
    """프레임 간 평균 밝기 차이 (0~1). 길이 = 샘플 프레임 수."""
    prev = None
    diffs: List[float] = []
    for _, f in read_frames(video, fps, 96, 96, gray=True):
        f = f.astype(np.float32)
        diffs.append(0.0 if prev is None else float(np.mean(np.abs(f - prev))) / 255.0)
        prev = f
    return np.array(diffs, dtype=np.float32)


# --------------------------------------------------------------------------- #
# 조각 나누기
# --------------------------------------------------------------------------- #
def segment_motion(diff: np.ndarray, fps: float, duration: float, opt: VisualOptions) -> List[Segment]:
    n = len(diff)
    if n < 3:
        return [Segment(0.0, duration, "action")]
    t = lambda i: min(duration, i / fps)  # noqa: E731

    med = float(np.median(diff))
    cut_thr = max(0.10, med * 6)
    cuts = {i for i in range(1, n) if diff[i] > cut_thr}

    w = max(1, int(round(0.6 * fps)))
    smooth = np.convolve(diff, np.ones(w) / w, mode="same")
    p20 = float(np.percentile(smooth, 20))
    still_thr = max(0.003, min(p20 * 1.8, med * 0.6))
    still = smooth < still_thr

    # 정지 구간 찾기
    min_len = int(round(opt.min_still * fps))
    idle_runs: List[Tuple[int, int]] = []
    i = 0
    while i < n:
        if still[i]:
            j = i
            while j < n and still[j]:
                j += 1
            if j - i >= min_len:
                idle_runs.append((i, j))
            i = j
        else:
            i += 1

    bounds = {0, n} | cuts
    for a, b in idle_runs:
        bounds |= {a, b}
    bounds = sorted(bounds)
    idle_set = set()
    for a, b in idle_runs:
        idle_set.update(range(a, b))

    segs: List[Segment] = []
    for a, b in zip(bounds, bounds[1:]):
        if b <= a:
            continue
        kind = "idle" if sum(1 for k in range(a, b) if k in idle_set) > (b - a) / 2 else "action"
        segs.append(Segment(t(a), t(b), kind))
    if segs:
        segs[-1].end = duration

    # 너무 짧은 조각은 앞 조각에 붙이고, 장면 전환 없이 이어진 같은 종류 조각은 합친다
    cut_times = {t(c) for c in cuts}
    merged: List[Segment] = []
    for s in segs:
        if merged and (s.duration < opt.min_segment or (s.kind == merged[-1].kind and s.start not in cut_times)):
            merged[-1].end = s.end
        else:
            merged.append(Segment(s.start, s.end, s.kind))
    if len(merged) > 1 and merged[0].duration < opt.min_segment:
        merged[1].start = merged[0].start
        merged.pop(0)
    return merged


# --------------------------------------------------------------------------- #
# 화면-텍스트 임베딩 (다국어 CLIP)
# --------------------------------------------------------------------------- #
class Embedder:
    """embed_images(list of RGB ndarray) / embed_texts(list of str) → 정규화된 벡터 (N, D)."""

    def embed_images(self, images: List[np.ndarray]) -> np.ndarray:
        raise NotImplementedError

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        raise NotImplementedError


class ClipEmbedder(Embedder):
    IMAGE_MODEL = "clip-ViT-B-32"
    TEXT_MODEL = "sentence-transformers/clip-ViT-B-32-multilingual-v1"

    def __init__(self, device: Optional[str] = None):
        from sentence_transformers import SentenceTransformer  # 무거워서 필요할 때만
        self.img = SentenceTransformer(self.IMAGE_MODEL, device=device)
        self.txt = SentenceTransformer(self.TEXT_MODEL, device=device)

    def embed_images(self, images):
        from PIL import Image
        return self.img.encode([Image.fromarray(a) for a in images], batch_size=32,
                               convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)

    def embed_texts(self, texts):
        return self.txt.encode(list(texts), convert_to_numpy=True, normalize_embeddings=True,
                               show_progress_bar=False)


def load_embedder(progress: Progress) -> Tuple[Optional[Embedder], Optional[str]]:
    """CLIP 모델을 불러온다. 실패하면 (None, 이유)."""
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return None, "AI 화면 분석 패키지(sentence-transformers)가 설치되지 않아 순서 기준으로만 배치했습니다"
    try:
        progress("화면 분석 AI 모델 준비 중 (처음엔 약 1GB 다운로드)")
        return ClipEmbedder(), None
    except Exception as e:  # noqa: BLE001
        return None, f"화면 분석 AI 모델을 불러오지 못해 순서 기준으로만 배치했습니다 ({e})"


def frame_embeddings(video: str, embedder: Embedder, fps: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
    times, embs, batch, idx = [], [], [], []
    for i, frame in read_frames(video, fps, 224, 224, gray=False):
        batch.append(frame)
        idx.append(i)
        if len(batch) == 32:
            embs.append(embedder.embed_images(batch))
            times.extend((k + 0.5) / fps for k in idx)
            batch, idx = [], []
    if batch:
        embs.append(embedder.embed_images(batch))
        times.extend((k + 0.5) / fps for k in idx)
    if not embs:
        return np.zeros(0), np.zeros((0, 1))
    return np.array(times), np.vstack(embs)


def segment_vectors(segs: Sequence[Segment], times: np.ndarray, embs: np.ndarray) -> np.ndarray:
    out = []
    for s in segs:
        mask = (times >= s.start) & (times < s.end)
        v = embs[mask].mean(axis=0) if mask.any() else embs[int(np.argmin(np.abs(times - (s.start + s.end) / 2)))]
        out.append(v / (np.linalg.norm(v) + 1e-9))
    return np.array(out)


# --------------------------------------------------------------------------- #
# [동작 설명] ↔ 조각 정렬
# --------------------------------------------------------------------------- #
def split_for_alignment(segs: List[Segment], needed: int) -> List[Segment]:
    """설명 개수보다 조각이 적으면 긴 동작 조각을 반으로 나눠 늘린다."""
    segs = [Segment(s.start, s.end, s.kind) for s in segs]
    while len(segs) < needed:
        k = max(range(len(segs)), key=lambda i: segs[i].duration)
        s = segs[k]
        if s.duration < 0.4:
            break
        mid = (s.start + s.end) / 2
        segs[k:k + 1] = [Segment(s.start, mid, s.kind), Segment(mid, s.end, s.kind)]
    return segs


def align_actions(z: np.ndarray, kinds: Sequence[str]) -> List[int]:
    """z[s, j] (조각 s 가 설명 j 와 얼마나 닮았는지, 설명별 표준화 점수) 에서
    설명 순서를 지키는 조각 배정(각 설명마다 조각 하나, 증가 순서)을 고른다.
    점수가 비슷하면 뒤쪽(마지막 테이크)을 고른다."""
    n, m = z.shape
    score = z.copy()
    for s, k in enumerate(kinds):
        if k == "idle":
            score[s] -= 0.5
    score += 1e-3 * (np.arange(n) / max(1, n))[:, None]  # 동점이면 뒤쪽

    neg = -1e18
    best = np.full((m, n), neg)
    back = np.zeros((m, n), dtype=np.int64)
    best[0] = score[:, 0]
    for j in range(1, m):
        # prefix max of best[j-1][:s]
        pm = np.full(n, neg)
        arg = np.zeros(n, dtype=np.int64)
        cur, cur_arg = neg, 0
        for s in range(n):
            pm[s], arg[s] = cur, cur_arg
            if best[j - 1][s] >= cur:
                cur, cur_arg = best[j - 1][s], s
        best[j] = pm + score[:, j]
        back[j] = arg
    s = int(np.argmax(best[m - 1]))
    anchors = [s]
    for j in range(m - 1, 0, -1):
        s = int(back[j][s])
        anchors.append(s)
    return anchors[::-1]


def last_takes(z: np.ndarray, anchors: Sequence[int], kinds: Sequence[str],
               margin: float) -> Tuple[List[int], List[int]]:
    """같은 동작을 여러 번 찍었으면 마지막 테이크를 남긴다.

    설명 j 의 선택 조각 주변(이전 설명 조각 ~ 다음 설명 조각 사이)에서 j 와 거의 똑같이 닮았고
    이웃 설명과는 덜 닮은 동작 조각들을 같은 동작의 테이크로 본다. 그중 마지막을 j 의 조각으로 쓰고
    나머지 앞쪽 테이크는 NG 로 돌려준다. 반환: (새 anchors, NG 조각 번호들)
    """
    m = len(anchors)
    anchors = list(anchors)
    ng: List[int] = []
    for j in range(m):
        lo = anchors[j - 1] + 1 if j > 0 else 0
        hi = anchors[j + 1] if j + 1 < m else len(kinds)
        ref = z[anchors[j], j]
        takes = []
        for g in range(lo, hi):
            if kinds[g] != "action" and g != anchors[j]:
                continue
            like = z[g, j]
            prev_like = z[g, j - 1] if j > 0 else -np.inf
            next_like = z[g, j + 1] if j + 1 < m else -np.inf
            if g == anchors[j] or (like >= ref - margin and like > prev_like + 0.25 and like > next_like + 0.25):
                takes.append(g)
        anchors[j] = takes[-1]
        ng.extend(takes[:-1])
    return anchors, ng


# --------------------------------------------------------------------------- #
# 긴 조각 줄이기
# --------------------------------------------------------------------------- #
def shorten(seg: Segment, opt: VisualOptions) -> List[Piece]:
    if seg.duration <= opt.max_action:
        return [Piece(seg.start, seg.end, True, reason=seg.kind)]
    if opt.long_mode == "speed" and seg.kind == "action":
        speed = round(min(opt.max_speed, seg.duration / opt.max_action), 2)
        return [Piece(seg.start, seg.end, True, speed=speed, reason="long", label=f"{speed:g}배속")]
    head = opt.max_action * 0.5
    tail = opt.max_action * 0.5
    return [Piece(seg.start, seg.start + head, True, reason=seg.kind),
            Piece(seg.start + head, seg.end - tail, False, reason="long", label="긴 동작 중간"),
            Piece(seg.end - tail, seg.end, True, reason=seg.kind)]


# --------------------------------------------------------------------------- #
# 전체
# --------------------------------------------------------------------------- #
def plan_from_visual(video: str, script: Sequence[Subtitle], duration: float,
                     opt: VisualOptions = VisualOptions(), cut: CutOptions = CutOptions(), *,
                     embedder: Optional[Embedder] = None, use_ai: bool = True,
                     progress: Progress = lambda _m: None) -> EditPlan:
    notes: List[str] = []
    progress("화면 움직임 분석 중")
    diff = motion_curve(video, opt.sample_fps)
    segs = segment_motion(diff, opt.sample_fps, duration, opt)

    descs = [(i, s.action) for i, s in enumerate(script) if s.action]
    anchors: List[int] = []
    ng: List[int] = []
    if descs:
        segs = split_for_alignment(segs, len(descs))
        kinds = [s.kind for s in segs]
        if embedder is None and use_ai:
            embedder, why = load_embedder(progress)
            if why:
                notes.append(why)
        if embedder is not None and len(segs) >= len(descs):
            progress("장면과 [동작 설명] 비교 중")
            times, embs = frame_embeddings(video, embedder)
            seg_v = segment_vectors(segs, times, embs)
            txt_v = embedder.embed_texts([a for _, a in descs])
            sim = seg_v @ txt_v.T
            z = (sim - sim.mean(axis=0)) / (sim.std(axis=0) + 1e-6)
            anchors = align_actions(z, kinds)
            if opt.remove_ng:
                anchors, ng = last_takes(z, anchors, kinds, opt.ng_margin)
        else:
            # 모델 없이: 설명 순서대로 동작 조각에 고르게 배정
            action_idx = [i for i, k in enumerate(kinds) if k == "action"] or list(range(len(segs)))
            anchors = sorted({action_idx[min(len(action_idx) - 1, (j * len(action_idx)) // len(descs))]
                              for j in range(len(descs))})
            while len(anchors) < len(descs):
                anchors.append(anchors[-1])
            if len(segs) < len(descs):
                notes.append("장면 수가 [동작 설명]보다 적어 일부 자막이 같은 장면을 나눠 씁니다")

    # 조각 → 남김/잘림
    pieces: List[Piece] = []
    ng_set = set(ng)
    # NG 테이크 바로 뒤의 정지(다시 준비하는 시간)도 같이 자른다
    for k in sorted(ng_set):
        if k + 1 < len(segs) and segs[k + 1].kind == "idle" and k + 1 not in anchors:
            ng_set.add(k + 1)
    for k, seg in enumerate(segs):
        if k in ng_set:
            j = next((jj for jj, a in enumerate(anchors) if a > k), None)
            label = f"NG: {descs[j][1]}" if j is not None else "NG"
            pieces.append(Piece(seg.start, seg.end, False, reason="ng", label=label))
        else:
            pieces.extend(shorten(seg, opt))
    if ng:
        notes.append(f"같은 동작을 다시 찍은 것으로 보이는 {len(ng)}곳을 NG 로 잘랐습니다 (타임라인에서 클릭해 되돌릴 수 있어요)")

    keep, speeds = keep_from_pieces(pieces)
    tmap = TimelineMap(keep, speeds)

    # 자막
    if descs:
        subs = [Subtitle(s.text, action=s.action) for s in script]
        anchor_starts = [segs[a].start for a in anchors]
        for j, (si, _) in enumerate(descs):
            start = anchor_starts[j]
            end = anchor_starts[j + 1] if j + 1 < len(descs) and anchor_starts[j + 1] > start else (
                segs[anchors[j]].end if j + 1 < len(descs) else duration)
            subs[si].start, subs[si].end = tmap(start), tmap(end)
        # 첫 동작 전에 오는 (동작 설명 없는) 자막은 영상 앞부분에 배치
        first = next(k for k, sub in enumerate(subs) if sub.start is not None)
        if first > 0 and subs[first].start >= 0.5:
            lead = distribute_evenly(subs[:first], [(0.0, subs[first].start)])
            for k, sub in enumerate(lead):
                subs[k].start, subs[k].end = sub.start, sub.end
        # 나머지 설명 없는 자막은 바로 앞 자막의 장면 시간을 나눠 쓴다
        _redistribute_missing(subs)
        if any(s.start is None for s in subs):
            subs = distribute_evenly(script, [(0.0, tmap.total)])
    else:
        notes.append("[동작 설명]이 없어 자막을 영상 길이에 맞춰 글자 수 비율로 배치했습니다")
        subs = distribute_evenly(script, [(0.0, tmap.total)])
    subs = finalize_subtitles(subs, tmap.total, cut)

    return EditPlan(keep=keep, speeds=speeds, subtitles=subs, pieces=pieces, mode="visual", notes=notes)
