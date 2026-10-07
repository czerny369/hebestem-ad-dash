"""스크립트 ↔ 음성인식 결과 글자 단위 정렬 (affine gap 전역 정렬, numpy 벡터화).

스크립트에 없는 음성(버벅임, 같은 말 반복, "음/어" 같은 군말, 재촬영 테이크)은
정렬에서 '삽입'으로 남기 때문에 잘라낼 대상으로 판별할 수 있다.
같은 문장을 여러 번 말한 경우, 동점이면 **마지막 테이크**가 선택되도록 역추적한다.
"""
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

MATCH = 2
MISMATCH = -1
GAP_OPEN = -3
GAP_EXTEND = -1
_NEG = -(1 << 40)

# 포인터 비트 배치 (셀당 1바이트)
#   bits 0-1: M 의 이전 상태 (0=M, 1=X, 2=Y)
#   bits 2-3: X 의 이전 상태 (0=M 에서 열림, 1=X 연장, 2=Y 에서 열림)
#   bits 4-5: Y 의 이전 상태 (0=M 에서 열림, 1=X 에서 열림, 2=Y 연장)
_M, _X, _Y = 0, 1, 2


def normalize(text: str) -> str:
    """비교용 정규화: 유니코드 NFKC, 소문자, 문자/숫자만 남김."""
    text = unicodedata.normalize("NFKC", text).lower()
    return "".join(c for c in text if c.isalnum())


def align_chars(a: str, b: str) -> List[Optional[int]]:
    """`a`의 각 글자가 정렬된 `b`의 글자 인덱스를 반환 (정렬되지 않으면 None).

    a: 스크립트(정규화된 문자열), b: 음성인식 결과(정규화된 문자열)
    """
    m, n = len(a), len(b)
    if m == 0:
        return []
    if n == 0:
        return [None] * m

    a_codes = np.frombuffer(a.encode("utf-32-le"), dtype=np.uint32)
    b_codes = np.frombuffer(b.encode("utf-32-le"), dtype=np.uint32)
    cols = np.arange(n + 1, dtype=np.int64)

    ptr = np.zeros((m + 1, n + 1), dtype=np.uint8)

    # 0행: 스크립트 시작 전의 음성은 모두 삽입(X)
    M = np.full(n + 1, _NEG, dtype=np.int64)
    M[0] = 0
    X = np.full(n + 1, _NEG, dtype=np.int64)
    X[1:] = GAP_OPEN + GAP_EXTEND * (cols[1:] - 1)
    ptr[0, 2:] |= (1 << 2)  # X 연장
    Y = np.full(n + 1, _NEG, dtype=np.int64)

    for i in range(1, m + 1):
        # ---- M: 대각선 ----
        stacked = np.stack([M[:-1], X[:-1], Y[:-1]])          # (3, n)
        # 동점일 때 M > Y > X 순으로 선호 (argmax 는 첫 최댓값을 고르므로 순서 배치)
        order = np.stack([stacked[_M], stacked[_Y], stacked[_X]])
        arg = np.argmax(order, axis=0)
        best_prev = np.max(order, axis=0)
        m_src = np.array([_M, _Y, _X], dtype=np.uint8)[arg]
        sub = np.where(b_codes == a_codes[i - 1], MATCH, MISMATCH)
        M_new = np.full(n + 1, _NEG, dtype=np.int64)
        M_new[1:] = best_prev + sub

        # ---- Y: 세로 (스크립트 글자가 음성에 없음) ----
        y_from_m = M + GAP_OPEN
        y_from_x = X + GAP_OPEN
        y_ext = Y + GAP_EXTEND
        y_stack = np.stack([y_ext, y_from_m, y_from_x])        # 동점이면 연장 선호
        y_arg = np.argmax(y_stack, axis=0)
        Y_new = np.max(y_stack, axis=0)
        y_src = np.array([_Y, _M, _X], dtype=np.uint8)[y_arg]

        # ---- X: 가로 (음성 글자가 스크립트에 없음) — cummax 로 벡터화 ----
        O = np.maximum(M_new, Y_new)
        o_from_y = Y_new > M_new
        base = O + GAP_OPEN - GAP_EXTEND * cols
        C = np.maximum.accumulate(base)
        X_new = np.full(n + 1, _NEG, dtype=np.int64)
        X_new[1:] = GAP_EXTEND * (cols[1:] - 1) + C[:-1]
        # X[j] 가 연장인지: X[j-1] + ext >= O[j-1] + open
        x_ext = np.zeros(n + 1, dtype=bool)
        x_ext[1:] = (X_new[:-1] + GAP_EXTEND) >= (O[:-1] + GAP_OPEN)
        x_src = np.where(x_ext, _X, np.where(np.r_[False, o_from_y[:-1]], _Y, _M)).astype(np.uint8)

        row = np.zeros(n + 1, dtype=np.uint8)
        row[1:] |= m_src
        row |= (x_src << 2)
        row |= (y_src << 4)
        ptr[i] = row
        M, X, Y = M_new, X_new, Y_new

    # ---- 역추적 ----
    end_scores = [(M[n], 0, _M), (Y[n], 1, _Y), (X[n], 2, _X)]  # 동점이면 M 우선 → 마지막 테이크
    state = max(end_scores, key=lambda t: (t[0], -t[1]))[2]
    i, j = m, n
    result: List[Optional[int]] = [None] * m
    while i > 0 or j > 0:
        p = int(ptr[i, j])
        if state == _M:
            result[i - 1] = j - 1
            state = p & 3
            i -= 1
            j -= 1
        elif state == _X:
            if i == 0:
                j -= 1
                continue
            state = (p >> 2) & 3
            j -= 1
        else:  # _Y
            if j == 0:
                i -= 1
                continue
            state = (p >> 4) & 3
            i -= 1
    return result


@dataclass
class AlignmentResult:
    word_kept: List[bool]                 # 음성인식 단어별 유지 여부
    unit_words: List[List[int]]           # 스크립트 단위(자막)별로 대응되는 단어 인덱스


def align_script_to_words(units: Sequence[str], words: Sequence[str],
                          keep_threshold: float = 0.5) -> AlignmentResult:
    """자막 단위 텍스트들과 음성인식 단어들을 정렬한다."""
    a_parts = [normalize(u) for u in units]
    b_parts = [normalize(w) for w in words]
    a = "".join(a_parts)
    b = "".join(b_parts)

    a_owner: List[int] = []
    for k, p in enumerate(a_parts):
        a_owner.extend([k] * len(p))
    b_owner: List[int] = []
    for k, p in enumerate(b_parts):
        b_owner.extend([k] * len(p))

    mapping = align_chars(a, b)

    aligned_per_word = [0] * len(words)
    unit_words: List[List[int]] = [[] for _ in units]
    for ai, bj in enumerate(mapping):
        if bj is None:
            continue
        w = b_owner[bj]
        aligned_per_word[w] += 1
        u = a_owner[ai]
        if not unit_words[u] or unit_words[u][-1] != w:
            unit_words[u].append(w)

    word_kept = []
    for k, p in enumerate(b_parts):
        word_kept.append(bool(p) and aligned_per_word[k] / len(p) >= keep_threshold)

    # 유지되지 않은 단어는 자막 대응에서도 제외
    unit_words = [[w for w in ws if word_kept[w]] for ws in unit_words]
    return AlignmentResult(word_kept=word_kept, unit_words=unit_words)


