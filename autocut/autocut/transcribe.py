"""음성인식(faster-whisper)으로 단어 단위 타임스탬프 얻기 + JSON 캐시."""
import json
from pathlib import Path
from typing import List, Optional

from .models import Word


def transcribe(video_path: str, *, model_size: str = "small", language: Optional[str] = "ko",
               device: str = "auto", compute_type: str = "default",
               initial_prompt: Optional[str] = None) -> List[Word]:
    """영상의 음성을 인식해 단어 리스트를 반환한다.

    `initial_prompt` 에 스크립트 일부를 넣으면 고유명사 인식률이 좋아진다.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "faster-whisper 가 설치되어 있지 않습니다. `pip install faster-whisper` 후 다시 실행하거나 "
            "--no-asr 옵션으로 무음 감지 모드를 사용하세요.") from e

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(
        video_path,
        language=language,
        word_timestamps=True,
        # 버벅임/반복을 '정리'하지 않고 들리는 그대로 받아적도록 VAD/이전문맥 사용을 끈다
        vad_filter=False,
        condition_on_previous_text=False,
        initial_prompt=initial_prompt,
    )
    words: List[Word] = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(Word(text=text, start=float(w.start), end=float(w.end)))
    return words


def save_words(words: List[Word], path: str) -> None:
    data = [{"text": w.text, "start": w.start, "end": w.end} for w in words]
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load_words(path: str) -> List[Word]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Word(text=d["text"], start=float(d["start"]), end=float(d["end"])) for d in data]
