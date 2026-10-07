"""자막 스크립트(.txt / .srt) 읽기 및 긴 문장 분할."""
import re
from pathlib import Path
from typing import List, Optional

from .models import Subtitle

_SRT_TIME = re.compile(r"\d+:\d+:\d+[,.]\d+\s*-->\s*\d+:\d+:\d+[,.]\d+")
# 문장 분할 우선순위: 문장부호 > 쉼표 > 공백
_SENTENCE_END = re.compile(r"(?<=[.!?。！？…])\s+")
_CLAUSE_END = re.compile(r"(?<=[,，、;:])\s+")


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _lines_from_srt(text: str) -> List[str]:
    """SRT는 시간 정보를 무시하고 텍스트 블록만 사용한다 (타이밍은 음성에 맞춰 다시 계산)."""
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n"))
    lines = []
    for block in blocks:
        rows = [r.strip() for r in block.strip().split("\n") if r.strip()]
        rows = [r for r in rows if not r.isdigit() and not _SRT_TIME.search(r)]
        if rows:
            lines.append(" ".join(rows))
    return lines


def split_long_line(line: str, max_chars: int) -> List[str]:
    """`max_chars`(공백 제외 글자 수)보다 긴 줄을 자연스러운 위치에서 나눈다."""
    def length(s: str) -> int:
        return len(s.replace(" ", ""))

    if max_chars <= 0 or length(line) <= max_chars:
        return [line]

    for pattern in (_SENTENCE_END, _CLAUSE_END):
        parts = [p.strip() for p in pattern.split(line) if p.strip()]
        if len(parts) > 1:
            out: List[str] = []
            for p in parts:
                out.extend(split_long_line(p, max_chars))
            return _merge_short(out, max_chars)

    words = line.split()
    if len(words) == 1:
        # 공백이 없는 긴 덩어리는 글자 수로 자른다.
        return [line[i:i + max_chars] for i in range(0, len(line), max_chars)]

    # 공백 기준으로 가능한 한 균등하게 나눈다.
    n_chunks = -(-length(line) // max_chars)
    target = length(line) / n_chunks
    chunks, cur = [], []
    for w in words:
        if cur and length(" ".join(cur + [w])) > target * 1.15 and len(chunks) < n_chunks - 1:
            chunks.append(" ".join(cur))
            cur = []
        cur.append(w)
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def _merge_short(parts: List[str], max_chars: int) -> List[str]:
    """너무 짧게 쪼개진 조각은 옆 조각과 합친다."""
    out: List[str] = []
    for p in parts:
        if out and len((out[-1] + p).replace(" ", "")) <= max_chars:
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return out


_ACTION_LINE = re.compile(r"^[\[［【(（]\s*(.+?)\s*[\]］】)）]$")
_ACTION_INLINE = re.compile(r"^(.*?)\s*[\[［【]\s*(.+?)\s*[\]］】]\s*$")


def parse_script_text(text: str, max_chars: int = 0, is_srt: Optional[bool] = None) -> List[Subtitle]:
    """스크립트 문자열을 자막 단위 리스트로 만든다. `is_srt` 가 None 이면 내용으로 판단.

    대괄호 줄 `[동작 설명]` 은 자막이 아니라 바로 위 자막의 동작 설명으로 붙는다.
    `자막 [동작]` 처럼 한 줄에 같이 써도 된다.
    """
    if is_srt is None:
        is_srt = bool(_SRT_TIME.search(text))
    if is_srt:
        lines = _lines_from_srt(text)
    else:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        lines = [l for l in lines if not l.startswith("#")]

    entries: List[List] = []        # [자막 텍스트, [동작들]]
    pending: List[str] = []          # 첫 자막보다 먼저 나온 동작
    for line in lines:
        m = _ACTION_LINE.match(line)
        if m:
            (entries[-1][1] if entries else pending).append(m.group(1))
            continue
        m = _ACTION_INLINE.match(line)
        if m and m.group(1):
            entries.append([m.group(1).strip(), [m.group(2)]])
        else:
            entries.append([line, []])
        if pending:
            entries[-1][1][:0] = pending
            pending = []

    subs: List[Subtitle] = []
    for line, actions in entries:
        action = " / ".join(actions) or None
        for k, chunk in enumerate(split_long_line(line, max_chars)):
            # 긴 자막이 나뉘면 동작 설명은 첫 조각에만 (나머지는 그 장면 시간을 나눠 가짐)
            subs.append(Subtitle(text=chunk, action=action if k == 0 else None))
    if not subs:
        raise ValueError("스크립트에 자막 내용이 없습니다")
    return subs


def read_script_file(path: str) -> str:
    return _read_text(Path(path))


def load_script(path: str, max_chars: int = 0) -> List[Subtitle]:
    """스크립트 파일을 읽어 자막 단위 리스트로 만든다.

    - .txt: 빈 줄이 아닌 각 줄이 자막 한 개 (# 으로 시작하는 줄은 메모로 무시)
    - .srt: 각 자막 블록의 텍스트만 사용
    - `max_chars` > 0 이면 긴 줄을 자동으로 나눈다.
    """
    p = Path(path)
    return parse_script_text(_read_text(p), max_chars, is_srt=p.suffix.lower() == ".srt")
