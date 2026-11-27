"""Key detection tests (keydetect.py): chord progressions in a known key, drums left out, transposing.

Run:  python tests/test_keydetect.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import keydetect  # noqa: E402

SR = keydetect.SR


def ok(msg):
    print("ok:", msg)


def tone(midi, secs):
    t = np.arange(int(SR * secs)) / SR
    f = 440 * 2 ** ((midi - 69) / 12)
    return sum(np.sin(2 * np.pi * f * k * t) / k for k in (1, 2, 3)).astype(np.float32)


def chords(progression, secs=2.0):
    """Each chord: MIDI notes (bass an octave down), played for secs."""
    out = []
    for notes in progression:
        out.append(sum(tone(n, secs) for n in notes) + tone(notes[0] - 12, secs))
    return np.concatenate(out) * 0.1


class T:
    def __init__(self, audio, label):
        self.orig = np.stack([audio, audio], axis=1)
        self.label = label


def main():
    C, F, G, Am, Dm, E = [60, 64, 67], [65, 69, 72], [67, 71, 74], [57, 60, 64], [62, 65, 69], [64, 68, 71]
    major = chords([C, F, G, C, Am, F, G, C] * 2)
    assert keydetect.song_key([T(major, "Piano")]) == "C major", keydetect.song_key([T(major, "Piano")])
    ok("I–IV–V in C: C major")

    minor = chords([Am, Dm, E, Am, F, Dm, E, Am] * 2)
    assert keydetect.song_key([T(minor, "Guitar")]) == "A minor", keydetect.song_key([T(minor, "Guitar")])
    ok("i–iv–V in A minor: A minor")

    rng = np.random.default_rng(1)
    noise = (rng.standard_normal(len(minor)) * 0.3).astype(np.float32)
    assert keydetect.song_key([T(minor, "Bass"), T(noise, "Drums")]) == "A minor"
    ok("the drum track is left out")

    assert keydetect.song_key([T(np.zeros(SR * 5, np.float32), "Vocals")]) == ""
    assert keydetect.song_key([]) == ""
    ok("silence or nothing: no key")

    assert keydetect.transpose("A minor", -1) == "G♯ minor"
    assert keydetect.transpose("C major", -1) == "B major"
    assert keydetect.transpose("E♭ major", 2) == "F major"
    assert keydetect.transpose("F♯ minor", 12) == "F♯ minor"
    assert keydetect.transpose("A minor", 0) == "A minor" and keydetect.transpose("", 3) == ""
    ok("transpose follows the pitch setting")
    print("KEYDETECT TESTS PASSED")


if __name__ == "__main__":
    main()
