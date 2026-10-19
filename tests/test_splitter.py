"""Add-from-YouTube pipeline tests with a stand-in for the AI separator.

Run:  python tests/test_splitter.py   (needs ffmpeg on PATH; no torch needed)
The real Demucs separation is tested by the GUI smoke test in the Windows build.
"""
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import engine  # noqa: E402
import splitter  # noqa: E402
import tuning  # noqa: E402
from tests.test_engine import tone_song, write_wav  # noqa: E402

SR = engine.SR


def fake_separator(parts):
    def sep(audio, model, on_progress, check_cancel):
        on_progress(0.5)
        names = splitter.SIX if model == "htdemucs_6s" else ["vocals", "drums", "bass", "other"]
        out = {}
        for n in names:
            x = np.zeros(len(audio))
            p = parts.get(n, x)[:len(audio)]
            x[:len(p)] = p
            out[n] = np.stack([x, x], 1).astype(np.float32)
        return out
    return sep


def main():
    ok = lambda m: print("ok:", m)
    tmp = Path(tempfile.mkdtemp(prefix="nish-split-"))
    chord, melody, drums = tone_song(8.0)
    song = chord + melody + drums
    src = tmp / "download" / "Some Video Title.m4a"
    src.parent.mkdir()
    st = np.stack([song, song], 1).astype(np.float32)
    engine._run([engine.ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-f", "f32le",
                 "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "aac", "-b:a", "256k", str(src)],
                st.tobytes())
    sep = fake_separator({"vocals": melody, "drums": drums, "other": chord})

    # plan / names
    o = splitter.default_settings()
    o.update(tune=True, tuned_original=True, fmt="FLAC")
    names = [r for _, r, _ in splitter.plan("My Song", o, ".opus")]
    assert names == ["My Song.opus", "My Song_440hz.flac", "My Song_NoVox_440hz.flac",
                     "My Song stems/My Song_VOX_440hz.flac", "My Song stems/My Song_DRM_440hz.flac",
                     "My Song stems/My Song_BASS_440hz.flac", "My Song stems/My Song_GTR_440hz.flac",
                     "My Song stems/My Song_KEYS_440hz.flac", "My Song stems/My Song_MISC_440hz.flac"], names
    o2 = splitter.default_settings()
    o2.update(stems=False, tune=False, fmt="MP3")
    o2["suffixes"]["karaoke"] = " (karaoke)"
    assert [r for _, r, _ in splitter.plan("A", o2, ".webm")] == ["A.webm", "A (karaoke).mp3"]
    assert splitter.workspace_keys(o) == splitter.SIX and splitter.workspace_keys(o2) == ["karaoke"]
    assert splitter.sanitize('a/b:c?*"d".  ') == "abcd"
    ok("file plan, suffixes and names")

    # full job: original + tuned copy + karaoke + 6 stems, Auto 440
    stages = []
    o["out_root"] = str(tmp / "out")
    res = splitter.run(str(src), "My Song", o, stage=lambda k, f: stages.append(k), separator=sep)
    folder = tmp / "out" / "My Song"
    assert res["folder"] == folder
    assert (folder / "My Song.m4a").exists(), list(folder.iterdir())
    for _, rel, _ in splitter.plan("My Song", o, ".m4a"):
        assert (folder / rel).exists(), rel
    assert [s for s in dict.fromkeys(stages)] == ["download", "split", "tune", "save"], stages
    assert "corrected by +1" in res["tuning"], res["tuning"]
    a = engine.decode(folder / "My Song_NoVox_440hz.flac")
    off, conf = tuning.estimate_offset_cents(a.mean(1), SR)
    assert abs(off) < 4, off
    a = engine.decode(folder / "My Song_440hz.flac")
    off, _ = tuning.estimate_offset_cents(a.mean(1), SR)
    assert abs(off) < 4, off
    orig = engine.decode(folder / "My Song.m4a")
    off, _ = tuning.estimate_offset_cents(orig.mean(1), SR)
    assert abs(off + 12.6) < 3, off  # original untouched
    peaks = [float(np.abs(engine.decode(p)).max()) for p in (folder / "My Song stems").iterdir()
             if p.suffix != ".nish"]
    assert max(peaks) <= 0.97, peaks
    assert [lbl for _, lbl in res["load"]] == ["Vocals", "Drums", "Bass", "Guitar", "Piano", "Other"]
    # karaoke is saved but not loaded with the stems; a project sits next to the stems
    assert res["project"] == folder / "My Song stems" / "My Song.nish" and res["project"].exists()
    import project
    st, missing = project.load(res["project"])
    assert not missing and [t["name"] for t in st["tracks"]] == ["Vocals", "Drums", "Bass", "Guitar", "Piano",
                                                                 "Other"]
    assert all("/" not in json_t["file"] for json_t in __import__("json").loads(
        res["project"].read_text(encoding="utf-8"))["tracks"])          # relative: just the file names
    ok(f"full job: {len(list(folder.rglob('*.*')))} files, {res['tuning']}")

    # karaoke only, no tuning, Opus; original only
    o3 = splitter.default_settings()
    o3.update(stems=False, karaoke=True, tune=False, fmt="OPUS", out_root=str(tmp / "out3"))
    res = splitter.run(str(src), "", o3, separator=sep)
    f = tmp / "out3" / "Some Video Title"
    assert sorted(p.name for p in f.iterdir()) == ["Some Video Title.m4a", "Some Video Title.nish",
                                                   "Some Video Title_NoVox.opus"]
    assert res["load"][0][1] == "Karaoke" and res["project"] == f / "Some Video Title.nish"
    o4 = splitter.default_settings()
    o4.update(stems=False, karaoke=False, tune=False, out_root=str(tmp / "out4"))
    res = splitter.run(str(src), "Plain", o4, separator=None)
    assert [p.name for p in (tmp / "out4" / "Plain").iterdir()] == ["Plain.m4a"]
    assert res["load"][0][1] == "Plain" and res["project"] is None
    ok("karaoke-only as Opus, and original-only (no split)")

    # cancel
    def cancel():
        raise splitter.Cancelled()
    try:
        splitter.run(str(src), "C", dict(o, out_root=str(tmp / "c")), check_cancel=cancel, separator=sep)
        raise AssertionError("should have been cancelled")
    except splitter.Cancelled:
        ok("cancel stops the job")
    print("SPLITTER TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
