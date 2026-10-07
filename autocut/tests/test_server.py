import importlib
import json
import shutil
import subprocess

import pytest

from tests.test_autocut import SCRIPT, WORDS

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCUT_HOME", str(tmp_path / "home"))
    from fastapi.testclient import TestClient
    import autocut.server as server
    server = importlib.reload(server)
    return TestClient(server.app), server


def test_upload_analyze_draft(client, tmp_path):
    c, server = client
    cond = "+".join(f"between(t,{w.start},{w.end})" for w in WORDS)
    video = tmp_path / "in.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=20",
                    "-f", "lavfi", "-i", f"aevalsrc='0.4*sin(2*PI*440*t)*({cond})':s=44100:d=20",
                    "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(video)], check=True)

    with video.open("rb") as f:
        r = c.post("/api/projects", files={"video": ("영상.mp4", f, "video/mp4")})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert r.json()["info"]["width"] == 320

    # 음성인식 대신 미리 만든 결과를 넣어 둔다
    (server.PROJECTS / pid / "transcript.json").write_text(
        json.dumps([w.__dict__ for w in WORDS], ensure_ascii=False), encoding="utf-8")
    r = c.post(f"/api/projects/{pid}/analyze", json={"script_text": "\n".join(s.text for s in SCRIPT)})
    assert r.status_code == 200, r.text
    for _ in range(100):
        p = c.get(f"/api/projects/{pid}").json()
        if p["status"]["state"] != "running":
            break
        import time
        time.sleep(0.05)
    assert p["status"]["state"] == "done", p["status"]
    subs = p["plan"]["subtitles"]
    assert [s["text"] for s in subs] == [s.text for s in SCRIPT]

    subs[0]["text"] = "수정된 첫 자막"
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    r = c.post(f"/api/projects/{pid}/draft", json={"name": "웹테스트", "drafts_dir": str(drafts), "subtitles": subs})
    assert r.status_code == 200, r.text
    content = json.loads((drafts / "웹테스트" / "draft_content.json").read_text(encoding="utf-8"))
    assert json.loads(content["materials"]["texts"][0]["content"])["text"] == "수정된 첫 자막"

    # 같은 이름 재생성은 덮어쓰기 없이는 409
    r = c.post(f"/api/projects/{pid}/draft", json={"name": "웹테스트", "drafts_dir": str(drafts), "subtitles": subs})
    assert r.status_code == 409

    srt = c.post(f"/api/projects/{pid}/srt", json=subs).text
    assert "수정된 첫 자막" in srt


def test_bad_project_id(client):
    c, _ = client
    assert c.get("/api/projects/../../etc").status_code == 404
    assert c.get("/api/projects/zzzzzzzzzzzz").status_code == 404
