"""Engine tests: decode, speed/pitch, Auto 440, mixing, clip light, export.

Run:  python tests/test_engine.py   (needs ffmpeg on PATH)
"""
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import engine  # noqa: E402

SR = engine.SR


def tone_song(seconds=6.0, a_hz=436.8):
    """A little 'song' tuned to a_hz: a chord and a melody line, plus a noise 'drum'."""
    t = np.arange(int(seconds * SR)) / SR
    def note(semi):
        return a_hz * 2 ** (semi / 12)
    chord = sum(np.sin(2 * np.pi * note(s) * t) for s in (-9, -5, -2, 0)) * 0.12
    melody = np.zeros_like(t)
    for i, s in enumerate([0, 2, 3, 5, 7, 5, 3, 2]):
        seg = (t >= i * seconds / 8) & (t < (i + 1) * seconds / 8)
        melody[seg] = 0.25 * np.sin(2 * np.pi * note(s + 12) * t[seg])
    rng = np.random.default_rng(1)
    drums = rng.standard_normal(len(t)) * 0.3 * (np.mod(t, 0.5) < 0.05)
    return chord, melody, drums


def write_wav(path, mono):
    st = np.stack([mono, mono], axis=1).astype(np.float32)
    engine._encode(st, path, "WAV")


def main(out_dir=None):
    out = Path(out_dir or tempfile.mkdtemp(prefix="nish-test-"))
    out.mkdir(parents=True, exist_ok=True)
    chord, melody, drums = tone_song()
    files = {
        "My Song_OTH.wav": chord,
        "My Song_VOX.wav": melody,
        "My Song_DRM.wav": drums,
    }
    for name, sig in files.items():
        write_wav(out / name, sig)
    ok = lambda msg: print("ok:", msg)

    # names
    assert engine.guess_label(out / "My Song_VOX.wav") == "Vocals"
    assert engine.guess_label("x/My Song_DRM.mp3") == "Drums"
    assert engine.guess_label("x/Karaoke version.mp3") == "Karaoke version"
    assert engine.song_name([out / n for n in files]) == "My Song"
    assert engine.song_name(["a/Full song.mp3"]) == "Full song"
    assert engine.is_vocal("My Song_VOX.wav") and not engine.is_vocal("My Song_DRM.wav")
    assert engine.tags(0.85, -2, 13, True) == ["0.85x", "-2st", "440hz"]
    assert engine.tags(1.0, 0, 12, False) == ["+12ct"]
    assert engine.tags(1.0, 0, 0, False) == []
    ok("names and tags")

    # decode
    tracks = [engine.Track(out / n, engine.decode(out / n)) for n in files]
    n0 = len(tracks[0].orig)
    assert abs(n0 - 6 * SR) < SR * 0.05, n0
    assert tracks[0].orig.shape[1] == 2 and tracks[0].orig.dtype == np.float32
    assert len(tracks[0].peaks) == 1600 and 0.99 <= tracks[0].peaks.max() <= 1.0
    ok(f"decode ({n0} frames)")

    # speed: 0.8x -> 1.25x as long
    r = engine.render(tracks[0].orig, 0.8, 0)
    ratio = len(r) / n0
    assert abs(ratio - 1.25) < 0.02, ratio
    ok(f"speed 0.8x -> length x{ratio:.3f}")

    # pitch: +2 semitones moves the melody's frequency up by 2^(2/12)
    def main_freq(x):
        x = x[:, 0][SR // 4: SR // 4 + 16384]
        spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
        return np.argmax(spec) * SR / len(x)
    f0 = main_freq(tracks[1].orig)
    f1 = main_freq(engine.render(tracks[1].orig, 1.0, 2))
    assert abs(f1 / f0 - 2 ** (2 / 12)) < 0.01, (f0, f1)
    ok(f"pitch +2 st: {f0:.1f} Hz -> {f1:.1f} Hz")

    # Auto 440: the test song is at A = 436.8 Hz, about +12.6 cents needed
    corr, a_hz, conf = engine.analyse_tuning(tracks)
    assert 9 <= corr <= 16 and abs(a_hz - 436.8) < 1.5, (corr, a_hz, conf)
    ok(f"Auto 440: A = {a_hz:.1f} Hz, correction {corr:+.1f} ct (confidence {conf})")

    # live mix: mute/solo/volume
    p = engine.Player()
    for t in tracks:
        p.add(t)
    assert p.gains() == [1.0, 1.0, 1.0]
    tracks[2].mute = True
    tracks[1].solo = True
    assert p.gains() == [0.0, 1.0, 0.0]
    tracks[1].solo = False
    tracks[0].volume = 0.5
    assert p.gains() == [0.5, 1.0, 0.0]
    blk = p.mix_block(1000, 512)
    expect = tracks[0].orig[1000:1512] * 0.5 + tracks[1].orig[1000:1512]
    assert np.allclose(blk, expect, atol=1e-6)
    ok("mute / solo / volume")

    # clip light latches, limiter keeps output under 0 dBFS
    loud = np.ones((256, 2), np.float32) * 1.7
    y = p.process_master(loud)
    assert p.clip and float(np.abs(y).max()) <= engine.LIMIT + 1e-6
    p.process_master(np.zeros((256, 2), np.float32))
    assert p.clip  # stays on until cleared by the user
    m = p.take_meter()
    assert m.max() >= 1.7 and p.take_meter().max() == 0
    ok("clip light latches, limiter holds -0.3 dBFS")

    # live speed change keeps the position
    p.seek(0.5)
    p.set_stretch(0.5, 0)
    import time
    for _ in range(300):
        if p.render_busy == 0 and all(t.buf_key == (0.5, 0.0) for t in tracks):
            break
        time.sleep(0.05)
    assert all(t.buf_key == (0.5, 0.0) for t in tracks), [t.buf_key for t in tracks]
    assert abs(p.position() - 0.5) < 0.01 and abs(p.length() / n0 - 2.0) < 0.03
    ok("live speed change keeps the playhead")

    # export: mix + each track, all formats
    gains = p.gains()
    for fmt in ("WAV", "FLAC", "MP3"):
        dst = out / "export" / f"My Song_mix_0.8x.{fmt.lower()}"
        dst.parent.mkdir(exist_ok=True)
        w = engine.export(tracks, gains, 1.0, 0.8, -2.0 + 0.13, "mix", fmt, dst)
        secs = engine.probe_seconds(w[0])
        assert abs(secs - 7.5) < 0.15, (fmt, secs)
    ok("export mix as WAV / FLAC / MP3 with speed and pitch")
    w = engine.export(tracks, gains, 1.0, 1.0, 0.13, "each", "WAV", out / "each",
                      name_tags=["440hz"])
    names = sorted(x.name for x in w)
    assert names == ["My Song_DRM_440hz.wav", "My Song_OTH_440hz.wav", "My Song_VOX_440hz.wav"], names
    ok("export each track separately")
    for t in tracks:
        t.mute = True
    try:
        engine.export(tracks, p.gains(), 1.0, 1.0, 0, "mix", "WAV", out / "x.wav")
        raise AssertionError("should refuse an all-muted export")
    except RuntimeError:
        ok("all-muted export is refused")
    p.close()
    print("ENGINE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
