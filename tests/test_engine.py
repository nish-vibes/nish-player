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


def _slice(a, start, n):
    out = np.zeros((n, 2), np.float32)
    lo, hi = max(start, 0), min(start + n, len(a))
    if hi > lo:
        out[lo - start:hi - start] = a[lo:hi]
    return out


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
    assert engine.tags(0.85, -2, 13, True) == ["0.85x", "-2semitones", "440hz"]
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

    # real-time stretcher: speed and pitch are heard at once
    tracks[2].mute = False
    tracks[0].volume = 1.0
    live = engine.LiveStretcher(p._fetch_mix)
    live.set_params(0.8, 0)
    live.reset(0)
    y = live.read(SR * 2)
    assert abs(live.pa / (SR * 2) - 0.8) < 0.05, live.pa / (SR * 2)
    assert 0.3 < float(np.abs(y[SR // 2:]).mean()) / float(np.abs(p._fetch_mix(SR // 2, SR)).mean()) < 1.6
    solo = engine.LiveStretcher(lambda s, n: _slice(tracks[1].orig, s, n))
    solo.set_params(1.0, 2)
    solo.reset(0)
    f0 = main_freq(tracks[1].orig)
    f1 = main_freq(solo.read(SR))
    assert abs(f1 / f0 - 2 ** (2 / 12)) < 0.015, (f0, f1)
    ok(f"live stretcher: speed 0.8x consumes {live.pa / (SR * 2):.3f}x, +2 st {f0:.0f} -> {f1:.0f} Hz")

    # playback: slider change -> live at once -> high-quality render takes over, same spot
    p.seek(0.5)
    p.playing = True
    assert p.ready()
    p.render_block(1024)
    assert p.mode == "direct"
    p.set_live(0.5, 0)              # slider moving: heard immediately
    blk = p.render_block(1024)
    assert p.mode == "live" and float(np.abs(blk).max()) > 0.01
    pos_live = p.src_pos
    p.request_render()               # slider released
    import time
    for _ in range(300):
        if p.ready():
            break
        time.sleep(0.05)
    assert p.ready(), [t.buf_key for t in tracks]
    p.render_block(1024)
    assert p.mode == "direct" and abs(p.src_pos - (pos_live + 512)) < 1
    assert abs(p.position() - 0.5) < 0.01 and abs(p.length() / n0 - 2.0) < 0.03
    p.playing = False
    ok("slider change is heard at once, high-quality render takes over at the same spot")

    # fine-tuning is always varispeed (no tempo compensation); Rubber Band always one pass.
    # Lowering: varispeed -> Rubber Band. Raising: Rubber Band -> varispeed.
    assert engine.stretch_filter(1.0, 0, cents=4) == engine.varispeed_filter(0.04)  # tuning only: no Rubber Band
    neg, pos = engine.stretch_filter(0.85, 0, cents=-40), engine.stretch_filter(0.85, 0, cents=40)
    assert neg.startswith("asetrate=") and neg.count("asetrate") == 1 + (not engine.has_rubberband()), neg
    assert pos.endswith(engine.varispeed_filter(0.4)) and not pos.startswith("asetrate="), pos
    if engine.has_rubberband():
        assert neg.count("rubberband=") == 1 and pos.count("rubberband=") == 1
        assert "tempo=0.850000" in neg and "pitch=1.000000" in pos    # no compensation
    assert engine.stretch_filter(1.0, 0, cents=0) is None
    vs = engine.vari_ratio(4)
    vr = engine.render(tracks[1].orig, 1.0, 0, cents=4)
    assert abs(len(tracks[1].orig) / len(vr) - vs) < 1e-3, (len(vr), vs)
    def fine_freq(x):  # parabolic peak interpolation inside the first note
        x = x[:, 0][:32000] * np.hanning(32000)
        spec = np.abs(np.fft.rfft(x, 1 << 18))
        k = int(np.argmax(spec))
        a, b, c = np.log(spec[k - 1:k + 2] + 1e-12)
        return (k + 0.5 * (a - c) / (a - 2 * b + c)) * SR / (1 << 18)
    f0, f2 = fine_freq(tracks[1].orig), fine_freq(vr)
    assert abs(f2 / f0 - vs) < 0.0004, (f0, f2, vs)
    for cents in (-40, 40):          # with speed: length = n / (speed * ratio), pitch x ratio
        rr = engine.render(tracks[1].orig, 0.8, 0, cents=cents)
        want = len(tracks[1].orig) / engine.chain_rate(0.8, cents)
        assert abs(len(rr) / want - 1) < 0.01, (cents, len(rr), want)
        fr = main_freq(rr[int(SR * 0.3):])
        assert abs(fr / main_freq(tracks[1].orig[int(SR * 0.3 * 0.8 * engine.vari_ratio(cents)):])
                   - engine.vari_ratio(cents)) < 0.02, (cents, fr)
    wild = engine.render(tracks[1].orig, 1.0, 0, cents=-500)
    assert abs(len(wild) / len(tracks[1].orig) - 2 ** (500 / 1200)) < 0.01, len(wild)
    p.set_stretch(1.0, 0, 4)
    for _ in range(300):
        if p.ready():
            break
        time.sleep(0.05)
    assert p.ready() and all(tr.buf_key == (1.0, 0.0, 4.0) for tr in tracks)
    assert p.varispeed and abs(p.speed - vs) < 1e-9 and abs(p.length() - n0 / vs) < 2
    assert abs(p.live.speed / p.live.ratio - 1.0) < 1e-9   # live preview: no stretching, just resampling
    ok(f"fine-tuning = varispeed: +4 ct pitch x{f2 / f0:.5f}, length x{len(vr) / len(tracks[1].orig):.5f}; "
       f"order by direction, one Rubber Band pass; wild -500 ct x{len(wild) / len(tracks[1].orig):.3f}")

    # loop area: playback stays inside it, with 2-second fades at both ends
    for tr in tracks:
        tr.mute = False
    p.set_stretch(1.0, 0)
    for _ in range(300):
        if p.ready():
            break
        time.sleep(0.05)
    p.set_region(SR * 0.5, SR * 5.5)
    p.loop = True
    p.seek(0.97)                     # outside the area
    assert p.toggle() and abs(p.src_pos - SR * 0.5) < 1, p.src_pos   # play starts at the area
    obuf = np.zeros((1024, 2), np.float32)
    levels, positions = [], []
    for _ in range(int(SR * 12 / 1024)):
        p._callback(obuf, 1024, None, None)
        levels.append(float(np.abs(obuf).max()))
        positions.append(p.src_pos)
    assert all(SR * 0.5 <= x < SR * 5.5 + 1024 for x in positions), (min(positions), max(positions))
    wraps = sum(1 for x, y in zip(positions, positions[1:]) if y < x)
    assert wraps == 2, wraps
    assert levels[0] < 0.05 and max(levels[80:150]) > 0.2, (levels[0], max(levels[80:150]))
    assert engine.loop_fade_len(0, SR * 5, 2.0) == SR * 1.25 and engine.loop_fade_len(0, SR * 60) == SR * 1
    g0 = engine.region_gain(np.array([99.0, 100.0, 150.0, 199.0, 200.0]), 100, 200, 0.0)
    assert list(g0) == [0, 1, 1, 1, 0], g0
    p.playing = False
    p.loop = False
    assert p.active_region() is None
    ok("loop area: starts at the area, wraps twice in 12 s, fades in/out (1 s default, 0 = none)")

    # export only the loop area
    w = engine.export(tracks, p.gains(), 1.0, 0.8, 0, "mix", "WAV", out / "loop.wav",
                      region=(SR * 1, SR * 4))
    secs = engine.probe_seconds(w[0])
    assert abs(secs - 3 / 0.8) < 0.05, secs
    y = engine.decode(w[0])
    assert float(np.abs(y[:200]).max()) < 0.02 and float(np.abs(y[-200:]).max()) < 0.02
    assert engine.region_tag(SR * 42, SR * 73) == "_0m42-1m13"
    w = engine.export(tracks, p.gains(), 1.0, 0.8, 0, "mix", "WAV", out / "loop-fine.wav",
                      region=(SR * 1, SR * 4), cents=40)
    fsecs = engine.probe_seconds(w[0])
    assert abs(fsecs - 3 / engine.chain_rate(0.8, 40)) < 0.05, fsecs
    w = engine.export(tracks, p.gains(), 1.0, 1.0, 0, "mix", "WAV", out / "vari.wav", cents=4)
    vsecs = engine.probe_seconds(w[0])
    assert abs(vsecs - 6.0 / vs) < 0.01, vsecs
    ok(f"export only the loop area: {secs:.2f} s with fades")

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
