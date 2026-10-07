"""음성 없는 영상의 화면 기준 편집 테스트 (AI 모델 대신 색으로 판단하는 가짜 임베더 사용)."""
import shutil
import subprocess

import numpy as np
import pytest

from autocut.models import keep_from_pieces
from autocut.script_parser import parse_script_text
from autocut.visual import (Embedder, VisualOptions, align_actions, last_takes, motion_curve,
                            plan_from_visual, segment_motion)

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")

W, H, FPS, D = 320, 180, 30, 24
# 정지 → 빨간 상자(NG) → 정지 → 빨간 상자(다시 찍음) → 정지 → 파란 상자 12초(긴 동작) → 정지
TIMELINE = [(0, 2, None), (2, 5, "red"), (5, 6.5, None), (6.5, 9.5, "red"), (9.5, 10.5, None),
            (10.5, 22.5, "blue"), (22.5, 24, None)]

SCRIPT = """안녕하세요
오늘은 빨간 상자를 보여드릴게요
[빨간 상자가 움직인다]
다음은 파란 상자예요
[파란 상자가 움직인다]
감사합니다"""


class ColorEmbedder(Embedder):
    def embed_images(self, imgs):
        out = []
        for a in imgs:
            m = a.reshape(-1, 3).astype(float)
            red = ((m[:, 0] > 180) & (m[:, 2] < 80)).mean()
            blue = ((m[:, 2] > 180) & (m[:, 0] < 80)).mean()
            v = np.array([red * 20, blue * 20, 0.3])
            out.append(v / np.linalg.norm(v))
        return np.array(out)

    def embed_texts(self, texts):
        out = []
        for t in texts:
            v = np.array([1.0 if "빨간" in t else 0, 1.0 if "파란" in t else 0, 0.1])
            out.append(v / np.linalg.norm(v))
        return np.array(out)


@pytest.fixture(scope="module")
def silent_video(tmp_path_factory):
    out = tmp_path_factory.mktemp("v") / "silent.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "ultrafast",
                          "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    rng = np.random.default_rng(0)
    for i in range(FPS * D):
        t = i / FPS
        img = np.full((H, W, 3), 110, np.uint8) + rng.integers(0, 3, (H, W, 3), dtype=np.uint8)
        kind = next(k for a, b, k in TIMELINE if a <= t < b)
        if kind:
            x, y = int((t * 90) % (W - 60)), int(60 + 40 * np.sin(t * 3))
            img[y:y + 50, x:x + 50] = (220, 30, 30) if kind == "red" else (30, 60, 230)
        p.stdin.write(img.tobytes())
    p.stdin.close()
    p.wait()
    return str(out)


def test_segments_follow_motion(silent_video):
    segs = segment_motion(motion_curve(silent_video, 5), 5, 24.0, VisualOptions())
    kinds = [s.kind for s in segs]
    assert kinds == ["idle", "action", "idle", "action", "idle", "action", "idle"]
    assert segs[5].start == pytest.approx(10.5, abs=0.4) and segs[5].end == pytest.approx(22.5, abs=0.4)


def test_visual_plan_ng_long_and_subtitles(silent_video):
    script = parse_script_text(SCRIPT)
    plan = plan_from_visual(silent_video, script, 24.0, VisualOptions(), embedder=ColorEmbedder())
    reasons = [(p.reason, p.keep) for p in plan.pieces]
    # 첫 번째 빨간 상자 테이크와 그 뒤 정지는 NG 로 잘림
    ng = [p for p in plan.pieces if p.reason == "ng"]
    assert ng and ng[0].start == pytest.approx(2.0, abs=0.4) and all(not p.keep for p in ng)
    assert ng[-1].end == pytest.approx(6.5, abs=0.5)
    # 12초 파란 상자는 빨리감기
    long = [p for p in plan.pieces if p.reason == "long"]
    assert len(long) == 1 and long[0].keep and long[0].speed == pytest.approx(2.0, abs=0.15), reasons
    assert plan.duration < 24.0 - 4.0 - 5.0
    # 자막: 빨간 상자 자막은 두 번째 테이크(원본 6.5초)에서 시작
    subs = {s.text: s for s in plan.subtitles}
    red_start = subs["오늘은 빨간 상자를 보여드릴게요"].start
    first_keep_end = plan.keep[0][1] - plan.keep[0][0]
    assert red_start == pytest.approx(first_keep_end, abs=0.4)  # 앞부분 정지(0~2초) 다음 = 두 번째 테이크
    blue = subs["다음은 파란 상자예요"]
    assert blue.start > red_start and blue.end > blue.start
    for a, b in zip(plan.subtitles, plan.subtitles[1:]):
        assert a.end <= b.start + 1e-6


def test_trim_mode(silent_video):
    script = parse_script_text(SCRIPT)
    plan = plan_from_visual(silent_video, script, 24.0, VisualOptions(long_mode="trim", remove_ng=False),
                            embedder=ColorEmbedder())
    cut = [p for p in plan.pieces if p.reason == "long"]
    assert len(cut) == 1 and not cut[0].keep and cut[0].end - cut[0].start == pytest.approx(6.0, abs=0.5)
    assert not [p for p in plan.pieces if p.reason == "ng"]


def test_without_ai_falls_back_to_order(silent_video):
    script = parse_script_text(SCRIPT)
    plan = plan_from_visual(silent_video, script, 24.0, use_ai=False)
    assert [s.text for s in plan.subtitles] == [s.text for s in script]
    keep, speeds = keep_from_pieces(plan.pieces)
    assert keep == plan.keep and speeds == plan.speeds


def test_align_prefers_order_and_last_take():
    z = np.array([[2.0, -1], [-1, -1], [2.0, -1], [-1, 2.0]])  # 조각0,2 = 설명0, 조각3 = 설명1
    kinds = ["action", "idle", "action", "action"]
    anchors = align_actions(z, kinds)
    assert anchors[1] == 3
    anchors, ng = last_takes(z, anchors, kinds, 0.6)
    assert anchors == [2, 3] and ng == [0]
