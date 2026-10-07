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
from .pipeline import AnalyzeOptions, analyze
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

    v = p.add_argument_group("화면 기준 편집 (음성 없는 영상)")
    v.add_argument("--mode", choices=["auto", "voice", "visual"], default="auto",
                   help="auto: 소리가 있으면 음성 기준, 없으면 화면 기준 (기본) / voice / visual")
    v.add_argument("--max-action", type=float, default=6.0, help="이보다 긴 장면은 줄임, 초 (기본 6)")
    v.add_argument("--long-action", choices=["speed", "trim"], default="speed",
                   help="긴 장면 처리: speed=빨리감기(기본), trim=중간 자르기")
    v.add_argument("--keep-ng", action="store_true", help="NG(다시 찍은 동작) 자동 제거 끄기")

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

    t = p.add_argument_group("전환 효과")
    t.add_argument("--transition", metavar="효과", help="컷 사이 전환 효과 (예: 叠化=디졸브, 闪白=화이트 플래시). "
                   "--list-transitions 로 목록 확인")
    t.add_argument("--transition-duration", type=float, default=0.5, help="전환 길이, 초 (기본 0.5)")
    t.add_argument("--transition-all", action="store_true",
                   help="모든 컷에 적용 (기본: --transition-min-cut 초 이상 잘린 곳에만)")
    t.add_argument("--transition-min-cut", type=float, default=2.0,
                   help="이 이상 잘려 나간 곳에만 전환 적용, 초 (기본 2.0)")
    t.add_argument("--list-transitions", action="store_true", help="쓸 수 있는 전환 효과 목록 출력 후 종료")

    p.add_argument("--preview", metavar="MP4", help="컷 편집 결과를 ffmpeg 로 미리보기 영상으로도 출력")
    p.add_argument("--dry-run", action="store_true", help="드래프트를 만들지 않고 분석 결과만 출력")
    return p


def _atempo(speed: float) -> str:
    """atempo 는 0.5~2.0 만 지원하므로 여러 번 이어붙인다."""
    parts = []
    while speed > 2.0:
        parts.append("atempo=2.0")
        speed /= 2.0
    while speed < 0.5:
        parts.append("atempo=0.5")
        speed /= 0.5
    parts.append(f"atempo={speed:.4f}")
    return ",".join(parts)


def render_preview(video: str, keep, out_path: str, speeds=None) -> None:
    """남길 구간만 이어붙인 미리보기 mp4 (자막 미포함). 배속 반영, 오디오 없는 영상도 지원."""
    speeds = speeds or [1.0] * len(keep)
    audio = media.audio_level(video) is not None
    parts, labels = [], []
    for k, ((s, e), sp) in enumerate(zip(keep, speeds)):
        parts.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=(PTS-STARTPTS)/{sp:.4f}[v{k}];")
        labels.append(f"[v{k}]")
        if audio:
            parts.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS,{_atempo(sp)}[a{k}];")
            labels.append(f"[a{k}]")
    graph = "".join(parts) + "".join(labels) + f"concat=n={len(keep)}:v=1:a={1 if audio else 0}[v]" + ("[a]" if audio else "")
    script = Path(out_path).with_suffix(".filter.txt")
    script.write_text(graph, encoding="utf-8")
    maps = ["-map", "[v]"] + (["-map", "[a]", "-c:a", "aac"] if audio else [])
    try:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", video,
                        "-filter_complex_script", str(script), *maps,
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", out_path], check=True)
    finally:
        script.unlink(missing_ok=True)


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if "--list-transitions" in argv:
        from .transitions import catalog
        cat = catalog()
        print("자주 쓰는 효과:")
        for item in cat["presets"]:
            print(f"  {item['id']:<10} {item['label']}")
        print(f"\n전체 {len(cat['all'])}개 (Pro = CapCut 유료):")
        print("  " + ", ".join(i["id"] + (" (Pro)" if i["vip"] else "") for i in cat["all"]))
        return 0
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

    opt = AnalyzeOptions(max_pause=args.max_pause, pause_keep=args.pause_keep,
                         keep_threshold=args.keep_threshold, silence_db=args.silence_db,
                         no_asr=args.no_asr, model=args.model, language=args.language, device=args.device,
                         mode=args.mode, max_action=args.max_action, long_mode=args.long_action,
                         remove_ng=not args.keep_ng)
    if args.transcript:
        transcript = args.transcript
    else:
        transcript = str(out_dir / f"{stem}.transcript.json")
        Path(transcript).unlink(missing_ok=True)  # 명시하지 않으면 항상 새로 인식
    plan = analyze(video, script, opt, transcript_path=None if args.no_asr else transcript, info=info,
                   progress=lambda msg: print(f"[2/4] {msg}..."))
    if not args.no_asr and not args.transcript and os.path.exists(transcript):
        print(f"      음성인식 결과 저장 → {transcript} (다음에 --transcript 로 재사용 가능)")

    for note in plan.notes:
        print(f"      ※ {note}")
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
        render_preview(video, plan.keep, args.preview, plan.speed_list())
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
    transitions = None
    if args.transition:
        from .transitions import TransitionSettings, resolve
        transitions = resolve(plan.keep, TransitionSettings(
            enabled=True, type=args.transition, duration=args.transition_duration,
            apply="all" if args.transition_all else "long_cuts", min_cut=args.transition_min_cut),
            plan.speed_list())
        print(f"      전환 효과 {args.transition}: {sum(1 for t in transitions if t)}곳")
    path = build_draft(video, plan, drafts_dir=drafts_dir, draft_name=name,
                       width=info.width, height=info.height, fps=info.fps,
                       style=style, transitions=transitions, allow_replace=args.replace)
    print(f"[4/4] CapCut 드래프트 생성 완료: {path}")
    print("      CapCut 을 열면 홈 화면 프로젝트 목록에 나타납니다 (안 보이면 CapCut 재시작).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
