"""컷편집 계획 수립: 남길 구간 계산 + 자막 타이밍 계산."""
from bisect import bisect_right
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .align import align_script_to_words
from .models import EditPlan, Subtitle, Word, pieces_from_keep

Interval = Tuple[float, float]


@dataclass
class CutOptions:
    max_pause: float = 0.6
    """이보다 긴 무음/정지 구간은 잘라서 `pause_keep` 길이로 줄인다 (초)."""
    pause_keep: float = 0.3
    """긴 공백을 줄였을 때 남겨둘 여유 시간 (앞뒤 합계, 초)."""
    lead_pad: float = 0.08
    """말 시작 직전에 붙일 최소 여유 (초)."""
    tail_pad: float = 0.12
    """말 끝 직후에 붙일 최소 여유 (초)."""
    keep_threshold: float = 0.5
    """단어 글자 중 스크립트와 정렬된 비율이 이 이상이면 유지."""
    min_segment: float = 0.15
    """이보다 짧은 유지 구간은 버린다 (초)."""
    min_sub_duration: float = 0.6
    """자막 최소 표시 시간 (초)."""
    sub_gap_fill: float = 0.4
    """자막 사이 공백이 이 이하면 앞 자막을 늘려 공백을 메운다 (초)."""


# --------------------------------------------------------------------------- #
# 구간 유틸
# --------------------------------------------------------------------------- #
def merge_intervals(intervals: Sequence[Interval], min_gap: float = 0.0) -> List[Interval]:
    out: List[Interval] = []
    for s, e in sorted(intervals):
        if e <= s:
            continue
        if out and s <= out[-1][1] + min_gap:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


class TimelineMap:
    """원본 시간 → 편집본 시간 변환. 잘린 구간 안의 시간은 다음 유지 구간 시작으로 붙는다."""

    def __init__(self, keep: Sequence[Interval], speeds: Optional[Sequence[float]] = None):
        self.keep = list(keep)
        self.speeds = list(speeds) if speeds and len(speeds) == len(self.keep) else [1.0] * len(self.keep)
        self.starts = [s for s, _ in self.keep]
        self.offsets = []
        acc = 0.0
        for (s, e), sp in zip(self.keep, self.speeds):
            self.offsets.append(acc)
            acc += (e - s) / sp
        self.total = acc

    def __call__(self, t: float) -> float:
        if not self.keep:
            return 0.0
        k = bisect_right(self.starts, t) - 1
        if k < 0:
            return 0.0
        s, e = self.keep[k]
        # 잘린 구간이면 다음 구간 시작으로
        return self.offsets[k] + (min(t, e) - s) / self.speeds[k]


# --------------------------------------------------------------------------- #
# 컷 계산
# --------------------------------------------------------------------------- #
def compute_keep_intervals(words: Sequence[Word], kept: Sequence[bool], duration: float,
                           opt: CutOptions) -> List[Interval]:
    """유지할 단어들 사이의 공백을 규칙에 따라 줄여 남길 구간을 만든다.

    - 인접한 유지 단어 사이에 버린 단어(버벅임/반복)가 있으면 그 부분은 잘라낸다.
    - 버린 단어가 없더라도 공백이 `max_pause` 보다 길면 `pause_keep` 만 남긴다.
    """
    order = sorted(range(len(words)), key=lambda k: words[k].start)
    half = opt.pause_keep / 2
    intervals: List[Interval] = []

    prev_kept: Optional[Word] = None
    dropped_between: List[Word] = []
    for k in order:
        w = words[k]
        if not kept[k]:
            dropped_between.append(w)
            continue

        if prev_kept is None:
            start = w.start - max(opt.lead_pad, half)
            if dropped_between:
                start = max(start, max(d.end for d in dropped_between))
            intervals.append((max(0.0, start), w.end))
        else:
            gap = w.start - prev_kept.end
            if not dropped_between and gap <= opt.max_pause:
                # 자연스러운 쉼 → 그대로 이어붙임
                intervals[-1] = (intervals[-1][0], w.end)
            else:
                tail = prev_kept.end + max(opt.tail_pad, half)
                head = w.start - max(opt.lead_pad, half)
                if dropped_between:
                    tail = min(tail, min(d.start for d in dropped_between))
                    head = max(head, max(d.end for d in dropped_between))
                tail = max(tail, prev_kept.end)
                head = min(head, w.start)
                if head <= tail:
                    intervals[-1] = (intervals[-1][0], w.end)
                else:
                    intervals[-1] = (intervals[-1][0], tail)
                    intervals.append((head, w.end))
        prev_kept = w
        dropped_between = []

    if not intervals:
        return []

    end = intervals[-1][1] + max(opt.tail_pad, half)
    if dropped_between:
        end = min(end, min(d.start for d in dropped_between))
    intervals[-1] = (intervals[-1][0], min(duration, max(end, intervals[-1][1])))

    merged = merge_intervals(intervals)
    merged = [(max(0.0, s), min(duration, e)) for s, e in merged]
    return [iv for iv in merged if iv[1] - iv[0] >= opt.min_segment]


# --------------------------------------------------------------------------- #
# 자막 타이밍
# --------------------------------------------------------------------------- #
def _redistribute_missing(subs: List[Subtitle]) -> None:
    """음성에서 찾지 못한 자막에 이웃 자막의 시간을 글자 수 비율로 나눠준다."""
    n = len(subs)
    i = 0
    while i < n:
        if subs[i].start is not None:
            i += 1
            continue
        j = i
        while j < n and subs[j].start is None:
            j += 1
        # [i, j) 가 시간 없음. 앞(또는 뒤) 자막과 묶어서 재분배
        if i > 0:
            group = list(range(i - 1, j))
        elif j < n:
            group = list(range(i, j + 1))
        else:
            return  # 전부 없음 → 호출자가 처리
        timed = [g for g in group if subs[g].start is not None]
        span_s = min(subs[g].start for g in timed)
        span_e = max(subs[g].end for g in timed)
        weights = [max(1, len(subs[g].text.replace(" ", ""))) for g in group]
        total = sum(weights)
        t = span_s
        for g, wgt in zip(group, weights):
            d = (span_e - span_s) * wgt / total
            subs[g].start, subs[g].end = t, t + d
            t += d
        i = j


def finalize_subtitles(subs: List[Subtitle], total: float, opt: CutOptions) -> List[Subtitle]:
    """겹침 제거, 최소 길이 보장, 짧은 공백 메우기."""
    subs = [s for s in subs if s.start is not None]
    subs.sort(key=lambda s: s.start)
    for k, s in enumerate(subs):
        nxt = subs[k + 1].start if k + 1 < len(subs) else total
        s.start = max(0.0, min(s.start, total))
        if s.end - s.start < opt.min_sub_duration:
            s.end = s.start + opt.min_sub_duration
        if nxt - s.end <= opt.sub_gap_fill:
            s.end = nxt
        s.end = min(s.end, nxt, total)
    return [s for s in subs if s.end - s.start > 0.05]


def plan_from_words(words: Sequence[Word], script: Sequence[Subtitle], duration: float,
                    opt: CutOptions = CutOptions()) -> EditPlan:
    """음성인식 단어 + 스크립트로 편집 계획을 만든다."""
    result = align_script_to_words([s.text for s in script], [w.text for w in words],
                                   keep_threshold=opt.keep_threshold)
    keep = compute_keep_intervals(words, result.word_kept, duration, opt)
    tmap = TimelineMap(keep)

    subs: List[Subtitle] = []
    for unit, ws in zip(script, result.unit_words):
        if ws:
            s = min(words[w].start for w in ws)
            e = max(words[w].end for w in ws)
            subs.append(Subtitle(unit.text, tmap(s), tmap(e), unit.action))
        else:
            subs.append(Subtitle(unit.text, action=unit.action))
    if all(s.start is None for s in subs):
        subs = distribute_evenly(script, [(0.0, tmap.total)])
    else:
        _redistribute_missing(subs)
    subs = finalize_subtitles(subs, tmap.total, opt)

    dropped = [w for w, k in zip(words, result.word_kept) if not k]

    def reason(s: float, e: float) -> str:
        return "stutter" if any(s <= (w.start + w.end) / 2 <= e for w in dropped) else "pause"

    return EditPlan(keep=keep, subtitles=subs, dropped_words=dropped, mode="voice",
                    pieces=pieces_from_keep(keep, duration, reason))


# --------------------------------------------------------------------------- #
# 음성인식 없이: 무음 감지 기반
# --------------------------------------------------------------------------- #
def distribute_evenly(script: Sequence[Subtitle], speech: Sequence[Interval]) -> List[Subtitle]:
    """말소리 구간들 위에 자막을 글자 수 비율로 배치한다 (편집본 타임라인 기준)."""
    total_speech = sum(e - s for s, e in speech)
    weights = [max(1, len(s.text.replace(" ", ""))) for s in script]
    wsum = sum(weights)

    def at(pos: float) -> float:
        acc = 0.0
        for s, e in speech:
            if pos <= acc + (e - s):
                return s + (pos - acc)
            acc += e - s
        return speech[-1][1] if speech else 0.0

    out, pos = [], 0.0
    for sub, w in zip(script, weights):
        d = total_speech * w / wsum
        out.append(Subtitle(sub.text, at(pos), at(pos + d), sub.action))
        pos += d
    return out


def plan_from_silence(silences: Sequence[Interval], script: Sequence[Subtitle], duration: float,
                      opt: CutOptions = CutOptions()) -> EditPlan:
    """무음 구간 정보만으로 편집 계획을 만든다 (버벅임 판별 불가, 긴 공백만 제거)."""
    half = opt.pause_keep / 2
    keep: List[Interval] = []
    cursor = 0.0
    for s, e in sorted(silences):
        if e - s <= opt.max_pause:
            continue
        cut_s = s + max(opt.tail_pad, half) if s > 0 else 0.0
        cut_e = e - max(opt.lead_pad, half) if e < duration else duration
        if cut_e > cut_s:
            keep.append((cursor, cut_s))
            cursor = cut_e
    keep.append((cursor, duration))
    keep = [iv for iv in merge_intervals(keep) if iv[1] - iv[0] >= opt.min_segment]

    tmap = TimelineMap(keep)
    # 편집본에서의 말소리 구간 = 유지 구간에서 남은 무음을 뺀 것
    speech_orig: List[Interval] = []
    for ks, ke in keep:
        t = ks
        for s, e in sorted(silences):
            if e <= ks or s >= ke:
                continue
            if s > t:
                speech_orig.append((t, s))
            t = max(t, e)
        if t < ke:
            speech_orig.append((t, ke))
    speech = [(tmap(s), tmap(e)) for s, e in speech_orig if e - s > 0.05] or [(0.0, tmap.total)]
    subs = finalize_subtitles(distribute_evenly(script, speech), tmap.total, opt)
    return EditPlan(keep=keep, subtitles=subs, mode="silence",
                    pieces=pieces_from_keep(keep, duration, lambda s, e: "pause"))
