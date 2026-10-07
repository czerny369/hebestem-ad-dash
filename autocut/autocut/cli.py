"""명령행 인터페이스.

예)  python -m autocut 영상.mp4 스크립트.txt --name "제품소개_자동편집"
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import media
from .draft import SubtitleStyle, build_draft, default_drafts_dir, hex_to_rgb, write_srt
from .planner import CutOptions, plan_from_silence, plan_from_words
from .script_parser import load_script


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="autocut",
        description="영상 + 자막 스크립트 → 버벅임/긴 공백 자동 컷 + 자막 자동 생성 → CapCut 드래프트")
    p.add_argument("video", help="원본 영상 파일")
    p.add_argument("script", help="자막 스크립트 (.txt: 한 줄 = 자막 하나, 또는 .srt)")
    p.add_argument("--name", help="생성할 CapCut 드래프트 이름 (기본: 영상 파일명_autocut)")
    p.add_argument("--drafts-dir", help="CapCut 드래프트 폴더 (기본: OS 별 기본 위치 자동 탐색)")
    p.add_argument("--replace", action="store_true", help="같은 이름의 드래프트가 있으면 덮어쓰기")
    p.add_argument("--out-dir", help="편집 결과 SRT/JSON 리포트를 저장할 폴더 (기본: 영상과 같은 폴더)")

    g = p.add_argument_group("음성 인식")
    g.add_argument("--model", default="small",
                   help="Whisper 모델 크기 (tiny/base/small/medium/large-v3, 기본 small)")
    g.add_argument("--language", default="ko", help="음성 언어 코드 (기본 ko)")
    g.add_argument("--device", default="auto", help="auto / cpu / cuda")
    g.add_argument("--transcript", help="이미 저장된 음성인식 결과(JSON)를 사용 (재실행 시 빠름)")
    g.add_argument("--no-asr", action="store_true",
                   help="음성인식 없이 무음 감지만으로 편집 (버벅임 제거 불가, 자막은 글자 수 비율 배치)")

    c = p.add_argument_group("컷 편집")
    c.add_argument("--max-pause", type=float, default=0.6,
                   help="이보다 긴 공백(멈춤/긴 동작)은 잘라냄, 초 (기본 0.6)")
    c.add_argument("--pause-keep", type=float, default=0.3,
                   help="잘라낸 자리에 남겨둘 여유, 초 (기본 0.3)")
    c.add_argument("--keep-threshold", type=float, default=0.5,
                   help="단어가 스크립트와 일치하는 비율이 이 이상이면 유지 (기본 0.5)")
    c.add_argument("--silence-db", type=float, default=-35.0,
                   help="--no-asr 모드의 무음 기준 dB (기본 -35)")

    s = p.add_argument_group("자막 스타일")
    s.add_argument("--max-chars", type=int, default=18,
                   help="자막 한 개의 최대 글자 수(공백 제외), 넘으면 자동 분할. 0 = 분할 안 함 (기본 18)")
    s.add_argument("--font-size", type=float, default=7.0, help="글자 크기 (기본 7)")
    s.add_argument("--color", default="#FFFFFF", help="글자 색 (기본 #FFFFFF)")
    s.add_argument("--border-color", default="#000000", help="테두리 색 (기본 #000000)")
    s.add_argument("--no-border", action="store_true", help="테두리 없음")
    s.add_argument("--bold", action="store_true", help="굵게")
    s.add_argument("--position", type=float, default=None,
                   help="세로 위치 (-1=맨 아래, 0=가운데, 1=맨 위). 기본: 가로영상 -0.8, 세로영상 -0.55")
    s.add_argument("--font", help="pycapcut.FontType 이름 (기본: CapCut 기본 폰트)")

    p.add_argument("--preview", metavar="MP4", help="컷 편집 결과를 ffmpeg 로 미리보기 영상으로도 출력")
    p.add_argument("--dry-run", action="store_true", help="드래프트를 만들지 않고 분석 결과만 출력")
    return p


def render_preview(video: str, keep, out_path: str) -> None:
    """남길 구간만 이어붙인 미리보기 mp4 (자막 미포함)."""
    parts, labels = [], []
    for k, (s, e) in enumerate(keep):
        parts.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{k}];"
                     f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{k}];")
        labels.append(f"[v{k}][a{k}]")
    graph = "".join(parts) + "".join(labels) + f"concat=n={len(keep)}:v=1:a=1[v][a]"
    script = Path(out_path).with_suffix(".filter.txt")
    script.write_text(graph, encoding="utf-8")
    try:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", video,
                        "-filter_complex_script", str(script), "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac",
                        out_path], check=True)
    finally:
        script.unlink(missing_ok=True)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    video = os.path.abspath(args.video)
    if not os.path.isfile(video):
        print(f"영상 파일을 찾을 수 없습니다: {video}", file=sys.stderr)
        return 1

    stem = Path(video).stem
    out_dir = Path(args.out_dir or Path(video).parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = args.name or f"{stem}_autocut"

    info = media.probe(video)
    print(f"[1/4] 영상 정보: {info.width}x{info.height}, {info.fps:.2f}fps, {info.duration:.1f}초")

    script = load_script(args.script, max_chars=args.max_chars)
    print(f"      스크립트: 자막 {len(script)}개")

    opt = CutOptions(max_pause=args.max_pause, pause_keep=args.pause_keep,
                     keep_threshold=args.keep_threshold)

    if args.no_asr:
        print("[2/4] 무음 구간 감지 중...")
        silences = media.detect_silences(video, noise_db=args.silence_db,
                                         min_silence=min(0.3, args.max_pause), duration=info.duration)
        plan = plan_from_silence(silences, script, info.duration, opt)
    else:
        from .transcribe import load_words, save_words, transcribe
        if args.transcript:
            words = load_words(args.transcript)
            print(f"[2/4] 저장된 음성인식 결과 사용: 단어 {len(words)}개")
        else:
            print(f"[2/4] 음성 인식 중 (Whisper {args.model})... 영상 길이에 따라 수 분 걸릴 수 있습니다")
            prompt = " ".join(s.text for s in script)[:200]
            words = transcribe(video, model_size=args.model, language=args.language,
                               device=args.device, initial_prompt=prompt)
            cache = out_dir / f"{stem}.transcript.json"
            save_words(words, str(cache))
            print(f"      단어 {len(words)}개 인식 → {cache} (다음에 --transcript 로 재사용 가능)")
        if not words:
            print("      음성이 인식되지 않아 무음 감지 모드로 전환합니다.")
            silences = media.detect_silences(video, noise_db=args.silence_db, duration=info.duration)
            plan = plan_from_silence(silences, script, info.duration, opt)
        else:
            plan = plan_from_words(words, script, info.duration, opt)

    cut = info.duration - plan.duration
    print(f"[3/4] 컷 편집: {info.duration:.1f}초 → {plan.duration:.1f}초 "
          f"({cut:.1f}초 제거, 구간 {len(plan.keep)}개)")
    if plan.dropped_words:
        preview = " ".join(w.text for w in plan.dropped_words[:30])
        more = " ..." if len(plan.dropped_words) > 30 else ""
        print(f"      제거된 말(버벅임/반복/스크립트 외): {preview}{more}")

    srt_path = out_dir / f"{name}.srt"
    write_srt(plan.subtitles, str(srt_path))
    report_path = out_dir / f"{name}.plan.json"
    report_path.write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"      자막 {len(plan.subtitles)}개 → {srt_path}")

    if args.preview:
        render_preview(video, plan.keep, args.preview)
        print(f"      미리보기 영상 → {args.preview}")

    if args.dry_run:
        print("[4/4] --dry-run: 드래프트 생성 생략")
        return 0

    drafts_dir = args.drafts_dir or default_drafts_dir()
    if not drafts_dir:
        print("CapCut 드래프트 폴더를 찾지 못했습니다. --drafts-dir 로 지정하세요.\n"
              "(CapCut → 설정 → 드래프트 위치 에서 확인 가능)", file=sys.stderr)
        return 2

    vertical = info.height > info.width
    style = SubtitleStyle(
        size=args.font_size, color=hex_to_rgb(args.color), bold=args.bold,
        border=not args.no_border, border_color=hex_to_rgb(args.border_color),
        transform_y=args.position if args.position is not None else (-0.55 if vertical else -0.8),
        max_line_width=0.9 if vertical else 0.82, font=args.font)
    path = build_draft(video, plan, drafts_dir=drafts_dir, draft_name=name,
                       width=info.width, height=info.height, fps=info.fps,
                       style=style, allow_replace=args.replace)
    print(f"[4/4] CapCut 드래프트 생성 완료: {path}")
    print("      CapCut 을 열면 홈 화면 프로젝트 목록에 나타납니다 (안 보이면 CapCut 재시작).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
