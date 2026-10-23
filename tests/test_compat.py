"""2.0 opens what 1.6 saved: project files written by NiSH Player 1.6.0 (tests/data/1.6).

Run:  python tests/test_compat.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import project  # noqa: E402
import settings  # noqa: E402

DATA = ROOT / "tests" / "data" / "1.6"


def ok(msg):
    print("ok:", msg)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="nish-compat-"))
    settings.FILE = tmp / "settings.json"          # recent projects go here, not to the real settings
    for f in DATA.glob("*.nish"):   # as if the song folder was moved: the old absolute paths are gone
        text = f.read_text(encoding="utf-8").replace("/tmp/smoke16", str(tmp / "old place").replace("\\", "/"))
        (tmp / f.name).write_text(text, encoding="utf-8")
    (tmp / "song").mkdir()
    for n in ("VOX", "DRM", "OTH"):
        (tmp / "song" / f"My Song_{n}.wav").write_bytes(b"")   # project.load only needs the files to exist

    st, missing = project.load(tmp / "Test Project.nish")
    assert not missing, missing
    assert [Path(t["file"]) for t in st["tracks"]] == [(tmp / "song" / f"My Song_{n}.wav").resolve()
                                                      for n in ("VOX", "DRM", "OTH")]
    assert [t["name"] for t in st["tracks"]] == ["Lead vocals", "Drums", "Other"]
    assert st["tracks"][0]["volume"] == 0.55 and st["tracks"][1]["mute"] and st["speed"] == 0.9
    assert st["loop"] == {"on": False, "start": 1.0, "end": 3.0, "fade": 1.0}
    ok("1.6 project: tracks found next to it (moved folder), names, volume, mute, speed, loop area")

    st, missing = project.load(tmp / "Automation.nish")
    assert not missing
    auto = st["tracks"][0]["automation"]
    assert auto["on"] and auto["points"] == [[0.0, 0.8], [4.0, 0.3026], [8.0, 0.8]] and st["master"] == 0.8
    ok("1.6 project with volume automation and master fader")

    (tmp / "song" / "My Song_OTH.wav").unlink()
    st, missing = project.load(tmp / "Test Project.nish")
    assert missing == ["Other"] and len(st["tracks"]) == 2
    ok("a missing file is reported by its track name")
    print("COMPAT TESTS PASSED")


if __name__ == "__main__":
    main()
