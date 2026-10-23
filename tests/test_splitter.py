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
from tests.test_engine import tone_song  # noqa: E402

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
    o.update(fmt="FLAC")
    o["out"] = {"original": True, "karaoke": True, "stems": False, "stems6": True}
    o["tune"] = {"original": True, "karaoke": True, "stems": True}
    names = [r for _, r, _ in splitter.plan("My Song", o, ".opus")]
    assert names == ["My Song Original.opus", "My Song Auto440.flac", "My Song KARAOKE Auto440.mp3",
                     "Separated Stems - My Song/My Song VOX Auto440.flac",
                     "Separated Stems - My Song/My Song DRM Auto440.flac",
                     "Separated Stems - My Song/My Song BASS Auto440.flac",
                     "Separated Stems - My Song/My Song GTR Auto440.flac",
                     "Separated Stems - My Song/My Song KEYS Auto440.flac",
                     "Separated Stems - My Song/My Song MISC Auto440.flac"], names
    assert splitter.project_rel("My Song") == "~My Song.nish"
    assert splitter.model_for(o) == "htdemucs_6s"
    o2 = splitter.default_settings()
    o2.update(fmt="WAV")
    o2["out"] = {"original": False, "karaoke": True, "stems": True, "stems6": False}
    o2["tune"] = {"original": False, "karaoke": False, "stems": True}
    assert [r for _, r, _ in splitter.plan("A", o2, ".wav", local=True)] == [
        "A KARAOKE.mp3", "Separated Stems - A/A VOX Auto440.wav", "Separated Stems - A/A DRM Auto440.wav",
        "Separated Stems - A/A BASS Auto440.wav", "Separated Stems - A/A MISC Auto440.wav"]
    assert splitter.model_for(o2, local=True) == "htdemucs_ft"
    # YouTube always keeps the original; its Auto440 copy only when that switch is on
    yt = [r for _, r, _ in splitter.plan("A", o2, ".opus")]
    assert yt[0] == "A Original.opus" and "A Auto440.wav" not in yt, yt
    o2b = dict(o2, tune=dict(o2["tune"], original=True))
    assert [r for _, r, _ in splitter.plan("A", o2b, ".opus")][:2] == ["A Original.opus", "A Auto440.wav"]
    # a file: the Auto440 version without copying the original
    assert [r for _, r, _ in splitter.plan("A", o2b, ".wav", local=True)][0] == "A Auto440.wav"
    assert splitter.workspace_keys(o) == splitter.SIX and splitter.workspace_keys(o2) == splitter.FOUR
    assert splitter.sanitize('a/b:c?*"d".  ') == "abcd"
    ok("file plan, names, models (best for each choice), YouTube keeps the original")

    # full job from a file: original + Auto440 copy + karaoke MP3 + 6 stems
    stages = []
    o["out_root"] = str(tmp / "out")
    res = splitter.run(str(src), "My Song", o, stage=lambda k, f: stages.append(k), separator=sep)
    folder = tmp / "out" / "My Song"
    assert res["folder"] == folder
    for _, rel, _ in splitter.plan("My Song", o, ".m4a", local=True):
        assert (folder / rel).exists(), (rel, sorted(str(p.relative_to(folder)) for p in folder.rglob("*")))
    assert [s for s in dict.fromkeys(stages)] == ["download", "split", "tune", "save"], stages
    assert "corrected by +1" in res["tuning"], res["tuning"]
    kar = folder / "My Song KARAOKE Auto440.mp3"
    import subprocess
    info = subprocess.run([engine.ffmpeg_exe(), "-hide_banner", "-i", str(kar)], capture_output=True,
                          text=True).stderr
    assert "Audio: mp3" in info and "320 kb/s" in info, info
    a = engine.decode(kar)
    off, conf = tuning.estimate_offset_cents(a.mean(1), SR)
    assert abs(off) < 4, off
    a = engine.decode(folder / "My Song Auto440.flac")
    off, _ = tuning.estimate_offset_cents(a.mean(1), SR)
    assert abs(off) < 4, off
    orig = engine.decode(folder / "My Song Original.m4a")
    off, _ = tuning.estimate_offset_cents(orig.mean(1), SR)
    assert abs(off + 12.6) < 3, off  # original untouched
    stems = folder / "Separated Stems - My Song"
    peaks = [float(np.abs(engine.decode(p)).max()) for p in stems.iterdir()]
    assert max(peaks) <= 0.97, peaks
    assert [lbl for _, lbl in res["load"]] == ["Vocals", "Drums", "Bass", "Guitar", "Piano", "Other"]
    assert res["project"] == folder / "~My Song.nish" and res["project"].exists()
    import project
    st, missing = project.load(res["project"])
    assert not missing and [t["name"] for t in st["tracks"]] == ["Vocals", "Drums", "Bass", "Guitar", "Piano",
                                                                 "Other"]
    ok(f"full job: {len(list(folder.rglob('*.*')))} files, {res['tuning']}")

    # from a file, without copying the original: karaoke only (no Auto 440) -> loaded, project at the top
    o3 = splitter.default_settings()
    o3["out"] = {"original": False, "karaoke": True, "stems": False, "stems6": False}
    o3["tune"] = {"original": False, "karaoke": False, "stems": False}
    o3["out_root"] = str(tmp / "out3")
    res = splitter.run(str(src), "", o3, separator=sep)
    f = tmp / "out3" / "Some Video Title"
    assert sorted(p.name for p in f.iterdir()) == ["Some Video Title KARAOKE.mp3", "~Some Video Title.nish"]
    assert res["load"][0][1] == "Karaoke" and res["project"] == f / "~Some Video Title.nish"
    # original only (a copy), no tuning -> the original is loaded
    o4 = splitter.default_settings()
    o4["out"] = {"original": True, "karaoke": False, "stems": False, "stems6": False}
    o4["tune"] = {"original": False, "karaoke": False, "stems": False}
    o4["out_root"] = str(tmp / "out4")
    res = splitter.run(str(src), "Plain", o4, separator=None)
    assert sorted(p.name for p in (tmp / "out4" / "Plain").iterdir()) == ["Plain Original.m4a", "~Plain.nish"]
    assert res["load"][0][1] == "Original"
    try:
        splitter.run(str(src), "None", dict(o4, out={k: False for k in o4["out"]}), separator=None)
        raise AssertionError("nothing chosen should be refused")
    except RuntimeError:
        pass
    o5 = splitter.default_settings()
    o5["out"] = {"original": False, "karaoke": False, "stems": False, "stems6": False}
    o5["tune"] = {"original": True, "karaoke": False, "stems": False}
    o5["out_root"] = str(tmp / "out5")
    res = splitter.run(str(src), "Tuned", o5, separator=None)
    assert sorted(p.name for p in (tmp / "out5" / "Tuned").iterdir()) == ["Tuned Auto440.flac", "~Tuned.nish"], \
        sorted(p.name for p in (tmp / "out5" / "Tuned").iterdir())
    assert res["load"][0][1] == "Original 440 Hz"
    ok("karaoke only (MP3, original not copied), original only, only the Auto440 version, nothing chosen refused")

    # cancel
    def cancel():
        raise splitter.Cancelled()
    try:
        splitter.run(str(src), "C", dict(o, out_root=str(tmp / "c")), check_cancel=cancel, separator=sep)
        raise AssertionError("should have been cancelled")
    except splitter.Cancelled:
        ok("cancel stops the job")
    test_original_kept_as_opus()
    print("SPLITTER TESTS PASSED")
    return 0


def test_original_kept_as_opus():
    """A YouTube download (Opus in .webm) ends up in the song folder as <name>.opus, not re-encoded."""
    tmp = Path(tempfile.mkdtemp(prefix="nish-opus-"))
    dl = tmp / "work" / "download"
    dl.mkdir(parents=True)
    webm = dl / "audio.webm"
    engine._run([engine.ffmpeg_exe(), "-hide_banner", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                 "-c:a", "libopus", "-b:a", "96k", str(webm)])
    folder = tmp / "out" / "Song"
    got = splitter.keep_original(webm, folder, "Song", "opus")
    assert got == folder / "Song.opus" and got.stat().st_size > 0, got
    assert not webm.exists()
    assert abs(len(engine.decode(got)) - engine.SR) < engine.SR * 0.1
    assert splitter.saved_ext("webm", "opus") == ".opus" and splitter.saved_ext("m4a", "mp4a") == ".m4a"
    # anything else keeps its container
    m4a = dl / "audio.m4a"
    m4a.write_bytes(b"x" * 10)
    assert splitter.keep_original(m4a, folder, "Other", "mp4a") == folder / "Other.m4a"
    print("ok: original YouTube audio saved in the song folder (Opus as .opus, no re-encoding)")


if __name__ == "__main__":
    sys.exit(main())
