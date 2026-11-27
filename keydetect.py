"""The song's key (for the Lux song header): a chroma profile of the tracks, matched against the
Krumhansl-Schmuckler key profiles. Drums are left out (they have no key).

song_key(tracks) -> "A minor" / "E♭ major", or "" when it can't tell.
transpose("A minor", -1) -> "A♭ minor"
"""
import numpy as np

SR = 44100
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
# how keys are usually written (flats for most major keys, sharps for F♯ major and C♯/G♯ minor)
MAJOR_NAMES = ["C", "D♭", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
MINOR_NAMES = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "G♯", "A", "B♭", "B"]
NO_KEY = ("drum", "perc", "click", "metronome")
SECONDS = 150          # enough to know the key; keeps it quick on long songs


def _mono(audio):
    a = np.asarray(audio, dtype=np.float32)
    if a.ndim == 2:
        a = a.mean(axis=1)
    return a[: SR * SECONDS]


def chroma(audio, sr=SR):
    """12 numbers: how much of each pitch class (C, C♯, …) the audio has."""
    x = _mono(audio)
    q = 4                                   # 44.1 kHz -> 11 kHz is plenty up to ~2 kHz
    n = len(x) // q * q
    if n < q * 4096:
        return np.zeros(12)
    x = x[:n].reshape(-1, q).mean(axis=1)
    sr = sr / q
    size, hop = 8192, 4096
    win = np.hanning(size).astype(np.float32)
    freqs = np.fft.rfftfreq(size, 1 / sr)
    band = (freqs >= 65) & (freqs <= 2100)
    pcs = (np.round(12 * np.log2(freqs[band] / 440.0) + 69).astype(int)) % 12
    total = np.zeros(12)
    for start in range(0, len(x) - size, hop):
        mag = np.abs(np.fft.rfft(x[start:start + size] * win))[band]
        frame = np.bincount(pcs, weights=mag, minlength=12)
        s = frame.sum()
        if s > 1e-6:
            total += frame / s              # every moment counts the same, loud or quiet
    return total


def best_key(ch):
    """The key whose profile matches the chroma best: (pitch class, "major"/"minor"), or None."""
    if ch.sum() <= 0 or np.allclose(ch, ch[0]):
        return None
    best, score = None, -2.0
    for mode, prof in (("major", MAJOR), ("minor", MINOR)):
        for pc in range(12):
            r = np.corrcoef(ch, np.roll(prof, pc))[0, 1]
            if r > score:
                best, score = (pc, mode), r
    return best


def name(pc, mode):
    return f"{(MAJOR_NAMES if mode == 'major' else MINOR_NAMES)[pc % 12]} {mode}"


def song_key(tracks):
    """The key of a set of tracks (engine.Track: .orig audio, .label), or "" when unsure."""
    try:
        use = [t for t in tracks if not any(w in (t.label or "").lower() for w in NO_KEY)] or list(tracks)
        ch = sum((chroma(t.orig) for t in use), np.zeros(12))
        k = best_key(ch)
        return name(*k) if k else ""
    except Exception:
        return ""


def parse(key):
    note, _, mode = key.partition(" ")
    names = MAJOR_NAMES if mode == "major" else MINOR_NAMES
    alt = {"C♯": "D♭", "D♭": "C♯", "D♯": "E♭", "E♭": "D♯", "F♯": "G♭", "G♭": "F♯", "G♯": "A♭",
           "A♭": "G♯", "A♯": "B♭", "B♭": "A♯"}
    if note not in names:
        note = alt.get(note, note)
    return names.index(note), mode


def transpose(key, semis):
    """The key after a pitch shift of whole semitones."""
    if not key or not semis:
        return key
    try:
        pc, mode = parse(key)
    except ValueError:
        return key
    return name(pc + int(semis), mode)
