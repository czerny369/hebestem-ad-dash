import json
import os
import shutil
import subprocess

import pytest

from autocut.align import align_chars, align_script_to_words, normalize
from autocut.models import Subtitle, Word
from autocut.planner import CutOptions, TimelineMap, plan_from_silence, plan_from_words
from autocut.script_parser import load_script, split_long_line


def test_normalize():
    assert normalize("안녕하세요, 여러분!") == "안녕하세요여러분"
    assert normalize("ABC 123") == "abc123"


def test_align_prefers_last_take():
    assert align_chars("abc", "abcabc") == [3, 4, 5]
    assert align_chars("abc", "xabyabc") == [4, 5, 6]


def test_align_drops_stutter_and_fillers():
    units = ["안녕하세요 여러분", "오늘은 제품을 소개할게요"]
    words = ["안녕하세요", "여러분", "어", "오늘은", "제", "오늘은", "제품을", "음", "소개할게요"]
    r = align_script_to_words(units, words)
    assert r.word_kept == [True, True, False, False, False, True, True, False, True]
    assert r.unit_words == [[0, 1], [5, 6, 8]]


def test_split_long_line():
    line = "이 제품은 정말 가볍고 튼튼해서 매일 들고 다니기에 좋습니다"
    parts = split_long_line(line, 12)
    assert len(parts) >= 2
    assert all(len(p.replace(" ", "")) <= 14 for p in parts)
    assert " ".join(parts) == line
    assert split_long_line("첫 문장입니다. 두번째 문장입니다.", 10) == ["첫 문장입니다.", "두번째 문장입니다."]


def test_load_script_txt_and_srt(tmp_path):
    txt = tmp_path / "s.txt"
    txt.write_text("# 메모\n첫 줄\n\n둘째 줄\n", encoding="utf-8")
    assert [s.text for s in load_script(str(txt))] == ["첫 줄", "둘째 줄"]
    srt = tmp_path / "s.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\n안녕\n하세요\n\n2\n00:00:03,000 --> 00:00:04,000\n반가워요\n",
                   encoding="utf-8")
    assert [s.text for s in load_script(str(srt))] == ["안녕 하세요", "반가워요"]


def test_timeline_map():
    m = TimelineMap([(1.0, 2.0), (5.0, 6.0)])
    assert m(1.5) == pytest.approx(0.5)
    assert m(3.0) == pytest.approx(1.0)   # 잘린 구간 → 다음 구간 시작
    assert m(5.5) == pytest.approx(1.5)
    assert m.total == pytest.approx(2.0)


WORDS = [
    Word("음", 0.5, 0.8),
    Word("안녕하세요", 1.0, 1.6), Word("여러분", 1.7, 2.1),
    Word("오늘은", 2.4, 2.8), Word("제", 2.9, 3.0),
    Word("오늘은", 3.6, 4.0), Word("제품을", 4.1, 4.5), Word("소개해", 4.6, 5.0), Word("드릴게요", 5.0, 5.5),
    Word("이", 11.5, 11.7), Word("제품은", 11.8, 12.2), Word("어", 12.3, 12.5), Word("정말", 12.6, 12.9),
    Word("가볍고", 13.0, 13.5), Word("튼튼합니다", 13.6, 14.3),
    Word("감사합니다", 16.0, 16.8), Word("아", 17.5, 17.7), Word("잠깐만", 17.8, 18.3),
]
SCRIPT = [Subtitle("안녕하세요 여러분"), Subtitle("오늘은 제품을 소개해 드릴게요"),
          Subtitle("이 제품은 정말 가볍고 튼튼합니다"), Subtitle("감사합니다")]


def _covered(keep, t):
    return any(s <= t <= e for s, e in keep)


def test_plan_from_words_cuts_stutters_and_long_pauses():
    plan = plan_from_words(WORDS, SCRIPT, 20.0, CutOptions())
    assert {w.text for w in plan.dropped_words} == {"음", "오늘은", "제", "어", "아", "잠깐만"}
    for w in WORDS:
        mid = (w.start + w.end) / 2
        dropped = any(d is w for d in plan.dropped_words)
        assert _covered(plan.keep, mid) != dropped, w
    # 5.5~11.5 의 긴 정지 구간은 잘려야 한다
    assert not _covered(plan.keep, 8.0)
    assert plan.duration < 9.0
    # 자막: 순서대로, 겹치지 않고, 편집본 길이 안에
    assert [s.text for s in plan.subtitles] == [s.text for s in SCRIPT]
    for a, b in zip(plan.subtitles, plan.subtitles[1:]):
        assert a.start < a.end <= b.start
    assert plan.subtitles[-1].end <= plan.duration + 1e-6


def test_missing_subtitle_gets_time():
    script = SCRIPT[:2] + [Subtitle("전혀 말하지 않은 문장")] + SCRIPT[2:]
    plan = plan_from_words(WORDS, script, 20.0, CutOptions())
    assert [s.text for s in plan.subtitles] == [s.text for s in script]


def test_plan_from_silence():
    silences = [(0.0, 0.9), (2.2, 3.4), (5.6, 11.4), (14.4, 15.9), (16.9, 20.0)]
    plan = plan_from_silence(silences, SCRIPT, 20.0, CutOptions())
    assert not _covered(plan.keep, 8.0)
    assert _covered(plan.keep, 13.0)
    assert len(plan.subtitles) == len(SCRIPT)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")
def test_cli_end_to_end(tmp_path):
    cond = "+".join(f"between(t,{w.start},{w.end})" for w in WORDS)
    video = tmp_path / "in.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=20",
                    "-f", "lavfi", "-i", f"aevalsrc='0.4*sin(2*PI*440*t)*({cond})':s=44100:d=20",
                    "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(video)],
                   check=True)
    transcript = tmp_path / "t.json"
    transcript.write_text(json.dumps([w.__dict__ for w in WORDS], ensure_ascii=False), encoding="utf-8")
    script = tmp_path / "s.txt"
    script.write_text("\n".join(s.text for s in SCRIPT), encoding="utf-8")
    drafts = tmp_path / "drafts"
    drafts.mkdir()

    from autocut.cli import main
    assert main([str(video), str(script), "--transcript", str(transcript), "--drafts-dir", str(drafts),
                 "--name", "t", "--out-dir", str(tmp_path)]) == 0

    content = json.loads((drafts / "t" / "draft_content.json").read_text(encoding="utf-8"))
    tracks = {t["type"]: t["segments"] for t in content["tracks"]}
    video_segs = tracks["video"]
    # 영상 조각들은 빈틈 없이 이어져야 한다
    for a, b in zip(video_segs, video_segs[1:]):
        assert a["target_timerange"]["start"] + a["target_timerange"]["duration"] == b["target_timerange"]["start"]
    texts = [json.loads(t["content"])["text"] for t in content["materials"]["texts"]]
    assert texts == [s.text for s in SCRIPT]
    assert os.path.exists(tmp_path / "t.srt")


def test_transition_resolve():
    from autocut.transitions import TransitionSettings, resolve
    keep = [(0.0, 2.0), (2.5, 4.0), (8.0, 8.3), (8.5, 12.0)]
    # 기본: 2초 이상 잘린 곳(4.0→8.0)만, 길이는 짧은 조각(0.3초)의 절반으로 제한
    r = resolve(keep, TransitionSettings(enabled=True, type="闪白", duration=0.5))
    assert r[0] is None and r[2] is None
    assert r[1] == ("闪白", pytest.approx(0.15))
    r = resolve(keep, TransitionSettings(enabled=True, apply="all", duration=0.5))
    assert [x[0] if x else None for x in r] == ["叠化", "叠化", "叠化"]
    # 개별 설정: 끄기/다른 효과 (전체 사용 안 함이어도 개별 지정은 적용)
    r = resolve(keep, TransitionSettings(enabled=False, overrides={0: "推近", 1: "none"}))
    assert r[0][0] == "推近" and r[1] is None and r[2] is None


def test_draft_with_transitions(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg 필요")
    from autocut.draft import build_draft
    from autocut.models import EditPlan
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=10",
                    "-c:v", "libx264", "-preset", "ultrafast", str(video)], check=True)
    plan = EditPlan(keep=[(0, 3), (5, 8)], subtitles=[Subtitle("안녕", 0.5, 2.0)])
    drafts = tmp_path / "d"
    drafts.mkdir()
    build_draft(str(video), plan, drafts_dir=str(drafts), draft_name="t", width=320, height=180, fps=30,
                transitions=[("叠化", 0.5)])
    content = json.loads((drafts / "t" / "draft_content.json").read_text(encoding="utf-8"))
    tr = content["materials"]["transitions"]
    assert len(tr) == 1 and tr[0]["name"] == "叠化" and tr[0]["duration"] == 500000
    with pytest.raises(ValueError):
        build_draft(str(video), plan, drafts_dir=str(drafts), draft_name="t2", width=320, height=180, fps=30,
                    transitions=[("없는효과", 0.5)])
    assert not (drafts / "t2").exists()
